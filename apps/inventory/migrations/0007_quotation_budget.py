"""
Add SupplierQuotation, QuotationItem, StoreBudget models.
ISO 9001 §8.4 vendor selection + §7.1 resource management.
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import uuid


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('inventory', '0006_add_updated_by_to_old_tables'),
    ]

    operations = [
        # ── SupplierQuotation ────────────────────────────────────────
        migrations.CreateModel(
            name='SupplierQuotation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('rfq_number', models.CharField(blank=True, max_length=30, unique=True)),
                ('status', models.CharField(choices=[
                    ('REQUESTED', 'Requested'), ('RECEIVED', 'Received'),
                    ('ACCEPTED', 'Accepted'), ('REJECTED', 'Rejected'),
                    ('EXPIRED', 'Expired'),
                ], default='REQUESTED', max_length=15)),
                ('requested_date', models.DateField(default=django.utils.timezone.localdate)),
                ('valid_until', models.DateField(blank=True, null=True)),
                ('total_amount', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('notes', models.TextField(blank=True)),
                ('vendor', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                                              related_name='quotations', to='inventory.vendor')),
                ('linked_po', models.ForeignKey(blank=True, null=True,
                                                 on_delete=django.db.models.deletion.SET_NULL,
                                                 related_name='quotations', to='inventory.purchaseorder')),
                ('requested_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                                                    related_name='store_quotations_requested',
                                                    to=settings.AUTH_USER_MODEL)),
                ('created_by', models.ForeignKey(blank=True, null=True,
                                                  on_delete=django.db.models.deletion.SET_NULL,
                                                  related_name='+', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True,
                                                  on_delete=django.db.models.deletion.SET_NULL,
                                                  related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-requested_date']},
        ),
        # ── QuotationItem ────────────────────────────────────────────
        migrations.CreateModel(
            name='QuotationItem',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('quantity', models.PositiveIntegerField()),
                ('quoted_price', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('notes', models.CharField(blank=True, max_length=200)),
                ('quotation', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                                 related_name='items', to='inventory.supplierquotation')),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                                            to='inventory.inventoryitem')),
            ],
        ),
        # ── StoreBudget ──────────────────────────────────────────────
        migrations.CreateModel(
            name='StoreBudget',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('name', models.CharField(max_length=100)),
                ('fiscal_year', models.PositiveIntegerField()),
                ('category', models.CharField(blank=True, choices=[
                    ('SURGICAL', 'Surgical Supplies'), ('MEDICAL_CONSUMABLE', 'Medical Consumables'),
                    ('DIAGNOSTIC', 'Diagnostic Equipment'), ('PHARMACEUTICAL', 'Pharmaceuticals / Reagents'),
                    ('IMPLANT', 'Implants / Prosthetics'), ('LENS', 'Ophthalmic Lenses (Consignment)'),
                    ('OFFICE', 'Office Supplies'), ('CLEANING', 'Cleaning / Housekeeping'),
                    ('IT', 'IT Equipment'), ('FURNITURE', 'Furniture'),
                    ('LINEN', 'Linen / Laundry'), ('OTHER', 'Other'),
                ], max_length=20)),
                ('allocated', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('spent', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('notes', models.TextField(blank=True)),
                ('created_by', models.ForeignKey(blank=True, null=True,
                                                  on_delete=django.db.models.deletion.SET_NULL,
                                                  related_name='+', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True,
                                                  on_delete=django.db.models.deletion.SET_NULL,
                                                  related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-fiscal_year', 'name'], 'unique_together': {('fiscal_year', 'category')}},
        ),
    ]
