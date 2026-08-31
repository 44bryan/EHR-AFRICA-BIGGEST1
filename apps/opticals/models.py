"""
Opticals Module
Frame/lens catalogue, dispensing linked to optical prescriptions.
"""
from django.db import models
from django.utils import timezone
from apps.core.models import TimeStampedModel, AuditModel


class FrameShape(models.TextChoices):
    FULL_RIM = 'FULL_RIM', 'Full Rim'
    HALF_RIM = 'HALF_RIM', 'Half Rim'
    RIMLESS = 'RIMLESS', 'Rimless'
    SUPRA = 'SUPRA', 'Supra'


class LensType(models.TextChoices):
    SINGLE_VISION = 'SV', 'Single Vision'
    BIFOCAL = 'BIFOCAL', 'Bifocal'
    PROGRESSIVE = 'PROGRESSIVE', 'Progressive'
    OCCUPATIONAL = 'OCCUPATIONAL', 'Occupational'
    CONTACT = 'CONTACT', 'Contact Lens'


class Frame(AuditModel):
    """Frame catalogue item"""
    brand = models.CharField(max_length=100)
    model = models.CharField(max_length=100)
    color = models.CharField(max_length=100, blank=True)
    shape = models.CharField(max_length=20, choices=FrameShape.choices, blank=True)
    material = models.CharField(max_length=100, blank=True)
    sku = models.CharField(max_length=100, unique=True, null=True, blank=True)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    quantity_in_stock = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    image = models.ImageField(upload_to='frames/', null=True, blank=True)

    class Meta:
        ordering = ['brand', 'model']

    def __str__(self):
        return f"{self.brand} {self.model} - {self.color}".strip()


class Lens(AuditModel):
    """Lens catalogue item"""
    name = models.CharField(max_length=200)
    lens_type = models.CharField(max_length=20, choices=LensType.choices)
    material = models.CharField(max_length=100, blank=True, help_text='e.g. CR-39, Polycarbonate, Hi-index 1.67')
    coating = models.CharField(max_length=200, blank=True, help_text='e.g. Anti-reflective, UV400, Photochromic')
    index = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.get_lens_type_display()})"


class OpticalOrderStatus(models.TextChoices):
    ORDERED = 'ORDERED', 'Ordered'
    LAB_PROCESSING = 'LAB', 'At Lab/Processing'
    READY = 'READY', 'Ready for Collection'
    DELIVERED = 'DELIVERED', 'Delivered'
    CANCELLED = 'CANCELLED', 'Cancelled'


class OpticalOrder(AuditModel):
    """Optical dispensing order"""
    order_number = models.CharField(max_length=30, unique=True)
    patient = models.ForeignKey(
        'patients.Patient', on_delete=models.PROTECT, related_name='optical_orders'
    )
    optical_prescription = models.ForeignKey(
        'prescriptions.OpticalPrescription', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='orders'
    )
    frame = models.ForeignKey(Frame, null=True, blank=True, on_delete=models.SET_NULL)
    lens = models.ForeignKey(Lens, null=True, blank=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=20, choices=OpticalOrderStatus.choices, default=OpticalOrderStatus.ORDERED)
    frame_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    lens_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    fitting_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    deposit_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    # Dispensing measurements
    mono_pd_re = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, help_text='Monocular PD Right (mm)')
    mono_pd_le = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, help_text='Monocular PD Left (mm)')
    fitting_height_re = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, help_text='Fitting Height RE (mm)')
    fitting_height_le = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, help_text='Fitting Height LE (mm)')
    vertex_distance = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, help_text='Vertex Distance (mm)')
    pantoscopic_tilt = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, help_text='Pantoscopic Tilt (degrees)')
    wrap_angle = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, help_text='Frame Wrap / Face-form Angle (degrees)')
    # QC verification
    qc_verified = models.BooleanField(default=False, help_text='Quality check passed by dispenser')
    qc_verified_by = models.ForeignKey(
        'accounts.User', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='optical_qc_verified',
    )
    qc_verified_at = models.DateTimeField(null=True, blank=True)
    qc_notes = models.TextField(blank=True, help_text='QC remarks — power verification, alignment, cosmetic check')

    special_instructions = models.TextField(blank=True)
    ordered_date = models.DateField(default=timezone.now)
    expected_date = models.DateField(null=True, blank=True)
    delivered_date = models.DateField(null=True, blank=True)
    delivered_to = models.ForeignKey(
        'accounts.User', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='delivered_opticals'
    )

    class Meta:
        ordering = ['-ordered_date']

    def __str__(self):
        return f"Optical Order {self.order_number} - {self.patient.full_name}"

    @property
    def balance_due(self):
        return max(0, self.total_amount - self.deposit_paid)

    def save(self, *args, **kwargs):
        if not self.order_number:
            today = timezone.localdate()
            count = OpticalOrder.objects.filter(ordered_date__year=today.year).count() + 1
            self.order_number = f"OPT-{today.strftime('%Y')}-{count:04d}"
        self.total_amount = self.frame_price + self.lens_price + self.fitting_charge
        super().save(*args, **kwargs)


# ── Contact Lens Fitting & Follow-Up ─────────────────────────────────────────

class ContactLensType(models.TextChoices):
    DAILY       = 'DAILY',    'Daily Disposable'
    FORTNIGHTLY = 'FORT',     'Fortnightly Disposable'
    MONTHLY     = 'MONTHLY',  'Monthly Disposable'
    ANNUAL      = 'ANNUAL',   'Annual / Extended Wear'
    RIGID       = 'RIGID',    'Rigid Gas-Permeable (RGP)'
    SCLERAL     = 'SCLERAL',  'Scleral Lens'
    ORTHO_K     = 'ORTHOK',   'Orthokeratology'
    THERAPEUTIC = 'THERAPEUTIC', 'Therapeutic / Bandage Lens'


class ContactLensFitting(AuditModel):
    """
    Contact lens fitting record — Orthoptist or Optometrist records the fitting
    parameters, dispenses the lenses, and schedules follow-up visits.
    """
    fitting_number = models.CharField(max_length=30, unique=True)
    patient = models.ForeignKey('patients.Patient', on_delete=models.PROTECT, related_name='cl_fittings')
    fitted_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT, related_name='cl_fittings_done')
    optical_prescription = models.ForeignKey(
        'prescriptions.OpticalPrescription', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='cl_fittings'
    )
    lens_type = models.CharField(max_length=20, choices=ContactLensType.choices)
    brand = models.CharField(max_length=100, blank=True)
    fitting_date = models.DateField(default=timezone.now)

    # Right eye parameters
    re_sphere    = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    re_cylinder  = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    re_axis      = models.PositiveSmallIntegerField(null=True, blank=True)
    re_add       = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    re_base_curve = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True, help_text='mm')
    re_diameter  = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True, help_text='mm')

    # Left eye parameters
    le_sphere    = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    le_cylinder  = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    le_axis      = models.PositiveSmallIntegerField(null=True, blank=True)
    le_add       = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    le_base_curve = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True, help_text='mm')
    le_diameter  = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True, help_text='mm')

    # Dispensing
    quantity_dispensed = models.PositiveIntegerField(default=1, help_text='Pairs or boxes dispensed')
    price_per_unit = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    care_solution_included = models.BooleanField(default=False)
    care_solution_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Follow-up
    next_follow_up = models.DateField(null=True, blank=True, help_text='Scheduled follow-up date')
    follow_up_notes = models.TextField(blank=True)
    patient_education_given = models.BooleanField(default=False, help_text='Insertion/removal and hygiene training given')
    fitting_assessment = models.TextField(blank=True, help_text='Centration, movement, fit assessment notes')
    over_refraction_va = models.CharField(max_length=20, blank=True, help_text='VA achieved with trial lens')
    is_successful = models.BooleanField(default=True, help_text='Fitting deemed satisfactory')

    class Meta:
        ordering = ['-fitting_date']
        verbose_name = 'Contact Lens Fitting'

    def __str__(self):
        return f"{self.fitting_number} — {self.patient.full_name} ({self.get_lens_type_display()})"

    def save(self, *args, **kwargs):
        if not self.fitting_number:
            today = timezone.localdate()
            count = ContactLensFitting.objects.filter(fitting_date__year=today.year).count() + 1
            self.fitting_number = f"CLF-{today.strftime('%Y')}-{count:04d}"
        self.total_amount = (self.price_per_unit * self.quantity_dispensed) + self.care_solution_price
        super().save(*args, **kwargs)


# ── Low Vision Aid Dispensing ─────────────────────────────────────────────────

class LowVisionAidType(models.TextChoices):
    OPTICAL_MAGNIFIER    = 'OPT_MAG',  'Optical Magnifier (Hand-held / Stand)'
    TELESCOPIC           = 'TELESC',   'Telescopic Aid / Monocular'
    BIOPTIC              = 'BIOPTIC',  'Bioptic Telescope'
    CLOSED_CIRCUIT_TV    = 'CCTV',     'CCTV / Electronic Magnifier'
    READING_SPECTACLE    = 'RD_SPEC',  'High Add Reading Spectacle'
    PRISM_SPECTACLE      = 'PRISM',    'Prism Spectacle'
    TINTED_FILTER        = 'TINTED',   'Tinted Filter / Light Management'
    TALKING_DEVICE       = 'TALKING',  'Talking / Audio Device'
    CANE                 = 'CANE',     'Mobility Cane'
    OTHER                = 'OTHER',    'Other Aid'


# ── Optical Lab Job Card ──────────────────────────────────────────────────────

class LabJobStatus(models.TextChoices):
    PENDING   = 'PENDING',   'Pending Send'
    SENT      = 'SENT',      'Sent to Lab'
    RETURNED  = 'RETURNED',  'Returned — QC Check'
    READY     = 'READY',     'Ready for Collection'
    COLLECTED = 'COLLECTED', 'Collected by Patient'
    CANCELLED = 'CANCELLED', 'Cancelled'


class OpticalLabJob(AuditModel):
    """
    Tracks an optical order through the glazing / fabrication lab workflow.
    Created automatically when an order is sent to the lab for lens cutting.
    """
    order      = models.OneToOneField(OpticalOrder, on_delete=models.CASCADE, related_name='lab_job')
    lab_name   = models.CharField(max_length=120, default='In-House Glazing Lab')
    job_number = models.CharField(max_length=60, blank=True, help_text='Lab reference / job ticket number')
    status     = models.CharField(max_length=20, choices=LabJobStatus.choices, default=LabJobStatus.PENDING)

    sent_date            = models.DateField(null=True, blank=True)
    expected_return_date = models.DateField(null=True, blank=True)
    actual_return_date   = models.DateField(null=True, blank=True)
    special_notes        = models.TextField(blank=True)

    sent_by     = models.ForeignKey(
        'accounts.User', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='lab_jobs_sent'
    )
    received_by = models.ForeignKey(
        'accounts.User', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='lab_jobs_received'
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Lab Job — {self.order.order_number} [{self.get_status_display()}]"

    @property
    def is_overdue(self):
        from django.utils import timezone
        if self.expected_return_date and self.status in (LabJobStatus.SENT,):
            return timezone.localdate() > self.expected_return_date
        return False


# ── Low Vision Aid Dispensing ─────────────────────────────────────────────────

class LowVisionAidDispensing(AuditModel):
    """
    Low Vision Aid dispensing record — Low Vision Specialist records
    assessment outcome and aids dispensed for rehabilitation.
    """
    dispensing_number = models.CharField(max_length=30, unique=True)
    patient = models.ForeignKey('patients.Patient', on_delete=models.PROTECT, related_name='lva_dispensings')
    dispensed_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT, related_name='lva_dispensings_done')
    dispensing_date = models.DateField(default=timezone.now)

    # Assessment summary
    distance_va_re = models.CharField(max_length=20, blank=True, help_text='Unaided Distance VA Right Eye')
    distance_va_le = models.CharField(max_length=20, blank=True, help_text='Unaided Distance VA Left Eye')
    near_va_re = models.CharField(max_length=20, blank=True, help_text='Unaided Near VA Right Eye')
    near_va_le = models.CharField(max_length=20, blank=True, help_text='Unaided Near VA Left Eye')
    vision_goal = models.TextField(blank=True, help_text='Patient\'s rehabilitation goal (e.g. read newspaper, recognise faces)')

    # Aid dispensed
    aid_type = models.CharField(max_length=20, choices=LowVisionAidType.choices)
    aid_brand_model = models.CharField(max_length=200, blank=True)
    magnification = models.CharField(max_length=50, blank=True, help_text='e.g. 4×, 8D, +20.00')
    va_achieved_with_aid = models.CharField(max_length=20, blank=True, help_text='VA measured with the dispensed aid')

    # Pricing
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    quantity = models.PositiveIntegerField(default=1)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Training & follow-up
    training_given = models.TextField(blank=True, help_text='Training and adaptation advice given')
    follow_up_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    patient_satisfied = models.BooleanField(default=True)

    class Meta:
        ordering = ['-dispensing_date']
        verbose_name = 'Low Vision Aid Dispensing'

    def __str__(self):
        return f"{self.dispensing_number} — {self.patient.full_name} ({self.get_aid_type_display()})"

    def save(self, *args, **kwargs):
        if not self.dispensing_number:
            today = timezone.localdate()
            count = LowVisionAidDispensing.objects.filter(dispensing_date__year=today.year).count() + 1
            self.dispensing_number = f"LVA-{today.strftime('%Y')}-{count:04d}"
        self.total_amount = self.unit_price * self.quantity
        super().save(*args, **kwargs)


# ── Lens Price Matrix ────────────────────────────────────────────────────────

class CoatingType(models.TextChoices):
    NONE        = 'NONE',    'No Coating'
    AR          = 'AR',      'Anti-Reflective'
    BLUE_LIGHT  = 'BLUE',    'Blue-Light Filter'
    PHOTOCHROM  = 'PHOTO',   'Photochromic (Transitions)'
    POLARISED   = 'POLAR',   'Polarised'
    UV400       = 'UV400',   'UV400'
    SCRATCH     = 'SCRATCH', 'Scratch-Resistant'
    HYDRO       = 'HYDRO',   'Hydrophobic'


class PowerBand(models.TextChoices):
    LOW       = 'LOW',   '0.00 to ±3.00'
    MEDIUM    = 'MED',   '±3.25 to ±6.00'
    HIGH      = 'HIGH',  '±6.25 to ±10.00'
    VERY_HIGH = 'VHIGH', '±10.25 and above'


class LensPriceMatrix(AuditModel):
    """
    Lookup table: lens_type × refractive_index × coating × power_band → price.
    Used by the optical shop to auto-price lenses based on prescription parameters.
    """
    lens_type = models.CharField(max_length=20, choices=LensType.choices)
    refractive_index = models.DecimalField(
        max_digits=4, decimal_places=2,
        help_text='e.g. 1.50, 1.56, 1.60, 1.67, 1.74'
    )
    coating = models.CharField(max_length=20, choices=CoatingType.choices, default=CoatingType.NONE)
    power_band = models.CharField(max_length=10, choices=PowerBand.choices, default=PowerBand.LOW)
    price = models.DecimalField(max_digits=10, decimal_places=2, help_text='Selling price in FCFA')

    class Meta:
        ordering = ['lens_type', 'refractive_index', 'coating', 'power_band']
        unique_together = [('lens_type', 'refractive_index', 'coating', 'power_band')]
        verbose_name = 'Lens Price Matrix Entry'
        verbose_name_plural = 'Lens Price Matrix'

    def __str__(self):
        return (
            f"{self.get_lens_type_display()} | "
            f"Index {self.refractive_index} | "
            f"{self.get_coating_display()} | "
            f"{self.get_power_band_display()} → "
            f"{self.price:,.0f} FCFA"
        )


# ── Warranty & After-Sales ───────────────────────────────────────────────────

class WarrantyStatus(models.TextChoices):
    ACTIVE    = 'ACTIVE',    'Active'
    CLAIMED   = 'CLAIMED',   'Claimed'
    EXPIRED   = 'EXPIRED',   'Expired'
    VOIDED    = 'VOIDED',    'Voided'


class OpticalWarranty(AuditModel):
    """
    Warranty record linked to an optical order.
    Auto-created when an order is delivered.
    """
    order = models.OneToOneField(OpticalOrder, on_delete=models.CASCADE, related_name='warranty')
    warranty_months = models.PositiveSmallIntegerField(default=12, help_text='Duration in months')
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=10, choices=WarrantyStatus.choices, default=WarrantyStatus.ACTIVE)
    terms = models.TextField(blank=True, help_text='Warranty terms / coverage details')

    class Meta:
        ordering = ['-start_date']
        verbose_name = 'Optical Warranty'
        verbose_name_plural = 'Optical Warranties'

    def __str__(self):
        return f"Warranty — {self.order.order_number} ({self.get_status_display()})"

    @property
    def is_valid(self):
        return self.status == WarrantyStatus.ACTIVE and self.end_date >= timezone.localdate()

    def save(self, *args, **kwargs):
        if not self.end_date:
            from datetime import timedelta
            self.end_date = self.start_date + timedelta(days=30 * self.warranty_months)
        super().save(*args, **kwargs)


class RepairType(models.TextChoices):
    WARRANTY_CLAIM = 'WARRANTY', 'Warranty Claim'
    FRAME_REPAIR   = 'FRAME',   'Frame Repair / Adjustment'
    LENS_REMAKE    = 'REMAKE',  'Lens Remake'
    RELENS         = 'RELENS',  'Re-lens (New Prescription)'
    NOSE_PAD       = 'NOSEPAD', 'Nose Pad Replacement'
    TEMPLE_REPLACE = 'TEMPLE',  'Temple Arm Replacement'
    SCREW_HINGE    = 'SCREW',   'Screw / Hinge Fix'
    TINTING        = 'TINT',    'Re-tint'
    OTHER          = 'OTHER',   'Other'


class RepairStatus(models.TextChoices):
    RECEIVED    = 'RECEIVED',   'Received'
    IN_PROGRESS = 'IN_PROG',    'In Progress'
    COMPLETED   = 'COMPLETED',  'Completed'
    RETURNED    = 'RETURNED',   'Returned to Patient'
    CANCELLED   = 'CANCELLED',  'Cancelled'


class OpticalRepair(AuditModel):
    """
    After-sales repair / adjustment record.
    Can be linked to an existing order (warranty claim) or standalone.
    """
    repair_number = models.CharField(max_length=30, unique=True)
    patient = models.ForeignKey('patients.Patient', on_delete=models.PROTECT, related_name='optical_repairs')
    order = models.ForeignKey(OpticalOrder, null=True, blank=True, on_delete=models.SET_NULL, related_name='repairs')
    repair_type = models.CharField(max_length=20, choices=RepairType.choices)
    status = models.CharField(max_length=20, choices=RepairStatus.choices, default=RepairStatus.RECEIVED)
    description = models.TextField(help_text='What is broken / what the patient wants')
    is_warranty_claim = models.BooleanField(default=False)
    cost = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text='Cost to patient (0 if warranty)')
    received_date = models.DateField(default=timezone.now)
    completed_date = models.DateField(null=True, blank=True)
    returned_date = models.DateField(null=True, blank=True)
    technician_notes = models.TextField(blank=True)
    received_by = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='optical_repairs_received'
    )

    class Meta:
        ordering = ['-received_date']

    def __str__(self):
        return f"Repair {self.repair_number} — {self.patient.full_name} ({self.get_repair_type_display()})"

    def save(self, *args, **kwargs):
        if not self.repair_number:
            today = timezone.localdate()
            count = OpticalRepair.objects.filter(received_date__year=today.year).count() + 1
            self.repair_number = f"RPR-{today.strftime('%Y')}-{count:04d}"
        super().save(*args, **kwargs)
