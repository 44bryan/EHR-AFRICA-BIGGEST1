from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0055_alter_billingoperationcc_category_key_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='serviceprice',
            name='track_batch',
            field=models.BooleanField(default=False, help_text='Require batch number on every receipt and dispensing.'),
        ),
        migrations.AddField(
            model_name='serviceprice',
            name='track_expiry',
            field=models.BooleanField(default=False, help_text='Track expiry dates; enables FEFO dispatch and expiry alerts.'),
        ),
        migrations.AddField(
            model_name='serviceprice',
            name='shelf_life_days',
            field=models.PositiveIntegerField(blank=True, null=True, help_text='Expected shelf life in days; used to auto-calculate expiry from manufacture date.'),
        ),
        migrations.AddField(
            model_name='serviceprice',
            name='expiry_alert_days',
            field=models.PositiveIntegerField(blank=True, null=True, default=30, help_text='Alert this many days before expiry. Default 30.'),
        ),
        migrations.AddField(
            model_name='serviceprice',
            name='valuation_method',
            field=models.CharField(
                max_length=10, default='AVCO',
                choices=[('AVCO', 'Average Cost (AVCO)'), ('FIFO', 'First In First Out (FIFO)'), ('FEFO', 'First Expiry First Out (FEFO)')],
                help_text='Inventory valuation method used when calculating COGS.',
            ),
        ),
    ]
