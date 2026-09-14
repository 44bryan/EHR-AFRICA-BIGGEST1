"""
Add international-standard features:
- InventoryItem: max_stock_level, barcode, abc_class, ven_class
- StoreTransfer + StoreTransferItem (inter-store transfers)
- GoodsReceivedNote + GRNItem (GRN with inspection checklist)
- DisposalRecord + DisposalItem (wastage/disposal workflow)
- StockTakeSchedule (recurring stock count)
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import uuid


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('inventory', '0003_store_locations_stockcount_returns'),
    ]

    operations = [
        # ── InventoryItem new fields ──
        migrations.AddField(
            model_name='inventoryitem',
            name='max_stock_level',
            field=models.PositiveIntegerField(default=0, help_text='Maximum stock level — 0 means no limit (ISO 9001 §8.5.4)'),
        ),
        migrations.AddField(
            model_name='inventoryitem',
            name='barcode',
            field=models.CharField(blank=True, max_length=100, null=True, unique=True, help_text='Auto-generated barcode for scanning'),
        ),
        migrations.AddField(
            model_name='inventoryitem',
            name='abc_class',
            field=models.CharField(blank=True, max_length=1, choices=[('A', 'A — High Value'), ('B', 'B — Medium Value'), ('C', 'C — Low Value')]),
        ),
        migrations.AddField(
            model_name='inventoryitem',
            name='ven_class',
            field=models.CharField(blank=True, max_length=1, choices=[('V', 'Vital'), ('E', 'Essential'), ('N', 'Non-Essential')]),
        ),

        # ── StoreTransfer ──
        migrations.CreateModel(
            name='StoreTransfer',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('transfer_number', models.CharField(blank=True, max_length=30, unique=True)),
                ('status', models.CharField(choices=[('REQUESTED', 'Requested'), ('APPROVED', 'Approved'), ('IN_TRANSIT', 'In Transit'), ('RECEIVED', 'Received'), ('CANCELLED', 'Cancelled')], default='REQUESTED', max_length=15)),
                ('transfer_date', models.DateField(default=django.utils.timezone.localdate)),
                ('notes', models.TextField(blank=True)),
                ('from_location', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='transfers_out', to='inventory.storelocation')),
                ('to_location', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='transfers_in', to='inventory.storelocation')),
                ('requested_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='store_transfer_requests', to=settings.AUTH_USER_MODEL)),
                ('approved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='store_transfer_approvals', to=settings.AUTH_USER_MODEL)),
                ('received_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='store_transfers_received', to=settings.AUTH_USER_MODEL)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='StoreTransferItem',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('quantity', models.PositiveIntegerField()),
                ('notes', models.CharField(blank=True, max_length=200)),
                ('transfer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='inventory.storetransfer')),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='inventory.inventoryitem')),
            ],
        ),

        # ── GoodsReceivedNote ──
        migrations.CreateModel(
            name='GoodsReceivedNote',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('grn_number', models.CharField(blank=True, max_length=30, unique=True)),
                ('status', models.CharField(choices=[('PENDING', 'Pending Inspection'), ('INSPECTED', 'Inspected'), ('ACCEPTED', 'Accepted'), ('REJECTED', 'Rejected')], default='PENDING', max_length=15)),
                ('received_date', models.DateField(default=django.utils.timezone.localdate)),
                ('packaging_intact', models.BooleanField(default=False)),
                ('labels_correct', models.BooleanField(default=False)),
                ('quantity_matches_po', models.BooleanField(default=False)),
                ('expiry_acceptable', models.BooleanField(default=False)),
                ('storage_temp_ok', models.BooleanField(default=False)),
                ('certificates_present', models.BooleanField(default=False)),
                ('visual_inspection_ok', models.BooleanField(default=False)),
                ('inspection_notes', models.TextField(blank=True)),
                ('notes', models.TextField(blank=True)),
                ('purchase_order', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='grns', to='inventory.purchaseorder')),
                ('received_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='grns_received', to=settings.AUTH_USER_MODEL)),
                ('inspected_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='grns_inspected', to=settings.AUTH_USER_MODEL)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-received_date']},
        ),
        migrations.CreateModel(
            name='GRNItem',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('quantity_received', models.PositiveIntegerField()),
                ('quantity_accepted', models.PositiveIntegerField(default=0)),
                ('quantity_rejected', models.PositiveIntegerField(default=0)),
                ('rejection_reason', models.CharField(blank=True, max_length=200)),
                ('lot_number', models.CharField(blank=True, max_length=100)),
                ('expiry_date', models.DateField(blank=True, null=True)),
                ('notes', models.CharField(blank=True, max_length=200)),
                ('grn', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='inventory.goodsreceivednote')),
                ('po_item', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='inventory.purchaseorderitem')),
            ],
        ),

        # ── DisposalRecord ──
        migrations.CreateModel(
            name='DisposalRecord',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('disposal_number', models.CharField(blank=True, max_length=30, unique=True)),
                ('status', models.CharField(choices=[('PENDING', 'Pending Authorization'), ('APPROVED', 'Authorized'), ('DISPOSED', 'Disposed'), ('REJECTED', 'Rejected')], default='PENDING', max_length=15)),
                ('reason', models.CharField(choices=[('EXPIRED', 'Expired'), ('DAMAGED', 'Damaged'), ('RECALLED', 'Recalled'), ('OBSOLETE', 'Obsolete'), ('CONTAMINATED', 'Contaminated'), ('OTHER', 'Other')], max_length=20)),
                ('disposal_method', models.CharField(blank=True, choices=[('INCINERATION', 'Incineration'), ('CHEMICAL', 'Chemical Treatment'), ('LANDFILL', 'Sanitary Landfill'), ('RETURN_VENDOR', 'Return to Vendor'), ('DONATION', 'Donation'), ('OTHER', 'Other')], max_length=20)),
                ('disposal_date', models.DateField(blank=True, null=True)),
                ('notes', models.TextField(blank=True)),
                ('environmental_certificate', models.BooleanField(default=False)),
                ('requested_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='disposal_requests', to=settings.AUTH_USER_MODEL)),
                ('authorized_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='disposal_authorizations', to=settings.AUTH_USER_MODEL)),
                ('witness', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='disposal_witnessed', to=settings.AUTH_USER_MODEL)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='DisposalItem',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('quantity', models.PositiveIntegerField()),
                ('unit_cost', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('notes', models.CharField(blank=True, max_length=200)),
                ('disposal', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='inventory.disposalrecord')),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='inventory.inventoryitem')),
                ('batch', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='inventory.batchstock')),
            ],
        ),

        # ── StockTakeSchedule ──
        migrations.CreateModel(
            name='StockTakeSchedule',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('name', models.CharField(max_length=100)),
                ('frequency', models.CharField(choices=[('WEEKLY', 'Weekly'), ('MONTHLY', 'Monthly'), ('QUARTERLY', 'Quarterly'), ('SEMI_ANNUAL', 'Semi-Annual'), ('ANNUAL', 'Annual')], max_length=20)),
                ('category_filter', models.CharField(blank=True, choices=[('SURGICAL', 'Surgical'), ('MEDICAL_CONSUMABLE', 'Consumables'), ('DIAGNOSTIC', 'Diagnostic'), ('PHARMACEUTICAL', 'Pharma'), ('IMPLANT', 'Implant'), ('LENS', 'Lens'), ('OFFICE', 'Office'), ('CLEANING', 'Cleaning'), ('IT', 'IT'), ('FURNITURE', 'Furniture'), ('LINEN', 'Linen'), ('OTHER', 'Other')], max_length=20)),
                ('abc_filter', models.CharField(blank=True, choices=[('A', 'A'), ('B', 'B'), ('C', 'C')], max_length=1)),
                ('next_due', models.DateField()),
                ('last_completed', models.DateField(blank=True, null=True)),
                ('is_active', models.BooleanField(default=True)),
                ('notes', models.TextField(blank=True)),
                ('assigned_to', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='assigned_stock_takes', to=settings.AUTH_USER_MODEL)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['next_due']},
        ),
    ]
