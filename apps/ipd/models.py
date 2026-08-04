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
    ADMITTED = 'ADMITTED', 'Admitted'
    DISCHARGED = 'DISCHARGED', 'Discharged'
    TRANSFERRED = 'TRANSFERRED', 'Transferred'


class Admission(AuditModel):
    admission_number = models.CharField(max_length=30, unique=True)
    patient = models.ForeignKey(
        'patients.Patient', on_delete=models.PROTECT, related_name='admissions'
    )
    bed = models.ForeignKey(Bed, on_delete=models.PROTECT, related_name='admissions')
    admitting_doctor = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='admissions_made'
    )
    surgical_booking = models.ForeignKey(
        'SurgicalBooking', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='admissions'
    )
    admission_date = models.DateTimeField(default=timezone.now)
    discharge_date = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=AdmissionStatus.choices, default=AdmissionStatus.ADMITTED)
    diagnosis_on_admission = models.TextField()
    discharge_summary = models.TextField(blank=True)
    notes = models.TextField(blank=True)

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

    def save(self, *args, **kwargs):
        if not self.booking_number:
            today = timezone.localdate()
            count = SurgicalBooking.objects.filter(
                created_at__year=today.year
            ).count() + 1
            self.booking_number = f"SB-{today.strftime('%Y')}-{count:04d}"
        super().save(*args, **kwargs)

    @property
    def balance_due(self):
        return max(self.deposit_required - self.deposit_paid, 0)

    @property
    def is_fully_deposited(self):
        return self.deposit_paid >= self.deposit_required


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

    # Theatre team
    lead_surgeon       = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='theatre_sessions_led'
    )
    anaesthetist_name  = models.CharField(max_length=200, blank=True,
        help_text='Anaesthetist or anaesthesia provider name')
    scrub_nurse        = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='theatre_sessions_scrub'
    )
    circulating_nurse  = models.ForeignKey(
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
