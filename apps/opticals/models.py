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


# ══════════════════════════════════════════════════════════════════════════════
# OPTICAL INVENTORY MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

class FrameSupplier(AuditModel):
    """Optical frame / lens supplier — separate from pharmacy suppliers."""
    name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    website = models.URLField(blank=True)
    brands_carried = models.TextField(blank=True, help_text='Comma-separated list of brands supplied')
    payment_terms = models.CharField(max_length=100, blank=True, help_text='e.g. Net 30, COD, 50% advance')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class FrameGRNStatus(models.TextChoices):
    DRAFT    = 'DRAFT',    'Draft'
    RECEIVED = 'RECEIVED', 'Received & Verified'
    RETURNED = 'RETURNED', 'Returned to Supplier'


class FrameGoodsReceived(AuditModel):
    """
    Goods Received Note for optical frames — tracks each delivery batch.
    Each GRN has line items (FrameGRNItem) that update frame stock on receipt.
    """
    grn_number = models.CharField(max_length=30, unique=True)
    supplier = models.ForeignKey(FrameSupplier, null=True, blank=True, on_delete=models.SET_NULL, related_name='grns')
    supplier_invoice = models.CharField(max_length=100, blank=True, help_text='Supplier invoice / delivery note number')
    received_date = models.DateField(default=timezone.now)
    received_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT, related_name='optical_grns_received')
    status = models.CharField(max_length=10, choices=FrameGRNStatus.choices, default=FrameGRNStatus.DRAFT)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-received_date']
        verbose_name = 'Frame GRN'

    def __str__(self):
        return f"GRN {self.grn_number} — {self.supplier or 'Unknown'}"

    def save(self, *args, **kwargs):
        if not self.grn_number:
            today = timezone.localdate()
            count = FrameGoodsReceived.objects.filter(received_date__year=today.year).count() + 1
            self.grn_number = f"OGRN-{today.strftime('%Y')}-{count:04d}"
        super().save(*args, **kwargs)

    @property
    def total_cost(self):
        return sum(item.line_total for item in self.items.all())

    @property
    def total_units(self):
        return sum(item.quantity for item in self.items.all())


class FrameGRNItem(TimeStampedModel):
    """Line item on a frame GRN — links to a Frame catalogue entry."""
    grn = models.ForeignKey(FrameGoodsReceived, on_delete=models.CASCADE, related_name='items')
    frame = models.ForeignKey(Frame, on_delete=models.PROTECT, related_name='grn_items')
    quantity = models.PositiveIntegerField(default=1)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text='Cost per unit from supplier')
    batch_number = models.CharField(max_length=50, blank=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.frame} x {self.quantity}"

    @property
    def line_total(self):
        return self.unit_cost * self.quantity


class FrameStocktakeStatus(models.TextChoices):
    IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
    FINALIZED   = 'FINALIZED',   'Finalized'


class FrameStocktake(AuditModel):
    """Physical inventory count session for optical frames."""
    title = models.CharField(max_length=200, blank=True)
    date = models.DateField(default=timezone.now)
    status = models.CharField(max_length=15, choices=FrameStocktakeStatus.choices, default=FrameStocktakeStatus.IN_PROGRESS)
    conducted_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT, related_name='optical_stocktakes')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"Stocktake {self.date} — {self.title or 'Untitled'}"

    @property
    def total_items(self):
        return self.items.count()

    @property
    def variance_count(self):
        return sum(1 for item in self.items.all() if item.variance != 0)


class FrameStocktakeItem(TimeStampedModel):
    """Individual frame count line in a stocktake."""
    stocktake = models.ForeignKey(FrameStocktake, on_delete=models.CASCADE, related_name='items')
    frame = models.ForeignKey(Frame, on_delete=models.PROTECT, related_name='stocktake_items')
    system_qty = models.PositiveIntegerField(default=0, help_text='System stock at time of count')
    counted_qty = models.PositiveIntegerField(null=True, blank=True, help_text='Actual physical count')

    class Meta:
        ordering = ['frame__brand', 'frame__model']
        unique_together = [('stocktake', 'frame')]

    def __str__(self):
        return f"{self.frame} — system:{self.system_qty} counted:{self.counted_qty}"

    @property
    def variance(self):
        if self.counted_qty is None:
            return 0
        return self.counted_qty - self.system_qty


class MinStockAlertStatus(models.TextChoices):
    ACTIVE       = 'ACTIVE',       'Active'
    ACKNOWLEDGED = 'ACKNOWLEDGED', 'Acknowledged'
    RESOLVED     = 'RESOLVED',     'Resolved'


class FrameMinStockAlert(AuditModel):
    """Minimum stock threshold alert for a frame."""
    frame = models.OneToOneField(Frame, on_delete=models.CASCADE, related_name='min_stock_alert')
    min_quantity = models.PositiveIntegerField(default=2, help_text='Alert when stock drops to or below this')
    status = models.CharField(max_length=15, choices=MinStockAlertStatus.choices, default=MinStockAlertStatus.ACTIVE)
    last_triggered = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['frame__brand', 'frame__model']

    def __str__(self):
        return f"Min stock alert: {self.frame} (threshold: {self.min_quantity})"

    @property
    def is_triggered(self):
        return self.frame.quantity_in_stock <= self.min_quantity


# ══════════════════════════════════════════════════════════════════════════════
# OPTICAL WORKFLOW — TurboClinic Parity
# ══════════════════════════════════════════════════════════════════════════════

class FrameMeasurement(AuditModel):
    """
    Frame measurement record — PD, segment heights, and other measurements
    taken by the optical dispenser before ordering lenses.
    """
    order = models.OneToOneField(OpticalOrder, on_delete=models.CASCADE, related_name='frame_measurement')
    patient = models.ForeignKey('patients.Patient', on_delete=models.PROTECT, related_name='frame_measurements')
    measured_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT, related_name='frame_measurements_done')
    measurement_date = models.DateField(default=timezone.now)
    # PD measurements
    pd_re = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, help_text='PD Right Eye (mm)')
    pd_le = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, help_text='PD Left Eye (mm)')
    # Segment heights
    segment_height_re = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, help_text='Segment Height RE (mm)')
    segment_height_le = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, help_text='Segment Height LE (mm)')
    # Other measurements
    other_re = models.CharField(max_length=100, blank=True, help_text='Other measurement RE')
    other_le = models.CharField(max_length=100, blank=True, help_text='Other measurement LE')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-measurement_date']

    def __str__(self):
        return f"Frame Measurement — {self.patient.full_name} ({self.measurement_date})"


class ExternalPrescription(AuditModel):
    """
    Optical prescription brought by a patient from an external doctor/clinic.
    Used when the patient was not examined at AEF but wants to purchase glasses.
    """
    prescription_number = models.CharField(max_length=30, unique=True)
    patient = models.ForeignKey('patients.Patient', on_delete=models.PROTECT, related_name='external_prescriptions')
    received_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT, related_name='external_rx_received')
    received_date = models.DateField(default=timezone.now)
    prescriber_name = models.CharField(max_length=200, help_text='Name of external prescribing doctor')
    prescriber_clinic = models.CharField(max_length=200, blank=True, help_text='External clinic/hospital name')
    prescription_date = models.DateField(null=True, blank=True, help_text='Date on the external prescription')
    # Right eye
    re_sphere = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    re_cylinder = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    re_axis = models.PositiveSmallIntegerField(null=True, blank=True)
    re_add = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    re_prism = models.CharField(max_length=30, blank=True)
    re_va = models.CharField(max_length=20, blank=True, help_text='VA achieved')
    # Left eye
    le_sphere = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    le_cylinder = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    le_axis = models.PositiveSmallIntegerField(null=True, blank=True)
    le_add = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    le_prism = models.CharField(max_length=30, blank=True)
    le_va = models.CharField(max_length=20, blank=True, help_text='VA achieved')
    # Lens options from prescription
    lens_type_prescribed = models.CharField(max_length=20, choices=LensType.choices, blank=True)
    anti_reflective = models.BooleanField(default=False)
    photochromic = models.BooleanField(default=False)
    high_index = models.BooleanField(default=False)
    polycarbonate = models.BooleanField(default=False)
    bifocal = models.BooleanField(default=False)
    tint = models.BooleanField(default=False)
    organic = models.BooleanField(default=False)
    trifocal = models.BooleanField(default=False)
    progressive_no_line = models.BooleanField(default=False)
    permanent_wear = models.BooleanField(default=False)
    other_options = models.CharField(max_length=200, blank=True)
    observations = models.TextField(blank=True)
    # Link to optical order when dispensed
    order = models.ForeignKey(OpticalOrder, null=True, blank=True, on_delete=models.SET_NULL, related_name='external_prescriptions')

    class Meta:
        ordering = ['-received_date']

    def __str__(self):
        return f"Ext Rx {self.prescription_number} — {self.patient.full_name}"

    def save(self, *args, **kwargs):
        if not self.prescription_number:
            today = timezone.localdate()
            count = ExternalPrescription.objects.filter(received_date__year=today.year).count() + 1
            self.prescription_number = f"EXT-{today.strftime('%Y')}-{count:04d}"
        super().save(*args, **kwargs)


class GlassOrderStatus(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft'
    ORDERED = 'ORDERED', 'Ordered from Supplier'
    RECEIVED = 'RECEIVED', 'Received'
    CANCELLED = 'CANCELLED', 'Cancelled'


class GlassOrder(AuditModel):
    """
    Lens/glass order to an external supplier (Commande Verre).
    Created when lenses need to be ordered from a supplier for a patient's optical order.
    """
    order_number = models.CharField(max_length=30, unique=True)
    optical_order = models.ForeignKey(OpticalOrder, on_delete=models.CASCADE, related_name='glass_orders')
    patient = models.ForeignKey('patients.Patient', on_delete=models.PROTECT, related_name='glass_orders')
    supplier = models.ForeignKey(FrameSupplier, null=True, blank=True, on_delete=models.SET_NULL, related_name='glass_orders')
    status = models.CharField(max_length=15, choices=GlassOrderStatus.choices, default=GlassOrderStatus.DRAFT)
    order_date = models.DateField(default=timezone.now)
    expected_date = models.DateField(null=True, blank=True)
    received_date = models.DateField(null=True, blank=True)
    # RE lens specs
    re_sphere = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    re_cylinder = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    re_axis = models.PositiveSmallIntegerField(null=True, blank=True)
    re_add = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    # LE lens specs
    le_sphere = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    le_cylinder = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    le_axis = models.PositiveSmallIntegerField(null=True, blank=True)
    le_add = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    # Lens details
    lens_type = models.CharField(max_length=20, choices=LensType.choices, blank=True)
    lens_material = models.CharField(max_length=100, blank=True)
    lens_coating = models.CharField(max_length=200, blank=True)
    refractive_index = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    ordered_by = models.ForeignKey('accounts.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='glass_orders_placed')
    received_by = models.ForeignKey('accounts.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='glass_orders_received')

    class Meta:
        ordering = ['-order_date']

    def __str__(self):
        return f"Glass Order {self.order_number} — {self.patient.full_name}"

    def save(self, *args, **kwargs):
        if not self.order_number:
            today = timezone.localdate()
            count = GlassOrder.objects.filter(order_date__year=today.year).count() + 1
            self.order_number = f"GO-{today.strftime('%Y')}-{count:04d}"
        super().save(*args, **kwargs)


class LensExitNote(AuditModel):
    """
    Lens exit from optical store — tracks when lenses leave the store for
    cutting/glazing or direct dispensing. Requires validation.
    """
    exit_number = models.CharField(max_length=30, unique=True)
    optical_order = models.ForeignKey(OpticalOrder, on_delete=models.CASCADE, related_name='lens_exits')
    store = models.CharField(max_length=100, default='Optical Store', help_text='Store from which lenses exit')
    exit_date = models.DateField(default=timezone.now)
    # Lens details
    lens_re = models.CharField(max_length=200, blank=True, help_text='RE lens description')
    lens_le = models.CharField(max_length=200, blank=True, help_text='LE lens description')
    quantity = models.PositiveIntegerField(default=2, help_text='Number of lenses (usually 2)')
    # Workflow
    issued_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT, related_name='lens_exits_issued')
    validated = models.BooleanField(default=False)
    validated_by = models.ForeignKey('accounts.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='lens_exits_validated')
    validated_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-exit_date']

    def __str__(self):
        return f"Lens Exit {self.exit_number} — {self.optical_order.order_number}"

    def save(self, *args, **kwargs):
        if not self.exit_number:
            today = timezone.localdate()
            count = LensExitNote.objects.filter(exit_date__year=today.year).count() + 1
            self.exit_number = f"LEX-{today.strftime('%Y')}-{count:04d}"
        super().save(*args, **kwargs)


class QCChecklistStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending QC'
    PASSED = 'PASSED', 'QC Passed'
    FAILED = 'FAILED', 'QC Failed'


class QCChecklist(AuditModel):
    """
    Quality Control Checklist — detailed QC inspection of completed glasses.
    Separate from the simple qc_verified flag on OpticalOrder.
    Covers control levels, results, and validation.
    """
    order = models.OneToOneField(OpticalOrder, on_delete=models.CASCADE, related_name='qc_checklist')
    patient = models.ForeignKey('patients.Patient', on_delete=models.PROTECT, related_name='optical_qc_checklists')
    qc_date = models.DateField(default=timezone.now)
    checked_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT, related_name='qc_checklists_done')
    status = models.CharField(max_length=10, choices=QCChecklistStatus.choices, default=QCChecklistStatus.PENDING)
    # Control checks
    power_re_ok = models.BooleanField(default=False, help_text='RE power within tolerance')
    power_le_ok = models.BooleanField(default=False, help_text='LE power within tolerance')
    axis_alignment_ok = models.BooleanField(default=False, help_text='Axis alignment correct')
    pd_ok = models.BooleanField(default=False, help_text='PD matches prescription')
    segment_height_ok = models.BooleanField(default=False, help_text='Segment / fitting height correct')
    lens_centering_ok = models.BooleanField(default=False, help_text='Lens properly centered in frame')
    coating_ok = models.BooleanField(default=False, help_text='Coating applied as ordered')
    cosmetic_ok = models.BooleanField(default=False, help_text='No scratches, chips, defects')
    frame_alignment_ok = models.BooleanField(default=False, help_text='Frame alignment and fit')
    # Results
    control_level = models.CharField(max_length=50, blank=True, help_text='QC control level')
    results = models.TextField(blank=True, help_text='QC results summary')
    comments = models.TextField(blank=True, help_text='QC comments and observations')
    # Validation
    validated = models.BooleanField(default=False)
    validated_by = models.ForeignKey('accounts.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='qc_checklists_validated')
    validated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-qc_date']
        verbose_name = 'QC Checklist'

    def __str__(self):
        return f"QC — {self.order.order_number} ({self.get_status_display()})"


class MountingStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
    COMPLETED = 'COMPLETED', 'Completed'
    FAILED = 'FAILED', 'Failed — Redo'


class MountingRecord(AuditModel):
    """
    Lens mounting / glazing record — tracks the mounting of lenses into frames.
    """
    order = models.OneToOneField(OpticalOrder, on_delete=models.CASCADE, related_name='mounting')
    mounted_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT, related_name='mountings_done')
    mounting_date = models.DateField(default=timezone.now)
    status = models.CharField(max_length=15, choices=MountingStatus.choices, default=MountingStatus.PENDING)
    # Mounting details
    frame_adjusted = models.BooleanField(default=False, help_text='Frame adjustment done')
    lenses_cut = models.BooleanField(default=False, help_text='Lenses cut to frame shape')
    lenses_fitted = models.BooleanField(default=False, help_text='Lenses fitted into frame')
    alignment_checked = models.BooleanField(default=False, help_text='Optical alignment verified')
    cosmetic_inspection = models.BooleanField(default=False, help_text='Cosmetic inspection passed')
    notes = models.TextField(blank=True)
    completion_time = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-mounting_date']

    def __str__(self):
        return f"Mounting — {self.order.order_number} ({self.get_status_display()})"


class ValidationDataChecklist(AuditModel):
    """
    Validation Data Checklist — summary review that ensures all frame/case data
    and frame measurements are complete and correct before proceeding.
    """
    order = models.OneToOneField(OpticalOrder, on_delete=models.CASCADE, related_name='validation_checklist')
    patient = models.ForeignKey('patients.Patient', on_delete=models.PROTECT, related_name='optical_validation_checklists')
    validated_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT, related_name='optical_validations_done')
    validation_date = models.DateField(default=timezone.now)
    # Checklist items
    frame_data_complete = models.BooleanField(default=False, help_text='Frame/case data fully entered')
    measurements_complete = models.BooleanField(default=False, help_text='Frame measurements recorded')
    prescription_verified = models.BooleanField(default=False, help_text='Prescription data verified')
    patient_confirmed = models.BooleanField(default=False, help_text='Patient identity confirmed')
    lens_selection_ok = models.BooleanField(default=False, help_text='Lens type/material selection appropriate')
    # Result
    is_approved = models.BooleanField(default=False, help_text='All checks passed — approved to proceed')
    rejection_reason = models.TextField(blank=True, help_text='Reason for rejection if not approved')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-validation_date']
        verbose_name = 'Validation Data Checklist'

    def __str__(self):
        return f"Validation — {self.order.order_number} ({'Approved' if self.is_approved else 'Rejected'})"