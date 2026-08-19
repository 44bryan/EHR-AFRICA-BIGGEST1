"""
Pharmacy enterprise upgrade:
- StorageCondition on Drug
- Supplier, PurchaseOrder, PurchaseOrderItem
- DispensingReturn
- Dispensing: counseling + pharmacist verification
- DispensingItem: quantity_prescribed, substitution tracking
- ChronicPrescription: drop unique_together
- DrugStock: fix received_date default
"""
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pharmacy', '0006_add_audit_fields'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 1. Storage condition on Drug
        migrations.AddField(
            model_name='drug',
            name='storage_condition',
            field=models.CharField(
                choices=[
                    ('ROOM', 'Room Temperature (15–25 °C)'),
                    ('COOL', 'Cool (8–15 °C)'),
                    ('FRIDGE', 'Refrigerated (2–8 °C)'),
                    ('FROZEN', 'Frozen (−20 °C or below)'),
                    ('LIGHT', 'Protect from Light'),
                    ('FLAME', 'Flammable — separate storage'),
                ],
                default='ROOM',
                max_length=10,
            ),
        ),

        # 2. DrugStock received_date default change (no schema change needed,
        #    only Python default — AlterField to update choices metadata)
        migrations.AlterField(
            model_name='drugstock',
            name='received_date',
            field=models.DateField(default=django.utils.timezone.localdate),
        ),

        # 3. Dispensing new fields
        migrations.AddField(
            model_name='dispensing',
            name='verified_by_pharmacist',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='pharmacy_verified_dispensings',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='dispensing',
            name='verified_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='dispensing',
            name='counseling_given',
            field=models.BooleanField(
                default=False,
                help_text='Patient/caregiver counseled on use, storage and side effects',
            ),
        ),
        migrations.AddField(
            model_name='dispensing',
            name='counseling_notes',
            field=models.TextField(blank=True),
        ),

        # 4. DispensingItem new fields
        migrations.AddField(
            model_name='dispensingitem',
            name='quantity_prescribed',
            field=models.PositiveIntegerField(
                blank=True, null=True,
                help_text='Quantity originally prescribed (for partial-fill tracking)',
            ),
        ),
        migrations.AddField(
            model_name='dispensingitem',
            name='substituted_for',
            field=models.CharField(
                blank=True, max_length=200,
                help_text='Original brand/drug name if a generic substitution was made',
            ),
        ),
        migrations.AddField(
            model_name='dispensingitem',
            name='substitution_approved_by',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='substitution_approvals',
                to=settings.AUTH_USER_MODEL,
            ),
        ),

        # 5. ChronicPrescription — drop unique_together
        migrations.AlterUniqueTogether(
            name='chronicprescription',
            unique_together=set(),
        ),

        # 6. Supplier model
        migrations.CreateModel(
            name='Supplier',
            fields=[
                ('id', models.UUIDField(primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(db_index=True, default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('name', models.CharField(max_length=200)),
                ('contact_person', models.CharField(blank=True, max_length=100)),
                ('phone', models.CharField(blank=True, max_length=30)),
                ('email', models.EmailField(blank=True)),
                ('address', models.TextField(blank=True)),
                ('registration_number', models.CharField(blank=True, max_length=100)),
                ('is_active', models.BooleanField(default=True)),
                ('created_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='%(class)s_created',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('updated_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='%(class)s_updated',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'ordering': ['name']},
        ),

        # 7. PurchaseOrder model
        migrations.CreateModel(
            name='PurchaseOrder',
            fields=[
                ('id', models.UUIDField(primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(db_index=True, default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('order_number', models.CharField(max_length=30, unique=True)),
                ('status', models.CharField(
                    choices=[
                        ('DRAFT', 'Draft'),
                        ('SUBMITTED', 'Submitted to Supplier'),
                        ('APPROVED', 'Approved'),
                        ('PARTIAL', 'Partially Received'),
                        ('RECEIVED', 'Fully Received'),
                        ('CANCELLED', 'Cancelled'),
                    ],
                    default='DRAFT', max_length=15,
                )),
                ('order_date', models.DateField(default=django.utils.timezone.localdate)),
                ('expected_delivery', models.DateField(blank=True, null=True)),
                ('approved_at', models.DateTimeField(blank=True, null=True)),
                ('total_amount', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('notes', models.TextField(blank=True)),
                ('supplier', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='purchase_orders',
                    to='pharmacy.supplier',
                )),
                ('approved_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='approved_purchase_orders',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('created_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='%(class)s_created',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('updated_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='%(class)s_updated',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'ordering': ['-order_date']},
        ),

        # 8. PurchaseOrderItem model
        migrations.CreateModel(
            name='PurchaseOrderItem',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('quantity_ordered', models.PositiveIntegerField()),
                ('quantity_received', models.PositiveIntegerField(default=0)),
                ('unit_cost', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('batch_number', models.CharField(blank=True, max_length=100)),
                ('manufacture_date', models.DateField(blank=True, null=True)),
                ('expiry_date', models.DateField(blank=True, null=True)),
                ('order', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='items',
                    to='pharmacy.purchaseorder',
                )),
                ('drug', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='purchase_items',
                    to='pharmacy.drug',
                )),
                ('stock_created', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='purchase_order_items',
                    to='pharmacy.drugstock',
                )),
            ],
        ),

        # 9. DispensingReturn model
        migrations.CreateModel(
            name='DispensingReturn',
            fields=[
                ('id', models.UUIDField(primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(db_index=True, default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('quantity_returned', models.PositiveIntegerField()),
                ('reason', models.CharField(
                    choices=[
                        ('REFUSED', 'Patient Refused Medication'),
                        ('DUPLICATE', 'Duplicate Dispensing'),
                        ('WRONG', 'Wrong Drug Dispensed'),
                        ('WRONG_QTY', 'Wrong Quantity'),
                        ('DECEASED', 'Patient Deceased'),
                        ('DISCHARGE', 'Patient Discharged — Unused Drugs'),
                        ('OTHER', 'Other'),
                    ],
                    max_length=15,
                )),
                ('notes', models.TextField(blank=True)),
                ('stock_restored', models.BooleanField(default=False)),
                ('dispensing', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='returns',
                    to='pharmacy.dispensing',
                )),
                ('drug', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='dispensing_returns',
                    to='pharmacy.drug',
                )),
                ('stock_batch', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='dispensing_returns',
                    to='pharmacy.drugstock',
                )),
                ('returned_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='dispensing_returns_processed',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('created_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='%(class)s_created',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('updated_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='%(class)s_updated',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'ordering': ['-created_at']},
        ),
    ]
