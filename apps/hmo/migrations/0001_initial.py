import django.db.models.deletion
import django.utils.timezone
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('patients', '0029_patientdocument'),
        ('billing', '0020_fix_audit_updated_by'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── InsuranceScheme ───────────────────────────────────────────────
        migrations.CreateModel(
            name='InsuranceScheme',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('name', models.CharField(max_length=200, unique=True)),
                ('code', models.CharField(help_text='Short internal code e.g. CNPS01', max_length=20, unique=True)),
                ('scheme_type', models.CharField(
                    choices=[
                        ('CNPS', 'CNPS (National Social Insurance)'),
                        ('MUTUAL', 'Mutual de Santé'),
                        ('CORPORATE', 'Corporate / Employer Scheme'),
                        ('NHIS', 'NHIS'),
                        ('OTHER', 'Other'),
                    ],
                    default='OTHER',
                    max_length=20,
                )),
                ('coverage_pct', models.DecimalField(decimal_places=2, default=80, max_digits=5)),
                ('pre_auth_required', models.BooleanField(default=False)),
                ('max_annual_claim', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('contact_phone', models.CharField(blank=True, max_length=30)),
                ('contact_email', models.EmailField(blank=True)),
                ('address', models.TextField(blank=True)),
                ('notes', models.TextField(blank=True)),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={
                'verbose_name': 'Insurance Scheme',
                'verbose_name_plural': 'Insurance Schemes',
                'ordering': ['name'],
            },
        ),

        # ── InsuredMember ─────────────────────────────────────────────────
        migrations.CreateModel(
            name='InsuredMember',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('member_number', models.CharField(max_length=60)),
                ('group_number', models.CharField(blank=True, max_length=60)),
                ('card_expiry', models.DateField(blank=True, null=True)),
                ('copay_pct', models.DecimalField(decimal_places=2, default=20, max_digits=5)),
                ('is_primary', models.BooleanField(default=True)),
                ('is_active', models.BooleanField(default=True)),
                ('enrolled_date', models.DateField(default=django.utils.timezone.localdate)),
                ('notes', models.TextField(blank=True)),
                ('patient', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='insurance_memberships',
                    to='patients.patient',
                )),
                ('scheme', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='members',
                    to='hmo.insurancescheme',
                )),
                ('dependant_of', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='dependants',
                    to='hmo.insuredmember',
                )),
            ],
            options={
                'verbose_name': 'Insured Member',
                'verbose_name_plural': 'Insured Members',
                'ordering': ['patient__last_name', 'patient__first_name'],
                'unique_together': {('patient', 'scheme')},
            },
        ),

        # ── PreAuthorization ──────────────────────────────────────────────
        migrations.CreateModel(
            name='PreAuthorization',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('created_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('updated_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('member', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='pre_auths',
                    to='hmo.insuredmember',
                )),
                ('visit', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='pre_auths',
                    to='patients.visit',
                )),
                ('service_description', models.TextField()),
                ('estimated_cost', models.DecimalField(decimal_places=2, max_digits=12)),
                ('status', models.CharField(
                    choices=[
                        ('PENDING', 'Pending Scheme Response'),
                        ('APPROVED', 'Approved'),
                        ('REJECTED', 'Rejected by Scheme'),
                        ('EXPIRED', 'Expired'),
                        ('WAIVED', 'Pre-auth Waived (Emergency)'),
                    ],
                    default='PENDING',
                    max_length=20,
                )),
                ('auth_code', models.CharField(blank=True, max_length=60)),
                ('requested_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('responded_at', models.DateTimeField(blank=True, null=True)),
                ('valid_until', models.DateField(blank=True, null=True)),
                ('rejection_reason', models.TextField(blank=True)),
                ('notes', models.TextField(blank=True)),
            ],
            options={
                'verbose_name': 'Pre-Authorisation',
                'verbose_name_plural': 'Pre-Authorisations',
                'ordering': ['-requested_at'],
            },
        ),

        # ── ClaimBatch ────────────────────────────────────────────────────
        migrations.CreateModel(
            name='ClaimBatch',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('created_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('updated_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('batch_number', models.CharField(max_length=30, unique=True)),
                ('scheme', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='claim_batches',
                    to='hmo.insurancescheme',
                )),
                ('submitted_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='claim_batches_submitted',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('submission_date', models.DateField(blank=True, null=True)),
                ('status', models.CharField(
                    choices=[
                        ('DRAFT', 'Draft — Building'),
                        ('SUBMITTED', 'Submitted to Scheme'),
                        ('PROCESSING', 'Scheme Processing'),
                        ('PAID', 'Paid in Full'),
                        ('PARTIAL', 'Partially Paid'),
                        ('REJECTED', 'Rejected by Scheme'),
                    ],
                    default='DRAFT',
                    max_length=20,
                )),
                ('total_claimed', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('total_approved', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('total_paid', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('payment_date', models.DateField(blank=True, null=True)),
                ('payment_ref', models.CharField(blank=True, max_length=100)),
                ('notes', models.TextField(blank=True)),
            ],
            options={
                'verbose_name': 'Claim Batch',
                'verbose_name_plural': 'Claim Batches',
                'ordering': ['-submission_date', '-created_at'],
            },
        ),

        # ── Claim ─────────────────────────────────────────────────────────
        migrations.CreateModel(
            name='Claim',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('created_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('updated_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('claim_number', models.CharField(max_length=30, unique=True)),
                ('batch', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='claims',
                    to='hmo.claimbatch',
                )),
                ('member', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='claims',
                    to='hmo.insuredmember',
                )),
                ('visit', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='insurance_claims',
                    to='patients.visit',
                )),
                ('invoice', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='insurance_claims',
                    to='billing.invoice',
                )),
                ('pre_auth', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='claims',
                    to='hmo.preauthorization',
                )),
                ('status', models.CharField(
                    choices=[
                        ('DRAFT', 'Draft'),
                        ('SUBMITTED', 'Submitted'),
                        ('APPROVED', 'Approved'),
                        ('REJECTED', 'Rejected'),
                        ('PARTIAL', 'Partially Approved'),
                        ('PAID', 'Paid'),
                    ],
                    default='DRAFT',
                    max_length=20,
                )),
                ('service_date', models.DateField(default=django.utils.timezone.localdate)),
                ('claimed_amount', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('approved_amount', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('paid_amount', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('patient_copay', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('rejection_reason', models.TextField(blank=True)),
                ('rejection_date', models.DateField(blank=True, null=True)),
                ('notes', models.TextField(blank=True)),
            ],
            options={
                'verbose_name': 'Claim',
                'verbose_name_plural': 'Claims',
                'ordering': ['-service_date', '-created_at'],
            },
        ),

        # ── ClaimItem ─────────────────────────────────────────────────────
        migrations.CreateModel(
            name='ClaimItem',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('claim', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='items',
                    to='hmo.claim',
                )),
                ('service_name', models.CharField(max_length=200)),
                ('quantity', models.PositiveIntegerField(default=1)),
                ('unit_price', models.DecimalField(decimal_places=2, max_digits=10)),
                ('claimed_amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('approved_amount', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('rejection_reason', models.CharField(blank=True, max_length=300)),
            ],
            options={
                'ordering': ['service_name'],
            },
        ),
    ]
