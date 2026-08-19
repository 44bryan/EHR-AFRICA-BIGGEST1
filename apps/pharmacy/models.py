"""
Pharmacy Module
Drug formulary, stock management, dispensing, reorder alerts.
Hospital-integrated pharmacy — JCI MMU standards.
"""
from django.db import models
from django.utils import timezone
from apps.core.models import TimeStampedModel, AuditModel


class StorageCondition(models.TextChoices):
    ROOM_TEMP  = 'ROOM',   'Room Temperature (15–25 °C)'
    COOL       = 'COOL',   'Cool (8–15 °C)'
    REFRIGERATED = 'FRIDGE', 'Refrigerated (2–8 °C)'
    FROZEN     = 'FROZEN', 'Frozen (−20 °C or below)'
    PROTECT_LIGHT = 'LIGHT', 'Protect from Light'
    FLAMMABLE  = 'FLAME',  'Flammable — separate storage'


class DrugCategory(models.TextChoices):
    ANTIBIOTIC = 'ANTIBIOTIC', 'Antibiotic'
    ANTIFUNGAL = 'ANTIFUNGAL', 'Antifungal'
    ANTIVIRAL = 'ANTIVIRAL', 'Antiviral'
    GLAUCOMA = 'GLAUCOMA', 'Anti-Glaucoma'
    STEROID = 'STEROID', 'Corticosteroid'
    NSAID = 'NSAID', 'NSAID'
    MYDRIATIC = 'MYDRIATIC', 'Mydriatic/Cycloplegic'
    LUBRICANT = 'LUBRICANT', 'Lubricant/Artificial Tear'
    ANAESTHETIC = 'ANAESTHETIC', 'Local Anaesthetic'
    VITAMIN = 'VITAMIN', 'Vitamin/Supplement'
    ANALGESIC = 'ANALGESIC', 'Analgesic'
    ANTIHYPERTENSIVE = 'ANTIHTN', 'Antihypertensive'
    ANTIDIABETIC = 'ANTIDIAB', 'Antidiabetic'
    OTHER = 'OTHER', 'Other'


class DrugForm(models.TextChoices):
    EYE_DROP = 'EYE_DROP', 'Eye Drop'
    EYE_OINTMENT = 'EYE_OINT', 'Eye Ointment'
    TABLET = 'TABLET', 'Tablet'
    CAPSULE = 'CAPSULE', 'Capsule'
    INJECTION = 'INJECTION', 'Injection'
    SYRUP = 'SYRUP', 'Syrup'
    CREAM = 'CREAM', 'Cream'
    NASAL_DROP = 'NASAL', 'Nasal Drop'
    OTHER = 'OTHER', 'Other'


class ControlledSchedule(models.TextChoices):
    S2 = 'S2', 'Schedule II — Opioids / Strong Narcotics'
    S3 = 'S3', 'Schedule III — Moderate Controlled'
    S4 = 'S4', 'Schedule IV — Benzodiazepines / Controlled'
    S5 = 'S5', 'Schedule V — Cough Preparations / Mild Controlled'


class Drug(AuditModel):
    """Master drug formulary"""
    name = models.CharField(max_length=200)
    generic_name = models.CharField(max_length=200)
    brand_name = models.CharField(max_length=200, blank=True)
    category = models.CharField(max_length=20, choices=DrugCategory.choices)
    form = models.CharField(max_length=20, choices=DrugForm.choices)
    strength = models.CharField(max_length=100, blank=True, help_text='e.g. 0.5%, 5mg')
    unit = models.CharField(max_length=50, default='unit', help_text='e.g. bottle, tube, tablet')
    barcode = models.CharField(max_length=100, blank=True, unique=True, null=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    requires_prescription = models.BooleanField(default=True)
    reorder_level = models.PositiveIntegerField(default=10)
    # Pricing
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    # Storage
    storage_condition = models.CharField(
        max_length=10, choices=StorageCondition.choices,
        default=StorageCondition.ROOM_TEMP,
    )
    # Controlled drug classification
    is_controlled = models.BooleanField(
        default=False,
        help_text='Requires narcotics register entry and witness signature on every dispensing'
    )
    controlled_schedule = models.CharField(
        max_length=5, blank=True, choices=ControlledSchedule.choices,
        help_text='WHO/national controlled drug schedule'
    )

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} {self.strength}".strip()

    @property
    def current_stock(self):
        return self.stock_items.filter(
            is_deleted=False, expiry_date__gte=timezone.localdate()
        ).aggregate(total=models.Sum('quantity_remaining'))['total'] or 0

    @property
    def needs_reorder(self):
        return self.current_stock <= self.reorder_level


class DrugStock(AuditModel):
    """Individual stock batch"""
    drug = models.ForeignKey(Drug, on_delete=models.PROTECT, related_name='stock_items')
    batch_number = models.CharField(max_length=100)
    expiry_date = models.DateField()
    quantity_received = models.PositiveIntegerField()
    quantity_remaining = models.PositiveIntegerField()
    supplier = models.CharField(max_length=200, blank=True)
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    received_date = models.DateField(default=timezone.localdate)
    manufacture_date = models.DateField(null=True, blank=True, help_text='Manufacturing / production date on the package')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['expiry_date']

    def __str__(self):
        return f"{self.drug.name} - Batch {self.batch_number} (Exp: {self.expiry_date})"

    @property
    def is_expired(self):
        return self.expiry_date < timezone.localdate()

    @property
    def days_to_expiry(self):
        delta = self.expiry_date - timezone.localdate()
        return delta.days


class DispensingStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    PARTIAL = 'PARTIAL', 'Partially Dispensed'
    DISPENSED = 'DISPENSED', 'Fully Dispensed'
    CANCELLED = 'CANCELLED', 'Cancelled'


class Dispensing(AuditModel):
    """Dispensing record linked to a prescription"""
    dispensing_number = models.CharField(max_length=30, unique=True)
    patient = models.ForeignKey(
        'patients.Patient', on_delete=models.PROTECT, related_name='dispensings'
    )
    prescription = models.ForeignKey(
        'prescriptions.DrugPrescription', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='dispensings'
    )
    dispensed_by = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='dispensed_records'
    )
    status = models.CharField(max_length=20, choices=DispensingStatus.choices, default=DispensingStatus.PENDING)
    dispensed_at = models.DateTimeField(default=timezone.now)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    # JCI MMU.6.1 — pharmacist verification and patient counseling
    verified_by_pharmacist = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='pharmacy_verified_dispensings',
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    counseling_given = models.BooleanField(
        default=False,
        help_text='Patient/caregiver counseled on use, storage and side effects'
    )
    counseling_notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-dispensed_at']

    def __str__(self):
        return f"Dispensing {self.dispensing_number} - {self.patient.full_name}"

    def save(self, *args, **kwargs):
        if not self.dispensing_number:
            today = timezone.localdate()
            count = Dispensing.objects.filter(
                dispensed_at__date=today
            ).count() + 1
            self.dispensing_number = f"DISP-{today.strftime('%Y%m%d')}-{count:04d}"
        super().save(*args, **kwargs)


class DispensingItem(TimeStampedModel):
    """Individual drug item within a dispensing record"""
    dispensing = models.ForeignKey(Dispensing, on_delete=models.CASCADE, related_name='items')
    drug = models.ForeignKey(Drug, on_delete=models.PROTECT, null=True, blank=True)
    custom_drug_name = models.CharField(max_length=200, blank=True,
                                        help_text='Used when drug is not in the formulary (Others)')
    stock_batch = models.ForeignKey(DrugStock, null=True, blank=True, on_delete=models.SET_NULL)
    quantity_prescribed = models.PositiveIntegerField(
        null=True, blank=True,
        help_text='Quantity originally prescribed (for partial-fill tracking)'
    )
    quantity_dispensed = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    instructions = models.TextField(blank=True)
    # Generic substitution tracking (JCI MMU.4)
    substituted_for = models.CharField(
        max_length=200, blank=True,
        help_text='Original brand/drug name if a generic substitution was made'
    )
    substitution_approved_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='substitution_approvals',
    )

    @property
    def display_name(self):
        """Drug name for display and billing."""
        if self.drug:
            return self.drug.name
        return self.custom_drug_name or 'Non-formulary Drug'

    def save(self, *args, **kwargs):
        self.subtotal = self.quantity_dispensed * self.unit_price
        super().save(*args, **kwargs)
        # Deduct from stock
        if self.stock_batch:
            self.stock_batch.quantity_remaining = max(
                0, self.stock_batch.quantity_remaining - self.quantity_dispensed
            )
            self.stock_batch.save()


class AdjustmentReason(models.TextChoices):
    DAMAGE = 'DAMAGE', 'Damaged / Broken'
    EXPIRED = 'EXPIRED', 'Expired — Disposal'
    COUNT_UP = 'COUNT_UP', 'Physical Count — Surplus'
    COUNT_DOWN = 'COUNT_DOWN', 'Physical Count — Shortage'
    RETURN = 'RETURN', 'Patient Return'
    THEFT = 'THEFT', 'Suspected Theft / Pilferage'
    OTHER = 'OTHER', 'Other'


class StockAdjustment(AuditModel):
    """Manual stock adjustment — records any change to a batch's quantity_remaining."""
    batch = models.ForeignKey(
        DrugStock, on_delete=models.PROTECT, related_name='adjustments'
    )
    reason = models.CharField(max_length=20, choices=AdjustmentReason.choices)
    quantity_before = models.IntegerField(help_text='Stock level before adjustment')
    quantity_change = models.IntegerField(
        help_text='Positive = stock added, Negative = stock removed'
    )
    quantity_after = models.IntegerField(help_text='Stock level after adjustment')
    notes = models.TextField(blank=True)
    adjusted_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-adjusted_at']

    def __str__(self):
        sign = '+' if self.quantity_change >= 0 else ''
        return (
            f'{self.batch.drug.name} | {self.get_reason_display()} | '
            f'{sign}{self.quantity_change} (Batch {self.batch.batch_number})'
        )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Apply the change to the batch
        self.batch.quantity_remaining = max(0, self.quantity_after)
        self.batch.save(update_fields=['quantity_remaining'])


# ── Controlled Drugs Register ────────────────────────────────────────────────

class ControlledDrugEntryType(models.TextChoices):
    STOCK_IN   = 'STOCK_IN',   'Stock Received'
    DISPENSE   = 'DISPENSE',   'Dispensed to Patient'
    RETURN     = 'RETURN',     'Patient Return'
    WASTAGE    = 'WASTAGE',    'Wastage / Destroyed'
    ADJUSTMENT = 'ADJUSTMENT', 'Manual Adjustment'


class ControlledDrugEntry(AuditModel):
    """
    Narcotics/controlled drugs register — every movement of a scheduled drug
    recorded here with pharmacist + witness (JCI MMU.3.1).
    """
    drug = models.ForeignKey(Drug, on_delete=models.PROTECT, related_name='controlled_entries')
    batch = models.ForeignKey(DrugStock, on_delete=models.PROTECT, null=True, blank=True, related_name='controlled_entries')
    entry_type = models.CharField(max_length=20, choices=ControlledDrugEntryType.choices)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    balance_before = models.DecimalField(max_digits=10, decimal_places=2)
    balance_after = models.DecimalField(max_digits=10, decimal_places=2)
    patient = models.ForeignKey('patients.Patient', on_delete=models.SET_NULL, null=True, blank=True, related_name='controlled_drug_entries')
    dispensing = models.ForeignKey(Dispensing, on_delete=models.SET_NULL, null=True, blank=True, related_name='controlled_entries')
    performed_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT, related_name='controlled_entries_made')
    witness = models.ForeignKey('accounts.User', on_delete=models.PROTECT, null=True, blank=True, related_name='controlled_entries_witnessed')
    witness_confirmed = models.BooleanField(default=False, help_text='Witness has counter-signed this entry')
    notes = models.TextField(blank=True)
    entry_date = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-entry_date']
        verbose_name = 'Controlled Drug Entry'
        verbose_name_plural = 'Controlled Drug Register'

    def __str__(self):
        return f"{self.drug.name} | {self.get_entry_type_display()} | {self.quantity} | {self.entry_date:%Y-%m-%d %H:%M}"


# ── Ward Drug Return ─────────────────────────────────────────────────────────

class WardDrugReturnStatus(models.TextChoices):
    PENDING  = 'PENDING',  'Pending Pharmacy Acceptance'
    ACCEPTED = 'ACCEPTED', 'Accepted — Stock Restored'
    REJECTED = 'REJECTED', 'Rejected — Disposed'


class WardDrugReturn(AuditModel):
    """
    Drug return from ward on patient discharge — nurse submits, pharmacist accepts/rejects.
    """
    return_number = models.CharField(max_length=30, unique=True)
    admission = models.ForeignKey('ipd.Admission', on_delete=models.PROTECT, related_name='drug_returns')
    drug = models.ForeignKey(Drug, on_delete=models.PROTECT, related_name='ward_returns')
    batch = models.ForeignKey(DrugStock, on_delete=models.SET_NULL, null=True, blank=True, related_name='ward_returns')
    quantity_returned = models.PositiveIntegerField()
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=WardDrugReturnStatus.choices, default=WardDrugReturnStatus.PENDING)
    returned_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT, related_name='drug_returns_submitted')
    returned_at = models.DateTimeField(default=timezone.now)
    actioned_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='drug_returns_actioned')
    actioned_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    class Meta:
        ordering = ['-returned_at']

    def __str__(self):
        return f"{self.return_number} — {self.drug.name} × {self.quantity_returned}"

    def save(self, *args, **kwargs):
        if not self.return_number:
            today = timezone.localdate()
            count = WardDrugReturn.objects.filter(returned_at__date=today).count() + 1
            self.return_number = f"WDR-{today.strftime('%Y%m%d')}-{count:04d}"
        super().save(*args, **kwargs)


# ── Chronic Prescription Refill Tracking ─────────────────────────────────────

class ChronicPrescription(AuditModel):
    """
    Long-term repeating prescription for chronic conditions.
    Flags patients due for refill so pharmacist can proactively contact them.
    """
    patient = models.ForeignKey('patients.Patient', on_delete=models.PROTECT, related_name='chronic_prescriptions')
    drug = models.ForeignKey(Drug, on_delete=models.PROTECT, related_name='chronic_prescriptions')
    prescribing_doctor = models.ForeignKey('accounts.User', on_delete=models.PROTECT, related_name='chronic_prescriptions_written')
    dose = models.CharField(max_length=100, help_text='e.g. 1 drop OD, 5 mg daily')
    frequency = models.CharField(max_length=100, help_text='e.g. Once daily, BD, TDS')
    quantity_per_refill = models.PositiveIntegerField(help_text='Units dispensed per refill visit')
    refill_interval_days = models.PositiveIntegerField(default=30)
    start_date = models.DateField(default=timezone.now)
    next_refill_date = models.DateField(null=True, blank=True)
    last_refill_date = models.DateField(null=True, blank=True)
    refill_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['next_refill_date']

    def __str__(self):
        return f"{self.patient.full_name} — {self.drug.name} (every {self.refill_interval_days}d)"

    def save(self, *args, **kwargs):
        import datetime
        if not self.next_refill_date and self.start_date:
            self.next_refill_date = self.start_date + datetime.timedelta(days=self.refill_interval_days)
        super().save(*args, **kwargs)

    @property
    def is_due(self):
        return self.is_active and self.next_refill_date and self.next_refill_date <= timezone.localdate()

    @property
    def days_until_refill(self):
        if not self.next_refill_date:
            return None
        return (self.next_refill_date - timezone.localdate()).days

    def record_refill(self):
        """Call when a refill dispensing is completed to advance the schedule."""
        import datetime
        today = timezone.localdate()
        self.refill_count += 1
        self.last_refill_date = today
        self.next_refill_date = today + datetime.timedelta(days=self.refill_interval_days)
        self.save(update_fields=['refill_count', 'last_refill_date', 'next_refill_date'])


# ── Supplier / Procurement ────────────────────────────────────────────────────

class Supplier(AuditModel):
    """
    Drug supplier / manufacturer / distributor.
    JCI MMU.3 — procurement from licensed sources only.
    """
    name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    registration_number = models.CharField(
        max_length=100, blank=True,
        help_text='Pharmacy Board / MINSANTE registration number'
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class PurchaseOrderStatus(models.TextChoices):
    DRAFT     = 'DRAFT',     'Draft'
    SUBMITTED = 'SUBMITTED', 'Submitted to Supplier'
    APPROVED  = 'APPROVED',  'Approved'
    PARTIAL   = 'PARTIAL',   'Partially Received'
    RECEIVED  = 'RECEIVED',  'Fully Received'
    CANCELLED = 'CANCELLED', 'Cancelled'


class PurchaseOrder(AuditModel):
    """
    Formal purchase order to a supplier.
    Supports partial receipts — each batch received creates a DrugStock.
    """
    order_number = models.CharField(max_length=30, unique=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='purchase_orders')
    status = models.CharField(max_length=15, choices=PurchaseOrderStatus.choices, default=PurchaseOrderStatus.DRAFT)
    order_date = models.DateField(default=timezone.localdate)
    expected_delivery = models.DateField(null=True, blank=True)
    approved_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='approved_purchase_orders',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-order_date']

    def __str__(self):
        return f"PO-{self.order_number} — {self.supplier.name}"

    def save(self, *args, **kwargs):
        if not self.order_number:
            today = timezone.localdate()
            count = PurchaseOrder.objects.filter(order_date__year=today.year).count() + 1
            self.order_number = f"{today.year}-{count:05d}"
        super().save(*args, **kwargs)


class PurchaseOrderItem(TimeStampedModel):
    """Line item on a purchase order."""
    order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='items')
    drug = models.ForeignKey(Drug, on_delete=models.PROTECT, related_name='purchase_items')
    quantity_ordered = models.PositiveIntegerField()
    quantity_received = models.PositiveIntegerField(default=0)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    # Filled in when goods are actually received
    batch_number = models.CharField(max_length=100, blank=True)
    manufacture_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    stock_created = models.ForeignKey(
        DrugStock, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='purchase_order_items',
        help_text='DrugStock batch created when this item was received'
    )

    @property
    def line_total(self):
        return self.quantity_ordered * self.unit_cost

    def __str__(self):
        return f"{self.drug.name} × {self.quantity_ordered} (PO {self.order.order_number})"


# ── Dispensing Return (patient/ward brings back dispensed drugs) ───────────────

class DispensingReturnReason(models.TextChoices):
    PATIENT_REFUSED   = 'REFUSED',   'Patient Refused Medication'
    DUPLICATE         = 'DUPLICATE', 'Duplicate Dispensing'
    WRONG_DRUG        = 'WRONG',     'Wrong Drug Dispensed'
    WRONG_QUANTITY    = 'WRONG_QTY', 'Wrong Quantity'
    PATIENT_DECEASED  = 'DECEASED',  'Patient Deceased'
    DISCHARGE         = 'DISCHARGE', 'Patient Discharged — Unused Drugs'
    OTHER             = 'OTHER',     'Other'


class DispensingReturn(AuditModel):
    """
    Return of already-dispensed drugs back to pharmacy stock.
    Stock is restored on save if the batch is still valid.
    JCI MMU.5 — medication return and restocking policy.
    """
    dispensing = models.ForeignKey(
        Dispensing, on_delete=models.PROTECT, related_name='returns'
    )
    drug = models.ForeignKey(Drug, on_delete=models.PROTECT, related_name='dispensing_returns')
    stock_batch = models.ForeignKey(
        DrugStock, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='dispensing_returns',
    )
    quantity_returned = models.PositiveIntegerField()
    reason = models.CharField(max_length=15, choices=DispensingReturnReason.choices)
    notes = models.TextField(blank=True)
    stock_restored = models.BooleanField(
        default=False,
        help_text='True when quantity_returned was added back to the stock batch'
    )
    returned_by = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='dispensing_returns_processed',
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Return {self.quantity_returned}× {self.drug.name} from {self.dispensing.dispensing_number}"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        # Restore stock once on first save (non-expired batch only)
        if is_new and not self.stock_restored and self.stock_batch:
            if not self.stock_batch.is_expired:
                self.stock_batch.quantity_remaining += self.quantity_returned
                self.stock_batch.save(update_fields=['quantity_remaining'])
                self.stock_restored = True
                DispensingReturn.objects.filter(pk=self.pk).update(stock_restored=True)
