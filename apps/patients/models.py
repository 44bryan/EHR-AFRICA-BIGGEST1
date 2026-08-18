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

    # ── Approximate DOB support ───────────────────────────────────────────────
    dob_is_approximate = models.BooleanField(
        default=False,
        help_text='True when DOB was estimated from year, year+month, or age only'
    )

    # ── Additional contact / address fields ───────────────────────────────────
    postal_code = models.CharField(max_length=10, blank=True, help_text='Zip / Postal code (optional)')
    phone_is_whatsapp = models.BooleanField(default=False, help_text='Phone number is also a WhatsApp number')

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
        prefix = '~' if self.dob_is_approximate else ''
        return f"{prefix}{a} year{'s' if a != 1 else ''}"

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

    @property
    def is_free_followup(self):
        """
        True if patient is within the 15-day consultation window.
        < 15 days since last payment → FREE, skip cashier, go directly to clinic.
        ≥ 15 days → expired, must pay again.
        """
        return self.has_active_consultation

    @property
    def consultation_visit_label(self):
        """
        Returns a human-readable label for the gatekeeper.
        e.g. 'FREE FOLLOW-UP (5 days ago — 10 days remaining)'
        """
        from datetime import date
        from apps.accounts.models import HospitalConfig
        active = self.active_consultation_visit
        if not active or not active.consultation_valid_until:
            return 'EXPIRED / NEW PATIENT'
        config = HospitalConfig.get()
        days_remaining = (active.consultation_valid_until - date.today()).days
        days_ago = config.consultation_days - days_remaining
        return (
            f'FREE FOLLOW-UP ({days_ago} day{"s" if days_ago != 1 else ""} ago'
            f' — {days_remaining} day{"s" if days_remaining != 1 else ""} remaining)'
        )


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
    # Room the patient was dispatched to at triage (set by nurse, filters doctor's queue)
    consultation_room = models.ForeignKey(
        'departments.ConsultationRoom',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='visits',
        help_text='Consultation room the triage nurse sent this patient to',
    )

    discharge_date = models.DateTimeField(null=True, blank=True)
    discharge_notes = models.TextField(blank=True)

    # ── Referral source ───────────────────────────────────────────────────────
    referral_hospital = models.CharField(
        max_length=150, blank=True,
        help_text='Name of hospital or doctor that referred this patient'
    )

    # ── Reception intake assessment (filled by receptionist at registration) ──
    intake_disability = models.CharField(
        max_length=200, blank=True,
        help_text='Disability status declared at intake (comma-separated)'
    )
    intake_eye_complaints = models.TextField(
        blank=True,
        help_text='Eye complaints ticked by receptionist at intake'
    )

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

    # Insurance pre-authorisation status (checked at triage for insured patients)
    PRE_AUTH_NOT_REQUIRED = 'NOT_REQUIRED'
    PRE_AUTH_PENDING      = 'PENDING'
    PRE_AUTH_OBTAINED     = 'OBTAINED'
    PRE_AUTH_DENIED       = 'DENIED'
    PRE_AUTH_STATUS_CHOICES = [
        (PRE_AUTH_NOT_REQUIRED, 'Not Required'),
        (PRE_AUTH_PENDING,      'Pending'),
        (PRE_AUTH_OBTAINED,     'Obtained'),
        (PRE_AUTH_DENIED,       'Denied / Rejected'),
    ]
    pre_auth_status = models.CharField(
        max_length=20, choices=PRE_AUTH_STATUS_CHOICES,
        default=PRE_AUTH_NOT_REQUIRED, blank=True,
        help_text='Insurance pre-authorisation status for this visit'
    )

    # Nursing notes recorded during triage
    nursing_notes = models.TextField(
        blank=True,
        help_text='Clinical observations and nursing assessment notes recorded at triage'
    )

    class Meta:
        ordering = ['-visit_date']
        verbose_name = 'Visit'
        verbose_name_plural = 'Visits'
        indexes = [
            # Dashboard queries visits by date constantly
            models.Index(fields=['visit_date'], name='visit_date_idx'),
            models.Index(fields=['patient', '-visit_date'], name='visit_patient_date_idx'),
            # Workflow dashboards filter by status (WAITING, IN_CONSULTATION, etc.)
            models.Index(fields=['status', 'visit_date'], name='visit_status_date_idx'),
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


class VisitTierChange(TimeStampedModel):
    """
    Audit log — every time a Visit's service_tier is changed by authorised staff.
    JCI compliance: COP / Governance trail for tier upgrades/downgrades.
    """
    visit      = models.ForeignKey(Visit, on_delete=models.CASCADE, related_name='tier_changes')
    old_tier   = models.CharField(max_length=12)
    new_tier   = models.CharField(max_length=12)
    changed_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, related_name='tier_changes_made'
    )
    reason     = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Visit Tier Change'
        verbose_name_plural = 'Visit Tier Changes'

    def __str__(self):
        return f'{self.visit.visit_number}: {self.old_tier} → {self.new_tier} ({self.changed_by})'


class PreRegistration(models.Model):
    """
    Stores patient pre-registration data submitted online BEFORE arrival.
    NOT a full patient record — only becomes an EHR record after gatekeeper
    confirms physical arrival and receptionist completes registration.
    """

    class Status(models.TextChoices):
        PENDING    = 'PENDING',    'Pending Arrival'
        ARRIVED    = 'ARRIVED',    'Arrived — Awaiting Registration'
        REGISTERED = 'REGISTERED', 'Registered'
        NO_SHOW    = 'NO_SHOW',    'Did Not Show'
        EXPIRED    = 'EXPIRED',    'Expired'

    code        = models.CharField(max_length=20, unique=True, db_index=True)
    data        = models.JSONField()
    visit_date  = models.DateField(null=True, blank=True, db_index=True,
                                   help_text='Date the patient intends to visit')
    status      = models.CharField(max_length=15, choices=Status.choices,
                                   default=Status.PENDING, db_index=True)
    arrived_at  = models.DateTimeField(null=True, blank=True)
    confirmed_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='confirmed_arrivals',
    )
    created_at  = models.DateTimeField(auto_now_add=True)
    expires_at  = models.DateTimeField()
    is_used     = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'PreReg {self.code} [{self.status}]'

    @property
    def is_expired(self):
        from django.utils import timezone
        return timezone.now() > self.expires_at

    def mark_arrived(self, confirmed_by_user):
        from django.utils import timezone
        self.status = self.Status.ARRIVED
        self.arrived_at = timezone.now()
        self.confirmed_by = confirmed_by_user
        self.save(update_fields=['status', 'arrived_at', 'confirmed_by'])


class PatientMedication(TimeStampedModel):
    """
    Chronic / long-term medications a patient is currently taking.
    Used for medication reconciliation at every consultation.
    """
    patient = models.ForeignKey(
        Patient, on_delete=models.CASCADE, related_name='medications'
    )
    drug_name = models.CharField(max_length=200, help_text='Generic or brand name of the drug')
    dose = models.CharField(max_length=100, blank=True, help_text='e.g. 500mg, 2 drops')
    frequency = models.CharField(max_length=100, blank=True, help_text='e.g. Once daily, BD, TDS')
    route = models.CharField(max_length=50, blank=True, help_text='e.g. Oral, Topical, IV')
    indication = models.CharField(max_length=200, blank=True, help_text='Condition this drug is for')
    start_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True, help_text='Is the patient currently on this medication?')
    prescribed_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='prescribed_medications',
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['drug_name']
        verbose_name = 'Patient Medication'
        verbose_name_plural = 'Patient Medications'

    def __str__(self):
        return f"{self.drug_name} — {self.patient.full_name}"


class PatientAllergy(TimeStampedModel):
    """
    Known drug and substance allergies for a patient.
    Shown as a red warning banner during drug prescribing.
    """

    class Severity(models.TextChoices):
        MILD = 'MILD', _('Mild')
        MODERATE = 'MODERATE', _('Moderate')
        SEVERE = 'SEVERE', _('Severe')
        ANAPHYLAXIS = 'ANAPHYLAXIS', _('Anaphylaxis')

    class AllergyType(models.TextChoices):
        DRUG = 'DRUG', _('Drug / Medication')
        FOOD = 'FOOD', _('Food')
        ENVIRONMENTAL = 'ENV', _('Environmental')
        LATEX = 'LATEX', _('Latex')
        OTHER = 'OTHER', _('Other')

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='allergies')
    allergen = models.CharField(max_length=200, help_text='Name of the drug or substance')
    allergy_type = models.CharField(
        max_length=10, choices=AllergyType.choices, default=AllergyType.DRUG
    )
    severity = models.CharField(
        max_length=15, choices=Severity.choices, default=Severity.MODERATE
    )
    reaction = models.CharField(
        max_length=200, blank=True,
        help_text='Nature of the reaction, e.g. rash, angioedema, bronchospasm'
    )
    date_noted = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    recorded_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='recorded_allergies'
    )

    class Meta:
        ordering = ['severity', 'allergen']
        verbose_name = 'Patient Allergy'
        verbose_name_plural = 'Patient Allergies'

    def __str__(self):
        return f"{self.allergen} ({self.get_severity_display()}) — {self.patient.full_name}"


class ProblemStatus(models.TextChoices):
    ACTIVE    = 'active',    _('Active')
    RESOLVED  = 'resolved',  _('Resolved')
    CHRONIC   = 'chronic',   _('Chronic / Ongoing')
    MONITORED = 'monitored', _('Under Monitoring')


class PatientProblem(TimeStampedModel):
    """
    Persistent problem list entry for a patient.
    Survives across consultations — active problems are always visible.
    """
    patient = models.ForeignKey(
        Patient, on_delete=models.CASCADE, related_name='problems'
    )
    problem = models.CharField(max_length=200, help_text='Brief problem description')
    icd10_code = models.CharField(
        max_length=10, blank=True,
        help_text='ICD-10 code if known, e.g. H40.1'
    )
    status = models.CharField(
        max_length=15, choices=ProblemStatus.choices, default=ProblemStatus.ACTIVE
    )
    onset_date = models.DateField(null=True, blank=True)
    resolved_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='recorded_problems'
    )

    class Meta:
        ordering = ['status', '-created_at']
        verbose_name = 'Patient Problem'
        verbose_name_plural = 'Patient Problems'

    def __str__(self):
        return f"{self.problem} ({self.get_status_display()}) — {self.patient.full_name}"

    @property
    def status_badge_class(self):
        return {
            ProblemStatus.ACTIVE:    'bg-danger',
            ProblemStatus.CHRONIC:   'bg-warning text-dark',
            ProblemStatus.MONITORED: 'bg-info text-dark',
            ProblemStatus.RESOLVED:  'bg-success',
        }.get(self.status, 'bg-secondary')


# ══════════════════════════════════════════════════════════════════════════════
# INFORMED CONSENT — JCI PFR.5 requirement
# ══════════════════════════════════════════════════════════════════════════════

class ConsentType(models.TextChoices):
    SURGICAL       = 'SURGICAL',       _('Surgical / Operative Consent')
    ANAESTHESIA    = 'ANAESTHESIA',    _('Anaesthesia Consent')
    INTRAVITREAL   = 'INTRAVITREAL',   _('Intravitreal Injection Consent')
    LASER          = 'LASER',          _('Laser Treatment Consent')
    PHOTOGRAPHY    = 'PHOTOGRAPHY',    _('Photography / Teaching Consent')
    DATA_RESEARCH  = 'DATA_RESEARCH',  _('Data Sharing / Research Consent')
    GENERAL        = 'GENERAL',        _('General Treatment Consent')
    PROCEDURE      = 'PROCEDURE',      _('Minor Procedure Consent')


class PatientConsent(AuditModel):
    """
    Informed consent record — JCI PFR.5.
    One record per consent event (surgery, anaesthesia, laser, etc.).
    """
    patient = models.ForeignKey(
        Patient, on_delete=models.CASCADE, related_name='consents'
    )
    consent_type = models.CharField(
        max_length=20, choices=ConsentType.choices, default=ConsentType.GENERAL
    )
    procedure_name = models.CharField(
        max_length=200,
        help_text='Specific procedure or treatment being consented to'
    )
    # Link to clinical context (optional but recommended)
    consultation = models.ForeignKey(
        'consultations.Consultation', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='consents'
    )
    # Who obtained the consent
    obtained_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True,
        related_name='consents_obtained',
        help_text='Doctor or nurse who obtained the consent'
    )
    signed_at = models.DateTimeField(
        default=None, null=True, blank=True,
        help_text='Date and time patient / guardian signed consent'
    )

    # Patient capacity and understanding
    patient_has_capacity = models.BooleanField(
        default=True,
        help_text='Patient has mental capacity to consent'
    )
    patient_representative = models.CharField(
        max_length=200, blank=True,
        help_text='Name of guardian/representative if patient lacks capacity'
    )
    relationship_to_patient = models.CharField(
        max_length=100, blank=True,
        help_text='e.g. Spouse, Parent, Legal Guardian'
    )

    # Content of consent discussion
    risks_explained = models.TextField(
        help_text='Risks of the procedure explained to patient'
    )
    benefits_explained = models.TextField(
        blank=True, help_text='Expected benefits explained'
    )
    alternatives_explained = models.TextField(
        blank=True, help_text='Alternative treatment options discussed'
    )
    questions_answered = models.BooleanField(
        default=False,
        help_text='Patient questions were answered satisfactorily'
    )
    interpreter_used = models.BooleanField(
        default=False,
        help_text='Interpreter was used during consent discussion'
    )
    interpreter_name = models.CharField(max_length=200, blank=True)

    # Witness
    witness_name = models.CharField(
        max_length=200, blank=True,
        help_text='Name of witness to the consent signing'
    )

    # Consent document scan (optional)
    consent_document = models.FileField(
        upload_to='consents/%Y/%m/', null=True, blank=True,
        help_text='Scanned signed consent form (PDF or image)'
    )

    # Validity
    is_valid = models.BooleanField(
        default=True,
        help_text='Set to False if consent was revoked or is no longer valid'
    )
    revoked_at = models.DateTimeField(null=True, blank=True)
    revocation_reason = models.TextField(blank=True)

    notes = models.TextField(blank=True)

    # Digital signature — base64 data URL captured on a canvas pad
    patient_signature = models.TextField(
        blank=True,
        help_text='Base64-encoded digital signature drawn by patient or representative'
    )

    class Meta:
        ordering = ['-signed_at', '-created_at']
        verbose_name = 'Patient Consent'
        verbose_name_plural = 'Patient Consents'

    def __str__(self):
        return (f"{self.get_consent_type_display()} — {self.patient.full_name} "
                f"({self.signed_at.strftime('%d/%m/%Y') if self.signed_at else 'Pending'})")

    def revoke(self, reason=''):
        from django.utils import timezone
        self.is_valid = False
        self.revoked_at = timezone.now()
        self.revocation_reason = reason
        self.save(update_fields=['is_valid', 'revoked_at', 'revocation_reason'])

    @property
    def status_label(self):
        if not self.signed_at:
            return 'Pending'
        if not self.is_valid:
            return 'Revoked'
        return 'Valid'

    @property
    def status_badge(self):
        if not self.signed_at:
            return 'bg-warning text-dark'
        if not self.is_valid:
            return 'bg-danger'
        return 'bg-success'

    @property
    def severity_badge_class(self):
        return {
            'MILD': 'bg-warning text-dark',
            'MODERATE': 'bg-orange text-white',
            'SEVERE': 'bg-danger',
            'ANAPHYLAXIS': 'bg-danger',
        }.get(self.severity, 'bg-secondary')


class PatientDocument(AuditModel):
    """
    Scanned or digital document attached to a patient record.
    e.g. referral letters, external lab results, old records.
    """

    class DocType(models.TextChoices):
        REFERRAL      = 'REFERRAL',      'Referral Letter'
        LAB_RESULT    = 'LAB_RESULT',    'External Lab Result'
        IMAGING       = 'IMAGING',       'Imaging / Radiology'
        PRESCRIPTION  = 'PRESCRIPTION',  'External Prescription'
        DISCHARGE     = 'DISCHARGE',     'Discharge Summary'
        ID_DOCUMENT   = 'ID_DOCUMENT',   'ID / Insurance Card'
        CONSENT       = 'CONSENT',       'Signed Consent'
        OTHER         = 'OTHER',         'Other'

    class Source(models.TextChoices):
        SCAN      = 'SCAN',      'Physical Scan'
        UPLOAD    = 'UPLOAD',    'Digital Upload'
        EMAIL     = 'EMAIL',     'Received by Email'
        WHATSAPP  = 'WHATSAPP',  'WhatsApp / Messaging'
        OTHER     = 'OTHER',     'Other'

    patient = models.ForeignKey(
        Patient, on_delete=models.CASCADE, related_name='documents'
    )
    title = models.CharField(max_length=200)
    document_type = models.CharField(
        max_length=20, choices=DocType.choices, default=DocType.OTHER
    )
    source = models.CharField(
        max_length=20, choices=Source.choices, default=Source.SCAN
    )
    description = models.TextField(blank=True)
    document_date = models.DateField(
        null=True, blank=True,
        help_text='Date on the original document (if known)'
    )
    file = models.FileField(upload_to='patient_documents/%Y/%m/')

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Patient Document'
        verbose_name_plural = 'Patient Documents'

    def __str__(self):
        return f"{self.title} — {self.patient.full_name} ({self.get_document_type_display()})"

    @property
    def filename(self):
        import os
        return os.path.basename(self.file.name) if self.file else ''

    @property
    def is_image(self):
        return self.filename.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp'))

    @property
    def is_pdf(self):
        return self.filename.lower().endswith('.pdf')


class RecordReleaseRequest(AuditModel):
    """
    Tracks every request to release / copy a patient's medical records
    to external parties — patient, insurer, lawyer, referring hospital, etc.
    JCI MOI.2 / HIPAA §164.524 compliant.
    """

    class RequestorType(models.TextChoices):
        PATIENT   = 'PATIENT',   'Patient / Next of Kin'
        INSURANCE = 'INSURANCE', 'Insurance Company'
        LEGAL     = 'LEGAL',     'Legal / Attorney'
        HOSPITAL  = 'HOSPITAL',  'Another Hospital / Referral'
        EMPLOYER  = 'EMPLOYER',  'Employer'
        OTHER     = 'OTHER',     'Other'

    class Status(models.TextChoices):
        PENDING    = 'PENDING',    'Pending Review'
        APPROVED   = 'APPROVED',   'Approved — Preparing'
        DISPATCHED = 'DISPATCHED', 'Dispatched / Released'
        REJECTED   = 'REJECTED',   'Rejected'

    patient                = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='release_requests')
    requestor_name         = models.CharField(max_length=200)
    requestor_type         = models.CharField(max_length=20, choices=RequestorType.choices)
    requestor_contact      = models.CharField(max_length=200, blank=True, help_text='Phone / email / address')
    purpose                = models.TextField()
    records_requested      = models.TextField(help_text='Which records: dates, visit types, specific docs')
    authorization_reference = models.CharField(max_length=200, blank=True,
                                               help_text='Auth letter ref, court order #, insurance ref')
    status                 = models.CharField(max_length=15, choices=Status.choices,
                                              default=Status.PENDING, db_index=True)
    processed_by           = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='processed_releases',
    )
    processed_at           = models.DateTimeField(null=True, blank=True)
    processing_notes       = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Record Release Request'

    def __str__(self):
        return f'Release #{self.pk} — {self.patient.full_name} ({self.get_status_display()})'
