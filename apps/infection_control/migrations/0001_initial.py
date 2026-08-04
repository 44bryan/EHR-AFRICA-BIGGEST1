import django.db.models.deletion
import django.utils.timezone
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('patients', '0029_patientdocument'),
        ('ipd', '0007_vitalsigns_fluidbalance'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── HAIReport ─────────────────────────────────────────────────────
        migrations.CreateModel(
            name='HAIReport',
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
                ('report_number', models.CharField(max_length=20, unique=True)),
                ('patient', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                    related_name='hai_reports', to='patients.patient')),
                ('visit', models.ForeignKey(blank=True, null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='hai_reports', to='patients.visit')),
                ('admission', models.ForeignKey(blank=True, null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='hai_reports', to='ipd.admission')),
                ('hai_type', models.CharField(
                    choices=[
                        ('SSI','Surgical Site Infection (SSI)'),('UTI','Catheter-Associated UTI (CAUTI)'),
                        ('BSI','Central Line BSI (CLABSI)'),('VAP','Ventilator-Associated Pneumonia (VAP)'),
                        ('CDI','C. difficile Infection (CDI)'),('MRSA','MRSA Bacteraemia'),
                        ('SKIN','Pressure Ulcer / Skin Breakdown'),('OTHER','Other HAI'),
                    ],
                    max_length=10,
                )),
                ('organism', models.CharField(blank=True, max_length=100)),
                ('onset_date', models.DateField(default=django.utils.timezone.localdate)),
                ('status', models.CharField(
                    choices=[
                        ('REPORTED','Reported'),('INVESTIGATING','Under Investigation'),
                        ('RESOLVED','Resolved'),('CLOSED','Closed'),
                    ],
                    default='REPORTED', max_length=20,
                )),
                ('ward', models.ForeignKey(blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='hai_reports', to='ipd.ward')),
                ('clinical_details', models.TextField(blank=True)),
                ('root_cause', models.TextField(blank=True)),
                ('corrective_action', models.TextField(blank=True)),
                ('reported_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                    related_name='hai_reports_filed', to=settings.AUTH_USER_MODEL)),
                ('reviewed_by', models.ForeignKey(blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='hai_reports_reviewed', to=settings.AUTH_USER_MODEL)),
                ('resolved_date', models.DateField(blank=True, null=True)),
                ('notes', models.TextField(blank=True)),
            ],
            options={'ordering': ['-onset_date'], 'verbose_name': 'HAI Report'},
        ),

        # ── AntibioticSensitivity ─────────────────────────────────────────
        migrations.CreateModel(
            name='AntibioticSensitivity',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('patient', models.ForeignKey(blank=True, null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='sensitivity_records', to='patients.patient')),
                ('organism', models.CharField(max_length=100)),
                ('sample_type', models.CharField(blank=True, max_length=60)),
                ('collection_date', models.DateField(default=django.utils.timezone.localdate)),
                ('ward', models.ForeignKey(blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='sensitivity_records', to='ipd.ward')),
                *[
                    (abx, models.CharField(max_length=2,
                        choices=[('S','Sensitive (S)'),('I','Intermediate (I)'),('R','Resistant (R)'),('NT','Not Tested')],
                        default='NT'))
                    for abx in ['amoxicillin', 'ampicillin', 'ciprofloxacin', 'gentamicin',
                                'ceftriaxone', 'metronidazole', 'cotrimoxazole',
                                'erythromycin', 'tetracycline', 'meropenem']
                ],
                ('notes', models.TextField(blank=True)),
                ('recorded_by', models.ForeignKey(blank=True, null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='sensitivity_records_entered', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-collection_date'], 'verbose_name': 'Antibiotic Sensitivity'},
        ),

        # ── OutbreakAlert ─────────────────────────────────────────────────
        migrations.CreateModel(
            name='OutbreakAlert',
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
                ('title', models.CharField(max_length=200)),
                ('pathogen', models.CharField(blank=True, max_length=100)),
                ('alert_level', models.CharField(
                    choices=[('WATCH','Watch'),('WARNING','Warning'),('OUTBREAK','Outbreak'),('RESOLVED','Resolved')],
                    default='WATCH', max_length=10,
                )),
                ('affected_areas', models.CharField(blank=True, max_length=300)),
                ('onset_date', models.DateField(default=django.utils.timezone.localdate)),
                ('resolved_date', models.DateField(blank=True, null=True)),
                ('case_count', models.PositiveIntegerField(default=1)),
                ('description', models.TextField()),
                ('actions_taken', models.TextField(blank=True)),
                ('is_active', models.BooleanField(default=True)),
                ('issued_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                    related_name='outbreak_alerts_issued', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-onset_date'], 'verbose_name': 'Outbreak Alert'},
        ),
    ]
