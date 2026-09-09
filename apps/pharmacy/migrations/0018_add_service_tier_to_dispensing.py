from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pharmacy', '0017_dispensing_discount_pct'),
    ]

    operations = [
        migrations.AddField(
            model_name='dispensing',
            name='service_tier',
            field=models.CharField(
                blank=True, max_length=20,
                help_text='Service tier for walk-in OTC pricing (STANDARD, EXPRESS, VIP). If blank, resolved from patient visit.',
            ),
        ),
    ]
