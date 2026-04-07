from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('appointments', '0002_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='appointment',
            name='service_tier',
            field=models.CharField(
                choices=[
                    ('STANDARD', 'Standard'),
                    ('EXPRESS', 'Express'),
                    ('FAST_TRACK', 'Fast Track'),
                    ('VIP', 'VIP'),
                ],
                default='STANDARD',
                max_length=15,
            ),
        ),
    ]
