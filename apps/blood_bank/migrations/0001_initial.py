import django.db.models.deletion
import django.utils.timezone
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('patients', '0029_patientdocument'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── BloodDonor ────────────────────────────────────────────────────
        migrations.CreateModel(
            name='BloodDonor',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('donor_id', models.CharField(max_length=20, unique=True)),
                ('full_name', models.CharField(max_length=150)),
                ('blood_group', models.CharField(
                    choices=[('A+','A+'),('A-','A-'),('B+','B+'),('B-','B-'),
                             ('AB+','AB+'),('AB-','AB-'),('O+','O+'),('O-','O-')],
                    max_length=5,
                )),
                ('date_of_birth', models.DateField(blank=True, null=True)),
                ('gender', models.CharField(blank=True, choices=[('M','Male'),('F','Female')], max_length=1)),
                ('phone', models.CharField(blank=True, max_length=20)),
                ('address', models.TextField(blank=True)),
                ('category', models.CharField(
                    choices=[('VOLUNTARY','Voluntary / Community'),('REPLACEMENT','Replacement (Family / Friend)'),
                             ('AUTOLOGOUS','Autologous (Patient Pre-deposit)'),('DIRECTED','Directed Donation')],
                    default='VOLUNTARY', max_length=15,
                )),
                ('patient', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='blood_donations',
                    to='patients.patient',
                )),
                ('last_donation', models.DateField(blank=True, null=True)),
                ('total_donations', models.PositiveIntegerField(default=0)),
                ('is_deferred', models.BooleanField(default=False)),
                ('deferral_reason', models.TextField(blank=True)),
                ('deferral_until', models.DateField(blank=True, null=True)),
                ('notes', models.TextField(blank=True)),
            ],
            options={'ordering': ['full_name'], 'verbose_name': 'Blood Donor'},
        ),

        # ── BloodUnit ─────────────────────────────────────────────────────
        migrations.CreateModel(
            name='BloodUnit',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('created_by', models.ForeignKey(blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL, related_name='+',
                    to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL, related_name='+',
                    to=settings.AUTH_USER_MODEL)),
                ('unit_number', models.CharField(max_length=30, unique=True)),
                ('product', models.CharField(
                    choices=[('WHOLE','Whole Blood'),('PRBC','Packed Red Blood Cells (pRBC)'),
                             ('FFP','Fresh Frozen Plasma (FFP)'),('PLT','Platelets'),
                             ('CRYO','Cryoprecipitate'),('ALB','Albumin')],
                    default='WHOLE', max_length=10,
                )),
                ('blood_group', models.CharField(
                    choices=[('A+','A+'),('A-','A-'),('B+','B+'),('B-','B-'),
                             ('AB+','AB+'),('AB-','AB-'),('O+','O+'),('O-','O-')],
                    max_length=5,
                )),
                ('volume_ml', models.PositiveIntegerField(default=450)),
                ('donor', models.ForeignKey(blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='donated_units', to='blood_bank.blooddonor')),
                ('collection_date', models.DateField(default=django.utils.timezone.localdate)),
                ('expiry_date', models.DateField()),
                ('status', models.CharField(
                    choices=[('AVAILABLE','Available'),('RESERVED','Reserved (Cross-matched)'),
                             ('ISSUED','Issued to Patient'),('EXPIRED','Expired'),
                             ('DISCARDED','Discarded / Wastage')],
                    default='AVAILABLE', max_length=15,
                )),
                ('storage_location', models.CharField(blank=True, max_length=60)),
                ('hiv_tested', models.BooleanField(default=False)),
                ('hbsag_tested', models.BooleanField(default=False)),
                ('hcv_tested', models.BooleanField(default=False)),
                ('syphilis_tested', models.BooleanField(default=False)),
                ('malaria_tested', models.BooleanField(default=False)),
                ('all_negative', models.BooleanField(default=False)),
                ('discarded_reason', models.TextField(blank=True)),
                ('notes', models.TextField(blank=True)),
            ],
            options={'ordering': ['expiry_date'], 'verbose_name': 'Blood Unit'},
        ),

        # ── CrossMatch ────────────────────────────────────────────────────
        migrations.CreateModel(
            name='CrossMatch',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('created_by', models.ForeignKey(blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL, related_name='+',
                    to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL, related_name='+',
                    to=settings.AUTH_USER_MODEL)),
                ('patient', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                    related_name='cross_matches', to='patients.patient')),
                ('blood_unit', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                    related_name='cross_matches', to='blood_bank.bloodunit')),
                ('visit', models.ForeignKey(blank=True, null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='cross_matches', to='patients.visit')),
                ('requested_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                    related_name='cross_match_requests', to=settings.AUTH_USER_MODEL)),
                ('performed_by', models.ForeignKey(blank=True, null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='cross_match_results', to=settings.AUTH_USER_MODEL)),
                ('requested_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('result', models.CharField(
                    choices=[('COMPATIBLE','Compatible'),('INCOMPATIBLE','Incompatible'),('PENDING','Pending')],
                    default='PENDING', max_length=15,
                )),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('notes', models.TextField(blank=True)),
            ],
            options={'ordering': ['-requested_at'], 'verbose_name': 'Cross-Match'},
        ),

        # ── BloodIssue ────────────────────────────────────────────────────
        migrations.CreateModel(
            name='BloodIssue',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('created_by', models.ForeignKey(blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL, related_name='+',
                    to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL, related_name='+',
                    to=settings.AUTH_USER_MODEL)),
                ('issue_number', models.CharField(max_length=30, unique=True)),
                ('blood_unit', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                    related_name='issues', to='blood_bank.bloodunit')),
                ('patient', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                    related_name='blood_issues', to='patients.patient')),
                ('visit', models.ForeignKey(blank=True, null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='blood_issues', to='patients.visit')),
                ('cross_match', models.ForeignKey(blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='issues', to='blood_bank.crossmatch')),
                ('issued_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                    related_name='blood_issued', to=settings.AUTH_USER_MODEL)),
                ('received_by', models.CharField(blank=True, max_length=100)),
                ('issued_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('status', models.CharField(
                    choices=[('ISSUED','Issued — In Progress'),('TRANSFUSED','Transfused'),
                             ('RETURNED','Returned Unused'),('REACTION','Transfusion Reaction')],
                    default='ISSUED', max_length=15,
                )),
                ('transfused_at', models.DateTimeField(blank=True, null=True)),
                ('volume_transfused_ml', models.PositiveIntegerField(blank=True, null=True)),
                ('reaction_description', models.TextField(blank=True)),
                ('notes', models.TextField(blank=True)),
            ],
            options={'ordering': ['-issued_at'], 'verbose_name': 'Blood Issue'},
        ),
    ]
