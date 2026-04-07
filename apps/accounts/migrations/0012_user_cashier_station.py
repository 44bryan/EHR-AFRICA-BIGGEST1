from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0011_user_totp_enabled_user_totp_secret'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='cashier_station',
            field=models.CharField(
                blank=True,
                choices=[
                    ('ALL',        'All Consultations'),
                    ('STANDARD',   'Standard Consultation'),
                    ('FAST_TRACK', 'Fast Track Consultation'),
                    ('VIP',        'VIP Consultation'),
                    ('INSURED',    'Insured / HMO'),
                ],
                default='ALL',
                help_text='For Cashier/Billing Officer accounts only — indicates which consultation desk this cashier serves. QMS tokens are routed to the matching station.',
                max_length=20,
                verbose_name='Cashier Station',
            ),
        ),
    ]
