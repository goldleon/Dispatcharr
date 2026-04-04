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
    channel = Channel.objects.filter(uuid=channel_uuid).prefetch_related('channelgroup_set__m3u_accounts').first()
    if channel:
        profile = channel.get_stream_profile()
        return getattr(profile, 'ssl_verify', True) if profile else True
    return True
