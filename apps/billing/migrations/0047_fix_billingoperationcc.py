"""
Migration 0047 — Fix BillingOperationCC table schema

0046 created the table with an incomplete field list (missing all AuditModel
FK audit columns and used BigAutoField instead of UUIDField).  This migration
drops and recreates the table with the correct schema, then re-seeds it.
"""

import uuid
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


REVENUE_SEED = [
    ('101', 'OPD — Doctor Consultation',       'CONSULT',   'CC-003', 1),
    ('102', 'OPD — Clinical / Procedure',      'CLINICAL',  'CC-003', 2),
    ('103', 'Laboratory — Investigation',      'INVEST',    'CC-004', 3),
    ('104', 'Laboratory — Lab Test',           'LAB',       'CC-004', 4),
    ('105', 'Pharmacy Store — Drug Sale',      'PHARMACY',  'CC-001', 5),
    ('106', 'Optical Store — Frame / Lens',    'OPTICAL',   'CC-005', 6),
    ('107', 'Theatre — Surgical Procedure',    'SURGICAL',  'CC-002', 7),
    ('108', 'IPD Ward — Inpatient Admission',  'ADMISSION', 'CC-006', 8),
    ('109', 'Registration Fee',                'REG',       'CC-008', 9),
    ('110', 'Other Revenue',                   'OTHER',     'CC-008', 10),
]

EXPENSE_SEED = [
    ('201', 'Medical Supplies Purchase',        'SUPPLIES',  'CC-008', 1),
    ('202', 'Utilities (Electricity / Water)',  'UTILITIES', 'CC-008', 2),
    ('203', 'Salaries & Staff Costs',           'SALARY',    'CC-008', 3),
    ('204', 'Rent & Facilities',                'RENT',      'CC-008', 4),
    ('205', 'Equipment & Maintenance',          'EQUIPMENT', 'CC-012', 5),
    ('206', 'Pharmacy Store — Drug Purchase',   'DRUGS',     'CC-001', 6),
    ('207', 'Transport & Logistics',            'TRANSPORT', 'CC-008', 7),
    ('208', 'Administrative Expenses',          'ADMIN',     'CC-008', 8),
    ('209', 'Marketing & Outreach',             'MARKETING', 'CC-008', 9),
    ('210', 'Other Expenses',                   'EXP_OTHER', 'CC-008', 10),
]


def reseed(apps, schema_editor):
    BillingOperationCC = apps.get_model('billing', 'BillingOperationCC')
    CostCenter         = apps.get_model('billing', 'CostCenter')

    # Clear stale rows from 0046's incorrect table
    BillingOperationCC.objects.all().delete()

    cc_map = {cc.code: cc for cc in CostCenter.objects.filter(is_active=True, is_deleted=False)}
    now = django.utils.timezone.now()

    for code, name, cat_key, cc_code, order in REVENUE_SEED:
        BillingOperationCC.objects.create(
            id=uuid.uuid4(),
            operation_code=code,
            operation_name=name,
            category_key=cat_key,
            group='REVENUE',
            cost_center=cc_map.get(cc_code),
            sort_order=order,
            created_at=now,
            updated_at=now,
            is_deleted=False,
            deletion_reason='',
        )

    for code, name, cat_key, cc_code, order in EXPENSE_SEED:
        BillingOperationCC.objects.create(
            id=uuid.uuid4(),
            operation_code=code,
            operation_name=name,
            category_key=cat_key,
            group='EXPENSE',
            cost_center=cc_map.get(cc_code),
            sort_order=order,
            created_at=now,
            updated_at=now,
            is_deleted=False,
            deletion_reason='',
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0046_billing_operation_cc'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Drop the incomplete table from 0046
        migrations.RunSQL(
            sql='DROP TABLE IF EXISTS billing_billingoperationcc CASCADE;',
            reverse_sql=migrations.RunSQL.noop,
        ),

        # Recreate with correct schema matching AuditModel
        migrations.CreateModel(
            name='BillingOperationCC',
            fields=[
                ('id',               models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('created_at',       models.DateTimeField(auto_now_add=True)),
                ('updated_at',       models.DateTimeField(auto_now=True)),
                ('is_deleted',       models.BooleanField(default=False)),
                ('deleted_at',       models.DateTimeField(blank=True, null=True)),
                ('deletion_reason',  models.TextField(blank=True, default='')),
                ('deleted_by',       models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('created_by',       models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('updated_by',       models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('operation_code',   models.CharField(max_length=20, unique=True, help_text='Short code shown in the UI, e.g. "101", "205"')),
                ('operation_name',   models.CharField(max_length=120)),
                ('category_key',     models.CharField(max_length=30)),
                ('group',            models.CharField(max_length=10, choices=[('REVENUE', 'Revenue Operation'), ('EXPENSE', 'Expense Operation')], default='REVENUE')),
                ('cost_center',      models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='operation_mappings', to='billing.costcenter')),
                ('sort_order',       models.PositiveSmallIntegerField(default=0)),
            ],
            options={
                'verbose_name':        'Billing Operation CC Mapping',
                'verbose_name_plural': 'Billing Operation CC Mappings',
                'ordering':            ['group', 'sort_order', 'operation_code'],
            },
        ),

        # Re-seed with correct UUIDs
        migrations.RunPython(reseed, reverse_code=noop),
    ]
