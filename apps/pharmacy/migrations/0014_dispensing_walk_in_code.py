"""Add walk_in_code field to Dispensing for unique walk-in customer identification."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pharmacy', '0013_drug_tier_pricing'),
    ]

    operations = [
        migrations.AddField(
            model_name='dispensing',
            name='walk_in_code',
            field=models.CharField(
                blank=True, max_length=20,
                help_text='Auto-generated unique code for walk-in customers (WLK-YYYYMMDD-NNNN)',
            ),
        ),
    ]
