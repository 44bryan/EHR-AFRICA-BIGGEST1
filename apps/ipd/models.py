"""
IPD - Inpatient Department
Admissions, ward/bed management, nursing notes, medication administration records.
"""
from django.db import models
from django.utils import timezone
from apps.core.models import TimeStampedModel, AuditModel


class WardType(models.TextChoices):
    GENERAL = 'GENERAL', 'General Ward'
    PRIVATE = 'PRIVATE', 'Private Room'
    SEMI_PRIVATE = 'SEMI', 'Semi-Private'
    ICU = 'ICU', 'ICU / High Dependency'
    DAY_CASE = 'DAY', 'Day Case / Surgical'


class BedStatus(models.TextChoices):
    AVAILABLE = 'AVAILABLE', 'Available'
    OCCUPIED = 'OCCUPIED', 'Occupied'
    MAINTENANCE = 'MAINTENANCE', 'Under Maintenance'
    RESERVED = 'RESERVED', 'Reserved'


class Ward(AuditModel):
    name = models.CharField(max_length=100)
    ward_type = models.CharField(max_length=20, choices=WardType.choices)
    floor = models.CharField(max_length=50, blank=True)
    total_beds = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    # Pricing (per night / per stay)
    price_per_night = models.DecimalField(max_digits=10, decimal_places=2, default=0,
        help_text='Bed/room fee charged per night of inpatient stay')
    description = models.TextField(blank=True, help_text='Room description, amenities, etc.')

    def __str__(self):
        return f"{self.name} ({self.get_ward_type_display()})"

    @property
    def available_beds(self):
        return self.beds.filter(status=BedStatus.AVAILABLE, is_deleted=False).count()


class Bed(AuditModel):
    ward = models.ForeignKey(Ward, on_delete=models.CASCADE, related_name='beds')
    bed_number = models.CharField(max_length=20)
    status = models.CharField(max_length=20, choices=BedStatus.choices, default=BedStatus.AVAILABLE)
    notes = models.TextField(blank=True)
    # Per-bed price override (null = use ward price_per_night)
    price_override = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
        help_text='Leave blank to use ward price. Set for VIP rooms with individual pricing.')

    @property
    def nightly_rate(self):
        """Effective nightly rate: bed override takes precedence over ward rate."""
        if self.price_override is not None:
            return self.price_override
        return self.ward.price_per_night

    class Meta:
        unique_together = ('ward', 'bed_number')
        ordering = ['ward', 'bed_number']

    def __str__(self):
        return f"{self.ward.name} - Bed {self.bed_number}"


class AdmissionStatus(models.TextChoices):
    ADMITTED    = 'ADMITTED',    'Admitted'
    POST_OP     = 'POST_OP',     'Post-Operative'
    DISCHARGED  = 'DISCHARGED',  'Discharged'
    TRANSFERRED = 'TRANSFERRED', 'Transferred'


class AdmissionType(models.TextChoices):
    ELECTIVE  = 'ELECTIVE',  'Elective (Planned)'
    EMERGENCY = 'EMERGENCY', 'Emergency'
    DAY_CASE  = 'DAY_CASE',  'Day Case / Same-Day Surgery'
    TRANSFER  = 'TRANSFER',  'Transfer from Another Facility'


class BloodGroup(models.TextChoices):
    A_POS  = 'A+',  'A+'
    A_NEG  = 'A-',  'A-'
    B_POS  = 'B+',  'B+'
    B_NEG  = 'B-',  'B-'
    AB_POS = 'AB+', 'AB+'
    AB_NEG = 'AB-', 'AB-'
    O_POS  = 'O+',  'O+'
    O_NEG  = 'O-',  'O-'
    UNKNOWN = 'UNKNOWN', 'Not Known'


class Admission(AuditModel):
    admission_number = models.CharField(max_length=30, unique=True)
    patient = models.ForeignKey(
        'patients.Patient', on_delete=models.PROTECT, related_name='admissions'
    )
    bed = models.ForeignKey(Bed, on_delete=models.PROTECT, related_name='admissions')
    admitting_doctor = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='admissions_made'
    )
    primary_nurse = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='primary_nurse_admissions',
        help_text='Nurse assigned as primary carer for this admission',
    )
    surgical_booking = models.ForeignKey(
        'SurgicalBooking', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='admissions'
    )
    admission_date = models.DateTimeField(default=timezone.now)
    expected_discharge_date = models.DateField(
        null=True, blank=True,
        help_text='Planned discharge date — JCI ACC.1.1 (Length of Stay planning)'
    )
    discharge_date = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=AdmissionStatus.choices, default=AdmissionStatus.ADMITTED)
    admission_type = models.CharField(
        max_length=20, choices=AdmissionType.choices, default=AdmissionType.ELECTIVE
    )
    diagnosis_on_admission = models.TextField()
    discharge_summary = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    # ── Clinical fields required for ophthalmology surgery ─────────────────
    blood_group = models.CharField(
        max_length=10, choices=BloodGroup.choices, default=BloodGroup.UNKNOWN,
        help_text='Blood group + Rhesus — required before theatre (transfusion planning)'
    )
    height_cm = models.DecimalField(
        max_digits=5, decimal_places=1, null=True, blank=True,
        help_text='Height in cm — used for anaesthesia drug dosing'
    )
    weight_kg = models.DecimalField(
        max_digits=5, decimal_places=1, null=True, blank=True,
        help_text='Weight in kg — used for anaesthesia drug dosing'
    )
    is_readmission = models.BooleanField(
        default=False,
        help_text='Readmitted within 30 days for same condition'
    )

    class Meta:
        ordering = ['-admission_date']

    def __str__(self):
        return f"Admission {self.admission_number} - {self.patient.full_name}"

    def save(self, *args, **kwargs):
        if not self.admission_number:
            today = timezone.localdate()
            count = Admission.objects.filter(admission_date__year=today.year).count() + 1
            self.admission_number = f"IPD-{today.strftime('%Y')}-{count:04d}"
        super().save(*args, **kwargs)

    def discharge(self, summary=''):
        self.status = AdmissionStatus.DISCHARGED
        self.discharge_date = timezone.now()
        self.discharge_summary = summary
        self.bed.status = BedStatus.AVAILABLE
        self.bed.save()
        self.save()

    @property
    def los_days(self):
        """Length of stay in days"""
        end = self.discharge_date or timezone.now()
        return (end - self.admission_date).days


class SurgeryType(models.TextChoices):
    """Standard ophthalmic surgical procedures — dropdown list used across the system."""
    # Cataract
    PHACO              = 'PHACO',              'Phacoemulsification (Phaco) + IOL'
    ECCE               = 'ECCE',               'ECCE (Extracapsular Cataract Extraction)'
    ICCE               = 'ICCE',               'ICCE (Intracapsular Cataract Extraction)'
    SICS               = 'SICS',               'SICS (Small-Incision Cataract Surgery)'
    IOL_EXCHANGE       = 'IOL_EXCHANGE',       'IOL Exchange / Repositioning'
    # Glaucoma
    TRABECULECTOMY     = 'TRABECULECTOMY',     'Trabeculectomy'
    TUBE_SHUNT         = 'TUBE_SHUNT',         'Tube Shunt / Drainage Implant'
    CYCLOPHOTOCOAG     = 'CYCLOPHOTOCOAG',     'Cyclo-photocoagulation (CPC)'
    LASER_TRABECULO    = 'LASER_TRABECULO',    'Selective Laser Trabeculoplasty (SLT)'
    PI                 = 'PI',                 'Peripheral Iridotomy (PI)'
    # Retina / Vitreoretinal
    VITRECTOMY         = 'VITRECTOMY',         'Pars Plana Vitrectomy (PPV)'
    BUCKLE             = 'BUCKLE',             'Scleral Buckle / Encirclement'
    ANTI_VEGF          = 'ANTI_VEGF',          'Intravitreal Anti-VEGF Injection'
    LASER_RETINA       = 'LASER_RETINA',       'Laser Photocoagulation (Retina)'
    # Cornea / External
    PKP                = 'PKP',                'Penetrating Keratoplasty (PKP)'
    DSAEK              = 'DSAEK',              'DSAEK / DMEK (Endothelial Keratoplasty)'
    PTERYGIUM_EXC      = 'PTERYGIUM_EXC',      'Pterygium Excision + Graft'
    KERATOCONUS        = 'KERATOCONUS',        'Corneal Collagen Cross-Linking (CXL)'
    # Oculoplastics
    ENTROPION_REPAIR   = 'ENTROPION_REPAIR',   'Entropion Repair'
    ECTROPION_REPAIR   = 'ECTROPION_REPAIR',   'Ectropion Repair'
    PTOSIS_REPAIR      = 'PTOSIS_REPAIR',      'Ptosis Repair'
    DCR                = 'DCR',                'Dacryocystorhinostomy (DCR)'
    ENUCLEATION        = 'ENUCLEATION',        'Enucleation / Evisceration'
    EXENTERATION       = 'EXENTERATION',       'Orbital Exenteration'
    CHALAZION_EXC      = 'CHALAZION_EXC',      'Chalazion Excision'
    LID_TUMOUR         = 'LID_TUMOUR',         'Eyelid Tumour Excision'
    # Squint / Paediatric
    STRABISMUS         = 'STRABISMUS',         'Strabismus Surgery (Squint Correction)'
    PROBING            = 'PROBING',            'Nasolacrimal Duct Probing'
    # Other
    FOREIGN_BODY_REMOVAL = 'FB_REMOVAL',       'Intraocular Foreign Body Removal'
    EUA                = 'EUA',                'Examination Under Anaesthesia (EUA)'
    OTHER              = 'OTHER',              'Other (specify in notes)'


class SurgicalBookingStatus(models.TextChoices):
    PENDING_PAYMENT  = 'PENDING_PAYMENT',  'Pending Payment / Deposit'
    CONFIRMED        = 'CONFIRMED',        'Confirmed'
    SCHEDULED        = 'SCHEDULED',        'Scheduled'
    COMPLETED        = 'COMPLETED',        'Completed'
    CANCELLED        = 'CANCELLED',        'Cancelled'
    RESCHEDULED      = 'RESCHEDULED',      'Rescheduled'


class SurgicalBooking(AuditModel):
    """
    Pre-surgical booking record created by the Admission Officer after
    the patient has been counseled.

    Flow:
      Doctor recommends surgery (consultation) →
      Counseling Nurse (pre-op counseling, consent) →
      Admission Officer creates SurgicalBooking →
      Patient knows what to pay + when to come.
    """
    booking_number = models.CharField(max_length=30, unique=True, editable=False)
    patient = models.ForeignKey(
        'patients.Patient', on_delete=models.PROTECT, related_name='surgical_bookings'
    )
    consultation = models.ForeignKey(
        'consultations.Consultation',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='surgical_bookings',
    )
    surgeon = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='surgical_bookings_as_surgeon'
    )
    admission_officer = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='surgical_bookings_created'
    )

    # Procedure details — use the SurgeryType dropdown; free-text override in procedure_notes
    procedure = models.CharField(
        max_length=50,
        choices=SurgeryType.choices,
        default=SurgeryType.OTHER,
        help_text='Select procedure type from the list',
    )
    procedure_notes = models.CharField(
        max_length=200, blank=True,
        help_text='Additional details or specify if "Other" selected',
    )
    eye_laterality = models.CharField(max_length=20, choices=[
        ('RE', 'Right Eye (RE)'),
        ('LE', 'Left Eye (LE)'),
        ('BE', 'Both Eyes (BE)'),
    ], blank=True)
    anaesthesia_type = models.CharField(max_length=30, choices=[
        ('LOCAL', 'Local (Peribulbar / Topical)'),
        ('GENERAL', 'General Anaesthesia (GA)'),
        ('SEDATION', 'Monitored Sedation'),
    ], blank=True)
    theatre = models.CharField(max_length=100, blank=True)

    # Scheduling
    surgery_date = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=SurgicalBookingStatus.choices,
        default=SurgicalBookingStatus.PENDING_PAYMENT
    )

    # Pre-operative requirements
    pre_op_requirements = models.TextField(blank=True,
        help_text='Blood work, fasting instructions, medications to stop, etc.')
    # e.g. {"CBC": true, "BGL": true, "ECG": false, "chest_xray": false}
    pre_op_checklist = models.JSONField(default=dict, blank=True)

    # Surgery category (for statistics)
    surgery_category = models.CharField(max_length=50, choices=[
        ('CATARACT',     'Cataract Surgery'),
        ('RETINA',       'Retina / Vitreoretinal'),
        ('GLAUCOMA',     'Glaucoma Surgery'),
        ('CORNEA',       'Corneal Transplant / Keratoplasty'),
        ('OCULOPLASTY',  'Oculoplastics / Lid Surgery'),
        ('STRABISMUS',   'Strabismus / Squint'),
        ('PTERYGIUM',    'Pterygium Excision'),
        ('LACRIMAL',     'Lacrimal / DCR'),
        ('CHALAZION',    'Chalazion / Lid Lesion'),
        ('TRAUMA',       'Ocular Trauma Repair'),
        ('TUMOUR',       'Tumour / Orbital'),
        ('OTHER',        'Other Procedure'),
    ], blank=True)

    # Payment
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    deposit_required = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    deposit_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payment_notes = models.TextField(blank=True)
    # Link to billing invoice (auto-created when booking confirmed)
    invoice = models.OneToOneField(
        'billing.Invoice', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='surgical_booking'
    )

    # Counseling record (from counseling nurse)
    counseling_notes = models.TextField(blank=True)
    consent_signed = models.BooleanField(default=False)
    consent_date = models.DateTimeField(null=True, blank=True)

    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Surgical Booking'
        verbose_name_plural = 'Surgical Bookings'

    def __str__(self):
        return f"SB-{self.booking_number} — {self.patient.full_name} ({self.procedure})"

    @property
    def balance_due(self):
        return max(self.deposit_required - self.deposit_paid, 0)

    @property
    def is_fully_deposited(self):
        return self.deposit_paid >= self.deposit_required

    def save(self, *args, **kwargs):
        if not self.booking_number:
            today = timezone.localdate()
            count = SurgicalBooking.objects.filter(
                created_at__year=today.year
            ).count() + 1
            self.booking_number = f"SB-{today.strftime('%Y')}-{count:04d}"
        super().save(*args, **kwargs)


# ── Surgical Outcome Tracking ─────────────────────────────────────────────────

class OutcomeGrade(models.TextChoices):
    EXCELLENT   = 'EXCELLENT',   'Excellent — VA ≥ 6/18'
    GOOD        = 'GOOD',        'Good — VA 6/36 to 6/60'
    FAIR        = 'FAIR',        'Fair — VA < 6/60'
    POOR        = 'POOR',        'Poor — No visual gain'
    COMPLICATED = 'COMPLICATED', 'Complicated — Adverse outcome'


class SurgicalOutcome(AuditModel):
    """
    Pre/post-operative visual outcome record.
    Core quality metric for a specialist eye hospital — tracks VA and IOP
    before and after every surgical procedure.
    """
    booking  = models.OneToOneField(SurgicalBooking, on_delete=models.CASCADE, related_name='outcome')
    patient  = models.ForeignKey('patients.Patient', on_delete=models.PROTECT, related_name='surgical_outcomes')
    surgeon  = models.ForeignKey(
        'accounts.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='surgical_outcomes_recorded'
    )
    surgery_date = models.DateField(null=True, blank=True)

    # Pre-operative vision
    pre_va_right  = models.CharField(max_length=20, blank=True, verbose_name='Pre-op VA (Right Eye)')
    pre_va_left   = models.CharField(max_length=20, blank=True, verbose_name='Pre-op VA (Left Eye)')
    pre_iop_right = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, verbose_name='Pre-op IOP Right (mmHg)')
    pre_iop_left  = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, verbose_name='Pre-op IOP Left (mmHg)')

    # Post-operative vision (day 1 / discharge)
    post_va_right  = models.CharField(max_length=20, blank=True, verbose_name='Post-op VA (Right Eye)')
    post_va_left   = models.CharField(max_length=20, blank=True, verbose_name='Post-op VA (Left Eye)')
    post_iop_right = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, verbose_name='Post-op IOP Right (mmHg)')
    post_iop_left  = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, verbose_name='Post-op IOP Left (mmHg)')

    outcome_grade                = models.CharField(max_length=20, choices=OutcomeGrade.choices, blank=True)
    intraoperative_complications = models.TextField(blank=True)
    postoperative_complications  = models.TextField(blank=True)
    follow_up_date               = models.DateField(null=True, blank=True)
    notes                        = models.TextField(blank=True)
    recorded_by                  = models.ForeignKey(
        'accounts.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='outcomes_entered'
    )

    class Meta:
        ordering = ['-surgery_date', '-created_at']
        verbose_name = 'Surgical Outcome'

    def __str__(self):
        return f"Outcome — {self.patient.full_name} ({self.booking.get_procedure_display()})"


class NursingNote(AuditModel):
    admission = models.ForeignKey(Admission, on_delete=models.CASCADE, related_name='nursing_notes')
    note_time = models.DateTimeField(default=timezone.now)
    note_type = models.CharField(max_length=50, choices=[
        ('ASSESSMENT', 'Nursing Assessment'),
        ('OBSERVATION', 'Observation'),
        ('MEDICATION', 'Medication Note'),
        ('PROCEDURE', 'Procedure Note'),
        ('HANDOVER', 'Handover'),
        ('OTHER', 'Other'),
    ], default='OBSERVATION')
    content = models.TextField()
    vital_signs = models.JSONField(default=dict, blank=True)
    nurse = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='nursing_notes'
    )

    class Meta:
        ordering = ['-note_time']

    def __str__(self):
        return f"{self.get_note_type_display()} - {self.admission.patient.full_name} ({self.note_time.strftime('%d/%m/%Y %H:%M')})"


class MAREntry(TimeStampedModel):
    """Medication Administration Record"""
    admission = models.ForeignKey(Admission, on_delete=models.CASCADE, related_name='mar_entries')
    drug_name = models.CharField(max_length=200)
    dose = models.CharField(max_length=100)
    route = models.CharField(max_length=50)
    frequency = models.CharField(max_length=100)
    scheduled_time = models.DateTimeField()
    administered_time = models.DateTimeField(null=True, blank=True)
    administered_by = models.ForeignKey(
        'accounts.User', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='mar_administered'
    )
    status = models.CharField(max_length=20, choices=[
        ('SCHEDULED', 'Scheduled'),
        ('GIVEN', 'Given'),
        ('MISSED', 'Missed'),
        ('REFUSED', 'Refused'),
        ('HELD', 'Held'),
    ], default='SCHEDULED')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['scheduled_time']


# ══════════════════════════════════════════════════════════════════════════════
# THEATRE / OPERATING ROOM MODULE
# ══════════════════════════════════════════════════════════════════════════════

class TheatreSessionStatus(models.TextChoices):
    SCHEDULED   = 'SCHEDULED',   'Scheduled'
    IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
    COMPLETED   = 'COMPLETED',   'Completed'
    CANCELLED   = 'CANCELLED',   'Cancelled'


class ProcedureOutcome(models.TextChoices):
    SUCCESS       = 'SUCCESS',     'Successful'
    COMPLICATION  = 'COMPLICATION','Complication (documented)'
    ABANDONED     = 'ABANDONED',   'Procedure Abandoned'
    CONVERTED     = 'CONVERTED',   'Converted to GA'


class TheatreSession(AuditModel):
    """
    A Theatre/OR list for one day — may contain multiple procedures.
    Created by the Admission Officer or Theatre Nurse.
    """
    session_number = models.CharField(max_length=30, unique=True, editable=False)
    session_date   = models.DateField(default=timezone.localdate)
    theatre_name   = models.CharField(
        max_length=100, default='Main Theatre',
        help_text='e.g. Main Theatre, Minor Theatre, Laser Suite'
    )
    start_time = models.TimeField(null=True, blank=True)
    end_time   = models.TimeField(null=True, blank=True)
    status     = models.CharField(
        max_length=20, choices=TheatreSessionStatus.choices,
        default=TheatreSessionStatus.SCHEDULED
    )

    # Theatre team — all FK to real User accounts for workload reporting
    lead_surgeon = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='theatre_sessions_led'
    )
    second_surgeon = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='theatre_sessions_second_surgeon',
        help_text='Assistant surgeon / co-surgeon'
    )
    anaesthetist = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='theatre_sessions_anaesthesia',
        limit_choices_to={'role': 'anaesthetist'},
    )
    anaesthetist_name = models.CharField(max_length=200, blank=True,
        help_text='Fallback text if anaesthetist has no system account')
    scrub_nurse = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='theatre_sessions_scrub'
    )
    circulating_nurse = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='theatre_sessions_circulating'
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-session_date', 'start_time']
        verbose_name = 'Theatre Session'
        verbose_name_plural = 'Theatre Sessions'

    def __str__(self):
        return f"TS-{self.session_number} | {self.theatre_name} | {self.session_date}"

    def save(self, *args, **kwargs):
        if not self.session_number:
            today = timezone.localdate()
            count = TheatreSession.objects.filter(
                session_date__year=today.year
            ).count() + 1
            self.session_number = f"{today.strftime('%Y%m%d')}-{count:03d}"
        super().save(*args, **kwargs)

    @property
    def total_procedures(self):
        return self.procedures.count()

    @property
    def completed_procedures(self):
        return self.procedures.filter(outcome__isnull=False).exclude(outcome='').count()


class TheatreProcedure(AuditModel):
    """
    Individual surgical procedure performed on one patient during a theatre session.
    Records WHO Safety Checklist, IOL details (cataract), intraop findings, outcome.
    """
    session         = models.ForeignKey(
        TheatreSession, on_delete=models.CASCADE, related_name='procedures'
    )
    surgical_booking = models.ForeignKey(
        SurgicalBooking, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='theatre_procedures'
    )
    patient = models.ForeignKey(
        'patients.Patient', on_delete=models.PROTECT, related_name='theatre_procedures'
    )
    surgeon = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='procedures_performed'
    )
    # Procedure
    procedure     = models.CharField(max_length=50, choices=SurgeryType.choices)
    procedure_notes = models.CharField(max_length=300, blank=True)
    eye_laterality  = models.CharField(max_length=20, choices=[
        ('RE', 'Right Eye (RE)'),
        ('LE', 'Left Eye (LE)'),
        ('BE', 'Both Eyes (BE)'),
    ], blank=True)
    anaesthesia_type = models.CharField(max_length=30, choices=[
        ('LOCAL',    'Local (Peribulbar / Topical)'),
        ('GENERAL',  'General Anaesthesia (GA)'),
        ('SEDATION', 'Monitored Sedation'),
    ], blank=True)
    position_on_list = models.PositiveSmallIntegerField(default=1,
        help_text='Order on the surgical list for this session')

    # Timing
    knife_time  = models.TimeField(null=True, blank=True, help_text='Incision start time')
    closure_time= models.TimeField(null=True, blank=True, help_text='Wound closure time')

    # ── IOL Tracking (Cataract) ───────────────────────────────────────────────
    iol_model      = models.CharField(max_length=200, blank=True)
    iol_power      = models.CharField(max_length=50, blank=True, help_text='e.g. +22.50 D')
    iol_lot_number = models.CharField(max_length=100, blank=True)
    iol_type       = models.CharField(max_length=100, blank=True,
        help_text='e.g. Monofocal, Toric, Multifocal, PMMA, Acrylic')

    # ── WHO Surgical Safety Checklist ─────────────────────────────────────────
    # Sign In (before anaesthesia)
    sign_in_done            = models.BooleanField(default=False)
    sign_in_time            = models.TimeField(null=True, blank=True)
    sign_in_identity_confirmed = models.BooleanField(default=False)
    sign_in_site_marked     = models.BooleanField(default=False)
    sign_in_anaesthesia_safe= models.BooleanField(default=False)
    sign_in_pulse_oximeter  = models.BooleanField(default=False)
    sign_in_allergies       = models.BooleanField(default=False)

    # Time Out (before skin incision)
    time_out_done           = models.BooleanField(default=False)
    time_out_time           = models.TimeField(null=True, blank=True)
    time_out_team_introduced= models.BooleanField(default=False)
    time_out_site_confirmed = models.BooleanField(default=False)
    time_out_antibiotics    = models.BooleanField(default=False)
    time_out_imaging_displayed = models.BooleanField(default=False)

    # Sign Out (before patient leaves theatre)
    sign_out_done           = models.BooleanField(default=False)
    sign_out_time           = models.TimeField(null=True, blank=True)
    sign_out_instrument_count_correct = models.BooleanField(default=False)
    sign_out_specimen_labelled = models.BooleanField(default=False)
    sign_out_equipment_issues  = models.BooleanField(default=False)
    sign_out_recovery_plan     = models.BooleanField(default=False)

    # ── Intraoperative ────────────────────────────────────────────────────────
    intraop_findings = models.TextField(blank=True,
        help_text='Intraoperative findings, observations')
    complications    = models.TextField(blank=True,
        help_text='Any complications encountered and management')

    # ── Outcome ───────────────────────────────────────────────────────────────
    outcome    = models.CharField(
        max_length=20, choices=ProcedureOutcome.choices, blank=True
    )
    post_op_notes = models.TextField(blank=True,
        help_text='Post-operative instructions and notes')
    post_op_medications = models.TextField(blank=True,
        help_text='Post-op medications prescribed (eye drops, systemic)')

    class Meta:
        ordering = ['session', 'position_on_list']
        verbose_name = 'Theatre Procedure'

    def __str__(self):
        return (f"{self.patient.full_name} — {self.get_procedure_display()} "
                f"({self.session.session_date})")

    @property
    def who_complete(self):
        return self.sign_in_done and self.time_out_done and self.sign_out_done

    @property
    def duration_minutes(self):
        if self.knife_time and self.closure_time:
            from datetime import datetime, date
            d = date.today()
            dt_start = datetime.combine(d, self.knife_time)
            dt_end   = datetime.combine(d, self.closure_time)
            delta    = dt_end - dt_start
            return int(delta.total_seconds() / 60)
        return None


# ══════════════════════════════════════════════════════════════════════════════
# WARD ROUNDS
# ══════════════════════════════════════════════════════════════════════════════

class WardRound(AuditModel):
    """
    Daily ward round note (SOAP format) written by a doctor for an admitted patient.
    """
    admission  = models.ForeignKey(
        Admission, on_delete=models.CASCADE, related_name='ward_rounds'
    )
    round_date = models.DateField(default=timezone.localdate)
    round_time = models.TimeField(null=True, blank=True)
    doctor     = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='ward_rounds_written'
    )

    # SOAP Notes
    subjective = models.TextField(blank=True,
        help_text='Patient complaints, how patient feels today')
    objective  = models.TextField(blank=True,
        help_text='Examination findings, vital signs review')
    assessment = models.TextField(blank=True,
        help_text='Clinical assessment, diagnosis, progress')
    plan       = models.TextField(
        help_text='Treatment plan, investigations ordered, medication changes, next steps'
    )

    # Quick vitals for today
    vital_signs = models.JSONField(default=dict, blank=True,
        help_text='{"bp_systolic":120,"bp_diastolic":80,"pulse":72,"temp":36.8,"spo2":98}')

    # Ocular vitals (ward rounds often check operated eye)
    va_re  = models.CharField(max_length=20, blank=True, help_text='Visual Acuity RE post-op')
    va_le  = models.CharField(max_length=20, blank=True, help_text='Visual Acuity LE post-op')
    iop_re = models.CharField(max_length=20, blank=True, help_text='IOP RE post-op')
    iop_le = models.CharField(max_length=20, blank=True, help_text='IOP LE post-op')

    # Discharge readiness
    is_discharge_ready = models.BooleanField(default=False,
        help_text='Mark true when patient is ready for discharge')
    discharge_plan     = models.TextField(blank=True,
        help_text='Discharge instructions, follow-up date, medications to take home')

    class Meta:
        ordering = ['-round_date', '-round_time']
        verbose_name = 'Ward Round'
        verbose_name_plural = 'Ward Rounds'

    def __str__(self):
        return (f"Ward Round — {self.admission.patient.full_name} "
                f"— {self.round_date} by Dr. {self.doctor.full_name}")


# ══════════════════════════════════════════════════════════════════════════════
# ANAESTHETIC RECORD — JCI ASC Standards
# ══════════════════════════════════════════════════════════════════════════════

class ASAGrade(models.TextChoices):
    I   = 'I',   'ASA I — Normal healthy patient'
    II  = 'II',  'ASA II — Mild systemic disease, no functional limitation'
    III = 'III', 'ASA III — Severe systemic disease with functional limitation'
    IV  = 'IV',  'ASA IV — Severe systemic disease, constant threat to life'
    V   = 'V',   'ASA V — Moribund, not expected to survive 24h without operation'
    E   = 'E',   'E — Emergency (added to any grade, e.g. IIE, IIIE)'


class AnaestheticRecord(AuditModel):
    """
    Pre-operative anaesthetic assessment + intraoperative monitoring summary.
    Completed by the Anaesthetist before and during surgery.
    JCI ASC.5 / ASC.6 requirements.
    """
    surgical_booking = models.ForeignKey(
        SurgicalBooking, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='anaesthetic_records'
    )
    theatre_procedure = models.ForeignKey(
        TheatreProcedure, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='anaesthetic_records'
    )
    patient = models.ForeignKey(
        'patients.Patient', on_delete=models.PROTECT, related_name='anaesthetic_records'
    )
    anaesthetist = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True,
        related_name='anaesthetic_records_authored'
    )

    # ── Pre-operative Assessment ───────────────────────────────────────────────
    asa_grade = models.CharField(
        max_length=5, choices=ASAGrade.choices, blank=True,
        help_text='ASA Physical Status Classification'
    )
    weight_kg = models.FloatField(null=True, blank=True)
    height_cm = models.FloatField(null=True, blank=True)

    # Airway assessment
    mallampati_score = models.CharField(
        max_length=5, blank=True,
        help_text='Mallampati score: I, II, III, or IV'
    )
    mouth_opening = models.CharField(max_length=50, blank=True,
        help_text='e.g. >4 cm, <3 cm')
    neck_mobility = models.CharField(max_length=50, blank=True,
        help_text='e.g. Full, Limited')
    thyromental_distance = models.CharField(max_length=50, blank=True,
        help_text='e.g. >6.5 cm')
    difficult_airway_predicted = models.BooleanField(
        default=False, help_text='Anticipated difficult airway')
    airway_notes = models.TextField(blank=True)

    # Fasting
    last_oral_intake = models.DateTimeField(null=True, blank=True,
        help_text='Date/time of last oral intake (food or fluid)')
    fasting_adequate = models.BooleanField(
        null=True, blank=True,
        help_text='True = fasting criteria met before anaesthesia'
    )

    # Allergy / drug review
    allergies_reviewed = models.BooleanField(default=False)
    anaesthetic_allergies = models.TextField(blank=True,
        help_text='Known allergies relevant to anaesthesia (latex, drugs, etc.)')
    current_medications_reviewed = models.BooleanField(default=False)
    medications_to_continue = models.TextField(blank=True)
    medications_to_stop = models.TextField(blank=True)

    # Pre-medication
    premedication_given = models.TextField(blank=True,
        help_text='Pre-operative medications administered (drug, dose, time)')

    # Consent
    anaesthetic_consent_obtained = models.BooleanField(default=False)
    pre_op_assessment_completed = models.DateTimeField(null=True, blank=True)

    # ── Anaesthetic Plan ──────────────────────────────────────────────────────
    anaesthesia_type = models.CharField(max_length=30, choices=[
        ('LOCAL',     'Local (Peribulbar / Sub-Tenon / Topical)'),
        ('REGIONAL',  'Regional Block'),
        ('GENERAL',   'General Anaesthesia (GA)'),
        ('SEDATION',  'Monitored Anaesthesia Care (MAC / Sedation)'),
        ('COMBINED',  'Combined GA + Regional'),
    ], blank=True)
    planned_agents = models.TextField(blank=True,
        help_text='Planned induction and maintenance agents')

    # ── Intraoperative Record ─────────────────────────────────────────────────
    induction_agent = models.CharField(max_length=200, blank=True,
        help_text='e.g. Propofol 2mg/kg IV, Ketamine 1.5mg/kg')
    induction_dose = models.CharField(max_length=100, blank=True)
    maintenance_agent = models.CharField(max_length=200, blank=True,
        help_text='e.g. Sevoflurane 2% in O2/Air, Propofol TIVA')
    airway_management = models.CharField(max_length=100, blank=True,
        help_text='e.g. ETT size 7.0, LMA #4, Face Mask')
    analgesics_used = models.TextField(blank=True,
        help_text='Analgesics given intraoperatively')
    muscle_relaxants_used = models.TextField(blank=True)
    reversal_agents = models.TextField(blank=True)

    anaesthesia_start_time = models.TimeField(null=True, blank=True)
    anaesthesia_end_time   = models.TimeField(null=True, blank=True)
    total_duration_minutes = models.PositiveIntegerField(null=True, blank=True)

    # Monitoring
    monitoring_notes = models.TextField(blank=True,
        help_text='Vital signs trends, any significant intraop events')
    estimated_blood_loss_ml = models.PositiveIntegerField(null=True, blank=True)
    iv_fluids_given = models.TextField(blank=True,
        help_text='Type and volume of IV fluids administered')
    urine_output_ml = models.PositiveIntegerField(null=True, blank=True)
    blood_products_given = models.TextField(blank=True)

    intraoperative_complications = models.TextField(blank=True,
        help_text='Any complications encountered intraoperatively')

    # ── Post-operative Recovery ───────────────────────────────────────────────
    recovery_start_time = models.TimeField(null=True, blank=True)
    discharge_from_recovery = models.DateTimeField(null=True, blank=True)
    pain_score_on_discharge = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text='Pain score 0-10 on discharge from recovery room'
    )
    post_op_nausea_vomiting = models.BooleanField(default=False)
    post_op_instructions = models.TextField(blank=True)
    post_op_complications = models.TextField(blank=True)

    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Anaesthetic Record'
        verbose_name_plural = 'Anaesthetic Records'

    def __str__(self):
        return (f"Anaesthetic Record — {self.patient.full_name} "
                f"({self.get_anaesthesia_type_display()}) "
                f"[{self.created_at.strftime('%d/%m/%Y')}]")

    @property
    def bmi(self):
        if self.weight_kg and self.height_cm and self.height_cm > 0:
            h_m = self.height_cm / 100
            return round(self.weight_kg / (h_m * h_m), 1)
        return None


# ══════════════════════════════════════════════════════════════════════════════
# NURSING CARE PLAN — JCI COP.8 requirement
# ══════════════════════════════════════════════════════════════════════════════

class NursingCarePlan(AuditModel):
    """
    Structured nursing care plan for an admitted patient.
    Based on NANDA nursing diagnoses and NIC/NOC outcomes.
    JCI COP.8 — every inpatient must have an individualized care plan.
    """
    admission = models.ForeignKey(
        Admission, on_delete=models.CASCADE, related_name='care_plans'
    )
    nurse = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True,
        related_name='care_plans_authored'
    )
    plan_date = models.DateField(auto_now_add=True)

    # NANDA-based nursing diagnoses
    nursing_diagnoses = models.TextField(
        help_text='NANDA nursing diagnoses (e.g. "Acute Pain r/t post-surgical state")'
    )

    # Expected outcomes / goals
    short_term_goals = models.TextField(
        help_text='Expected outcomes within this shift/24h'
    )
    long_term_goals = models.TextField(
        blank=True,
        help_text='Expected outcomes for entire admission'
    )

    # Nursing interventions by category
    hygiene_mobility_care = models.TextField(
        blank=True,
        help_text='Personal hygiene, positioning, mobility plan, fall prevention'
    )
    medication_eye_drop_schedule = models.TextField(
        blank=True,
        help_text='Post-op eye drop schedule, systemic medications, timing'
    )
    wound_eye_dressing_care = models.TextField(
        blank=True,
        help_text='Wound inspection, eye pad/shield management, dressing changes'
    )
    nutrition_hydration_plan = models.TextField(
        blank=True,
        help_text='Diet type, fluid restriction/encouragement, IV fluids'
    )
    vital_signs_monitoring = models.TextField(
        blank=True,
        help_text='Frequency and parameters to monitor (BP, pulse, SPO2, VA, IOP post-op)'
    )
    patient_family_education = models.TextField(
        blank=True,
        help_text='Teaching provided: eye drop instillation, activity restrictions, warning signs'
    )
    psychological_support = models.TextField(
        blank=True,
        help_text='Emotional support, anxiety management, patient concerns addressed'
    )
    discharge_planning = models.TextField(
        blank=True,
        help_text='Discharge criteria, transport, home support, follow-up appointment'
    )
    safety_measures = models.TextField(
        blank=True,
        help_text='Fall risk measures, call bell, bed rails, orientation'
    )

    # Evaluation
    evaluation_notes = models.TextField(
        blank=True,
        help_text='Outcome evaluation — goals met / partially met / not met + rationale'
    )
    next_review_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-plan_date', '-created_at']
        verbose_name = 'Nursing Care Plan'
        verbose_name_plural = 'Nursing Care Plans'

    def __str__(self):
        return (f"Care Plan — {self.admission.patient.full_name} "
                f"({self.plan_date}) by {self.nurse.full_name if self.nurse else 'Unknown'}")


# ── Vital Signs Flowsheet ────────────────────────────────────────────────────

class VitalSigns(TimeStampedModel):
    """
    Nurse-charted vital signs for admitted patients — timestamped observations
    recorded at each monitoring interval (e.g. q4h, q1h post-op).
    """
    admission = models.ForeignKey(Admission, on_delete=models.CASCADE, related_name='vital_signs')
    recorded_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT, related_name='vitals_recorded')
    recorded_at = models.DateTimeField(default=timezone.now)

    # Core vitals
    temperature = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, help_text='°C')
    pulse = models.PositiveSmallIntegerField(null=True, blank=True, help_text='bpm')
    respiratory_rate = models.PositiveSmallIntegerField(null=True, blank=True, help_text='breaths/min')
    spo2 = models.PositiveSmallIntegerField(null=True, blank=True, help_text='%')
    bp_systolic = models.PositiveSmallIntegerField(null=True, blank=True, help_text='mmHg')
    bp_diastolic = models.PositiveSmallIntegerField(null=True, blank=True, help_text='mmHg')
    # Blood sugar
    blood_glucose = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, help_text='mmol/L')
    # Pain
    pain_score = models.PositiveSmallIntegerField(null=True, blank=True, help_text='0–10 VAS')
    # Ophthalmic post-op
    visual_acuity_re = models.CharField(max_length=20, blank=True, help_text='Post-op VA Right Eye')
    visual_acuity_le = models.CharField(max_length=20, blank=True, help_text='Post-op VA Left Eye')
    iop_re = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, help_text='IOP Right Eye mmHg')
    iop_le = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, help_text='IOP Left Eye mmHg')
    # Glasgow Coma Scale (post-op monitoring)
    gcs = models.PositiveSmallIntegerField(null=True, blank=True, help_text='3–15')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-recorded_at']
        verbose_name = 'Vital Signs Entry'
        verbose_name_plural = 'Vital Signs Flowsheet'

    def __str__(self):
        return f"Vitals — {self.admission.patient.full_name} @ {self.recorded_at:%Y-%m-%d %H:%M}"

    @property
    def bp_display(self):
        if self.bp_systolic and self.bp_diastolic:
            return f"{self.bp_systolic}/{self.bp_diastolic}"
        return '—'


# ── Fluid Balance Chart ──────────────────────────────────────────────────────

class FluidEntryType(models.TextChoices):
    # Intake
    IV_FLUID    = 'IV_FLUID',   'IV Fluid'
    ORAL        = 'ORAL',       'Oral Intake'
    NG_FEED     = 'NG_FEED',    'NG / Nasogastric Feed'
    BLOOD_TRANSFUSION = 'BLOOD','Blood Transfusion'
    # Output
    URINE       = 'URINE',      'Urine Output'
    DRAIN       = 'DRAIN',      'Drain / Wound Drainage'
    VOMIT       = 'VOMIT',      'Vomit'
    STOOL       = 'STOOL',      'Stool'
    OTHER_OUT   = 'OTHER_OUT',  'Other Output'


class FluidBalance(TimeStampedModel):
    """
    Fluid balance chart for admitted patients — tracks all intake and output
    to compute running balance (essential post-op & ICU monitoring).
    """
    admission = models.ForeignKey(Admission, on_delete=models.CASCADE, related_name='fluid_entries')
    recorded_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT, related_name='fluid_entries_recorded')
    recorded_at = models.DateTimeField(default=timezone.now)
    entry_type = models.CharField(max_length=20, choices=FluidEntryType.choices)
    description = models.CharField(max_length=200, blank=True, help_text='e.g. Normal Saline 0.9%, Ringer Lactate')
    volume_ml = models.PositiveIntegerField(help_text='Volume in millilitres')
    is_intake = models.BooleanField(help_text='True = intake, False = output')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-recorded_at']
        verbose_name = 'Fluid Balance Entry'
        verbose_name_plural = 'Fluid Balance Chart'

    def __str__(self):
        direction = 'IN' if self.is_intake else 'OUT'
        return f"{self.admission.patient.full_name} | {direction} | {self.volume_ml} mL | {self.get_entry_type_display()}"

    def save(self, *args, **kwargs):
        # Auto-set is_intake based on entry type
        output_types = {
            FluidEntryType.URINE, FluidEntryType.DRAIN,
            FluidEntryType.VOMIT, FluidEntryType.STOOL, FluidEntryType.OTHER_OUT
        }
        self.is_intake = self.entry_type not in output_types
        super().save(*args, **kwargs)


# ═══════════════════════════════════════════════════════════════════════════════
#  Medication Reconciliation  (JCI MMU.4 — Med Rec at every transition of care)
# ═══════════════════════════════════════════════════════════════════════════════

class MedRecPhase(models.TextChoices):
    ADMISSION  = 'ADMISSION',  'On Admission'
    TRANSFER   = 'TRANSFER',   'On Transfer'
    DISCHARGE  = 'DISCHARGE',  'On Discharge'


class MedRecAction(models.TextChoices):
    CONTINUE     = 'CONTINUE',     'Continue'
    MODIFY       = 'MODIFY',       'Modify Dose / Route'
    HOLD         = 'HOLD',         'Hold (Temporary)'
    DISCONTINUE  = 'DISCONTINUE',  'Discontinue'
    NEW          = 'NEW',          'New Order'


class MedicationReconciliation(AuditModel):
    """
    Master reconciliation record — one per transition of care.
    Contains individual MedRecItem entries for each home medication.
    """
    admission = models.ForeignKey(
        Admission, on_delete=models.CASCADE, related_name='med_reconciliations',
    )
    patient = models.ForeignKey('patients.Patient', on_delete=models.CASCADE, related_name='med_reconciliations')
    phase = models.CharField(max_length=12, choices=MedRecPhase.choices)
    reconciled_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, related_name='med_reconciliations_done',
    )
    reconciled_at = models.DateTimeField(null=True, blank=True)
    is_complete = models.BooleanField(default=False, help_text='Marked complete when pharmacist verifies')
    verified_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='med_reconciliations_verified',
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Medication Reconciliation'

    def __str__(self):
        return f"MedRec {self.get_phase_display()} — {self.patient.full_name}"


class MedRecItem(TimeStampedModel):
    """Individual medication line within a reconciliation."""
    reconciliation = models.ForeignKey(
        MedicationReconciliation, on_delete=models.CASCADE, related_name='items',
    )
    medication_name = models.CharField(max_length=255, help_text='Drug name as reported by patient')
    dose = models.CharField(max_length=100, blank=True)
    route = models.CharField(max_length=50, blank=True, help_text='PO, IV, topical, etc.')
    frequency = models.CharField(max_length=100, blank=True)
    action = models.CharField(max_length=15, choices=MedRecAction.choices, default=MedRecAction.CONTINUE)
    new_dose = models.CharField(max_length=100, blank=True, help_text='If action=MODIFY, new dose')
    new_frequency = models.CharField(max_length=100, blank=True)
    reason = models.TextField(blank=True, help_text='Reason for change/discontinuation')
    source = models.CharField(max_length=50, blank=True, help_text='Patient report, pharmacy record, referral letter')

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.medication_name} → {self.get_action_display()}"


# ── Minor Procedures / Injections / Laser ─────────────────────────────────────

class ProcedureType(models.TextChoices):
    """Procedure types done in procedure room (NOT full theatre)."""
    # Intravitreal Injections
    ANTI_VEGF       = 'ANTI_VEGF',       'Intravitreal Anti-VEGF Injection'
    IVT_STEROID     = 'IVT_STEROID',     'Intravitreal Steroid Injection'
    IVT_ANTIBIOTIC  = 'IVT_ANTIBIOTIC',  'Intravitreal Antibiotic Injection'
    # Laser Procedures
    SLT             = 'SLT',             'Selective Laser Trabeculoplasty (SLT)'
    YAG_CAPSULOTOMY = 'YAG_CAPSULOTOMY', 'YAG Laser Capsulotomy'
    YAG_PI          = 'YAG_PI',          'YAG Peripheral Iridotomy (PI)'
    PRP             = 'PRP',             'Pan-Retinal Photocoagulation (PRP)'
    FOCAL_LASER     = 'FOCAL_LASER',     'Focal / Grid Laser Photocoagulation'
    # Minor Procedures
    CHALAZION       = 'CHALAZION',       'Chalazion Incision & Curettage'
    FB_REMOVAL      = 'FB_REMOVAL',      'Corneal / Conjunctival Foreign Body Removal'
    SUTURE_REMOVAL  = 'SUTURE_REMOVAL',  'Suture Removal'
    PUNCTAL_PLUG    = 'PUNCTAL_PLUG',    'Punctal Plug Insertion'
    PROBING         = 'PROBING',         'Nasolacrimal Duct Probing'
    SUBCONJ_INJ     = 'SUBCONJ_INJ',    'Sub-conjunctival Injection'
    PERIBULBAR_INJ  = 'PERIBULBAR_INJ',  'Peribulbar / Retrobulbar Injection'
    OTHER           = 'OTHER',           'Other (specify in notes)'


class ProcedureRecordStatus(models.TextChoices):
    ORDERED         = 'ORDERED',         'Ordered'
    CONSENT_PENDING = 'CONSENT_PENDING', 'Awaiting Consent'
    READY           = 'READY',           'Ready for Procedure'
    IN_PROGRESS     = 'IN_PROGRESS',     'In Progress'
    COMPLETED       = 'COMPLETED',       'Completed'
    MONITORING      = 'MONITORING',      'Post-Procedure Monitoring'
    DISCHARGED      = 'DISCHARGED',      'Discharged'
    CANCELLED       = 'CANCELLED',       'Cancelled'


class ProcedureRecord(AuditModel):
    """
    Record of a minor procedure / injection / laser done in the procedure room.
    NOT a full theatre case — no IPD admission needed.

    Flow:
      Doctor orders procedure (from consultation) →
      Patient routed to PROCEDURE_ROOM queue →
      Consent recorded →
      Pre-procedure vitals checked →
      Procedure performed + recorded →
      Post-procedure monitoring (IOP check for injections) →
      Patient discharged or routed to pharmacy
    """
    # Identifiers
    record_number = models.CharField(max_length=30, unique=True, editable=False)
    patient = models.ForeignKey(
        'patients.Patient', on_delete=models.PROTECT, related_name='procedure_records'
    )
    visit = models.ForeignKey(
        'patients.Visit', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='procedure_records'
    )
    consultation = models.ForeignKey(
        'consultations.Consultation', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='procedure_records'
    )

    # Procedure details
    procedure_type = models.CharField(max_length=20, choices=ProcedureType.choices)
    procedure_notes = models.CharField(
        max_length=300, blank=True,
        help_text='Additional details or specify if "Other" selected'
    )
    eye = models.CharField(max_length=2, choices=[
        ('RE', 'Right Eye (OD)'),
        ('LE', 'Left Eye (OS)'),
        ('BE', 'Both Eyes (OU)'),
        ('NA', 'Not Eye-specific'),
    ], default='RE')
    status = models.CharField(
        max_length=20, choices=ProcedureRecordStatus.choices,
        default=ProcedureRecordStatus.ORDERED
    )

    # Ordering & performing
    ordered_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, related_name='procedures_ordered'
    )
    performed_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='minor_procedures_performed'
    )

    # Consent
    consent_signed = models.BooleanField(default=False)
    consent_date = models.DateTimeField(null=True, blank=True)

    # Pre-procedure
    pre_vitals = models.JSONField(
        default=dict, blank=True,
        help_text='Pre-procedure vitals: BP, IOP, VA, pupil dilation status'
    )
    anaesthesia = models.CharField(max_length=50, blank=True,
        help_text='e.g. Topical proparacaine, Peribulbar lidocaine')

    # Procedure execution
    procedure_date = models.DateTimeField(null=True, blank=True)
    medication_used = models.CharField(
        max_length=200, blank=True,
        help_text='Drug name, dose, batch/lot number'
    )
    medication_batch = models.CharField(max_length=50, blank=True,
        help_text='Batch/lot number for traceability')
    medication_expiry = models.DateField(null=True, blank=True)
    laser_settings = models.JSONField(
        default=dict, blank=True,
        help_text='For laser: power (mW), duration (ms), spot size (um), number of spots'
    )
    injection_site = models.CharField(max_length=100, blank=True,
        help_text='e.g. 3.5mm from limbus inferotemporal')
    complications = models.TextField(blank=True,
        help_text='Any immediate complications')
    procedure_outcome = models.TextField(blank=True,
        help_text='Immediate outcome notes')

    # Post-procedure monitoring
    post_vitals = models.JSONField(
        default=dict, blank=True,
        help_text='Post-procedure vitals: IOP at 15min, 30min, VA'
    )
    post_instructions = models.TextField(blank=True,
        help_text='Post-procedure instructions given to patient')
    monitoring_complete = models.BooleanField(default=False)
    discharged_at = models.DateTimeField(null=True, blank=True)

    # Next visit
    follow_up_date = models.DateField(null=True, blank=True)
    follow_up_instructions = models.CharField(max_length=300, blank=True)
    next_injection_date = models.DateField(null=True, blank=True,
        help_text='For anti-VEGF: planned next injection date')

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Procedure Record'
        verbose_name_plural = 'Procedure Records'

    def __str__(self):
        return f"{self.record_number} — {self.get_procedure_type_display()} ({self.patient.full_name})"

    def save(self, *args, **kwargs):
        if not self.record_number:
            today = timezone.localdate()
            count = ProcedureRecord.objects.filter(
                created_at__year=today.year
            ).count() + 1
            self.record_number = f"PR-{today.strftime('%Y')}-{count:04d}"
        super().save(*args, **kwargs)


# ═══════════════════════════════════════════════════════════════════════════════
# PRE-OPERATIVE COUNSELLING CHECKLIST (G001–G007)
# Mirrors TurboClinic 'Conseil pré-opératoire' structured accordion form.
# ═══════════════════════════════════════════════════════════════════════════════

class PreOpCounsellingChecklist(AuditModel):
    """
    Structured pre-operative counselling record with 7 sections (G001–G007).
    One per SurgicalBooking, completed by the counselling nurse.
    """
    booking   = models.OneToOneField(
        SurgicalBooking, on_delete=models.CASCADE, related_name='preop_checklist'
    )
    counsellor = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='preop_checklists'
    )
    date = models.DateField(default=timezone.localdate)

    # ── G001 — Scheduling & Logistics ──────────────────────────────────────────
    g001_surgery_date_confirmed = models.BooleanField(default=False,
        verbose_name='Surgery date communicated to patient')
    g001_transport_arranged     = models.BooleanField(default=False,
        verbose_name='Transport arrangement discussed')
    g001_companion_informed     = models.BooleanField(default=False,
        verbose_name='Companion / escort informed')
    g001_notes                  = models.TextField(blank=True)

    # ── G002 — Pre-operative Preparation ───────────────────────────────────────
    g002_fasting_instructions   = models.BooleanField(default=False,
        verbose_name='Fasting instructions given (nil by mouth)')
    g002_medications_reviewed   = models.BooleanField(default=False,
        verbose_name='Current medications reviewed (stop/continue list)')
    g002_blood_tests_ordered    = models.BooleanField(default=False,
        verbose_name='Pre-op blood tests ordered (CBC, RBG, etc.)')
    g002_bp_sugar_checked       = models.BooleanField(default=False,
        verbose_name='BP and blood sugar targets explained')
    g002_notes                  = models.TextField(blank=True)

    # ── G003 — Consent & Surgical Information ──────────────────────────────────
    g003_procedure_explained    = models.BooleanField(default=False,
        verbose_name='Procedure steps explained to patient')
    g003_risks_explained        = models.BooleanField(default=False,
        verbose_name='Risks and complications explained')
    g003_alternatives_discussed = models.BooleanField(default=False,
        verbose_name='Alternative treatments discussed')
    g003_consent_signed         = models.BooleanField(default=False,
        verbose_name='Written informed consent obtained')
    g003_notes                  = models.TextField(blank=True)

    # ── G004 — Hospitalisation Conditions ──────────────────────────────────────
    g004_ward_explained         = models.BooleanField(default=False,
        verbose_name='Ward / admission process explained')
    g004_stay_duration          = models.CharField(max_length=100, blank=True,
        verbose_name='Expected length of stay',
        help_text='e.g. Day case, Overnight, 2-3 days')
    g004_items_to_bring         = models.BooleanField(default=False,
        verbose_name='Items to bring list given (clothing, toiletries, ID)')
    g004_notes                  = models.TextField(blank=True)

    # ── G005 — Surgical Fees & Financial Counselling ────────────────────────────
    g005_total_fees_quoted      = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name='Total fees quoted (FCFA)'
    )
    g005_deposit_amount         = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name='Deposit / advance payment (FCFA)'
    )
    g005_insurance_share        = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name='Insurance / 3rd-party share (FCFA)'
    )
    g005_patient_share          = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name='Patient out-of-pocket share (FCFA)'
    )
    g005_payment_plan_discussed = models.BooleanField(default=False,
        verbose_name='Payment plan / financial assistance discussed')
    g005_notes                  = models.TextField(blank=True)

    # ── G006 — Post-operative Care & Follow-up ─────────────────────────────────
    g006_post_op_instructions   = models.BooleanField(default=False,
        verbose_name='Post-op care instructions given')
    g006_eye_drop_schedule      = models.BooleanField(default=False,
        verbose_name='Eye drop / medication schedule explained')
    g006_followup_date          = models.DateField(null=True, blank=True,
        verbose_name='First follow-up appointment date')
    g006_activity_restrictions  = models.BooleanField(default=False,
        verbose_name='Activity restrictions explained (no driving, swimming, etc.)')
    g006_emergency_contact      = models.BooleanField(default=False,
        verbose_name='Emergency contact / when to return to hospital given')
    g006_notes                  = models.TextField(blank=True)

    # ── G007 — Special Notes ────────────────────────────────────────────────────
    g007_notes = models.TextField(blank=True,
        verbose_name='Special notes / additional instructions')

    # ── Signatures ──────────────────────────────────────────────────────────────
    patient_understood         = models.BooleanField(default=False,
        verbose_name='Patient / guardian confirms understanding')
    patient_signature_obtained = models.BooleanField(default=False,
        verbose_name='Patient / guardian signature obtained')
    counsellor_signature       = models.BooleanField(default=False,
        verbose_name='Counselling nurse signature')

    class Meta:
        verbose_name = 'Pre-Op Counselling Checklist'

    def __str__(self):
        return f'Pre-Op Checklist — {self.booking.patient.full_name} ({self.date})'


# ─────────────────────────────────────────────────────────────────────────────
# PRE-OPERATIVE INVESTIGATION REQUIREMENTS (JCI ASC.4)
# ─────────────────────────────────────────────────────────────────────────────

class PreOpInvType(models.TextChoices):
    BIOMETRY        = 'BIOMETRY',        'Biometry (A-scan / IOLMaster)'
    OCT             = 'OCT',             'OCT — Macula / Optic Nerve'
    CORNEAL_TOPO    = 'CORNEAL_TOPO',    'Corneal Topography / Pentacam'
    SPECULAR_MICRO  = 'SPECULAR_MICRO',  'Specular Microscopy'
    B_SCAN          = 'B_SCAN',          'B-scan Ultrasound'
    VF              = 'VF',              'Visual Field (Perimetry)'
    FFA             = 'FFA',             'Fundus Fluorescein Angiography'
    ELECTRODIAG     = 'ELECTRODIAG',     'Electrodiagnostics (ERG/VEP)'
    CBC             = 'CBC',             'Full Blood Count (CBC)'
    RBG             = 'RBG',             'Random Blood Glucose'
    HBA1C           = 'HBA1C',           'HbA1c'
    UREA_CREAT      = 'UREA_CREAT',      'Urea & Creatinine'
    SICKLE_CELL     = 'SICKLE_CELL',     'Sickle-cell Screen'
    HIV             = 'HIV',             'HIV Screen'
    COAGULATION     = 'COAGULATION',     'Coagulation Profile (PT/APTT)'
    ECG             = 'ECG',             'ECG'
    CXR             = 'CXR',             'Chest X-ray'
    ANAESTHESIA     = 'ANAESTHESIA',     'Anaesthesia Fitness Assessment'
    OTHER           = 'OTHER',           'Other'


class PreOpInvStatus(models.TextChoices):
    PENDING     = 'PENDING',     'Pending'
    ORDERED     = 'ORDERED',     'Ordered'
    RESULT_IN   = 'RESULT_IN',   'Result Available'
    CLEARED     = 'CLEARED',     'Cleared by Surgeon'
    WAIVED      = 'WAIVED',      'Waived (documented reason)'


class PreOpInvestigation(AuditModel):
    """
    Tracks each required pre-operative investigation for a surgical booking (JCI ASC.4).
    """
    booking     = models.ForeignKey('SurgicalBooking', on_delete=models.CASCADE,
                                    related_name='preop_investigations')
    inv_type    = models.CharField(max_length=20, choices=PreOpInvType.choices)
    status      = models.CharField(max_length=15, choices=PreOpInvStatus.choices,
                                   default=PreOpInvStatus.PENDING)
    ordered_at  = models.DateTimeField(null=True, blank=True)
    result_at   = models.DateTimeField(null=True, blank=True)
    result_summary = models.TextField(blank=True)
    cleared_by  = models.ForeignKey('accounts.User', on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='cleared_preop_invs')
    cleared_at  = models.DateTimeField(null=True, blank=True)
    waiver_reason = models.TextField(blank=True)
    notes       = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Pre-Op Investigation'
        unique_together = [('booking', 'inv_type')]
        ordering = ['inv_type']

    def __str__(self):
        return f'{self.get_inv_type_display()} — {self.booking}'

    @property
    def is_cleared(self):
        return self.status in (PreOpInvStatus.CLEARED, PreOpInvStatus.WAIVED)


# ─────────────────────────────────────────────────────────────────────────────
# INTRA-OPERATIVE SURGICAL MATERIALS / IMPLANTS (JCI ASC.5.1)
# ─────────────────────────────────────────────────────────────────────────────

class SurgicalMaterialType(models.TextChoices):
    IOL             = 'IOL',            'Intraocular Lens (IOL)'
    SUTURE          = 'SUTURE',         'Suture'
    VISCOELASTIC    = 'VISCOELASTIC',   'Viscoelastic / OVD'
    IRRIGATING_SOL  = 'IRRIGATING_SOL', 'Irrigating Solution (BSS)'
    TAMPONADE       = 'TAMPONADE',      'Intraocular Tamponade (Gas/Oil)'
    GLAUCOMA_IMPL   = 'GLAUCOMA_IMPL',  'Glaucoma Implant / Tube Shunt'
    CORNEAL_RING    = 'CORNEAL_RING',   'Intrastromal Corneal Ring Segment'
    AMNIOTIC        = 'AMNIOTIC',       'Amniotic Membrane'
    HAEMOSTATIC     = 'HAEMOSTATIC',    'Haemostatic Agent'
    ADHESIVE        = 'ADHESIVE',       'Tissue Adhesive / Glue'
    SPONGE          = 'SPONGE',         'Surgical Sponge / Merocel'
    PROBE           = 'PROBE',          'Lacrimal Probe / Stent'
    OTHER           = 'OTHER',          'Other'


class SurgicalMaterial(AuditModel):
    """
    Records every implant and consumable used during a TheatreProcedure (JCI ASC.5.1).
    Provides full lot/batch traceability.
    """
    procedure       = models.ForeignKey('TheatreProcedure', on_delete=models.CASCADE,
                                        related_name='surgical_materials')
    material_type   = models.CharField(max_length=20, choices=SurgicalMaterialType.choices)
    description     = models.CharField(max_length=200)
    manufacturer    = models.CharField(max_length=100, blank=True)
    model_reference = models.CharField(max_length=100, blank=True)
    lot_number      = models.CharField(max_length=100, blank=True)
    serial_number   = models.CharField(max_length=100, blank=True)
    expiry_date     = models.DateField(null=True, blank=True)
    quantity_used   = models.PositiveSmallIntegerField(default=1)
    unit_cost       = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    eye             = models.CharField(max_length=5, choices=[
        ('OD', 'OD — Right Eye'), ('OS', 'OS — Left Eye'), ('OU', 'OU — Both Eyes'), ('NA', 'N/A'),
    ], default='NA')
    notes           = models.TextField(blank=True)
    recorded_by     = models.ForeignKey('accounts.User', on_delete=models.SET_NULL,
                                        null=True, blank=True, related_name='recorded_materials')

    class Meta:
        verbose_name = 'Surgical Material'
        ordering = ['material_type', 'description']

    def __str__(self):
        return f'{self.get_material_type_display()} — {self.description} (Proc {self.procedure_id})'

    @property
    def total_cost(self):
        return self.unit_cost * self.quantity_used


# ─────────────────────────────────────────────────────────────────────────────
# OPERATIVE REPORT (JCI ASC.7.1)
# ─────────────────────────────────────────────────────────────────────────────

class IncisionType(models.TextChoices):
    CLEAR_CORNEAL       = 'CLEAR_CORNEAL',      'Clear Corneal Incision'
    SCLERAL_TUNNEL      = 'SCLERAL_TUNNEL',     'Scleral Tunnel'
    LIMBAL              = 'LIMBAL',             'Limbal Incision'
    PARS_PLANA          = 'PARS_PLANA',         'Pars Plana (Vitreoretinal)'
    STAB_INCISION       = 'STAB_INCISION',      'Stab / Side-port Incision'
    TRABECULECTOMY      = 'TRABECULECTOMY',     'Trabeculectomy Flap'
    CANTHOTOMY          = 'CANTHOTOMY',         'Canthotomy'
    CONJUNCTIVAL_PERITOMY = 'CONJ_PERITOMY',    'Conjunctival Peritomy'
    OTHER               = 'OTHER',             'Other'


class OperativeReport(AuditModel):
    """
    Formal operative report completed by the operating surgeon immediately
    after surgery (JCI ASC.7.1). One report per TheatreProcedure.
    """
    procedure           = models.OneToOneField('TheatreProcedure', on_delete=models.CASCADE,
                                               related_name='operative_report')
    # ── Timing ──────────────────────────────────────────────────────────────
    procedure_start     = models.DateTimeField(null=True, blank=True)
    procedure_end       = models.DateTimeField(null=True, blank=True)
    # ── Procedure details ────────────────────────────────────────────────────
    operating_eye       = models.CharField(max_length=5, choices=[
        ('OD', 'OD — Right Eye'), ('OS', 'OS — Left Eye'), ('OU', 'OU — Both Eyes'),
    ], blank=True)
    incision_type       = models.CharField(max_length=25, choices=IncisionType.choices, blank=True)
    incision_size_mm    = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True,
                                              verbose_name='Incision size (mm)')
    anaesthesia_used    = models.CharField(max_length=200, blank=True,
                                           help_text='e.g. Topical, Peribulbar, General')
    # ── Intraoperative findings ───────────────────────────────────────────────
    preop_va            = models.CharField(max_length=20, blank=True,
                                           verbose_name='Pre-op VA (Snellen / LogMAR)')
    preop_iop           = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True,
                                              verbose_name='Pre-op IOP (mmHg)')
    lens_status         = models.CharField(max_length=200, blank=True,
                                           help_text='e.g. Dense NSIII cataract, clear lens, phakic')
    vitreous_status     = models.CharField(max_length=200, blank=True)
    fundus_intraop      = models.TextField(blank=True, verbose_name='Intraoperative fundus findings')
    # ── Procedure narrative ───────────────────────────────────────────────────
    procedure_description = models.TextField(
        verbose_name='Procedure Description',
        help_text='Step-by-step narrative of the surgical technique'
    )
    # ── IOL specifics (duplicated from TheatreProcedure for report completeness) ─
    iol_inserted        = models.BooleanField(default=False)
    iol_type            = models.CharField(max_length=30, blank=True,
                                           choices=[
                                               ('MONOFOCAL', 'Monofocal'), ('TORIC', 'Toric'),
                                               ('MULTIFOCAL', 'Multifocal'), ('EDOF', 'EDOF'),
                                               ('PHAKIC', 'Phakic IOL'), ('OTHER', 'Other'),
                                           ])
    iol_model           = models.CharField(max_length=100, blank=True)
    iol_power           = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True,
                                              verbose_name='IOL power (D)')
    iol_lot             = models.CharField(max_length=100, blank=True, verbose_name='IOL lot #')
    # ── Complications ────────────────────────────────────────────────────────
    intraop_complications = models.TextField(blank=True,
                                             verbose_name='Intraoperative complications')
    posterior_capsule_rupture = models.BooleanField(default=False)
    vitreous_loss       = models.BooleanField(default=False)
    expulsive_haemorrhage = models.BooleanField(default=False)
    # ── Closure & End of case ────────────────────────────────────────────────
    sutures_placed      = models.CharField(max_length=200, blank=True)
    subconj_injection   = models.CharField(max_length=200, blank=True,
                                           verbose_name='Sub-conjunctival / intracameral injection')
    eye_pad_shield      = models.BooleanField(default=True, verbose_name='Eye pad & shield applied')
    eop_iop             = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True,
                                              verbose_name='End-of-procedure IOP (mmHg)')
    # ── Surgeon sign-off ─────────────────────────────────────────────────────
    surgeon             = models.ForeignKey('accounts.User', on_delete=models.SET_NULL,
                                            null=True, blank=True, related_name='operative_reports')
    dictated_at         = models.DateTimeField(auto_now_add=True)
    is_finalised        = models.BooleanField(default=False)
    finalised_at        = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Operative Report'

    def __str__(self):
        return f'Op Report — {self.procedure}'

    @property
    def duration_minutes(self):
        if self.procedure_start and self.procedure_end:
            delta = self.procedure_end - self.procedure_start
            return int(delta.total_seconds() / 60)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# RECOVERY ROOM RECORD (JCI ASC.7.2)
# ─────────────────────────────────────────────────────────────────────────────

class RecoveryDischargeStatus(models.TextChoices):
    MONITORING      = 'MONITORING',     'Under Monitoring'
    READY_FOR_WARD  = 'READY_WARD',     'Ready for Ward Transfer'
    READY_FOR_HOME  = 'READY_HOME',     'Ready for Discharge Home'
    TRANSFERRED     = 'TRANSFERRED',    'Transferred to Ward'
    DISCHARGED      = 'DISCHARGED',     'Discharged Home'
    ICU_ESCALATED   = 'ICU',            'Escalated to ICU'


class RecoveryRoomRecord(AuditModel):
    """
    Post-anaesthesia / recovery room monitoring record (JCI ASC.7.2).
    Tracks Aldrete score and ophthalmology-specific recovery parameters.
    """
    procedure           = models.OneToOneField('TheatreProcedure', on_delete=models.CASCADE,
                                               related_name='recovery_record')
    arrival_time        = models.DateTimeField(null=True, blank=True)
    discharge_time      = models.DateTimeField(null=True, blank=True)
    recovery_nurse      = models.ForeignKey('accounts.User', on_delete=models.SET_NULL,
                                            null=True, blank=True, related_name='recovery_records')

    # ── Aldrete Score (for GA / sedation) ────────────────────────────────────
    # Each component 0-2; total 0-10; score ≥9 = safe for discharge
    aldrete_activity        = models.PositiveSmallIntegerField(default=0,
        help_text='0=none, 1=2 extremities, 2=4 extremities')
    aldrete_respiration     = models.PositiveSmallIntegerField(default=0,
        help_text='0=apnoeic, 1=shallow/dyspnoeic, 2=deep/coughs')
    aldrete_circulation     = models.PositiveSmallIntegerField(default=0,
        help_text='0=<50% baseline BP, 1=20-50%, 2=<20%')
    aldrete_consciousness   = models.PositiveSmallIntegerField(default=0,
        help_text='0=unresponsive, 1=responds to name, 2=fully awake')
    aldrete_colour          = models.PositiveSmallIntegerField(default=0,
        help_text='0=cyanotic, 1=pale/dusky, 2=normal')

    # ── Vital signs ──────────────────────────────────────────────────────────
    bp_systolic         = models.PositiveSmallIntegerField(null=True, blank=True)
    bp_diastolic        = models.PositiveSmallIntegerField(null=True, blank=True)
    heart_rate          = models.PositiveSmallIntegerField(null=True, blank=True)
    spo2                = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True,
                                             verbose_name='SpO2 (%)')
    temperature_c       = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    pain_score          = models.PositiveSmallIntegerField(null=True, blank=True,
                                                           help_text='0-10 NRS pain score')
    nausea_vomiting     = models.BooleanField(default=False, verbose_name='PONV present')

    # ── Ophthalmic recovery checks ───────────────────────────────────────────
    eye_shield_in_place = models.BooleanField(default=True)
    recovery_va         = models.CharField(max_length=20, blank=True,
                                           verbose_name='Recovery VA (count fingers / LogMAR)')
    recovery_iop        = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True,
                                              verbose_name='Recovery IOP (mmHg)')
    anterior_segment_check = models.TextField(blank=True,
                                              verbose_name='Anterior segment recovery observation')
    eye_drops_given     = models.TextField(blank=True,
                                           verbose_name='Eye drops / medications given in recovery')

    # ── Status & discharge ───────────────────────────────────────────────────
    status              = models.CharField(max_length=20, choices=RecoveryDischargeStatus.choices,
                                           default=RecoveryDischargeStatus.MONITORING)
    discharge_criteria_met = models.BooleanField(default=False)
    discharged_by       = models.ForeignKey('accounts.User', on_delete=models.SET_NULL,
                                            null=True, blank=True,
                                            related_name='recovery_discharges')
    notes               = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Recovery Room Record'

    def __str__(self):
        return f'Recovery — {self.procedure}'

    @property
    def aldrete_total(self):
        return (self.aldrete_activity + self.aldrete_respiration +
                self.aldrete_circulation + self.aldrete_consciousness +
                self.aldrete_colour)

    @property
    def aldrete_safe_for_discharge(self):
        return self.aldrete_total >= 9

    @property
    def time_in_recovery_minutes(self):
        if self.arrival_time and self.discharge_time:
            delta = self.discharge_time - self.arrival_time
            return int(delta.total_seconds() / 60)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# DISCHARGE CHECKLIST (JCI ACC.3)
# ─────────────────────────────────────────────────────────────────────────────

class DischargeChecklist(AuditModel):
    """
    Discharge planning and readiness checklist (JCI ACC.3).
    Completed by ward nurse / doctor before patient leaves.
    """
    admission       = models.OneToOneField('Admission', on_delete=models.CASCADE,
                                           related_name='discharge_checklist')
    completed_by    = models.ForeignKey('accounts.User', on_delete=models.SET_NULL,
                                        null=True, blank=True, related_name='discharge_checklists')
    completed_at    = models.DateTimeField(auto_now_add=True)

    # ── Clinical readiness ────────────────────────────────────────────────────
    final_va_od             = models.CharField(max_length=20, blank=True,
                                               verbose_name='Final VA — OD (Right Eye)')
    final_va_os             = models.CharField(max_length=20, blank=True,
                                               verbose_name='Final VA — OS (Left Eye)')
    final_iop_od            = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True,
                                                  verbose_name='Final IOP OD (mmHg)')
    final_iop_os            = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True,
                                                  verbose_name='Final IOP OS (mmHg)')
    wound_check_ok          = models.BooleanField(default=False, verbose_name='Wound secure / no leak')
    anterior_segment_stable = models.BooleanField(default=False, verbose_name='Anterior segment stable')
    no_active_infection     = models.BooleanField(default=False, verbose_name='No signs of infection/endophthalmitis')
    pain_controlled         = models.BooleanField(default=False, verbose_name='Pain controlled (score ≤3)')

    # ── Medications & instructions ────────────────────────────────────────────
    discharge_medications_prescribed = models.BooleanField(default=False,
                                                           verbose_name='Discharge medications prescribed')
    eye_drop_schedule_given = models.BooleanField(default=False,
                                                  verbose_name='Eye drop schedule given (written)')
    systemic_meds_reconciled = models.BooleanField(default=False,
                                                   verbose_name='Systemic medications reconciled')
    medication_counselling   = models.BooleanField(default=False,
                                                   verbose_name='Medication counselling completed')

    # ── Follow-up planning ────────────────────────────────────────────────────
    followup_1_date         = models.DateField(null=True, blank=True,
                                               verbose_name='1st Follow-up (Day 1 / next day)')
    followup_2_date         = models.DateField(null=True, blank=True,
                                               verbose_name='2nd Follow-up (Week 1)')
    followup_3_date         = models.DateField(null=True, blank=True,
                                               verbose_name='3rd Follow-up (Week 4 / Month 1)')
    followup_appointment_booked = models.BooleanField(default=False,
                                                      verbose_name='Follow-up appointment(s) booked')
    referral_required       = models.BooleanField(default=False)
    referral_letter_given   = models.BooleanField(default=False)

    # ── Patient education ─────────────────────────────────────────────────────
    activity_restrictions_explained = models.BooleanField(default=False,
                                                          verbose_name='Activity restrictions explained (no driving, no rubbing)')
    protective_shield_given         = models.BooleanField(default=False,
                                                          verbose_name='Protective eye shield given')
    sun_protection_advised          = models.BooleanField(default=False,
                                                          verbose_name='UV protection / sunglasses advised')
    emergency_signs_explained       = models.BooleanField(default=False,
                                                          verbose_name='Return-to-hospital red flags explained')
    patient_discharge_summary_given = models.BooleanField(default=False,
                                                          verbose_name='Written discharge summary given to patient')

    # ── Administrative ────────────────────────────────────────────────────────
    final_invoice_settled   = models.BooleanField(default=False,
                                                  verbose_name='Final invoice settled / billing complete')
    insurance_forms_completed = models.BooleanField(default=False,
                                                    verbose_name='Insurance / CNPS forms completed')
    patient_transport_arranged = models.BooleanField(default=False,
                                                     verbose_name='Patient transport arranged')

    # ── Signature confirmation ────────────────────────────────────────────────
    patient_agrees_to_discharge = models.BooleanField(default=False,
                                                      verbose_name='Patient / guardian consents to discharge')
    doctor_discharge_order      = models.BooleanField(default=False,
                                                      verbose_name='Doctor discharge order signed')

    # ── Additional notes ──────────────────────────────────────────────────────
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Discharge Checklist'

    def __str__(self):
        return f'Discharge Checklist — {self.admission}'

    @property
    def readiness_score(self):
        """Count of clinical readiness items ticked (out of 4)."""
        return sum([
            self.wound_check_ok, self.anterior_segment_stable,
            self.no_active_infection, self.pain_controlled,
        ])

    @property
    def is_complete(self):
        return (
            self.wound_check_ok and self.anterior_segment_stable and
            self.no_active_infection and self.discharge_medications_prescribed and
            self.eye_drop_schedule_given and self.followup_appointment_booked and
            self.doctor_discharge_order
        )

    @property
    def completion_pct(self):
        checks = [
            self.g001_surgery_date_confirmed, self.g001_transport_arranged,
            self.g002_fasting_instructions, self.g002_medications_reviewed,
            self.g002_blood_tests_ordered,
            self.g003_procedure_explained, self.g003_risks_explained,
            self.g003_consent_signed,
            self.g004_ward_explained,
            bool(self.g005_total_fees_quoted),
            self.g006_post_op_instructions, self.g006_eye_drop_schedule,
            self.g006_activity_restrictions,
            self.patient_understood, self.patient_signature_obtained,
        ]
        done = sum(1 for c in checks if c)
        return round(done / len(checks) * 100)
