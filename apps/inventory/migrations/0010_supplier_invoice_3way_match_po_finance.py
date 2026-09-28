"""
Add SupplierInvoice, SupplierInvoiceItem, ThreeWayMatch models.
Add PO finance approval fields (finance_approved_by, finance_approved_at, finance_notes).
"""
import django.db.models.deletion
import django.utils.timezone
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('inventory', '0009_four_eyes_validation'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # PO finance approval fields
        migrations.AddField(
            model_name='purchaseorder',
            name='finance_approved_by',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='finance_approved_pos',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='purchaseorder',
            name='finance_approved_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='purchaseorder',
            name='finance_notes',
            field=models.TextField(blank=True, help_text='Finance Director remarks on PO approval'),
        ),

        # SupplierInvoice
        migrations.CreateModel(
            name='SupplierInvoice',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(db_index=True, default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('invoice_number', models.CharField(max_length=100)),
                ('invoice_date', models.DateField()),
                ('due_date', models.DateField(blank=True, null=True)),
                ('total_amount', models.DecimalField(decimal_places=2, max_digits=14)),
                ('status', models.CharField(
                    choices=[
                        ('RECEIVED', 'Received'), ('MATCHED', 'Matched (3-Way OK)'),
                        ('DISPUTED', 'Disputed'), ('PAID', 'Paid'), ('VOID', 'Void'),
                    ],
                    default='RECEIVED', max_length=20,
                )),
                ('notes', models.TextField(blank=True)),
                ('vendor', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='supplier_invoices', to='inventory.vendor',
                )),
                ('purchase_order', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='supplier_invoices', to='inventory.purchaseorder',
                )),
                ('grn', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='supplier_invoices', to='inventory.goodsreceivednote',
                )),
                ('created_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+', to=settings.AUTH_USER_MODEL,
                )),
                ('updated_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+', to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['-invoice_date'],
                'verbose_name': 'Supplier Invoice',
            },
        ),

        # SupplierInvoiceItem
        migrations.CreateModel(
            name='SupplierInvoiceItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('quantity', models.PositiveIntegerField()),
                ('unit_price', models.DecimalField(decimal_places=2, max_digits=10)),
                ('supplier_invoice', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='items', to='inventory.supplierinvoice',
                )),
                ('item', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    to='inventory.inventoryitem',
                )),
            ],
        ),

        # ThreeWayMatch
        migrations.CreateModel(
            name='ThreeWayMatch',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(db_index=True, default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('match_number', models.CharField(max_length=30, unique=True)),
                ('status', models.CharField(
                    choices=[
                        ('PENDING', 'Pending Review'), ('MATCHED', 'Fully Matched'),
                        ('PARTIAL', 'Partial Match'), ('MISMATCH', 'Mismatch (Discrepancy)'),
                        ('RESOLVED', 'Resolved'),
                    ],
                    default='PENDING', max_length=20,
                )),
                ('po_total', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('grn_total', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('invoice_total', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('qty_match', models.BooleanField(default=False)),
                ('price_match', models.BooleanField(default=False)),
                ('total_match', models.BooleanField(default=False)),
                ('discrepancy_notes', models.TextField(blank=True)),
                ('resolved_at', models.DateTimeField(blank=True, null=True)),
                ('purchase_order', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='three_way_matches', to='inventory.purchaseorder',
                )),
                ('grn', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='three_way_matches', to='inventory.goodsreceivednote',
                )),
                ('supplier_invoice', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='three_way_matches', to='inventory.supplierinvoice',
                )),
                ('resolved_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='resolved_matches', to=settings.AUTH_USER_MODEL,
                )),
                ('created_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+', to=settings.AUTH_USER_MODEL,
                )),
                ('updated_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+', to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['-created_at'],
                'verbose_name': '3-Way Match',
                'verbose_name_plural': '3-Way Matches',
            },
        ),
    ]
