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
