"""
Migration 0002 — International-standard inventory upgrade
- Add fields to InventoryItem: requires_expiry_tracking, is_consignment, udi_code,
  storage_conditions, preferred_vendor
- Add fields to Vendor: total_orders, on_time_deliveries, late_deliveries,
  quality_incidents, notes
- Add fields to PurchaseOrderItem: lot_number, manufactured_date, expiry_date
- Add field to PurchaseOrder: is_auto_generated
- Add field to StockMovement: batch (FK to BatchStock)
- New models: BatchStock, DepartmentRequisition, RequisitionItem
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [

        # ── InventoryItem new fields ───────────────────────────────────────────
        migrations.AddField(
            model_name='inventoryitem',
            name='requires_expiry_tracking',
            field=models.BooleanField(default=False, help_text='Track lot/batch and expiry date (JCI MMU.3)'),
        ),
        migrations.AddField(
            model_name='inventoryitem',
            name='is_consignment',
            field=models.BooleanField(default=False, help_text='Consignment stock \u2014 not paid until used (e.g. lenses)'),
        ),
        migrations.AddField(
            model_name='inventoryitem',
            name='udi_code',
            field=models.CharField(blank=True, help_text='Unique Device Identifier (FDA UDI / EU MDR \u2014 for implants/reusable devices)', max_length=100),
        ),
        migrations.AddField(
            model_name='inventoryitem',
            name='storage_conditions',
            field=models.CharField(blank=True, help_text='e.g. Room temperature, Refrigerate 2\u20138 \u00b0C, Freeze \u201320 \u00b0C', max_length=100),
        ),
        migrations.AddField(
            model_name='inventoryitem',
            name='preferred_vendor',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='preferred_items',
                to='inventory.vendor',
                help_text='Default vendor for auto-reorder',
            ),
        ),

        # ── Vendor new fields (ISO 9001 §8.4 supplier scoring) ─────────────────
        migrations.AddField(
            model_name='vendor',
            name='total_orders',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='vendor',
            name='on_time_deliveries',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='vendor',
            name='late_deliveries',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='vendor',
            name='quality_incidents',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='vendor',
            name='notes',
            field=models.TextField(blank=True),
        ),

        # ── PurchaseOrder new field ────────────────────────────────────────────
        migrations.AddField(
            model_name='purchaseorder',
            name='is_auto_generated',
            field=models.BooleanField(default=False, help_text='Created by auto-reorder trigger'),
        ),

        # ── PurchaseOrderItem: lot/batch fields captured at receiving ──────────
        migrations.AddField(
            model_name='purchaseorderitem',
            name='lot_number',
            field=models.CharField(blank=True, help_text='Manufacturer lot/batch number', max_length=100),
        ),
        migrations.AddField(
            model_name='purchaseorderitem',
            name='manufactured_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='purchaseorderitem',
            name='expiry_date',
            field=models.DateField(blank=True, null=True),
        ),

        # ── BatchStock model ───────────────────────────────────────────────────
        migrations.CreateModel(
            name='BatchStock',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('lot_number', models.CharField(max_length=100)),
                ('manufactured_date', models.DateField(blank=True, null=True)),
                ('expiry_date', models.DateField()),
                ('quantity_received', models.PositiveIntegerField()),
                ('quantity_remaining', models.PositiveIntegerField()),
                ('unit_cost', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('is_quarantined', models.BooleanField(default=False, help_text='Failed QC \u2014 do not dispense')),
                ('quarantine_reason', models.CharField(blank=True, max_length=200)),
                ('notes', models.TextField(blank=True)),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='batches', to='inventory.inventoryitem')),
                ('purchase_order', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='batch_stocks', to='inventory.purchaseorder')),
            ],
            options={
                'ordering': ['expiry_date'],
            },
        ),

        # ── StockMovement: add batch FK ────────────────────────────────────────
        migrations.AddField(
            model_name='stockmovement',
            name='batch',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='movements',
                to='inventory.batchstock',
                help_text='Linked batch (for expiry-tracked items)',
            ),
        ),
        # Also add EXPIRE and ISSUE to movement_type choices
        migrations.AlterField(
            model_name='stockmovement',
            name='movement_type',
            field=models.CharField(max_length=20, choices=[
                ('IN', 'Stock In'), ('OUT', 'Stock Out'), ('ADJUST', 'Adjustment'),
                ('RETURN', 'Return'), ('EXPIRE', 'Expiry Write-off'), ('ISSUE', 'Dept. Issue'),
            ]),
        ),

        # ── DepartmentRequisition model ────────────────────────────────────────
        migrations.CreateModel(
            name='DepartmentRequisition',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('req_number', models.CharField(blank=True, max_length=30, unique=True)),
                ('department', models.CharField(max_length=100)),
                ('status', models.CharField(
                    choices=[('PENDING', 'Pending Approval'), ('APPROVED', 'Approved'),
                             ('ISSUED', 'Fully Issued'), ('PARTIAL', 'Partially Issued'),
                             ('REJECTED', 'Rejected')],
                    default='PENDING', max_length=20,
                )),
                ('priority', models.CharField(
                    choices=[('ROUTINE', 'Routine'), ('URGENT', 'Urgent'), ('EMERGENCY', 'Emergency')],
                    default='ROUTINE', max_length=10,
                )),
                ('needed_by', models.DateField(blank=True, null=True)),
                ('notes', models.TextField(blank=True)),
                ('issued_at', models.DateTimeField(blank=True, null=True)),
                ('rejected_reason', models.TextField(blank=True)),
                ('approved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='approved_requisitions', to=settings.AUTH_USER_MODEL)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('issued_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='issued_requisitions', to=settings.AUTH_USER_MODEL)),
                ('requested_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='requisitions', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),

        # ── RequisitionItem model ──────────────────────────────────────────────
        migrations.CreateModel(
            name='RequisitionItem',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('quantity_requested', models.PositiveIntegerField()),
                ('quantity_issued', models.PositiveIntegerField(default=0)),
                ('notes', models.CharField(blank=True, max_length=200)),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='inventory.inventoryitem')),
                ('requisition', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='inventory.departmentrequisition')),
            ],
            options={
                'ordering': ['-created_at'],
                'abstract': False,
            },
        ),
    ]
