"""Process-local caches for live proxy lookups.

post_save/post_delete signals clear these, but only in the process that
saved the row; uWSGI stream workers are separate processes. Entries therefore
also expire after ``_TTL_SECONDS`` so a stream profile, user agent or header
change reaches every worker within a minute instead of at the next restart.
"""
import functools
import threading
import time

_TTL_SECONDS = 60.0


def lru_cache(maxsize=128):
    """Bounded memoize with a TTL; exposes ``cache_clear()`` like functools."""

    def decorator(fn):
        cache = {}
        lock = threading.Lock()

        @functools.wraps(fn)
        def wrapper(*args):
            now = time.monotonic()
            with lock:
                hit = cache.get(args)
                if hit is not None and now - hit[0] < _TTL_SECONDS:
                    return hit[1]
            value = fn(*args)
            with lock:
                if len(cache) >= maxsize:
                    # Drop the oldest entry (dicts keep insertion order).
                    cache.pop(next(iter(cache)), None)
                cache.pop(args, None)
                cache[args] = (now, value)
            return value

        def cache_clear():
            with lock:
                cache.clear()

        wrapper.cache_clear = cache_clear
        return wrapper

    return decorator


@lru_cache(maxsize=1000)
def get_channel_name(channel_uuid):
    from apps.channels.models import Channel
    return Channel.objects.filter(uuid=channel_uuid).values_list('name', flat=True).first()

@lru_cache(maxsize=1000)
def get_stream_name(stream_id):
    from apps.channels.models import Stream
    return Stream.objects.filter(id=stream_id).values_list('name', flat=True).first()

@lru_cache(maxsize=1000)
def get_channel_ssl_verify(channel_uuid):
    from apps.channels.models import Channel
    channel = Channel.objects.filter(uuid=channel_uuid).select_related('stream_profile').first()
    if channel:
        profile = channel.get_stream_profile()
        return getattr(profile, 'ssl_verify', True) if profile else True
    return True

@lru_cache(maxsize=1000)
def get_stream_profile_data(channel_uuid):
    """Get full StreamProfile data for a channel, cached."""
    from apps.channels.models import Channel
    channel = Channel.objects.filter(uuid=channel_uuid).select_related('stream_profile').first()
    if not channel:
        return None
    
    profile = channel.get_stream_profile()
    if not profile:
        return None
    
    return {
        'id': profile.id,
        'name': profile.name,
        'command': profile.command,
        'parameters': profile.parameters,
        'ssl_verify': profile.ssl_verify,
        'user_agent_id': profile.user_agent_id,
        'is_proxy': profile.is_proxy(),
        'is_redirect': profile.is_redirect()
    }

@lru_cache(maxsize=500)
def get_user_agent_data(user_agent_id):
    """Get full UserAgent data, cached."""
    from core.models import UserAgent
    ua = UserAgent.objects.filter(id=user_agent_id).first()
    if not ua:
        return None
    
    return {
        'user_agent': ua.user_agent,
        'headers': ua.headers or {}
    }

@lru_cache(maxsize=1000)
def get_stream_extra_data(stream_id):
    """Get stream-specific headers (Referer, Origin, Custom), cached."""
    from apps.channels.models import Stream
    stream = Stream.objects.filter(id=stream_id).first()
    if not stream:
        return None
    
    return {
        'http_referrer': getattr(stream, 'http_referrer', None),
        'http_origin': getattr(stream, 'http_origin', None),
        'custom_headers': getattr(stream, 'custom_headers', None)
    }


def clear_proxy_caches():
    """Clear all process-local LRU caches for live proxy data."""
    get_channel_name.cache_clear()
    get_stream_name.cache_clear()
    get_channel_ssl_verify.cache_clear()
    get_stream_profile_data.cache_clear()
    get_user_agent_data.cache_clear()
    get_stream_extra_data.cache_clear()

