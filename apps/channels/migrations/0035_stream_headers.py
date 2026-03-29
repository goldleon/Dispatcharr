# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('channels', '0034_remove_stream_dispatcharr_stream_id_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='stream',
            name='http_referrer',
            field=models.URLField(blank=True, help_text='Referer header for the stream', max_length=512, null=True),
        ),
        migrations.AddField(
            model_name='stream',
            name='http_origin',
            field=models.URLField(blank=True, help_text='Origin header for the stream', max_length=512, null=True),
        ),
        migrations.AddField(
            model_name='stream',
            name='custom_headers',
            field=models.JSONField(blank=True, default=dict, help_text='Stream specific custom headers'),
        ),
    ]
