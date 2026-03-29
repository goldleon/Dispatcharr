from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0021_systemnotification_notificationdismissal'),
    ]

    operations = [
        migrations.AddField(
            model_name='streamprofile',
            name='ssl_verify',
            field=models.BooleanField(
                default=True,
                help_text='Verify SSL certificates when connecting to provider. '
                          'Disable for providers with self-signed or expired certificates.',
            ),
        ),
    ]
