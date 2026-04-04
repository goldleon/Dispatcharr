# Generated manually

from django.db import migrations, models
from django.db.models import Count

def remove_duplicate_channel_streams(apps, schema_editor):
    ChannelStream = apps.get_model('dispatcharr_channels', 'ChannelStream')
    # Find duplicates by (channel, stream)
    duplicates = (
        ChannelStream.objects
        .values('channel', 'stream')
        .annotate(count=Count('id'))
        .filter(count__gt=1)
    )

    for dupe in duplicates:
        # Get all duplicates for this pair, order by 'order' so user's ranking is preserved, then 'id' as fallback
        dups = ChannelStream.objects.filter(
            channel=dupe['channel'],
            stream=dupe['stream']
        ).order_by('order', 'id')

        # Keep the first one, delete the rest
        first_id = dups.first().id
        dups.exclude(id=first_id).delete()

class Migration(migrations.Migration):

    dependencies = [
        ('dispatcharr_channels', '0016_channelstream_unique_channel_stream'),
    ]

    operations = [
        migrations.RunPython(remove_duplicate_channel_streams, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name='channelstream',
            name='unique_channel_stream',
        ),
        migrations.AlterUniqueTogether(
            name='channelstream',
            unique_together={('channel', 'stream')},
        ),
    ]
