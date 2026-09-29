"""
Fix SupplierInvoiceItem: add audit fields, convert id from bigint to UUID,
and align ThreeWayMatch/SupplierInvoice field definitions.
"""
import uuid
from django.db import migrations, models


def convert_id_to_uuid(apps, schema_editor):
    """Convert SupplierInvoiceItem.id from bigint to UUID (table is empty)."""
    schema_editor.execute("""
        ALTER TABLE inventory_supplierinvoiceitem
            DROP CONSTRAINT IF EXISTS inventory_supplierinvoiceitem_pkey CASCADE;
        ALTER TABLE inventory_supplierinvoiceitem
            DROP COLUMN id;
        ALTER TABLE inventory_supplierinvoiceitem
            ADD COLUMN id uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY;
    """)


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0011_store_location_types_gl'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='supplierinvoiceitem',
            options={'ordering': ['-created_at']},
        ),
        migrations.AddField(
            model_name='supplierinvoiceitem',
            name='deleted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='supplierinvoiceitem',
            name='is_deleted',
            field=models.BooleanField(default=False),
        ),
        # Convert bigint id → UUID using raw SQL
        migrations.RunPython(convert_id_to_uuid, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='supplierinvoice',
            name='is_deleted',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='threewaymatch',
            name='is_deleted',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='threewaymatch',
            name='price_match',
            field=models.BooleanField(default=False, help_text='Do PO/Invoice unit prices match?'),
        ),
        migrations.AlterField(
            model_name='threewaymatch',
            name='qty_match',
            field=models.BooleanField(default=False, help_text='Do PO/GRN/Invoice quantities match?'),
        ),
        migrations.AlterField(
            model_name='threewaymatch',
            name='total_match',
            field=models.BooleanField(default=False, help_text='Do totals match within tolerance?'),
        ),
    ]
