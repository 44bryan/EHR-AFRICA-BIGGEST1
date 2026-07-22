from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('departments', '0007_consultationroom_room_tier'),
    ]

    operations = [
        # Free the department code from the predefined enum choices
        # and increase max_length to 20 so custom codes like GEN_MED fit
        migrations.AlterField(
            model_name='department',
            name='code',
            field=models.CharField(
                max_length=20,
                unique=True,
                help_text='Short unique code e.g. GEN_OPH, GEN_MED, CARDIO (no spaces)',
            ),
        ),
        # Add ALL tier choice to ConsultationRoom (CharField — no DB change needed,
        # but recorded in migration history for Django's validation tracking)
        migrations.AlterField(
            model_name='consultationroom',
            name='room_tier',
            field=models.CharField(
                max_length=12,
                choices=[
                    ('STANDARD',   'Standard'),
                    ('EXPRESS',    'Express'),
                    ('FAST_TRACK', 'Fast Track'),
                    ('VIP',        'VIP'),
                    ('ALL',        'All Tiers'),
                ],
                default='STANDARD',
                help_text='Service tier this room handles — determines QMS queue on dispatch. '
                          'All Tiers = doctor sees every patient regardless of tier.',
            ),
        ),
    ]
