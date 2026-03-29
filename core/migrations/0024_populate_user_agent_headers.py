# Generated manually for data migration

from django.db import migrations

def populate_headers(apps, schema_editor):
    UserAgent = apps.get_model('core', 'UserAgent')
    
    profiles = {
        "VLC": {
            "User-Agent": "VLC/3.0.16 LibVLC/3.0.16",
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate",
            "Icy-MetaData": "1",
            "Connection": "keep-alive"
        },
        "Kodi": {
            "User-Agent": "Kodi/20.2 (X11; Linux x86_64) App_Bitness/64 Version/20.2",
            "Accept": "*/*",
            "Accept-Encoding": "gzip",
            "Connection": "keep-alive"
        },
        "TiviMate": {
            "User-Agent": "TiviMate/4.7.0",
            "Accept": "*/*",
            "Accept-Encoding": "gzip",
            "Connection": "keep-alive"
        },
        "Browser (Chrome)": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive"
        },
        "FFmpeg": {
            "User-Agent": "Lavf/58.76.100",
            "Accept": "*/*",
            "Accept-Encoding": "gzip",
            "Icy-MetaData": "1"
        }
    }
    
    for name, headers in profiles.items():
        # Update if it exists by matching name or user_agent
        ua = UserAgent.objects.filter(user_agent=headers["User-Agent"]).first()
        if not ua:
            ua = UserAgent.objects.filter(name=name).first()
            
        if ua:
            ua.headers = headers
            ua.save(update_fields=['headers'])

def reverse_populate_headers(apps, schema_editor):
    UserAgent = apps.get_model('core', 'UserAgent')
    UserAgent.objects.all().update(headers={})

class Migration(migrations.Migration):

    dependencies = [
        ('core', '0023_useragent_headers'),
    ]

    operations = [
        migrations.RunPython(populate_headers, reverse_populate_headers),
    ]
