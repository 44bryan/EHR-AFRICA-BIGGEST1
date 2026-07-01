from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0013_alter_payment_receipt_number_alter_payment_reference'),
    ]

    operations = [
        migrations.AddField(
            model_name='serviceprice',
            name='tier',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Leave blank = visible to ALL cashier desks. Set to restrict this service to a specific desk tier only (e.g. VIP consultation at a higher price for VIP desk).',
                max_length=20,
            ),
        ),
    ]
