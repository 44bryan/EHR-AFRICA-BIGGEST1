from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0042_journal_type_stock_operation_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='stockoperationtype',
            name='location_types',
            field=models.CharField(
                max_length=200,
                blank=True,
                default='',
                help_text=(
                    'Comma-separated StoreLocation.location_type codes this operation applies to. '
                    'Leave blank to show in ALL stores. '
                    'e.g. "GENERAL,PHARMACY" or "PHARMACY" or "OPTICAL,SHOWROOM"'
                ),
            ),
        ),
    ]
