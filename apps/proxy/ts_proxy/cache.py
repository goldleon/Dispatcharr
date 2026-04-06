from functools import lru_cache

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
