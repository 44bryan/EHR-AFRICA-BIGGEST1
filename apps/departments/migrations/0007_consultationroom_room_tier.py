from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('departments', '0006_visit_consultation_room'),
    ]

    operations = [
        migrations.AddField(
            model_name='consultationroom',
            name='room_tier',
            field=models.CharField(
                choices=[
                    ('STANDARD', 'Standard'),
                    ('EXPRESS', 'Express'),
                    ('FAST_TRACK', 'Fast Track'),
                    ('VIP', 'VIP'),
                ],
                default='STANDARD',
                help_text='Service tier this room handles — determines QMS queue on dispatch',
                max_length=12,
            ),
        ),
    ]
