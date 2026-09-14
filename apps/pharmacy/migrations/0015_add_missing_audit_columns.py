"""Add missing is_deleted/deleted_at to PurchaseOrderItem and StockTransferItem."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pharmacy', '0014_dispensing_walk_in_code'),
    ]

    operations = [
        migrations.AddField(
            model_name='purchaseorderitem',
            name='is_deleted',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='purchaseorderitem',
            name='deleted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='stocktransferitem',
            name='is_deleted',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='stocktransferitem',
            name='deleted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
