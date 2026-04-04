"""
Fix 9: Convert EPGData.name and ProgramData.title from CharField(max_length=255)
to TextField to prevent truncation on unusually long EPG entries.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("epg", "0021_epgsource_priority"),
    ]

    operations = [
        migrations.AlterField(
            model_name="epgdata",
            name="name",
            field=models.TextField(),
        ),
        migrations.AlterField(
            model_name="programdata",
            name="title",
            field=models.TextField(),
        ),
    ]
