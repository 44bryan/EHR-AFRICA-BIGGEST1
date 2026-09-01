"""
Head Pharmacist Module — PharmacyLocation, StockTransfer, StockExit, DrugRecall
WHO GPP, FIP Guidelines, JCI MMU Standards
"""
import django.db.models.deletion
import django.utils.timezone
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('pharmacy', '0009_fix_rxlineunavailable_missing_cols'),
    ]

    operations = [
        # ── PharmacyLocation ────────────────────────────────────────────
        migrations.CreateModel(
            name='PharmacyLocation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('name', models.CharField(max_length=100)),
                ('location_type', models.CharField(max_length=20, choices=[
                    ('MAIN', 'Main Pharmacy'),
                    ('SATELLITE', 'Satellite Pharmacy'),
                    ('WARD', 'Ward Pharmacy'),
                    ('THEATRE', 'Theatre Pharmacy'),
                    ('EMERGENCY', 'Emergency Pharmacy'),
                    ('OUTPATIENT', 'Outpatient Pharmacy'),
                ])),
                ('address', models.TextField(blank=True, help_text='Physical location within facility')),
                ('phone_ext', models.CharField(blank=True, max_length=20)),
                ('is_active', models.BooleanField(default=True)),
                ('manager', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                              related_name='managed_pharmacy_locations', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['name'],
            },
        ),

        # ── Drug.ven_class + Drug.location ──────────────────────────────
        migrations.AddField(
            model_name='drug',
            name='ven_class',
            field=models.CharField(blank=True, help_text='V=Vital, E=Essential, N=Non-essential (WHO VEN analysis)', max_length=1),
        ),
        migrations.AddField(
            model_name='drug',
            name='location',
            field=models.ForeignKey(blank=True, help_text='Primary pharmacy location for this drug', null=True,
                                    on_delete=django.db.models.deletion.SET_NULL, related_name='drugs',
                                    to='pharmacy.pharmacylocation'),
        ),

        # ── StockTransfer ───────────────────────────────────────────────
        migrations.CreateModel(
            name='StockTransfer',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('transfer_number', models.CharField(max_length=30, unique=True)),
                ('status', models.CharField(choices=[
                    ('PENDING', 'Pending — Awaiting Acceptance'),
                    ('IN_TRANSIT', 'In Transit'),
                    ('RECEIVED', 'Received — Stock Updated'),
                    ('REJECTED', 'Rejected by Receiver'),
                    ('CANCELLED', 'Cancelled by Sender'),
                ], default='PENDING', max_length=15)),
                ('initiated_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('received_at', models.DateTimeField(blank=True, null=True)),
                ('notes', models.TextField(blank=True)),
                ('rejection_reason', models.TextField(blank=True)),
                ('from_location', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                                                     related_name='transfers_out', to='pharmacy.pharmacylocation')),
                ('to_location', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                                                   related_name='transfers_in', to='pharmacy.pharmacylocation')),
                ('initiated_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                                                    related_name='transfers_initiated', to=settings.AUTH_USER_MODEL)),
                ('received_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                   related_name='transfers_received', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-initiated_at'],
            },
        ),

        # ── StockTransferItem ───────────────────────────────────────────
        migrations.CreateModel(
            name='StockTransferItem',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('quantity', models.PositiveIntegerField()),
                ('quantity_received', models.PositiveIntegerField(default=0, help_text='Actual qty confirmed by receiver')),
                ('transfer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                                related_name='items', to='pharmacy.stocktransfer')),
                ('drug', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                                           related_name='transfer_items', to='pharmacy.drug')),
                ('stock_batch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                                                   related_name='transfer_items', to='pharmacy.drugstock')),
            ],
        ),

        # ── StockExit ──────────────────────────────────────────────────
        migrations.CreateModel(
            name='StockExit',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('exit_number', models.CharField(max_length=30, unique=True)),
                ('quantity', models.PositiveIntegerField()),
                ('reason', models.CharField(choices=[
                    ('EXPIRED', 'Expired — Destruction'),
                    ('DAMAGED', 'Damaged / Broken'),
                    ('DONATION', 'Donation / Sample'),
                    ('THEFT', 'Theft / Loss'),
                    ('RECALL', 'Manufacturer Recall'),
                    ('QUALITY', 'Quality Failure'),
                    ('OTHER', 'Other'),
                ], max_length=15)),
                ('notes', models.TextField(blank=True)),
                ('exit_date', models.DateTimeField(default=django.utils.timezone.now)),
                ('disposal_method', models.CharField(blank=True, help_text='e.g. Incineration, Return to supplier', max_length=100)),
                ('drug', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                                           related_name='stock_exits', to='pharmacy.drug')),
                ('stock_batch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                                                   related_name='stock_exits', to='pharmacy.drugstock')),
                ('authorized_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                                                     related_name='stock_exits_authorized', to=settings.AUTH_USER_MODEL)),
                ('witness', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                              related_name='stock_exits_witnessed', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-exit_date'],
            },
        ),

        # ── DrugRecall ──────────────────────────────────────────────────
        migrations.CreateModel(
            name='DrugRecall',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('recall_number', models.CharField(max_length=30, unique=True)),
                ('batch_numbers', models.TextField(help_text='Comma-separated batch numbers affected')),
                ('reason', models.TextField(help_text='Reason for recall (contamination, labeling error, etc.)')),
                ('severity', models.CharField(choices=[
                    ('CLASS_I', 'Class I — Life-threatening'),
                    ('CLASS_II', 'Class II — Temporary health risk'),
                    ('CLASS_III', 'Class III — Unlikely to cause harm'),
                ], max_length=10)),
                ('recall_source', models.CharField(help_text='Manufacturer, WHO, MINSANTE, etc.', max_length=100)),
                ('recall_date', models.DateField(default=django.utils.timezone.localdate)),
                ('status', models.CharField(choices=[
                    ('ACTIVE', 'Active — Quarantine in Effect'),
                    ('COMPLETED', 'Completed — All Stock Removed'),
                    ('CANCELLED', 'Cancelled — False Alarm'),
                ], default='ACTIVE', max_length=15)),
                ('quarantined_qty', models.PositiveIntegerField(default=0, help_text='Total units quarantined')),
                ('patients_affected', models.PositiveIntegerField(default=0, help_text='Patients who received recalled batch')),
                ('notes', models.TextField(blank=True)),
                ('drug', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                                           related_name='recalls', to='pharmacy.drug')),
                ('reported_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                                                   related_name='drug_recalls_reported', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-recall_date'],
            },
        ),
    ]
