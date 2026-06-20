from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0006_user_stream_limit"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="api_key_prefix",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="First 8 chars of the raw key for indexed lookup.",
                max_length=16,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="user",
            name="api_key",
            field=models.CharField(
                blank=True,
                db_index=False,
                max_length=200,
                null=True,
            ),
        ),
    ]
