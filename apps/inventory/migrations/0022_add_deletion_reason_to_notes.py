"""Add deletion_reason field to StockEntryNote and StockExitNote (missed from AuditModel)."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0021_stock_entry_exit_notes'),
    ]

    operations = [
        migrations.AddField(
            model_name='stockentrynote',
            name='deletion_reason',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='stockexitnote',
            name='deletion_reason',
            field=models.TextField(blank=True, default=''),
        ),
    ]
