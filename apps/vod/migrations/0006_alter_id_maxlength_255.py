# Generated migration to update max_length of tmdb_id and imdb_id fields
# from 50 to 255 on Movie, Series, and Episode models.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('vod', '0005_m3uepisoderelation_unique_together'),
    ]

    operations = [
        # Movie model
        migrations.AlterField(
            model_name='movie',
            name='tmdb_id',
            field=models.CharField(blank=True, help_text='TMDB ID for metadata', max_length=255, null=True, unique=True),
        ),
        migrations.AlterField(
            model_name='movie',
            name='imdb_id',
            field=models.CharField(blank=True, help_text='IMDB ID for metadata', max_length=255, null=True, unique=True),
        ),
        # Series model
        migrations.AlterField(
            model_name='series',
            name='tmdb_id',
            field=models.CharField(blank=True, help_text='TMDB ID for metadata', max_length=255, null=True, unique=True),
        ),
        migrations.AlterField(
            model_name='series',
            name='imdb_id',
            field=models.CharField(blank=True, help_text='IMDB ID for metadata', max_length=255, null=True, unique=True),
        ),
        # Episode model
        migrations.AlterField(
            model_name='episode',
            name='tmdb_id',
            field=models.CharField(blank=True, db_index=True, help_text='TMDB ID for metadata', max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='episode',
            name='imdb_id',
            field=models.CharField(blank=True, db_index=True, help_text='IMDB ID for metadata', max_length=255, null=True),
        ),
    ]
