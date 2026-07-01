import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0007_workorder_missing_fields'),
        ('patients', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── 1. CorporateAccount ──────────────────────────────────────────────
        migrations.CreateModel(
            name='CorporateAccount',
            fields=[
                ('id', models.UUIDField(primary_key=True, serialize=False, editable=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('name', models.CharField(max_length=200, unique=True)),
                ('account_code', models.CharField(blank=True, max_length=30, null=True, unique=True)),
                ('contact_name', models.CharField(blank=True, max_length=150)),
                ('phone', models.CharField(blank=True, max_length=20)),
                ('email', models.EmailField(blank=True)),
                ('address', models.TextField(blank=True)),
                ('credit_limit', models.DecimalField(decimal_places=2, default=0, help_text='Max outstanding balance in FCFA (0 = no limit)', max_digits=14)),
                ('payment_terms_days', models.PositiveSmallIntegerField(default=30, help_text='Net payment days')),
                ('discount_pct', models.DecimalField(decimal_places=2, default=0, help_text='Flat discount % applied to all invoices', max_digits=5)),
                ('is_active', models.BooleanField(default=True)),
                ('notes', models.TextField(blank=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['name'], 'verbose_name': 'Corporate Account', 'verbose_name_plural': 'Corporate Accounts'},
        ),

        # ── 2. CorporateAccountMember ────────────────────────────────────────
        migrations.CreateModel(
            name='CorporateAccountMember',
            fields=[
                ('id', models.UUIDField(primary_key=True, serialize=False, editable=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('employee_id', models.CharField(blank=True, max_length=50)),
                ('coverage_limit', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('is_active', models.BooleanField(default=True)),
                ('corporate_account', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='members', to='billing.corporateaccount')),
                ('patient', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='corporate_memberships', to='patients.patient')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={'verbose_name': 'Corporate Account Member', 'unique_together': {('corporate_account', 'patient')}},
        ),

        # ── 3. Expense ───────────────────────────────────────────────────────
        migrations.CreateModel(
            name='Expense',
            fields=[
                ('id', models.UUIDField(primary_key=True, serialize=False, editable=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('date', models.DateField(default=django.utils.timezone.localdate)),
                ('category', models.CharField(choices=[('SUPPLIES', 'Medical Supplies'), ('UTILITIES', 'Utilities (Electricity / Water)'), ('SALARY', 'Salaries & Staff Costs'), ('RENT', 'Rent & Facilities'), ('EQUIPMENT', 'Equipment & Maintenance'), ('DRUGS', 'Drug / Pharmacy Stock'), ('TRANSPORT', 'Transport & Logistics'), ('ADMIN', 'Administrative'), ('MARKETING', 'Marketing & Outreach'), ('EXP_OTHER', 'Other')], max_length=20)),
                ('description', models.CharField(max_length=300)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('payment_method', models.CharField(choices=[('CASH', 'Cash'), ('CARD', 'POS / Card'), ('TRANSFER', 'Bank Transfer'), ('MOBILE', 'Mobile Money'), ('INSURANCE', 'Insurance'), ('NHIS', 'NHIS'), ('WAIVER', 'Waiver')], default='CASH', max_length=20)),
                ('vendor', models.CharField(blank=True, max_length=200)),
                ('reference', models.CharField(blank=True, max_length=100)),
                ('department', models.CharField(blank=True, max_length=100)),
                ('notes', models.TextField(blank=True)),
                ('approved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='approved_expenses', to=settings.AUTH_USER_MODEL)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-date', '-created_at'], 'verbose_name': 'Expense'},
        ),

        # ── 4. PettyCashFund ─────────────────────────────────────────────────
        migrations.CreateModel(
            name='PettyCashFund',
            fields=[
                ('id', models.UUIDField(primary_key=True, serialize=False, editable=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('name', models.CharField(max_length=100)),
                ('opening_balance', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('is_active', models.BooleanField(default=True)),
                ('custodian', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='petty_cash_funds', to=settings.AUTH_USER_MODEL)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['name'], 'verbose_name': 'Petty Cash Fund'},
        ),

        # ── 5. PettyCashEntry ────────────────────────────────────────────────
        migrations.CreateModel(
            name='PettyCashEntry',
            fields=[
                ('id', models.UUIDField(primary_key=True, serialize=False, editable=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('entry_type', models.CharField(choices=[('DEBIT', 'Payment / Expense'), ('CREDIT', 'Top-up / Replenishment')], max_length=10)),
                ('date', models.DateField(default=django.utils.timezone.localdate)),
                ('description', models.CharField(max_length=300)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('category', models.CharField(blank=True, choices=[('SUPPLIES', 'Medical Supplies'), ('UTILITIES', 'Utilities (Electricity / Water)'), ('SALARY', 'Salaries & Staff Costs'), ('RENT', 'Rent & Facilities'), ('EQUIPMENT', 'Equipment & Maintenance'), ('DRUGS', 'Drug / Pharmacy Stock'), ('TRANSPORT', 'Transport & Logistics'), ('ADMIN', 'Administrative'), ('MARKETING', 'Marketing & Outreach'), ('EXP_OTHER', 'Other')], max_length=20)),
                ('reference', models.CharField(blank=True, max_length=100)),
                ('fund', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='entries', to='billing.pettycashfund')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-date', '-created_at'], 'verbose_name': 'Petty Cash Entry'},
        ),

        # ── 6. Add corporate_account FK to Invoice ───────────────────────────
        migrations.AddField(
            model_name='invoice',
            name='corporate_account',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='invoices',
                to='billing.corporateaccount',
                help_text='Set when this invoice is billed to a corporate/insurer account',
            ),
        ),
    ]
