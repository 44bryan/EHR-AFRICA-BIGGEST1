from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pharmacy', '0016_drugstock_expiry_nullable'),
    ]

    operations = [
        migrations.AddField(
            model_name='dispensing',
            name='discount_pct',
            field=models.DecimalField(
                decimal_places=2, default=0, help_text='Discount percentage (0-100)',
                max_digits=5,
            ),
        ),
    ]
