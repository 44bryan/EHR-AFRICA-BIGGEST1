"""
Migration 0018 — Advanced Tier-Scoped Cashier Desk Module

Adds:
  - CashDesk
  - DeskReceiptSequence
  - CashierSession
  - DiscountApproval
  - InvoiceTierChange

Extends:
  - Invoice: service_tier, routing_type, cash_desk FK
  - Payment: cashier_session FK
"""
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0017_serviceworkorder_lab_order_item'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── CashDesk ──────────────────────────────────────────────────────────
        migrations.CreateModel(
            name='CashDesk',
            fields=[
                ('id', models.UUIDField(primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False, db_index=True)),
                ('created_by', models.ForeignKey(
                    null=True, blank=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('name', models.CharField(max_length=100)),
                ('desk_type', models.CharField(
                    choices=[
                        ('TIER', 'Tier Desk (Standard / Fast Track / VIP)'),
                        ('PHARMACY', 'Pharmacy Desk'),
                        ('OPTICAL', 'Optical Desk'),
                        ('INSURANCE', 'Insurance / HMO Desk'),
                    ],
                    default='TIER',
                    max_length=20,
                )),
                ('tier', models.CharField(blank=True, default='', max_length=20)),
                ('location', models.CharField(blank=True, max_length=200)),
                ('receipt_prefix', models.CharField(default='RCT', max_length=10)),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={
                'verbose_name': 'Cash Desk',
                'verbose_name_plural': 'Cash Desks',
                'ordering': ['desk_type', 'name'],
            },
        ),

        # ── DeskReceiptSequence ───────────────────────────────────────────────
        migrations.CreateModel(
            name='DeskReceiptSequence',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('desk', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='receipt_sequences',
                    to='billing.cashdesk',
                )),
                ('sequence_date', models.DateField(default=django.utils.timezone.localdate)),
                ('last_number', models.PositiveIntegerField(default=0)),
            ],
            options={
                'verbose_name': 'Desk Receipt Sequence',
                'unique_together': {('desk', 'sequence_date')},
            },
        ),

        # ── CashierSession ────────────────────────────────────────────────────
        migrations.CreateModel(
            name='CashierSession',
            fields=[
                ('id', models.UUIDField(primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False, db_index=True)),
                ('created_by', models.ForeignKey(
                    null=True, blank=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('cashier', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='cashier_sessions',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('cash_desk', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='sessions',
                    to='billing.cashdesk',
                )),
                ('opened_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('closed_at', models.DateTimeField(blank=True, null=True)),
                ('opening_float', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('closing_declared_cash', models.DecimalField(
                    blank=True, decimal_places=2, max_digits=12, null=True,
                )),
                ('status', models.CharField(
                    choices=[
                        ('OPEN', 'Open'),
                        ('CLOSED', 'Closed'),
                        ('VERIFIED', 'Verified'),
                    ],
                    default='OPEN',
                    max_length=20,
                )),
                ('variance_flag', models.BooleanField(default=False)),
                ('variance_notes', models.CharField(blank=True, max_length=300)),
                ('verified_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='verified_cashier_sessions',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('verified_at', models.DateTimeField(blank=True, null=True)),
                ('notes', models.TextField(blank=True)),
            ],
            options={
                'verbose_name': 'Cashier Session',
                'verbose_name_plural': 'Cashier Sessions',
                'ordering': ['-opened_at'],
            },
        ),

        # ── DiscountApproval ──────────────────────────────────────────────────
        migrations.CreateModel(
            name='DiscountApproval',
            fields=[
                ('id', models.UUIDField(primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False, db_index=True)),
                ('created_by', models.ForeignKey(
                    null=True, blank=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('invoice', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='discount_approvals',
                    to='billing.invoice',
                )),
                ('requested_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='discount_requests',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('approved_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='approved_discounts',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('requested_amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('approved_amount', models.DecimalField(
                    blank=True, decimal_places=2, max_digits=10, null=True,
                )),
                ('reason', models.CharField(max_length=300)),
                ('status', models.CharField(
                    choices=[
                        ('PENDING', 'Pending Supervisor Review'),
                        ('APPROVED', 'Approved'),
                        ('REJECTED', 'Rejected'),
                    ],
                    default='PENDING',
                    max_length=20,
                )),
                ('decision_at', models.DateTimeField(blank=True, null=True)),
                ('decision_notes', models.CharField(blank=True, max_length=300)),
            ],
            options={
                'verbose_name': 'Discount Approval',
                'verbose_name_plural': 'Discount Approvals',
                'ordering': ['-created_at'],
            },
        ),

        # ── InvoiceTierChange ─────────────────────────────────────────────────
        migrations.CreateModel(
            name='InvoiceTierChange',
            fields=[
                ('id', models.UUIDField(primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False, db_index=True)),
                ('created_by', models.ForeignKey(
                    null=True, blank=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('invoice', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='tier_changes',
                    to='billing.invoice',
                )),
                ('old_tier', models.CharField(max_length=20)),
                ('new_tier', models.CharField(max_length=20)),
                ('old_desk', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='outgoing_tier_changes',
                    to='billing.cashdesk',
                )),
                ('new_desk', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='incoming_tier_changes',
                    to='billing.cashdesk',
                )),
                ('changed_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='invoice_tier_changes',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('reason', models.CharField(max_length=300)),
            ],
            options={
                'verbose_name': 'Invoice Tier Change',
                'verbose_name_plural': 'Invoice Tier Changes',
                'ordering': ['-created_at'],
            },
        ),

        # ── Extend Invoice ────────────────────────────────────────────────────
        migrations.AddField(
            model_name='invoice',
            name='service_tier',
            field=models.CharField(
                blank=True, default='', max_length=20,
                help_text='Patient service tier at time of billing',
            ),
        ),
        migrations.AddField(
            model_name='invoice',
            name='routing_type',
            field=models.CharField(
                blank=True, default='', max_length=20,
                choices=[
                    ('TIER', 'Tier (Main Cashier)'),
                    ('PHARMACY', 'Pharmacy'),
                    ('OPTICAL', 'Optical'),
                    ('INSURANCE', 'Insurance / HMO'),
                ],
                help_text='Which desk type handles this invoice',
            ),
        ),
        migrations.AddField(
            model_name='invoice',
            name='cash_desk',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='invoices',
                to='billing.cashdesk',
                help_text='The cash desk that processed this invoice',
            ),
        ),

        # ── Extend Payment ────────────────────────────────────────────────────
        migrations.AddField(
            model_name='payment',
            name='cashier_session',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='payments',
                to='billing.cashiersession',
                help_text='The cashier desk session during which this payment was collected',
            ),
        ),
    ]
