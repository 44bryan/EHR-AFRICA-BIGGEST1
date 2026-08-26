"""
Migration 0005: Ophthalmic investigation workflow overhaul.
- New models: Device, DeviceDowntime, AcquisitionRecord, BiometryRecord,
  VisitInvestigationPlan, VisitInvestigationStep, ContrastReactionLog,
  InvestigationResultAmendment
- Enhanced InvestigationType with DICOM, dilation, laterality, quality fields
- Enhanced InvestigationOrder with 4 state machines
- Enhanced InvestigationResult with report workflow + acknowledgment
- Enhanced ImagingStudy with laterality
- Enhanced InvestigationFile with laterality + new file types
"""
import django.db.models.deletion
import django.utils.timezone
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('investigations', '0004_investigationtype_unit_price_investigationorder_location'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('patients', '0001_initial'),
        ('consultations', '0001_initial'),
    ]

    operations = [
        # ══════════════════════════════════════════════════════════════
        # NEW MODEL: Device
        # ══════════════════════════════════════════════════════════════
        migrations.CreateModel(
            name='Device',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                  related_name='+', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                  related_name='+', to=settings.AUTH_USER_MODEL)),
                ('name', models.CharField(max_length=120)),
                ('code', models.CharField(max_length=30, unique=True)),
                ('manufacturer', models.CharField(blank=True, max_length=100)),
                ('model_number', models.CharField(blank=True, max_length=100)),
                ('serial_number', models.CharField(blank=True, max_length=100)),
                ('room', models.CharField(blank=True, max_length=60)),
                ('category', models.CharField(choices=[
                    ('REFRACTION', 'Refraction / Autorefraction'), ('TONOMETRY', 'Tonometry'),
                    ('IMAGING', 'Imaging'), ('ELECTROPHYSIOLOGY', 'Electrophysiology'),
                    ('VISUAL_FIELD', 'Visual Field / Perimetry'), ('BIOMETRY', 'Biometry / IOL Calculation'),
                    ('PACHYMETRY', 'Pachymetry'), ('ANT_SEG', 'Anterior Segment'),
                    ('TOPOGRAPHY', 'Corneal Topography / Tomography'), ('SPECULAR', 'Specular Microscopy'),
                    ('ANGIOGRAPHY', 'FFA / ICG Angiography'), ('ORTHOPTICS', 'Orthoptics / Binocular Vision'),
                    ('LOW_VISION', 'Low Vision'), ('DRY_EYE', 'Dry Eye / Meibography'),
                    ('EXTERNAL', 'Referred-out CT / MRI'), ('OTHER', 'Other'),
                ], max_length=30)),
                ('is_dicom_capable', models.BooleanField(default=False)),
                ('dicom_ae_title', models.CharField(blank=True, max_length=32)),
                ('slot_duration_minutes', models.PositiveSmallIntegerField(default=15)),
                ('is_active', models.BooleanField(default=True)),
                ('last_calibration_date', models.DateField(blank=True, null=True)),
                ('next_calibration_due', models.DateField(blank=True, null=True)),
                ('notes', models.TextField(blank=True)),
            ],
            options={'ordering': ['category', 'name']},
        ),

        # ══════════════════════════════════════════════════════════════
        # NEW MODEL: DeviceDowntime
        # ══════════════════════════════════════════════════════════════
        migrations.CreateModel(
            name='DeviceDowntime',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('device', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                              related_name='downtimes', to='investigations.device')),
                ('start', models.DateTimeField()),
                ('end', models.DateTimeField()),
                ('reason', models.CharField(max_length=200)),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                  to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-start']},
        ),

        # ══════════════════════════════════════════════════════════════
        # ENHANCE InvestigationType
        # ══════════════════════════════════════════════════════════════
        migrations.AddField(model_name='investigationtype', name='dicom_modality_code',
                           field=models.CharField(blank=True, max_length=10)),
        migrations.AddField(model_name='investigationtype', name='loinc_code',
                           field=models.CharField(blank=True, max_length=20)),
        migrations.AddField(model_name='investigationtype', name='dilation_requirement',
                           field=models.CharField(choices=[
                               ('BEFORE', 'Must be done BEFORE dilation'),
                               ('AFTER', 'Requires dilation'),
                               ('INDIFFERENT', 'Dilation indifferent'),
                           ], default='INDIFFERENT', max_length=15)),
        migrations.AddField(model_name='investigationtype', name='laterality_required',
                           field=models.BooleanField(default=True)),
        migrations.AddField(model_name='investigationtype', name='billed_per_eye',
                           field=models.BooleanField(default=False)),
        migrations.AddField(model_name='investigationtype', name='consent_required',
                           field=models.BooleanField(default=False)),
        migrations.AddField(model_name='investigationtype', name='contrast_involved',
                           field=models.BooleanField(default=False)),
        migrations.AddField(model_name='investigationtype', name='typical_duration_minutes',
                           field=models.PositiveSmallIntegerField(default=15)),
        migrations.AddField(model_name='investigationtype', name='default_device',
                           field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                    related_name='default_for_types', to='investigations.device')),
        migrations.AddField(model_name='investigationtype', name='technician_skill_level',
                           field=models.CharField(blank=True, max_length=30)),
        migrations.AddField(model_name='investigationtype', name='quality_metric_name',
                           field=models.CharField(blank=True, max_length=60)),
        migrations.AddField(model_name='investigationtype', name='quality_threshold_min',
                           field=models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True)),
        migrations.AddField(model_name='investigationtype', name='quality_threshold_field',
                           field=models.CharField(blank=True, max_length=60)),

        # ══════════════════════════════════════════════════════════════
        # ENHANCE InvestigationOrder — 4 state machines
        # ══════════════════════════════════════════════════════════════
        migrations.AddField(model_name='investigationorder', name='payment_status',
                           field=models.CharField(choices=[
                               ('UNPAID', 'Unpaid'), ('PAID', 'Paid'), ('INSURED', 'Insurance'),
                               ('WAIVED', 'Waived'), ('PACKAGE', 'Package Covered'),
                               ('BILL_LATER', 'Bill Later'), ('STAT_OVERRIDE', 'Emergency Override'),
                               ('FREE_REPEAT', 'Free Repeat (quality failure)'),
                           ], db_index=True, default='UNPAID', max_length=20)),
        migrations.AddField(model_name='investigationorder', name='payment_authorized_by',
                           field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                    related_name='+', to=settings.AUTH_USER_MODEL)),
        migrations.AddField(model_name='investigationorder', name='payment_authorized_at',
                           field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='investigationorder', name='payment_authorization_reason',
                           field=models.CharField(blank=True, max_length=255)),
        migrations.AddField(model_name='investigationorder', name='acquisition_status',
                           field=models.CharField(choices=[
                               ('SCHEDULED', 'Scheduled'), ('PATIENT_PREPARED', 'Patient Prepared'),
                               ('IN_PROGRESS', 'In Progress'), ('ACQUIRED', 'Acquired'),
                               ('QUALITY_FAILED', 'Quality Failed'), ('REPEAT', 'Repeat Acquisition'),
                           ], db_index=True, default='SCHEDULED', max_length=20)),
        migrations.AddField(model_name='investigationorder', name='device',
                           field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                    related_name='orders', to='investigations.device')),
        migrations.AddField(model_name='investigationorder', name='slot_sequence',
                           field=models.PositiveSmallIntegerField(default=0)),
        migrations.AddField(model_name='investigationorder', name='dilation_status',
                           field=models.CharField(blank=True, max_length=20)),
        migrations.AddField(model_name='investigationorder', name='dilation_time',
                           field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='investigationorder', name='dilation_agent',
                           field=models.CharField(blank=True, max_length=60)),
        migrations.AddField(model_name='investigationorder', name='consent_obtained',
                           field=models.BooleanField(blank=True, null=True)),
        migrations.AddField(model_name='investigationorder', name='consent_obtained_by',
                           field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                    related_name='+', to=settings.AUTH_USER_MODEL)),
        migrations.AddField(model_name='investigationorder', name='consent_obtained_at',
                           field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='investigationorder', name='allergy_check_done',
                           field=models.BooleanField(default=False)),
        migrations.AddField(model_name='investigationorder', name='pregnancy_check_done',
                           field=models.BooleanField(blank=True, null=True)),
        migrations.AddField(model_name='investigationorder', name='resuscitation_trolley_checked',
                           field=models.BooleanField(default=False)),
        migrations.AddField(model_name='investigationorder', name='contrast_dye_batch',
                           field=models.CharField(blank=True, max_length=60)),
        migrations.AddField(model_name='investigationorder', name='contrast_volume_ml',
                           field=models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True)),
        migrations.AddField(model_name='investigationorder', name='contrast_adverse_reaction',
                           field=models.TextField(blank=True)),
        migrations.AddField(model_name='investigationorder', name='prior_study_warning',
                           field=models.BooleanField(default=False)),
        migrations.AddField(model_name='investigationorder', name='prior_study_warning_text',
                           field=models.CharField(blank=True, max_length=255)),
        migrations.AddField(model_name='investigationorder', name='prior_study_acknowledged',
                           field=models.BooleanField(default=False)),
        migrations.AddField(model_name='investigationorder', name='report_status',
                           field=models.CharField(choices=[
                               ('PENDING', 'Pending'), ('PRELIMINARY', 'Preliminary'),
                               ('REPORTED', 'Reported'), ('VERIFIED', 'Verified'),
                               ('AMENDED', 'Amended'),
                           ], db_index=True, default='PENDING', max_length=15)),

        # ══════════════════════════════════════════════════════════════
        # ENHANCE InvestigationResult — report workflow + acknowledgment
        # ══════════════════════════════════════════════════════════════
        migrations.AddField(model_name='investigationresult', name='reported_by',
                           field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                    related_name='reported_investigations', to=settings.AUTH_USER_MODEL)),
        migrations.AddField(model_name='investigationresult', name='reported_at',
                           field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='investigationresult', name='version_number',
                           field=models.PositiveSmallIntegerField(default=1)),
        migrations.AddField(model_name='investigationresult', name='compared_with_prior',
                           field=models.BooleanField(default=False)),
        migrations.AddField(model_name='investigationresult', name='prior_comparison_notes',
                           field=models.TextField(blank=True)),
        migrations.AddField(model_name='investigationresult', name='acknowledged_by',
                           field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                    related_name='acknowledged_investigations', to=settings.AUTH_USER_MODEL)),
        migrations.AddField(model_name='investigationresult', name='acknowledged_at',
                           field=models.DateTimeField(blank=True, null=True)),

        # ══════════════════════════════════════════════════════════════
        # ENHANCE ImagingStudy — laterality
        # ══════════════════════════════════════════════════════════════
        migrations.AddField(model_name='imagingstudy', name='laterality',
                           field=models.CharField(choices=[
                               ('OD', 'OD (Right Eye)'), ('OS', 'OS (Left Eye)'),
                               ('OU', 'OU (Both Eyes)'), ('NA', 'N/A'),
                           ], default='OU', max_length=5)),

        # ══════════════════════════════════════════════════════════════
        # ENHANCE InvestigationFile — laterality
        # ══════════════════════════════════════════════════════════════
        migrations.AddField(model_name='investigationfile', name='laterality',
                           field=models.CharField(choices=[
                               ('OD', 'OD (Right Eye)'), ('OS', 'OS (Left Eye)'),
                               ('OU', 'OU (Both Eyes)'), ('NA', 'N/A'),
                           ], default='NA', max_length=5)),

        # ══════════════════════════════════════════════════════════════
        # NEW MODEL: AcquisitionRecord
        # ══════════════════════════════════════════════════════════════
        migrations.CreateModel(
            name='AcquisitionRecord',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                  related_name='+', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                  related_name='+', to=settings.AUTH_USER_MODEL)),
                ('order', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,
                                               related_name='acquisition', to='investigations.investigationorder')),
                ('performed_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                    related_name='performed_acquisitions', to=settings.AUTH_USER_MODEL)),
                ('device', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                              to='investigations.device')),
                ('device_serial', models.CharField(blank=True, max_length=100)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('laterality_confirmed', models.CharField(blank=True, choices=[
                    ('OD', 'OD (Right Eye)'), ('OS', 'OS (Left Eye)'),
                    ('OU', 'OU (Both Eyes)'), ('NA', 'N/A'),
                ], max_length=5)),
                ('dilation_status_at_acquisition', models.CharField(blank=True, max_length=20)),
                ('protocol_used', models.CharField(blank=True, max_length=100)),
                ('quality_metric_value', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True)),
                ('quality_passed', models.BooleanField(blank=True, null=True)),
                ('quality_notes', models.TextField(blank=True)),
                ('fixation_losses_percent', models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True)),
                ('false_positive_percent', models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True)),
                ('false_negative_percent', models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True)),
                ('signal_strength', models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True)),
                ('is_repeat', models.BooleanField(default=False)),
                ('repeat_reason', models.CharField(blank=True, max_length=255)),
                ('repeat_count', models.PositiveSmallIntegerField(default=0)),
            ],
            options={'verbose_name': 'Acquisition Record'},
        ),

        # ══════════════════════════════════════════════════════════════
        # NEW MODEL: BiometryRecord
        # ══════════════════════════════════════════════════════════════
        migrations.CreateModel(
            name='BiometryRecord',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                  related_name='+', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                  related_name='+', to=settings.AUTH_USER_MODEL)),
                ('order', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,
                                               related_name='biometry', to='investigations.investigationorder')),
                ('measured_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                   related_name='biometry_measurements', to=settings.AUTH_USER_MODEL)),
                ('axial_length_od', models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True)),
                ('axial_length_os', models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True)),
                ('al_method', models.CharField(blank=True, max_length=30)),
                ('k1_od', models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True)),
                ('k2_od', models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True)),
                ('k1_os', models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True)),
                ('k2_os', models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True)),
                ('acd_od', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('acd_os', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('wtw', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('lens_thickness_od', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('lens_thickness_os', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('formula_primary', models.CharField(blank=True, max_length=30)),
                ('formula_secondary', models.CharField(blank=True, max_length=30)),
                ('a_constant', models.DecimalField(blank=True, decimal_places=3, max_digits=7, null=True)),
                ('iol_model', models.CharField(blank=True, max_length=60)),
                ('iol_power_od', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('iol_power_os', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('target_refraction_od', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('target_refraction_os', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('inter_eye_al_difference', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('inter_eye_al_flagged', models.BooleanField(default=False)),
                ('al_plausibility_check', models.BooleanField(default=False)),
                ('k_consistency_check', models.BooleanField(default=False)),
                ('refraction_crosscheck_done', models.BooleanField(default=False)),
                ('signal_quality_od', models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True)),
                ('signal_quality_os', models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True)),
                ('valid_measurements_od', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('valid_measurements_os', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('surgeon', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                               related_name='biometry_signoffs', to=settings.AUTH_USER_MODEL)),
                ('surgeon_approved', models.BooleanField(default=False)),
                ('surgeon_approved_at', models.DateTimeField(blank=True, null=True)),
                ('surgeon_notes', models.TextField(blank=True)),
                ('second_verified_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                          related_name='biometry_second_checks', to=settings.AUTH_USER_MODEL)),
                ('second_verified_at', models.DateTimeField(blank=True, null=True)),
                ('is_locked', models.BooleanField(default=False)),
                ('locked_at', models.DateTimeField(blank=True, null=True)),
                ('locked_reason', models.CharField(blank=True, max_length=255)),
                ('post_op_refraction_od', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('post_op_refraction_os', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('post_op_recorded_at', models.DateTimeField(blank=True, null=True)),
                ('prediction_error_od', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('prediction_error_os', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
            ],
            options={'verbose_name': 'Biometry Record'},
        ),

        # ══════════════════════════════════════════════════════════════
        # NEW MODEL: InvestigationResultAmendment
        # ══════════════════════════════════════════════════════════════
        migrations.CreateModel(
            name='InvestigationResultAmendment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                  related_name='+', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                  related_name='+', to=settings.AUTH_USER_MODEL)),
                ('result', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                              related_name='amendments', to='investigations.investigationresult')),
                ('previous_interpretation', models.TextField()),
                ('previous_data', models.JSONField(default=dict)),
                ('reason', models.TextField()),
                ('amended_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                  to=settings.AUTH_USER_MODEL)),
                ('version_number', models.PositiveSmallIntegerField(default=1)),
                ('doctor_re_notified', models.BooleanField(default=False)),
            ],
            options={'ordering': ['-created_at']},
        ),

        # ══════════════════════════════════════════════════════════════
        # NEW MODEL: VisitInvestigationPlan
        # ══════════════════════════════════════════════════════════════
        migrations.CreateModel(
            name='VisitInvestigationPlan',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                  related_name='+', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                  related_name='+', to=settings.AUTH_USER_MODEL)),
                ('patient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                               related_name='investigation_plans', to='patients.patient')),
                ('visit_date', models.DateField()),
                ('planned_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                  to=settings.AUTH_USER_MODEL)),
                ('notes', models.TextField(blank=True)),
                ('is_completed', models.BooleanField(default=False)),
            ],
            options={'ordering': ['-visit_date']},
        ),

        # ══════════════════════════════════════════════════════════════
        # NEW MODEL: VisitInvestigationStep
        # ══════════════════════════════════════════════════════════════
        migrations.CreateModel(
            name='VisitInvestigationStep',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('plan', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                            related_name='steps', to='investigations.visitinvestigationplan')),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                             related_name='plan_steps', to='investigations.investigationorder')),
                ('sequence', models.PositiveSmallIntegerField()),
                ('phase', models.CharField(choices=[
                    ('PRE', 'Pre-dilation'), ('DILATE', 'Dilation Wait'),
                    ('POST', 'Post-dilation'), ('ANY', 'Any time'),
                ], default='ANY', max_length=10)),
                ('estimated_start', models.TimeField(blank=True, null=True)),
                ('estimated_duration_minutes', models.PositiveSmallIntegerField(default=15)),
                ('is_completed', models.BooleanField(default=False)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={'ordering': ['sequence']},
        ),

        # ══════════════════════════════════════════════════════════════
        # NEW MODEL: ContrastReactionLog
        # ══════════════════════════════════════════════════════════════
        migrations.CreateModel(
            name='ContrastReactionLog',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                  related_name='+', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                  related_name='+', to=settings.AUTH_USER_MODEL)),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                              related_name='contrast_reactions', to='investigations.investigationorder')),
                ('patient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                               related_name='contrast_reactions', to='patients.patient')),
                ('dye_used', models.CharField(max_length=60)),
                ('dye_batch', models.CharField(blank=True, max_length=60)),
                ('dye_volume_ml', models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True)),
                ('reaction_time', models.DateTimeField(default=django.utils.timezone.now)),
                ('severity', models.CharField(choices=[
                    ('MILD', 'Mild (nausea, urticaria)'),
                    ('MODERATE', 'Moderate (vomiting, severe urticaria)'),
                    ('SEVERE', 'Severe (anaphylaxis, bronchospasm)'),
                ], max_length=10)),
                ('symptoms', models.TextField()),
                ('treatment_given', models.TextField(blank=True)),
                ('outcome', models.TextField(blank=True)),
                ('photographer', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                    related_name='+', to=settings.AUTH_USER_MODEL)),
                ('injector', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                related_name='+', to=settings.AUTH_USER_MODEL)),
                ('escalated', models.BooleanField(default=False)),
                ('escalated_to', models.CharField(blank=True, max_length=120)),
            ],
            options={'ordering': ['-reaction_time']},
        ),

        # ══════════════════════════════════════════════════════════════
        # Update Eye choices to use new Laterality (OD/OS/OU/NA)
        # ══════════════════════════════════════════════════════════════
        migrations.AlterField(
            model_name='investigationorder',
            name='eye',
            field=models.CharField(choices=[
                ('OD', 'OD (Right Eye)'), ('OS', 'OS (Left Eye)'),
                ('OU', 'OU (Both Eyes)'), ('NA', 'N/A'),
            ], default='OU', max_length=5),
        ),

        # Update urgency to add STAT
        migrations.AlterField(
            model_name='investigationorder',
            name='urgency',
            field=models.CharField(choices=[
                ('ROUTINE', 'Routine'), ('URGENT', 'Urgent'),
                ('STAT', 'STAT'), ('EMERGENCY', 'Emergency'),
            ], default='ROUTINE', max_length=10),
        ),

        # Widen ImagingModality choices
        migrations.AlterField(
            model_name='imagingstudy',
            name='modality',
            field=models.CharField(choices=[
                ('OCT', 'OCT (Optical Coherence Tomography)'), ('OCTA', 'OCT Angiography'),
                ('FFA', 'Fundus Fluorescein Angiography'), ('ICG', 'Indocyanine Green Angiography'),
                ('FUNDUS', 'Fundus Photography'), ('WIDEFIELD', 'Wide-field Imaging'),
                ('PENTACAM', 'Pentacam / Corneal Topography'),
                ('BIOMETRY', 'Biometry (IOL Master / A-Scan)'),
                ('BSCAN', 'B-Scan Ultrasound'), ('UBM', 'Ultrasound Biomicroscopy'),
                ('PERIMETRY', 'Visual Field / Perimetry'),
                ('SPECULAR', 'Specular Microscopy'), ('PACHYMETRY', 'Pachymetry'),
                ('ERG', 'Electroretinography'), ('VEP', 'Visual Evoked Potential'),
                ('EOG', 'Electro-oculography'),
                ('ANT_SEG', 'Anterior Segment Photography'),
                ('MEIBOGRAPHY', 'Meibography'), ('TOPOGRAPHY', 'Corneal Topography'),
                ('XRAY', 'X-Ray'), ('CT', 'CT Scan'), ('MRI', 'MRI'),
                ('OTHER', 'Other'),
            ], max_length=20),
        ),

        # Widen InvestigationFile file_type choices
        migrations.AlterField(
            model_name='investigationfile',
            name='file_type',
            field=models.CharField(choices=[
                ('IMAGE', 'Image'), ('PDF', 'PDF'),
                ('DICOM_PDF', 'DICOM Encapsulated PDF'),
                ('SCREEN_CAPTURE', 'Screen Capture'),
                ('DATA', 'Data File'), ('VIDEO', 'Video'),
            ], max_length=20),
        ),
    ]
