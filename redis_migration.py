#!/usr/bin/env python
import os
import sys
import redis

# Add the project path to PYTHONPATH if needed
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def run_migration():
    # Retrieve Redis connection details from Django settings if possible, otherwise fallback
    try:
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dispatcharr.settings')
        import django
        django.setup()
        from django.conf import settings
        # Retrieve Redis URL from settings
        redis_url = getattr(settings, 'REDIS_URL', 'redis://localhost:6379/0')
        client = redis.from_url(redis_url)
        print(f"Connected to Redis at: {redis_url}")
    except Exception as django_err:
        print(f"Django environment not loaded ({django_err}). Connecting to default local Redis.")
        client = redis.StrictRedis(host='localhost', port=6379, db=0)

    print("Starting one-time Redis migration...")
    
    # 1. Scan for profile:*:connections
    connections_pattern = "profile:*:connections"
    keys_checked = 0
    keys_recreated = 0
    
    # Scan for keys
    for key in client.scan_iter(match=connections_pattern):
        keys_checked += 1
        key_str = key.decode('utf-8') if isinstance(key, bytes) else key
        try:
            key_type = client.type(key)
            if isinstance(key_type, bytes):
                key_type = key_type.decode('utf-8')
            
            if key_type != 'string':
                print(f"Key {key_str} has type '{key_type}' (expected 'string'). Deleting and recreating as '0'...")
                client.delete(key)
                client.set(key, "0")
                keys_recreated += 1
        except Exception as err:
            print(f"Error checking key {key_str}: {err}")

    print(f"Checked {keys_checked} connections keys, recreated {keys_recreated} keys.")

    # 2. Scan sessions ZSET: profile:*:sessions
    sessions_pattern = "profile:*:sessions"
    zset_keys_checked = 0
    members_purged = 0
    
    for key in client.scan_iter(match=sessions_pattern):
        zset_keys_checked += 1
        key_str = key.decode('utf-8') if isinstance(key, bytes) else key
        try:
            # Get all members of the ZSET
            members = client.zrange(key, 0, -1)
            for member in members:
                session_id = member.decode('utf-8') if isinstance(member, bytes) else member
                meta_key = f"vod:{session_id}:meta"
                if not client.exists(meta_key):
                    print(f"Session {session_id} has no meta key {meta_key}. Purging from ZSET {key_str}...")
                    client.zrem(key, member)
                    members_purged += 1
        except Exception as err:
            print(f"Error processing sessions ZSET {key_str}: {err}")

    print(f"Checked {zset_keys_checked} sessions ZSETs, purged {members_purged} orphaned session members.")
    print("Migration completed successfully.")

if __name__ == '__main__':
    run_migration()
