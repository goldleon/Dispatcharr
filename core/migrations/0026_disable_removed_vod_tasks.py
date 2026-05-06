"""
Data migration: disable stale Celery beat periodic tasks that were removed
from apps/proxy/tasks.py in upstream commit dcefc654.

The DatabaseScheduler (django_celery_beat) persists tasks in the DB and does
NOT auto-delete entries that have been removed from CELERY_BEAT_SCHEDULE.
Without this migration, every deployment that reuses an existing database will
keep dispatching these dead tasks, causing a recurring KeyError in the worker.
"""

from django.db import migrations


def disable_removed_vod_tasks(apps, schema_editor):
    """Set enabled=False for periodic tasks whose backing functions no longer exist."""
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    stale_tasks = [
        "cleanup-vod-connections",
        "cleanup-vod-heartbeats",
    ]
    updated = PeriodicTask.objects.filter(name__in=stale_tasks).update(enabled=False)
    if updated:
        print(f"\n  Disabled {updated} stale periodic task(s): {stale_tasks}")


def noop(apps, schema_editor):
    """Reverse is a no-op — we never want to re-enable removed tasks."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0025_merge_20260426_1917"),
        # Ensure django_celery_beat table exists before we touch it
        ("django_celery_beat", "0018_improve_crontab_helptext"),
    ]

    operations = [
        migrations.RunPython(disable_removed_vod_tasks, noop),
    ]
