"""
Fix 10: Deduplicate M3UEpisodeRelation and add unique constraint on (m3u_account, episode).
"""
from django.db import migrations


def deduplicate_m3u_episode_relations(apps, schema_editor):
    M3UEpisodeRelation = apps.get_model('vod', 'M3UEpisodeRelation')
    if not M3UEpisodeRelation.objects.exists():
        return

    # To avoid issues with large subqueries, we evaluate the kept IDs into a list
    # or use a raw query if preferable. Evaluating to a list is safest for ORM.
    from django.db.models import Min
    kept_ids = list(
        M3UEpisodeRelation.objects.values('m3u_account', 'episode')
        .annotate(min_id=Min('id'))
        .values_list('min_id', flat=True)
    )
    M3UEpisodeRelation.objects.exclude(id__in=kept_ids).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('vod', '0004_m3uepisoderelation_series_relation'),
    ]

    operations = [
        migrations.RunPython(deduplicate_m3u_episode_relations, reverse_code=migrations.RunPython.noop),
        migrations.AlterUniqueTogether(
            name='m3uepisoderelation',
            unique_together={('m3u_account', 'stream_id'), ('m3u_account', 'episode')},
        ),
    ]
