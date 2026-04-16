"""
Patient registration, demographics, medical history, and visits.
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.core.models import AuditModel, TimeStampedModel
from apps.core.utils import generate_patient_id, generate_visit_number


class BloodGroup(models.TextChoices):
    A_POS = 'A+', 'A+'
    A_NEG = 'A-', 'A-'
    B_POS = 'B+', 'B+'
    B_NEG = 'B-', 'B-'
    AB_POS = 'AB+', 'AB+'
    AB_NEG = 'AB-', 'AB-'
    O_POS = 'O+', 'O+'
    O_NEG = 'O-', 'O-'
    UNKNOWN = 'Unknown', 'Unknown'


class Genotype(models.TextChoices):
    AA = 'AA', 'AA'
    AS = 'AS', 'AS'
    SS = 'SS', 'SS'
    AC = 'AC', 'AC'
    SC = 'SC', 'SC'
    UNKNOWN = 'Unknown', 'Unknown'


class Gender(models.TextChoices):
    MALE = 'M', 'Male'
    FEMALE = 'F', 'Female'
    OTHER = 'Other', 'Other'


class MaritalStatus(models.TextChoices):
    SINGLE = 'Single', 'Single'
    MARRIED = 'Married', 'Married'
    DIVORCED = 'Divorced', 'Divorced'
    WIDOWED = 'Widowed', 'Widowed'


class Patient(AuditModel):
    patient_id = models.CharField(max_length=20, unique=True, editable=False)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True)
    date_of_birth = models.DateField()
    gender = models.CharField(max_length=10, choices=Gender.choices)
    blood_group = models.CharField(max_length=10, choices=BloodGroup.choices, default=BloodGroup.UNKNOWN)
    genotype = models.CharField(max_length=10, choices=Genotype.choices, default=Genotype.UNKNOWN)
    phone_number = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    state_of_origin = models.CharField(max_length=50, blank=True)
    occupation = models.CharField(max_length=100, blank=True)
    religion = models.CharField(max_length=50, blank=True)
    marital_status = models.CharField(max_length=20, choices=MaritalStatus.choices, blank=True)
    nationality = models.CharField(max_length=50, default='Cameroonian')

    # ── Structured Cameroonian address ────────────────────────────────────────
    post_address = models.CharField(max_length=100, blank=True, help_text='P.O. Box / Postal address')
    quarter      = models.CharField(max_length=100, blank=True, help_text='Quartier / Neighbourhood')
    village_town = models.CharField(max_length=100, blank=True, help_text='Village or Town')
    division     = models.CharField(max_length=100, blank=True, help_text='Division (administrative)')
    region       = models.CharField(max_length=50,  blank=True, help_text='Region (e.g. Centre, Littoral)')
    country      = models.CharField(max_length=50,  default='Cameroon')

    photo = models.ImageField(upload_to='patients/photos/', null=True, blank=True)
    registration_date = models.DateField(auto_now_add=True)
    registered_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='registered_patients',
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, help_text='General administrative notes')

    class Meta:
        ordering = ['-registration_date', 'last_name']
        verbose_name = 'Patient'
        verbose_name_plural = 'Patients'
        indexes = [
            # Speed up name/phone search (used in patient_list_view and patient_search_api)
            models.Index(fields=['last_name', 'first_name'], name='patient_name_idx'),
            models.Index(fields=['phone_number'], name='patient_phone_idx'),
            # Speed up is_active + registration_date filtering (default list view)
            models.Index(fields=['is_active', '-registration_date'], name='patient_active_date_idx'),
        ]

    def __str__(self):
        return f"{self.patient_id} — {self.full_name}"

    def save(self, *args, **kwargs):
        if not self.patient_id:
            self.patient_id = generate_patient_id()
        super().save(*args, **kwargs)

    @property
    def full_name(self):
        parts = filter(None, [self.first_name, self.middle_name, self.last_name])
        return ' '.join(parts)

    @property
    def age(self):
        from apps.core.utils import calculate_age
        return calculate_age(self.date_of_birth)

    @property
    def age_display(self):
        a = self.age
        return f"{a} year{'s' if a != 1 else ''}"

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('patients:detail', kwargs={'patient_id': self.patient_id})

    @property
    def active_consultation_visit(self):
        """
        Returns the most recent visit whose consultation window is still open (within 15 days).
        Reception uses this to detect returning patients who don't need to pay again.
        """
        from datetime import date
        return self.visits.filter(
            consultation_valid_until__gte=date.today(),
            is_deleted=False,
        ).order_by('-visit_date').first()

    @property
    def has_active_consultation(self):
        """True if patient has a valid consultation within the 15-day window."""
        return self.active_consultation_visit is not None


class NextOfKin(TimeStampedModel):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='next_of_kin')
    full_name = models.CharField(max_length=200)
    relationship = models.CharField(max_length=50)
    phone_number = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Next of Kin'
        verbose_name_plural = 'Next of Kin'

    def __str__(self):
        return f"{self.full_name} ({self.relationship}) — {self.patient}"


class InsuranceInfo(TimeStampedModel):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='insurance')
    provider = models.CharField(max_length=100)
    policy_number = models.CharField(max_length=50)
    group_number = models.CharField(max_length=50, blank=True)
    plan_name = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    expiry_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Insurance Info'
        verbose_name_plural = 'Insurance Info'

    def __str__(self):
        return f"{self.provider} — {self.patient}"


class MedicalHistory(AuditModel):
    patient = models.OneToOneField(Patient, on_delete=models.CASCADE, related_name='medical_history')

    # Ocular history
    known_allergies = models.TextField(blank=True, help_text='Drug and other allergies')
    previous_eye_surgeries = models.TextField(blank=True)
    previous_eye_conditions = models.TextField(blank=True)
    spectacle_history = models.TextField(blank=True)

    # Systemic history
    chronic_conditions = models.TextField(blank=True, help_text='e.g. Diabetes, Hypertension')
    previous_surgeries = models.TextField(blank=True)
    current_medications = models.TextField(blank=True)
    family_ocular_history = models.TextField(blank=True)
    social_history = models.TextField(
        blank=True,
        help_text='Smoking, alcohol, occupation hazards'
    )
    systemic_history = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Medical History'
        verbose_name_plural = 'Medical Histories'

    def __str__(self):
        return f"Medical History — {self.patient}"


class ServiceTier(models.TextChoices):
    STANDARD   = 'STANDARD',   _('Standard')
    EXPRESS    = 'EXPRESS',    _('Express')
    FAST_TRACK = 'FAST_TRACK', _('Fast Track')
    VIP        = 'VIP',        _('VIP')


class VisitStatus(models.TextChoices):
    # ── Entry ──────────────────────────────────────────────────────────────
    REGISTERED       = 'REGISTERED',       _('Registered at Gate')
    AT_RECEPTIONIST  = 'AT_RECEPTIONIST',  _('At Receptionist (New Patient Registration)')
    AT_CASHIER       = 'AT_CASHIER',       _('At Cashier / Registration')
    # ── Clinical entry ─────────────────────────────────────────────────────
    PARAMETERS       = 'PARAMETERS',       _('At Parameters / Triage')
    WAITING          = 'WAITING',          _('Waiting for Doctor')
    TRIAGE           = 'TRIAGE',           _('In Triage')           # legacy compat
    # ── Insurance pathway ──────────────────────────────────────────────────
    INSURANCE_CONSULT = 'INSURANCE_CONSULT', _('Insurance Consultation Room')
    # ── Consultation ───────────────────────────────────────────────────────
    IN_CONSULTATION  = 'IN_CONSULTATION',  _('In Consultation')
    # ── Diagnostics ────────────────────────────────────────────────────────
    INVESTIGATION    = 'INVESTIGATION',    _('In Investigation')
    REFRACTION       = 'REFRACTION',       _('In Refraction')
    # ── Sub-specialties ────────────────────────────────────────────────────
    UVEITIS          = 'UVEITIS',          _('Uveitis Clinic')
    AT_RETINA        = 'AT_RETINA',        _('Retina Clinic')
    AT_GLAUCOMA      = 'AT_GLAUCOMA',      _('Glaucoma Clinic')
    AT_CATARACT      = 'AT_CATARACT',      _('Cataract / Surgical')
    AT_PEDIATRIC     = 'AT_PEDIATRIC',     _('Pediatric Ophthalmology')
    AT_NEURO         = 'AT_NEURO',         _('Neuro-ophthalmology')
    AT_OCULOPLASTY   = 'AT_OCULOPLASTY',   _('Oculoplastics')
    AT_CORNEA        = 'AT_CORNEA',        _('Cornea Clinic')
    LABORATORY       = 'LABORATORY',       _('In Laboratory')
    # ── Dispensing ─────────────────────────────────────────────────────────
    PHARMACY         = 'PHARMACY',         _('At Pharmacy')
    OPTICAL          = 'OPTICAL',          _('At Optical Shop')
    # ── Surgical pathway ───────────────────────────────────────────────────
    COUNSELING       = 'COUNSELING',       _('Surgical Counseling')
    WAITING_ADMISSION= 'WAITING_ADMISSION',_('Awaiting Admission')
    ADMITTED         = 'ADMITTED',         _('Admitted / IPD')
    PRE_OP           = 'PRE_OP',           _('Pre-operative Prep')
    IN_THEATRE       = 'IN_THEATRE',       _('In Theatre')
    POST_OP          = 'POST_OP',          _('Post-operative Recovery')
    # ── End states ─────────────────────────────────────────────────────────
    BILLING          = 'BILLING',          _('At Billing')
    COMPLETED        = 'COMPLETED',        _('Completed')
    DISCHARGED       = 'DISCHARGED',       _('Discharged')


# Mapping visit status → QMS ServiceType (for auto-routing)
VISIT_STATUS_TO_SERVICE_TYPE = {
    'AT_RECEPTIONIST':    'RECEPTIONIST',
    'AT_CASHIER':         'CASHIER',
    'INSURANCE_CONSULT':  'INSUR_CONSULT',
    'PARAMETERS':         'PARAMETERS',
    'WAITING':            'GENERAL',
    'IN_CONSULTATION':    'GENERAL',
    'INVESTIGATION':      'INVEST',
    'UVEITIS':            'UVEITIS',
    'REFRACTION':         'REFRACTION',
    # Sub-specialty routing — visit status updates when patient is referred to specialist
    'AT_RETINA':          'RETINA',
    'AT_GLAUCOMA':        'GLAUCOMA',
    'AT_CATARACT':        'CATARACT',
    'AT_PEDIATRIC':       'PEDIATRIC',
    'AT_NEURO':           'NEURO',
    'AT_OCULOPLASTY':     'OCULOPLASTY',
    'AT_CORNEA':          'CORNEA',
    'LABORATORY':         'LAB',
    'PHARMACY':           'PHARMACY',
    'OPTICAL':            'OPTICAL',
    'COUNSELING':         'COUNSEL',
    'WAITING_ADMISSION':  'ADMISSION',
    'IN_THEATRE':         'THEATRE',
    'BILLING':            'BILLING',
}


class BillingType(models.TextChoices):
    SELF_PAY  = 'SELF_PAY',  _('Self Pay (Cash / Card)')
    HMO       = 'HMO',       _('HMO / Managed Care')
    INSURANCE = 'INSURANCE', _('Insurance Company')
    WAIVER    = 'WAIVER',    _('Waiver / Exempt')
    FREE      = 'FREE',      _('Free / Subsidized')


class VisitType(models.TextChoices):
    NEW = 'NEW', _('New Patient')
    FOLLOW_UP = 'FOLLOW_UP', _('Follow-up')
    EMERGENCY = 'EMERGENCY', _('Emergency')
    REVIEW = 'REVIEW', _('Review')
    PROCEDURE = 'PROCEDURE', _('Procedure')


class Visit(AuditModel):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='visits')
    visit_number = models.CharField(max_length=20, unique=True, editable=False)
    visit_date = models.DateTimeField(auto_now_add=True)
    visit_type = models.CharField(max_length=20, choices=VisitType.choices, default=VisitType.NEW)
    department = models.ForeignKey(
        'departments.Department',
        on_delete=models.SET_NULL,
        null=True,
        related_name='visits',
    )
    attending_doctor = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='attended_visits',
    )
    triage_nurse = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='triaged_visits',
    )
    chief_complaint = models.TextField()
    # Vital signs stored as JSON for flexibility
    vital_signs = models.JSONField(
        default=dict,
        help_text='''Example: {
            "blood_pressure": "120/80",
            "pulse": 72,
            "temperature": 36.5,
            "weight": 70.0,
            "height": 175.0,
            "visual_acuity_right": "6/6",
            "visual_acuity_left": "6/9",
            "intraocular_pressure_right": 14,
            "intraocular_pressure_left": 15
        }'''
    )
    status = models.CharField(max_length=25, choices=VisitStatus.choices, default=VisitStatus.REGISTERED)
    service_tier = models.CharField(
        max_length=20, choices=ServiceTier.choices, default=ServiceTier.STANDARD,
        help_text='Patient service tier determines queue priority and care pathway'
    )
    billing_type = models.CharField(
        max_length=20, choices=BillingType.choices, default=BillingType.SELF_PAY,
        help_text='How this visit will be billed'
    )
    insurance_company = models.CharField(
        max_length=100, blank=True,
        help_text='Insurance company name if billing_type is INSURANCE'
    )
    insurance_policy_ref = models.CharField(
        max_length=100, blank=True,
        help_text='Insurance authorisation / policy reference number'
    )
    discharge_date = models.DateTimeField(null=True, blank=True)
    discharge_notes = models.TextField(blank=True)

    # Registration card questions
    previously_registered = models.BooleanField(
        null=True, blank=True,
        help_text='Has the patient consulted at this hospital before?'
    )
    has_referral_letter = models.BooleanField(
        null=True, blank=True,
        help_text='Does the patient have a referral letter from another doctor/hospital?'
    )
    referral_document = models.FileField(
        upload_to='patients/referrals/',
        null=True, blank=True,
        help_text='Scanned copy of the referral letter (uploaded by patient during pre-registration or by receptionist at desk)'
    )
    patient_signature = models.TextField(
        blank=True,
        help_text='Base64 PNG of patient digital signature from pre-registration'
    )

    # Consultation validity — set when patient pays registration fee
    # Patient may return within 15 days without paying again (FOLLOW_UP visit type)
    consultation_valid_until = models.DateField(
        null=True, blank=True,
        help_text='Consultation open period expires on this date (15 days from first payment)'
    )

    # Link to the appointment that triggered this visit (optional)
    appointment = models.OneToOneField(
        'appointments.Appointment',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='visit',
    )

    class Meta:
        ordering = ['-visit_date']
        verbose_name = 'Visit'
        verbose_name_plural = 'Visits'
        indexes = [
            # Dashboard queries visits by date constantly
            models.Index(fields=['visit_date'], name='visit_date_idx'),
            models.Index(fields=['patient', '-visit_date'], name='visit_patient_date_idx'),
        ]

    def __str__(self):
        return f"{self.visit_number} — {self.patient.full_name}"

    def save(self, *args, **kwargs):
        if not self.visit_number:
            self.visit_number = generate_visit_number()
        super().save(*args, **kwargs)

    def mark_consultation_paid(self):
        """
        Called when the patient pays their registration/consultation fee.
        Sets consultation_valid_until = today + 15 days.
        Within this window, returning patients are FOLLOW_UP (no new payment).
        """
        from datetime import date, timedelta
        self.consultation_valid_until = date.today() + timedelta(days=15)
        self.save(update_fields=['consultation_valid_until', 'updated_at'])

    @property
    def consultation_is_valid(self):
        """True if the patient is within their 15-day consultation window."""
        from datetime import date
        if not self.consultation_valid_until:
            return False
        return date.today() <= self.consultation_valid_until

    @property
    def consultation_days_remaining(self):
        """Number of days left in the consultation window. 0 if expired."""
        from datetime import date
        if not self.consultation_valid_until:
            return 0
        delta = (self.consultation_valid_until - date.today()).days
        return max(0, delta)

    @property
    def va_right(self):
        return self.vital_signs.get('visual_acuity_right', 'N/R')

    @property
    def va_left(self):
        return self.vital_signs.get('visual_acuity_left', 'N/R')

    @property
    def iop_right(self):
        return self.vital_signs.get('intraocular_pressure_right', 'N/R')

    @property
    def iop_left(self):
        return self.vital_signs.get('intraocular_pressure_left', 'N/R')


class PreRegistration(models.Model):
    """
    Stores patient pre-registration data in the database so any
    receptionist can look it up by code — session-independent.
    """
    code        = models.CharField(max_length=20, unique=True, db_index=True)
    data        = models.JSONField()
    created_at  = models.DateTimeField(auto_now_add=True)
    expires_at  = models.DateTimeField()
    is_used     = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'PreReg {self.code}'

    @property
    def is_expired(self):
        from django.utils import timezone
        return timezone.now() > self.expires_at
