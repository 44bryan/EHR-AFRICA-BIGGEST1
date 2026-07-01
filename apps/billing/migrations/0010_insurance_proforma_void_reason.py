"""
Migration 0010 — Financial module enhancements:
  1. InvoiceVoidReason — configurable reason codes for cancel/reverse
  2. Invoice.insurance_amount — insurer share per invoice
  3. Invoice.void_reason FK — links cancelled invoice to a reason
  4. Proforma + ProformaItem — pre-billing estimate model
"""
import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


_VOID_REASONS = [
    ('001', 'Declination by Patient',    False),
    ('002', 'Billing Error / Wrong Item', False),
    ('003', 'Duplicate Invoice',          False),
    ('004', 'Service Not Rendered',       False),
    ('005', 'Insurance Pre-Auth Denied',  True),
    ('006', 'Management Waiver',          True),
    ('007', 'Other (specify in notes)',   False),
]


def _seed_void_reasons(apps, schema_editor):
    InvoiceVoidReason = apps.get_model('billing', 'InvoiceVoidReason')
    for code, label, req_super in _VOID_REASONS:
        InvoiceVoidReason.objects.get_or_create(
            code=code,
            defaults={
                'id': uuid.uuid4(),
                'label': label,
                'requires_supervisor': req_super,
                'is_active': True,
                'is_deleted': False,
            }
        )


def _unseed_void_reasons(apps, schema_editor):
    InvoiceVoidReason = apps.get_model('billing', 'InvoiceVoidReason')
    InvoiceVoidReason.objects.filter(code__in=[r[0] for r in _VOID_REASONS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0009_add_budget_model'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('patients', '0016_add_patient_problem_list'),
    ]

    operations = [

        # ── 1. InvoiceVoidReason ─────────────────────────────────────────────
        migrations.CreateModel(
            name='InvoiceVoidReason',
            fields=[
                ('id', models.UUIDField(primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('created_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+', to=settings.AUTH_USER_MODEL
                )),
                ('code',  models.CharField(max_length=10, unique=True)),
                ('label', models.CharField(max_length=200)),
                ('requires_supervisor', models.BooleanField(default=False)),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={'ordering': ['code'], 'verbose_name': 'Invoice Void Reason',
                     'verbose_name_plural': 'Invoice Void Reasons'},
        ),

        # ── 2. Invoice.insurance_amount ──────────────────────────────────────
        migrations.AddField(
            model_name='invoice',
            name='insurance_amount',
            field=models.DecimalField(
                decimal_places=2, default=0, max_digits=10,
                help_text='Amount the insurer is expected to cover (set at billing time)'
            ),
        ),

        # ── 3. Invoice.void_reason ───────────────────────────────────────────
        migrations.AddField(
            model_name='invoice',
            name='void_reason',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='voided_invoices',
                to='billing.invoicevoidreason',
                help_text='Required when cancelling or reversing an invoice'
            ),
        ),

        # ── 4. Seed default void reasons (cross-DB safe) ─────────────────────
        migrations.RunPython(_seed_void_reasons, _unseed_void_reasons),

        # ── 5. Proforma ──────────────────────────────────────────────────────
        migrations.CreateModel(
            name='Proforma',
            fields=[
                ('id', models.UUIDField(primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('created_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+', to=settings.AUTH_USER_MODEL
                )),
                ('proforma_number', models.CharField(max_length=30, unique=True)),
                ('patient', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='proformas', to='patients.patient'
                )),
                ('issued_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='issued_proformas', to=settings.AUTH_USER_MODEL
                )),
                ('status', models.CharField(
                    choices=[('DRAFT','Draft'),('ISSUED','Issued to Patient'),
                             ('CONVERTED','Converted to Invoice'),('CANCELLED','Cancelled / Expired')],
                    default='DRAFT', max_length=15
                )),
                ('issue_date',  models.DateField(default=django.utils.timezone.localdate)),
                ('valid_days',  models.PositiveSmallIntegerField(default=3)),
                ('insurance_amount', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('invoice', models.OneToOneField(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='proforma', to='billing.invoice'
                )),
                ('notes', models.TextField(blank=True)),
            ],
            options={'ordering': ['-created_at'], 'verbose_name': 'Proforma Invoice',
                     'verbose_name_plural': 'Proforma Invoices'},
        ),

        # ── 6. ProformaItem ──────────────────────────────────────────────────
        migrations.CreateModel(
            name='ProformaItem',
            fields=[
                ('id', models.UUIDField(primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('created_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+', to=settings.AUTH_USER_MODEL
                )),
                ('proforma', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='items', to='billing.proforma'
                )),
                ('category',    models.CharField(max_length=20)),
                ('description', models.CharField(max_length=255)),
                ('quantity',    models.PositiveSmallIntegerField(default=1)),
                ('unit_price',  models.DecimalField(decimal_places=2, max_digits=10)),
            ],
            options={'ordering': ['created_at']},
        ),
    ]
