"""
Migration 0046 — BillingOperationCC table + seed data

Creates the configurable operation → cost center mapping table and seeds
it with the same rows that were previously hardcoded in gl_service.py.

Revenue operations: codes 101–110 (ServiceCategory)
Expense operations: codes 201–210 (ExpenseCategory)
"""

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


# ── Seed helper ───────────────────────────────────────────────────────────────

REVENUE_SEED = [
    # (operation_code, operation_name, category_key, cc_code, sort_order)
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
    ('201', 'Medical Supplies Purchase',       'SUPPLIES',  'CC-008', 1),
    ('202', 'Utilities (Electricity / Water)', 'UTILITIES', 'CC-008', 2),
    ('203', 'Salaries & Staff Costs',          'SALARY',    'CC-008', 3),
    ('204', 'Rent & Facilities',               'RENT',      'CC-008', 4),
    ('205', 'Equipment & Maintenance',         'EQUIPMENT', 'CC-012', 5),
    ('206', 'Pharmacy Store — Drug Purchase',  'DRUGS',     'CC-001', 6),
    ('207', 'Transport & Logistics',           'TRANSPORT', 'CC-008', 7),
    ('208', 'Administrative Expenses',         'ADMIN',     'CC-008', 8),
    ('209', 'Marketing & Outreach',            'MARKETING', 'CC-008', 9),
    ('210', 'Other Expenses',                  'EXP_OTHER', 'CC-008', 10),
]


def seed_operation_cc(apps, schema_editor):
    BillingOperationCC = apps.get_model('billing', 'BillingOperationCC')
    CostCenter         = apps.get_model('billing', 'CostCenter')

    cc_map = {cc.code: cc for cc in CostCenter.objects.filter(is_active=True, is_deleted=False)}

    now = django.utils.timezone.now()

    for code, name, cat_key, cc_code, order in REVENUE_SEED:
        BillingOperationCC.objects.get_or_create(
            operation_code=code,
            defaults=dict(
                operation_name=name,
                category_key=cat_key,
                group='REVENUE',
                cost_center=cc_map.get(cc_code),
                sort_order=order,
                created_at=now,
                updated_at=now,
                is_deleted=False,
            ),
        )

    for code, name, cat_key, cc_code, order in EXPENSE_SEED:
        BillingOperationCC.objects.get_or_create(
            operation_code=code,
            defaults=dict(
                operation_name=name,
                category_key=cat_key,
                group='EXPENSE',
                cost_center=cc_map.get(cc_code),
                sort_order=order,
                created_at=now,
                updated_at=now,
                is_deleted=False,
            ),
        )


def unseed_operation_cc(apps, schema_editor):
    # Reverse: nothing to do — drop table handles it
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0045_apbill_grn_link_3way_match'),
    ]

    operations = [
        migrations.CreateModel(
            name='BillingOperationCC',
            fields=[
                ('id',             models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at',     models.DateTimeField(auto_now_add=True)),
                ('updated_at',     models.DateTimeField(auto_now=True)),
                ('is_deleted',     models.BooleanField(default=False)),
                ('deleted_at',     models.DateTimeField(blank=True, null=True)),
                ('operation_code', models.CharField(max_length=20, unique=True, help_text='Short code shown in the UI, e.g. "101", "205"')),
                ('operation_name', models.CharField(max_length=120)),
                ('category_key',   models.CharField(max_length=30, help_text='Internal category code matched by gl_service')),
                ('group',          models.CharField(max_length=10, choices=[('REVENUE', 'Revenue Operation'), ('EXPENSE', 'Expense Operation')], default='REVENUE')),
                ('cost_center',    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='operation_mappings', to='billing.costcenter')),
                ('sort_order',     models.PositiveSmallIntegerField(default=0)),
            ],
            options={
                'verbose_name':        'Billing Operation CC Mapping',
                'verbose_name_plural': 'Billing Operation CC Mappings',
                'ordering':            ['group', 'sort_order', 'operation_code'],
            },
        ),
        migrations.RunPython(seed_operation_cc, reverse_code=unseed_operation_cc),
    ]
