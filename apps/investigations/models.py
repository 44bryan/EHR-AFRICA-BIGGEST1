"""
Ophthalmic investigation orders, device scheduling, acquisition, and reporting.
Designed for ophthalmology-specific workflows with dilation-aware sequencing,
laterality safety, quality gating, biometry safety, and DICOM integration.

Four independent state machines: Order, Payment, Acquisition, Report.
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from apps.core.models import AuditModel, TimeStampedModel


# ══════════════════════════════════════════════════════════════════════════════
# ENUMS
# ══════════════════════════════════════════════════════════════════════════════

class InvestigationCategory(models.TextChoices):
    IMAGING = 'IMAGING', _('Imaging')
    BIOMETRY = 'BIOMETRY', _('Biometry / IOL Calculation')
    VISUAL_FIELD = 'VISUAL_FIELD', _('Visual Field / Perimetry')
    PACHYMETRY = 'PACHYMETRY', _('Pachymetry')
    TOPOGRAPHY = 'TOPOGRAPHY', _('Corneal Topography')
    SPECULAR = 'SPECULAR', _('Specular Microscopy')
    REFRACTION = 'REFRACTION', _('Refraction')
    ORTHOPTICS = 'ORTHOPTICS', _('Orthoptics / Binocular Vision')
    LOW_VISION = 'LOW_VISION', _('Low Vision')
    TONOMETRY = 'TONOMETRY', _('Tonometry')
    ELECTROPHYSIOLOGY = 'ELECTROPHYSIOLOGY', _('Electrophysiology')
    ANTERIOR_SEGMENT = 'ANT_SEG', _('Anterior Segment')
    ANGIOGRAPHY = 'ANGIOGRAPHY', _('FFA / ICG Angiography')
    DRY_EYE = 'DRY_EYE', _('Dry Eye / Meibography')
    EXTERNAL = 'EXTERNAL', _('External Lab / CT / MRI')
    FUNDUS_PHOTO = 'FUNDUS_PHOTO', _('Fundus Photography')
    OCT = 'OCT', _('OCT')
    PERIMETRY = 'PERIMETRY', _('Perimetry')
    OTHER = 'OTHER', _('Other')


class DilationRequirement(models.TextChoices):
    BEFORE = 'BEFORE', _('Must be done BEFORE dilation')
    AFTER = 'AFTER', _('Requires dilation')
    INDIFFERENT = 'INDIFFERENT', _('Dilation indifferent')


class PaymentStatus(models.TextChoices):
    UNPAID = 'UNPAID', _('Unpaid')
    PAID = 'PAID', _('Paid')
    INSURED = 'INSURED', _('Insurance')
    WAIVED = 'WAIVED', _('Waived')
    PACKAGE = 'PACKAGE', _('Package Covered')
    BILL_LATER = 'BILL_LATER', _('Bill Later')
    STAT_OVERRIDE = 'STAT_OVERRIDE', _('Emergency Override')
    FREE_REPEAT = 'FREE_REPEAT', _('Free Repeat (quality failure)')


class AcquisitionStatus(models.TextChoices):
    SCHEDULED = 'SCHEDULED', _('Scheduled')
    PATIENT_PREPARED = 'PATIENT_PREPARED', _('Patient Prepared')
    IN_PROGRESS = 'IN_PROGRESS', _('In Progress')
    ACQUIRED = 'ACQUIRED', _('Acquired')
    QUALITY_FAILED = 'QUALITY_FAILED', _('Quality Failed')
    REPEAT = 'REPEAT', _('Repeat Acquisition')


class ReportStatus(models.TextChoices):
    PENDING = 'PENDING', _('Pending')
    PRELIMINARY = 'PRELIMINARY', _('Preliminary')
    REPORTED = 'REPORTED', _('Reported')
    VERIFIED = 'VERIFIED', _('Verified')
    AMENDED = 'AMENDED', _('Amended')


class Laterality(models.TextChoices):
    OD = 'OD', _('OD (Right Eye)')
    OS = 'OS', _('OS (Left Eye)')
    OU = 'OU', _('OU (Both Eyes)')
    NA = 'NA', _('N/A')


# ══════════════════════════════════════════════════════════════════════════════
# DEVICE / ROOM — Bookable Resources
# ══════════════════════════════════════════════════════════════════════════════

class Device(AuditModel):
    """Physical investigation device/machine — bookable resource."""
    name = models.CharField(max_length=120, help_text='e.g. Humphrey HFA3, IOLMaster 700')
    code = models.CharField(max_length=30, unique=True)
    manufacturer = models.CharField(max_length=100, blank=True)
    model_number = models.CharField(max_length=100, blank=True)
    serial_number = models.CharField(max_length=100, blank=True)
    room = models.CharField(max_length=60, blank=True, help_text='Room/location')
    category = models.CharField(max_length=30, choices=InvestigationCategory.choices)
    is_dicom_capable = models.BooleanField(default=False)
    dicom_ae_title = models.CharField(max_length=32, blank=True, help_text='DICOM AE Title')
    slot_duration_minutes = models.PositiveSmallIntegerField(default=15)
    is_active = models.BooleanField(default=True)
    last_calibration_date = models.DateField(null=True, blank=True)
    next_calibration_due = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['category', 'name']

    def __str__(self):
        return f"{self.name} ({self.room})" if self.room else self.name


class DeviceDowntime(TimeStampedModel):
    """Maintenance / downtime block for a device."""
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='downtimes')
    start = models.DateTimeField()
    end = models.DateTimeField()
    reason = models.CharField(max_length=200)
    created_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True)

    class Meta:
        ordering = ['-start']

    def __str__(self):
        return f"{self.device.name} down {self.start:%d/%m %H:%M}–{self.end:%H:%M}"


# ══════════════════════════════════════════════════════════════════════════════
# INVESTIGATION TYPE (Modality Catalogue)
# ══════════════════════════════════════════════════════════════════════════════

class InvestigationType(TimeStampedModel):
    name = models.CharField(max_length=120, unique=True)
    code = models.CharField(max_length=30, unique=True)
    category = models.CharField(max_length=30, choices=InvestigationCategory.choices)
    description = models.TextField(blank=True)

    # ── DICOM / Interop ──
    dicom_modality_code = models.CharField(max_length=10, blank=True, help_text='DICOM modality code e.g. OPT, OP, OPM')
    loinc_code = models.CharField(max_length=20, blank=True, help_text='LOINC code for measurement')

    # ── Ophthalmic-specific ──
    dilation_requirement = models.CharField(
        max_length=15, choices=DilationRequirement.choices,
        default=DilationRequirement.INDIFFERENT,
        help_text='BEFORE=must be done pre-dilation; AFTER=requires dilation'
    )
    laterality_required = models.BooleanField(default=True, help_text='Require OD/OS/OU on every order')
    billed_per_eye = models.BooleanField(default=False, help_text='If True, price applies per eye (×2 for OU)')
    consent_required = models.BooleanField(default=False, help_text='e.g. FFA, ICG — requires signed consent')
    contrast_involved = models.BooleanField(default=False, help_text='Fluorescein, ICG, or other contrast agent')

    # ── Scheduling ──
    typical_duration_minutes = models.PositiveSmallIntegerField(default=15)
    default_device = models.ForeignKey(Device, on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='default_for_types')
    technician_skill_level = models.CharField(max_length=30, blank=True,
                                               help_text='Required skill: junior, senior, specialist')

    # ── Patient prep ──
    requires_preparation = models.BooleanField(default=False)
    preparation_instructions = models.TextField(blank=True)

    # ── Quality thresholds ──
    quality_metric_name = models.CharField(max_length=60, blank=True,
                                            help_text='e.g. Signal Strength, Fixation Losses %')
    quality_threshold_min = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True,
                                                 help_text='Below this = quality fail')
    quality_threshold_field = models.CharField(max_length=60, blank=True,
                                                help_text='JSON key in result_data for quality metric')

    # ── Pricing ──
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                      help_text='Price per investigation (FCFA)')

    # ── Result template ──
    result_template = models.JSONField(default=dict, blank=True,
                                        help_text='JSON schema for structured result entry')

    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['category', 'name']
        verbose_name = 'Investigation Type'

    def __str__(self):
        return f"{self.code} — {self.name}"


# ══════════════════════════════════════════════════════════════════════════════
# INVESTIGATION ORDER — with 4 state machines
# ══════════════════════════════════════════════════════════════════════════════

class InvestigationOrder(AuditModel):
    class Urgency(models.TextChoices):
        ROUTINE = 'ROUTINE', _('Routine')
        URGENT = 'URGENT', _('Urgent')
        STAT = 'STAT', _('STAT')
        EMERGENCY = 'EMERGENCY', _('Emergency')

    class Status(models.TextChoices):
        ORDERED = 'ORDERED', _('Ordered')
        SCHEDULED = 'SCHEDULED', _('Scheduled')
        IN_PROGRESS = 'IN_PROGRESS', _('In Progress')
        COMPLETED = 'COMPLETED', _('Completed')
        CANCELLED = 'CANCELLED', _('Cancelled')

    class Location(models.TextChoices):
        CLINIC = 'CLINIC', _('Clinic')
        OUTREACH = 'OUTREACH', _('Outreach / Field')

    # ── Core FKs ──
    consultation = models.ForeignKey(
        'consultations.Consultation', on_delete=models.CASCADE,
        related_name='investigation_orders',
    )
    patient = models.ForeignKey(
        'patients.Patient', on_delete=models.CASCADE,
        related_name='investigation_orders',
    )
    ordered_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True,
        related_name='ordered_investigations',
    )
    assigned_to = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assigned_investigations',
    )
    investigation_type = models.ForeignKey(InvestigationType, on_delete=models.PROTECT)

    # ── Order state machine ──
    urgency = models.CharField(max_length=10, choices=Urgency.choices, default=Urgency.ROUTINE)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.ORDERED)
    clinical_indication = models.TextField()
    notes = models.TextField(blank=True)
    location = models.CharField(max_length=10, choices=Location.choices, default=Location.CLINIC, db_index=True)

    # ── Laterality (safety field — mandatory, controlled) ──
    eye = models.CharField(max_length=5, choices=Laterality.choices, default=Laterality.OU,
                           help_text='OD/OS/OU — propagates to device, study, report, surgical plan')

    # ── Payment state machine ──
    payment_status = models.CharField(max_length=20, choices=PaymentStatus.choices,
                                       default=PaymentStatus.UNPAID, db_index=True)
    payment_authorized_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+',
    )
    payment_authorized_at = models.DateTimeField(null=True, blank=True)
    payment_authorization_reason = models.CharField(max_length=255, blank=True)

    # ── Acquisition state machine ──
    acquisition_status = models.CharField(
        max_length=20, choices=AcquisitionStatus.choices,
        default=AcquisitionStatus.SCHEDULED, db_index=True,
    )

    # ── Scheduling ──
    scheduled_time = models.DateTimeField(null=True, blank=True)
    device = models.ForeignKey(Device, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')
    slot_sequence = models.PositiveSmallIntegerField(default=0,
                                                      help_text='Order within multi-investigation visit (dilation-aware)')

    # ── Dilation tracking ──
    dilation_status = models.CharField(max_length=20, blank=True,
                                        help_text='undilated / dilating / dilated')
    dilation_time = models.DateTimeField(null=True, blank=True)
    dilation_agent = models.CharField(max_length=60, blank=True)

    # ── Contrast / Consent (FFA/ICG) ──
    consent_obtained = models.BooleanField(null=True, blank=True)
    consent_obtained_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL,
                                             null=True, blank=True, related_name='+')
    consent_obtained_at = models.DateTimeField(null=True, blank=True)
    allergy_check_done = models.BooleanField(default=False)
    pregnancy_check_done = models.BooleanField(null=True, blank=True)
    resuscitation_trolley_checked = models.BooleanField(default=False)
    contrast_dye_batch = models.CharField(max_length=60, blank=True)
    contrast_volume_ml = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    contrast_adverse_reaction = models.TextField(blank=True)

    # ── Prior study awareness ──
    prior_study_warning = models.BooleanField(default=False)
    prior_study_warning_text = models.CharField(max_length=255, blank=True)
    prior_study_acknowledged = models.BooleanField(default=False)

    # ── Report state machine ──
    report_status = models.CharField(max_length=15, choices=ReportStatus.choices,
                                      default=ReportStatus.PENDING, db_index=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Investigation Order'

    def __str__(self):
        return f"{self.investigation_type.name} — {self.patient.full_name} ({self.get_eye_display()})"

    def can_proceed_without_payment(self):
        return self.payment_status in (
            PaymentStatus.PAID, PaymentStatus.INSURED, PaymentStatus.WAIVED,
            PaymentStatus.PACKAGE, PaymentStatus.STAT_OVERRIDE,
            PaymentStatus.BILL_LATER, PaymentStatus.FREE_REPEAT,
        )


# ══════════════════════════════════════════════════════════════════════════════
# ACQUISITION RECORD — What happened at the device
# ══════════════════════════════════════════════════════════════════════════════

class AcquisitionRecord(AuditModel):
    """Records what happened during image/measurement acquisition at the device."""
    order = models.OneToOneField(InvestigationOrder, on_delete=models.CASCADE, related_name='acquisition')
    performed_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True,
                                      related_name='performed_acquisitions')
    device = models.ForeignKey(Device, on_delete=models.SET_NULL, null=True, blank=True)
    device_serial = models.CharField(max_length=100, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # ── Laterality confirmed at chair ──
    laterality_confirmed = models.CharField(max_length=5, choices=Laterality.choices, blank=True)
    dilation_status_at_acquisition = models.CharField(max_length=20, blank=True)
    protocol_used = models.CharField(max_length=100, blank=True,
                                      help_text='e.g. SITA-Standard 24-2, Macular Cube 512x128')

    # ── Quality metrics (structured per modality) ──
    quality_metric_value = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True,
                                                help_text='e.g. signal strength 8/10, fixation losses 12%')
    quality_passed = models.BooleanField(null=True, blank=True)
    quality_notes = models.TextField(blank=True)

    # ── Visual Field specific quality ──
    fixation_losses_percent = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    false_positive_percent = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    false_negative_percent = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)

    # ── OCT specific quality ──
    signal_strength = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)

    # ── Repeat info ──
    is_repeat = models.BooleanField(default=False)
    repeat_reason = models.CharField(max_length=255, blank=True)
    repeat_count = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = 'Acquisition Record'

    def __str__(self):
        return f"Acquisition: {self.order}"

    def check_quality(self):
        """Auto-check quality against type thresholds. Returns (passed, reason)."""
        inv_type = self.order.investigation_type
        if not inv_type.quality_threshold_min or self.quality_metric_value is None:
            return True, ''
        if self.quality_metric_value < inv_type.quality_threshold_min:
            return False, f'{inv_type.quality_metric_name} = {self.quality_metric_value} (min: {inv_type.quality_threshold_min})'
        return True, ''


# ══════════════════════════════════════════════════════════════════════════════
# INVESTIGATION RESULT — Interpretation & Report
# ══════════════════════════════════════════════════════════════════════════════

class InvestigationResult(AuditModel):
    order = models.OneToOneField(InvestigationOrder, on_delete=models.CASCADE, related_name='result')
    performed_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True,
        related_name='performed_investigations',
    )
    result_date = models.DateTimeField(auto_now_add=True)
    result_data = models.JSONField(default=dict, help_text='Structured result per investigation type')
    interpretation = models.TextField(blank=True)
    is_normal = models.BooleanField(null=True, blank=True)

    # ── Report workflow ──
    reported_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='reported_investigations')
    reported_at = models.DateTimeField(null=True, blank=True)

    # ── Verification ──
    is_verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='verified_investigations',
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    report_generated = models.BooleanField(default=False)

    # ── Version control ──
    version_number = models.PositiveSmallIntegerField(default=1)

    # ── Prior study comparison ──
    compared_with_prior = models.BooleanField(default=False)
    prior_comparison_notes = models.TextField(blank=True)

    # ── Doctor acknowledgment ──
    acknowledged_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
                                         related_name='acknowledged_investigations')
    acknowledged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Investigation Result'

    def __str__(self):
        return f"Result: {self.order.investigation_type.name} — {self.order.patient.full_name}"


class InvestigationResultAmendment(AuditModel):
    """Amendment trail for investigation results (version control)."""
    result = models.ForeignKey(InvestigationResult, on_delete=models.CASCADE, related_name='amendments')
    previous_interpretation = models.TextField()
    previous_data = models.JSONField(default=dict)
    reason = models.TextField()
    amended_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True)
    version_number = models.PositiveSmallIntegerField(default=1)
    doctor_re_notified = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']


# ══════════════════════════════════════════════════════════════════════════════
# BIOMETRY — IOL Calculation Safety Workflow
# ══════════════════════════════════════════════════════════════════════════════

class BiometryRecord(AuditModel):
    """
    Dedicated biometry/IOL calculation record.
    Highest-liability item — wrong IOL power is silent until post-op.
    """
    order = models.OneToOneField(InvestigationOrder, on_delete=models.CASCADE, related_name='biometry')
    measured_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True,
                                    related_name='biometry_measurements')

    # ── Axial Length ──
    axial_length_od = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    axial_length_os = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    al_method = models.CharField(max_length=30, blank=True, help_text='Optical / Ultrasound')

    # ── Keratometry ──
    k1_od = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, help_text='Flat K (D)')
    k2_od = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, help_text='Steep K (D)')
    k1_os = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    k2_os = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    # ── ACD / WTW / LT ──
    acd_od = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text='Anterior Chamber Depth (mm)')
    acd_os = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    wtw = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text='White-to-White (mm)')
    lens_thickness_od = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    lens_thickness_os = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    # ── IOL Calculation ──
    formula_primary = models.CharField(max_length=30, blank=True,
                                        help_text='e.g. SRK/T, Barrett Universal II, Haigis, Hill-RBF')
    formula_secondary = models.CharField(max_length=30, blank=True)
    a_constant = models.DecimalField(max_digits=7, decimal_places=3, null=True, blank=True)
    iol_model = models.CharField(max_length=60, blank=True, help_text='IOL model name')
    iol_power_od = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    iol_power_os = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    target_refraction_od = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True,
                                                help_text='Target post-op refraction (D)')
    target_refraction_os = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    # ── Safety checks ──
    inter_eye_al_difference = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    inter_eye_al_flagged = models.BooleanField(default=False,
                                                help_text='Auto-flagged if >0.3mm difference')
    al_plausibility_check = models.BooleanField(default=False,
                                                 help_text='Axial length within expected range')
    k_consistency_check = models.BooleanField(default=False,
                                               help_text='K readings consistent between eyes')
    refraction_crosscheck_done = models.BooleanField(default=False,
                                                      help_text='Biometry cross-checked vs current Rx')
    signal_quality_od = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    signal_quality_os = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    valid_measurements_od = models.PositiveSmallIntegerField(null=True, blank=True)
    valid_measurements_os = models.PositiveSmallIntegerField(null=True, blank=True)

    # ── Surgeon sign-off ──
    surgeon = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='biometry_signoffs')
    surgeon_approved = models.BooleanField(default=False)
    surgeon_approved_at = models.DateTimeField(null=True, blank=True)
    surgeon_notes = models.TextField(blank=True)

    # ── Second-person verification ──
    second_verified_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
                                            related_name='biometry_second_checks')
    second_verified_at = models.DateTimeField(null=True, blank=True)

    # ── Surgery booking lock ──
    is_locked = models.BooleanField(default=False, help_text='Locked once surgery is booked')
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_reason = models.CharField(max_length=255, blank=True)

    # ── Post-op outcome loop ──
    post_op_refraction_od = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    post_op_refraction_os = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    post_op_recorded_at = models.DateTimeField(null=True, blank=True)
    prediction_error_od = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True,
                                               help_text='Actual - Target refraction')
    prediction_error_os = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    class Meta:
        verbose_name = 'Biometry Record'

    def __str__(self):
        return f"Biometry: {self.order.patient.full_name}"

    def save(self, *args, **kwargs):
        # Auto inter-eye AL check
        if self.axial_length_od and self.axial_length_os:
            diff = abs(self.axial_length_od - self.axial_length_os)
            self.inter_eye_al_difference = diff
            self.inter_eye_al_flagged = diff > 0.3

        # Auto prediction error calculation
        if self.post_op_refraction_od is not None and self.target_refraction_od is not None:
            self.prediction_error_od = self.post_op_refraction_od - self.target_refraction_od
        if self.post_op_refraction_os is not None and self.target_refraction_os is not None:
            self.prediction_error_os = self.post_op_refraction_os - self.target_refraction_os

        super().save(*args, **kwargs)


# ══════════════════════════════════════════════════════════════════════════════
# DICOM IMAGING STUDY
# ══════════════════════════════════════════════════════════════════════════════

class ImagingModality(models.TextChoices):
    OCT = 'OCT', 'OCT (Optical Coherence Tomography)'
    OCTA = 'OCTA', 'OCT Angiography'
    FFA = 'FFA', 'Fundus Fluorescein Angiography'
    ICG = 'ICG', 'Indocyanine Green Angiography'
    FUNDUS = 'FUNDUS', 'Fundus Photography'
    WIDEFIELD = 'WIDEFIELD', 'Wide-field Imaging'
    PENTACAM = 'PENTACAM', 'Pentacam / Corneal Topography'
    BIOMETRY = 'BIOMETRY', 'Biometry (IOL Master / A-Scan)'
    BSCAN = 'BSCAN', 'B-Scan Ultrasound'
    UBM = 'UBM', 'Ultrasound Biomicroscopy'
    PERIMETRY = 'PERIMETRY', 'Visual Field / Perimetry'
    SPECULAR = 'SPECULAR', 'Specular Microscopy'
    PACHYMETRY = 'PACHYMETRY', 'Pachymetry'
    ERG = 'ERG', 'Electroretinography'
    VEP = 'VEP', 'Visual Evoked Potential'
    EOG = 'EOG', 'Electro-oculography'
    ANT_SEG_PHOTO = 'ANT_SEG', 'Anterior Segment Photography'
    MEIBOGRAPHY = 'MEIBOGRAPHY', 'Meibography'
    TOPOGRAPHY = 'TOPOGRAPHY', 'Corneal Topography'
    XRAY = 'XRAY', 'X-Ray'
    CT = 'CT', 'CT Scan'
    MRI = 'MRI', 'MRI'
    OTHER = 'OTHER', 'Other'


class ImagingStudy(AuditModel):
    """DICOM imaging study linked to a patient / investigation order."""
    patient = models.ForeignKey(
        'patients.Patient', on_delete=models.PROTECT, related_name='imaging_studies'
    )
    consultation = models.ForeignKey(
        'consultations.Consultation', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='imaging_studies'
    )
    order = models.ForeignKey(
        InvestigationOrder, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='imaging_studies'
    )
    modality = models.CharField(max_length=20, choices=ImagingModality.choices)
    laterality = models.CharField(max_length=5, choices=Laterality.choices, default=Laterality.OU)
    study_date = models.DateField(default=None, null=True, blank=True)
    description = models.CharField(max_length=255)
    study_uid = models.CharField(max_length=200, blank=True,
                                  help_text='DICOM Study Instance UID')
    accession_number = models.CharField(max_length=50, blank=True)
    series_count = models.PositiveSmallIntegerField(default=1)
    viewer_url = models.URLField(max_length=500, blank=True)
    report = models.TextField(blank=True)
    is_reported = models.BooleanField(default=False)
    reported_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='imaging_reports'
    )
    ordered_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ordered_imaging'
    )

    class Meta:
        ordering = ['-study_date', '-created_at']
        verbose_name = 'Imaging Study'
        verbose_name_plural = 'Imaging Studies'

    def __str__(self):
        return f"{self.get_modality_display()} — {self.patient.full_name} ({self.study_date})"

    def save(self, *args, **kwargs):
        if not self.viewer_url and self.study_uid:
            from django.conf import settings
            base = getattr(settings, 'DICOM_VIEWER_BASE_URL', '').rstrip('/')
            if base:
                self.viewer_url = f"{base}?StudyInstanceUIDs={self.study_uid}"
        if not self.study_date:
            self.study_date = timezone.localdate()
        super().save(*args, **kwargs)

    @property
    def can_view_in_browser(self):
        return bool(self.viewer_url)


# ══════════════════════════════════════════════════════════════════════════════
# INVESTIGATION FILE — Attachments (images, PDFs, legacy device output)
# ══════════════════════════════════════════════════════════════════════════════

class InvestigationFile(TimeStampedModel):
    class FileType(models.TextChoices):
        IMAGE = 'IMAGE', _('Image')
        PDF = 'PDF', _('PDF')
        DICOM_PDF = 'DICOM_PDF', _('DICOM Encapsulated PDF')
        SCREEN_CAPTURE = 'SCREEN_CAPTURE', _('Screen Capture')
        DATA = 'DATA', _('Data File')
        VIDEO = 'VIDEO', _('Video')

    result = models.ForeignKey(InvestigationResult, on_delete=models.CASCADE, related_name='files')
    file = models.FileField(upload_to='investigations/files/%Y/%m/')
    file_type = models.CharField(max_length=20, choices=FileType.choices)
    description = models.CharField(max_length=200, blank=True)
    laterality = models.CharField(max_length=5, choices=Laterality.choices, default=Laterality.NA,
                                   help_text='Which eye does this file correspond to')
    uploaded_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return f"{self.file_type} — {self.result}"


# ══════════════════════════════════════════════════════════════════════════════
# DILATION SEQUENCING — Combined-visit optimizer
# ══════════════════════════════════════════════════════════════════════════════

class VisitInvestigationPlan(AuditModel):
    """
    Combined-visit plan that sequences a patient's multiple investigations
    into a dilation-aware order for a single visit.
    """
    patient = models.ForeignKey('patients.Patient', on_delete=models.CASCADE, related_name='investigation_plans')
    visit_date = models.DateField()
    planned_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True)
    notes = models.TextField(blank=True)
    is_completed = models.BooleanField(default=False)

    class Meta:
        ordering = ['-visit_date']

    def __str__(self):
        return f"Investigation Plan: {self.patient.full_name} ({self.visit_date})"


class VisitInvestigationStep(TimeStampedModel):
    """Individual step in a visit investigation plan."""
    plan = models.ForeignKey(VisitInvestigationPlan, on_delete=models.CASCADE, related_name='steps')
    order = models.ForeignKey(InvestigationOrder, on_delete=models.CASCADE, related_name='plan_steps')
    sequence = models.PositiveSmallIntegerField(help_text='Execution order within the plan')

    class Phase(models.TextChoices):
        PRE_DILATION = 'PRE', _('Pre-dilation')
        DILATION_WAIT = 'DILATE', _('Dilation Wait')
        POST_DILATION = 'POST', _('Post-dilation')
        ANY = 'ANY', _('Any time')

    phase = models.CharField(max_length=10, choices=Phase.choices, default=Phase.ANY)
    estimated_start = models.TimeField(null=True, blank=True)
    estimated_duration_minutes = models.PositiveSmallIntegerField(default=15)
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['sequence']

    def __str__(self):
        return f"Step {self.sequence}: {self.order.investigation_type.name}"


# ══════════════════════════════════════════════════════════════════════════════
# CONTRAST ADVERSE REACTION LOG
# ══════════════════════════════════════════════════════════════════════════════

class ContrastReactionLog(AuditModel):
    """Log of adverse reactions during FFA/ICG procedures."""
    class Severity(models.TextChoices):
        MILD = 'MILD', _('Mild (nausea, urticaria)')
        MODERATE = 'MODERATE', _('Moderate (vomiting, severe urticaria)')
        SEVERE = 'SEVERE', _('Severe (anaphylaxis, bronchospasm)')

    order = models.ForeignKey(InvestigationOrder, on_delete=models.CASCADE, related_name='contrast_reactions')
    patient = models.ForeignKey('patients.Patient', on_delete=models.CASCADE, related_name='contrast_reactions')
    dye_used = models.CharField(max_length=60, help_text='Fluorescein / ICG / other')
    dye_batch = models.CharField(max_length=60, blank=True)
    dye_volume_ml = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    reaction_time = models.DateTimeField(default=timezone.now)
    severity = models.CharField(max_length=10, choices=Severity.choices)
    symptoms = models.TextField()
    treatment_given = models.TextField(blank=True)
    outcome = models.TextField(blank=True)
    photographer = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name='+')
    injector = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='+')
    escalated = models.BooleanField(default=False)
    escalated_to = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ['-reaction_time']

    def __str__(self):
        return f"Contrast Reaction: {self.patient.full_name} — {self.severity}"
