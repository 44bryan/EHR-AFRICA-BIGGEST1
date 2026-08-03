"""
Migration: advanced outreach module
- OutreachPatient (individual patients at camps)
- OutreachExamination (ophthalmology exam per patient)
- OutreachReferral (referral ticket with unique code)
- OutreachSyncLog (sync audit trail)
- Enhancements to OutreachActivity (budget_fcfa, target_screened)
"""
import apps.outreach.models
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('outreach', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── OutreachActivity — add new fields ────────────────────────────────
        migrations.AddField(
            model_name='outreachactivity',
            name='budget_fcfa',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12,
                                      help_text='Total approved budget (FCFA)'),
        ),
        migrations.AddField(
            model_name='outreachactivity',
            name='target_screened',
            field=models.PositiveIntegerField(default=0,
                  help_text='Target number of people to screen'),
        ),

        # ── OutreachPatient ──────────────────────────────────────────────────
        migrations.CreateModel(
            name='OutreachPatient',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True,
                                        serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('outreach_patient_id', models.CharField(
                    default=apps.outreach.models._gen_patient_id,
                    editable=False, max_length=20, unique=True,
                    help_text='Auto-generated field ID e.g. OP-2026-00123')),
                ('first_name', models.CharField(max_length=100)),
                ('last_name', models.CharField(max_length=100)),
                ('date_of_birth', models.DateField(blank=True, null=True)),
                ('age_years', models.PositiveSmallIntegerField(blank=True, null=True,
                              help_text='Age in years if DOB unknown')),
                ('sex', models.CharField(choices=[('M', 'Male'), ('F', 'Female'),
                                                  ('U', 'Not Specified')],
                                         default='U', max_length=1)),
                ('village', models.CharField(blank=True, max_length=150)),
                ('district', models.CharField(blank=True, max_length=150)),
                ('phone', models.CharField(blank=True, max_length=20)),
                ('next_of_kin', models.CharField(blank=True, max_length=200)),
                ('known_diabetic', models.BooleanField(default=False)),
                ('known_hypertensive', models.BooleanField(default=False)),
                ('previous_eye_surgery', models.BooleanField(default=False)),
                ('chief_complaint', models.CharField(blank=True, max_length=300)),
                ('is_synced', models.BooleanField(default=False)),
                ('field_device_id', models.CharField(blank=True, max_length=100,
                                    help_text='Device that created this record')),
                ('activity', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='patients', to='outreach.outreachactivity')),
                ('hospital_patient', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='outreach_records', to='patients.patient')),
                ('registered_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='outreach_registered',
                    to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['last_name', 'first_name'],
                     'verbose_name': 'Outreach Patient'},
        ),

        # ── OutreachExamination ──────────────────────────────────────────────
        migrations.CreateModel(
            name='OutreachExamination',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True,
                                        serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('created_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+', to=settings.AUTH_USER_MODEL)),
                ('exam_date', models.DateField(default=django.utils.timezone.localdate)),
                # VA
                ('va_re_distance', models.CharField(blank=True, default='', max_length=10)),
                ('va_le_distance', models.CharField(blank=True, default='', max_length=10)),
                ('va_re_distance_ph', models.CharField(blank=True, default='', max_length=10)),
                ('va_le_distance_ph', models.CharField(blank=True, default='', max_length=10)),
                ('va_re_distance_corrected', models.CharField(blank=True, default='', max_length=10)),
                ('va_le_distance_corrected', models.CharField(blank=True, default='', max_length=10)),
                ('va_re_near', models.CharField(blank=True, default='', max_length=10)),
                ('va_le_near', models.CharField(blank=True, default='', max_length=10)),
                # Refraction
                ('re_sphere', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('re_cylinder', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('re_axis', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('le_sphere', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('le_cylinder', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('le_axis', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('add_power', models.DecimalField(blank=True, decimal_places=2, max_digits=4, null=True)),
                ('glasses_dispensed', models.BooleanField(default=False)),
                ('rx_frame_type', models.CharField(blank=True, max_length=100)),
                # IOP
                ('iop_re', models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True)),
                ('iop_le', models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True)),
                ('iop_method', models.CharField(blank=True, default='', max_length=20)),
                # Segments
                ('ant_segment_re', models.TextField(blank=True)),
                ('ant_segment_le', models.TextField(blank=True)),
                ('post_segment_re', models.TextField(blank=True)),
                ('post_segment_le', models.TextField(blank=True)),
                # Diagnoses
                ('diagnoses_re', models.CharField(blank=True, max_length=500)),
                ('diagnoses_le', models.CharField(blank=True, max_length=500)),
                # Interventions
                ('medications_given', models.TextField(blank=True)),
                ('surgery_performed', models.BooleanField(default=False)),
                ('surgery_type', models.CharField(blank=True, max_length=200)),
                # Referral
                ('needs_referral', models.BooleanField(default=False)),
                ('referral_urgency', models.CharField(blank=True, default='', max_length=20)),
                ('referral_reason', models.TextField(blank=True)),
                ('clinical_notes', models.TextField(blank=True)),
                # Relations
                ('patient', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='examination', to='outreach.outreachpatient')),
                ('examiner', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='outreach_examinations',
                    to=settings.AUTH_USER_MODEL)),
            ],
            options={'verbose_name': 'Outreach Examination'},
        ),

        # ── OutreachReferral ─────────────────────────────────────────────────
        migrations.CreateModel(
            name='OutreachReferral',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True,
                                        serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('referral_code', models.CharField(
                    default=apps.outreach.models._gen_referral_code,
                    editable=False, max_length=25, unique=True)),
                ('urgency', models.CharField(
                    choices=[('ROUTINE', 'Routine (within 1 month)'),
                              ('URGENT', 'Urgent (within 1 week)'),
                              ('EMERGENCY', 'Emergency (same day)')],
                    default='ROUTINE', max_length=20)),
                ('diagnosis', models.CharField(blank=True, max_length=300)),
                ('reason', models.TextField()),
                ('recommendations', models.TextField(blank=True)),
                ('status', models.CharField(
                    choices=[('PENDING', 'Pending — Not Yet Arrived'),
                              ('ARRIVED', 'Arrived at Hospital'),
                              ('IN_TREATMENT', 'Currently in Treatment'),
                              ('COMPLETED', 'Treatment Completed'),
                              ('DID_NOT_ATTEND', 'Did Not Attend'),
                              ('REFERRED_OUT', 'Referred to Another Facility')],
                    default='PENDING', max_length=20)),
                ('arrived_date', models.DateField(blank=True, null=True)),
                ('outcome_notes', models.TextField(blank=True)),
                ('is_synced', models.BooleanField(default=False)),
                ('patient', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='referral', to='outreach.outreachpatient')),
                ('referred_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='outreach_referrals',
                    to=settings.AUTH_USER_MODEL)),
                ('received_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='received_outreach_referrals',
                    to=settings.AUTH_USER_MODEL)),
                ('hospital_visit', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='outreach_referral',
                    to='patients.visit')),
            ],
            options={'ordering': ['-created_at'], 'verbose_name': 'Outreach Referral'},
        ),

        # ── OutreachSyncLog ──────────────────────────────────────────────────
        migrations.CreateModel(
            name='OutreachSyncLog',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True,
                                        serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('device_id', models.CharField(max_length=100)),
                ('device_label', models.CharField(blank=True, max_length=200)),
                ('sync_status', models.CharField(
                    choices=[('PENDING', 'Pending Sync'), ('SUCCESS', 'Synced Successfully'),
                              ('FAILED', 'Sync Failed'), ('PARTIAL', 'Partially Synced')],
                    default='PENDING', max_length=10)),
                ('activities_synced', models.PositiveIntegerField(default=0)),
                ('patients_synced', models.PositiveIntegerField(default=0)),
                ('examinations_synced', models.PositiveIntegerField(default=0)),
                ('referrals_synced', models.PositiveIntegerField(default=0)),
                ('records_synced', models.PositiveIntegerField(default=0)),
                ('error_log', models.TextField(blank=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('synced_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='outreach_syncs',
                    to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at'], 'verbose_name': 'Outreach Sync Log'},
        ),
    ]
