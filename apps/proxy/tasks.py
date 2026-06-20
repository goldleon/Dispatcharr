from celery import shared_task
import json
import logging
import re
import gc
import time
from core.utils import RedisClient
from apps.proxy.live_proxy.channel_status import ChannelStatus
from core.utils import send_websocket_update
from apps.proxy.vod_proxy.multi_worker_connection_manager import MultiWorkerVODConnectionManager
from apps.m3u.models import M3UAccountProfile

logger = logging.getLogger(__name__)

# Store the last known value to compare with new data
last_known_data = {}

@shared_task
def fetch_channel_stats():
    redis_client = RedisClient.get_client()

    try:
        # Basic info for all channels
        channel_pattern = "live:channel:*:metadata"
        all_channels = []

        # Extract channel IDs from keys
        cursor = 0
        while True:
            cursor, keys = redis_client.scan(cursor, match=channel_pattern)
            for key in keys:
                channel_id_match = re.search(r"live:channel:(.*):metadata", key)
                if channel_id_match:
                    ch_id = channel_id_match.group(1)
                    channel_info = ChannelStatus.get_basic_channel_info(ch_id)
                    if channel_info:
                        all_channels.append(channel_info)

            if cursor == 0:
                break

    except Exception as e:
        logger.error(f"Error in channel_status: {e}", exc_info=True)
        return
        # return JsonResponse({'error': str(e)}, status=500)

    send_websocket_update(
        "updates",
        "update",
        {
            "success": True,
            "type": "channel_stats",
            "stats": json.dumps({'channels': all_channels, 'count': len(all_channels)})
        },
        collect_garbage=True
    )

    # Explicitly clean up large data structures
    all_channels = None
    gc.collect()


@shared_task
def reconcile_profile_connections():
    """
    Periodic task to reconcile Redis connection counters with actual active sessions.
    Handles both Live (TS) and VOD (Multi-Worker) streams.
    Runs every 5 minutes (configured in Celery Beat).
    """
    redis_client = RedisClient.get_client()
    if not redis_client:
        return "Redis not available"

    try:
        # profile_id -> count
        total_counts = {}

        # 1. Reconcile Live (TS Proxy) Streams
        # Pattern: stream_profile:{channel_id} -> profile_id
        cursor = 0
        while True:
            cursor, keys = redis_client.scan(cursor, match="stream_profile:*", count=100)
            for key in keys:
                try:
                    ch_id = key.split(':')[1]
                    # Check if the channel metadata still exists (is the stream actually running?)
                    meta_key = f"ts_proxy:channel:{ch_id}:metadata"
                    if not redis_client.exists(meta_key):
                        logger.warning(f"Reconciliation: Cleaning up orphaned stream_profile key for inactive channel {ch_id}")
                        redis_client.delete(key)
                        continue

                    profile_id_raw = redis_client.get(key)
                    if profile_id_raw:
                        p_id = int(profile_id_raw)
                        total_counts[p_id] = total_counts.get(p_id, 0) + 1
                except (IndexError, ValueError, TypeError) as e:
                    logger.error(f"Error processing stream_profile key {key}: {e}")

            if cursor == 0:
                break

        # 2. Reconcile VOD Streams (using heartbeat ZSETs from MultiWorkerVODConnectionManager)
        # Pattern: profile_connections:{profile_id}:zset
        cursor = 0
        current_time = time.time()
        while True:
            cursor, keys = redis_client.scan(cursor, match="profile_connections:*:zset", count=100)
            for key in keys:
                try:
                    # Key is profile_connections:{id}:zset
                    p_id = int(key.split(':')[1])

                    # Purge expired heartbeats (score is timestamp when they expire or last update)
                    # Note: MW manager uses score = current_time + 60
                    # We purge members older than current_time
                    redis_client.zremrangebyscore(key, "-inf", current_time)
                    vod_count = redis_client.zcard(key) or 0

                    if vod_count > 0:
                        total_counts[p_id] = total_counts.get(p_id, 0) + vod_count
                except (IndexError, ValueError, TypeError) as e:
                    logger.error(f"Error processing VOD zset key {key}: {e}")

            if cursor == 0:
                break

        # 3. Calculate ServerGroup credential counts and Synchronize with Database
        from apps.m3u.connection_pool import get_enforced_server_group_for_profile, _credential_counter_key

        active_profiles = M3UAccountProfile.objects.filter(is_active=True)
        synced_count = 0
        processed_ids = set()
        cred_counts = {}

        for profile in active_profiles:
            actual_count = total_counts.get(profile.id, 0)
            processed_ids.add(profile.id)

            # Update Redis counter (the one used for INCR/DECR locks)
            redis_client.set(f"profile_connections:{profile.id}", actual_count)

            # Update DB field if changed
            if profile.active_streams != actual_count:
                logger.info(f"Reconciliation: Correcting profile {profile.id} count {profile.active_streams} -> {actual_count}")
                profile.active_streams = actual_count
                profile.save(update_fields=['active_streams'])
                synced_count += 1

            # Accumulate ServerGroup credential limit counts
            group = get_enforced_server_group_for_profile(profile)
            if group:
                cred_key = _credential_counter_key(profile, group)
                if cred_key:
                    cred_counts[cred_key] = cred_counts.get(cred_key, 0) + actual_count

        # 4. Update ServerGroup Redis counters
        for cred_key, count in cred_counts.items():
            logger.debug(f"Reconciliation: Setting ServerGroup connection count for {cred_key} to {count}")
            redis_client.set(cred_key, count)

        # 5. Handle orphaned profile_connections keys for non-existent or inactive profiles
        cursor = 0
        while True:
            cursor, keys = redis_client.scan(cursor, match="profile_connections:*", count=100)
            for key in keys:
                key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                # Skip zset keys
                if key_str.endswith(':zset'):
                    continue

                try:
                    p_id = int(key_str.split(':')[1])
                    if p_id not in processed_ids:
                        logger.debug(f"Reconciliation: Cleaning up orphaned counter for profile {p_id}")
                        redis_client.delete(key)
                except (IndexError, ValueError):
                    continue

            if cursor == 0:
                break

        # 6. Handle orphaned server_group_connections keys
        cursor = 0
        while True:
            cursor, keys = redis_client.scan(cursor, match="server_group_connections:*", count=100)
            for key in keys:
                key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                if key_str not in cred_counts:
                    logger.debug(f"Reconciliation: Cleaning up orphaned ServerGroup counter {key_str}")
                    redis_client.delete(key)

            if cursor == 0:
                break

        logger.info(f"Profile connection reconciliation complete. Updated {synced_count} profiles, reconciled {len(cred_counts)} ServerGroup credentials.")
        return f"Reconciled {len(total_counts)} profiles, updated {synced_count} in DB."

    except Exception as e:
        logger.error(f"Critical error in reconcile_profile_connections: {e}", exc_info=True)
        return f"Error: {str(e)}"
