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
    # ── Tier-Based Pricing ──────────────────────────────────────────────
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                        help_text='Standard tier selling price')
    price_express = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                         help_text='Express tier price')
    price_vip = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                     help_text='VIP tier price')
    price_executive_vip = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                               help_text='Executive VIP tier price')
    price_staff = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                       help_text='Staff / employee price')
    price_outreach = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                          help_text='Outreach / community campaign price')
    insurance_markup_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text='Markup % on cost_price for insured patients (e.g. 30 = cost + 30%)'
    )
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
    ven_class = models.CharField(
        max_length=1, blank=True,
        help_text='V=Vital, E=Essential, N=Non-essential (WHO VEN analysis)'
    )
    location = models.ForeignKey(
        'pharmacy.PharmacyLocation', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='drugs',
        help_text='Primary pharmacy location for this drug'
    )

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} {self.strength}".strip()

    def save(self, *args, **kwargs):
        # Auto-generate barcode if empty
        if not self.barcode:
            import uuid
            self.barcode = f"DRG{uuid.uuid4().hex[:10].upper()}"
        super().save(*args, **kwargs)

    def get_tier_price(self, tier=None, billing_type=None, insurance_copay_pct=None):
        """
        Return the correct selling price based on visit tier and billing type.
        Tier mapping:
          STANDARD    → selling_price
          EXPRESS     → price_express (falls back to selling_price)
          VIP         → price_vip (falls back to selling_price)
          EXECUTIVE_VIP → price_executive_vip (falls back to price_vip → selling_price)
          STAFF       → price_staff (falls back to cost_price)
          OUTREACH    → price_outreach (falls back to cost_price)
        Insurance:   cost_price + insurance_markup_pct% (scheme pays coverage_pct, patient pays copay)
        """
        from decimal import Decimal
        sp = self.selling_price or Decimal('0')

        # Insurance billing: cost + markup
        if billing_type in ('INSURANCE', 'HMO'):
            base = self.cost_price or Decimal('0')
            markup = self.insurance_markup_pct or Decimal('0')
            return round(base * (1 + markup / 100), 0)

        tier = (tier or '').upper().replace(' ', '_')
        _map = {
            'STANDARD': sp,
            'EXPRESS': self.price_express or sp,
            'VIP': self.price_vip or sp,
            'EXECUTIVE_VIP': self.price_executive_vip or self.price_vip or sp,
            'STAFF': self.price_staff or self.cost_price or sp,
            'OUTREACH': self.price_outreach or self.cost_price or sp,
        }
        return _map.get(tier, sp)

    @property
    def current_stock(self):
        return self.stock_items.filter(
            is_deleted=False,
        ).filter(
            models.Q(expiry_date__gte=timezone.localdate()) | models.Q(expiry_date__isnull=True)
        ).aggregate(total=models.Sum('quantity_remaining'))['total'] or 0

    @property
    def needs_reorder(self):
        return self.current_stock <= self.reorder_level


class DrugStock(AuditModel):
    """Individual stock batch"""
    drug = models.ForeignKey(Drug, on_delete=models.PROTECT, related_name='stock_items')
    batch_number = models.CharField(max_length=100)
    expiry_date = models.DateField(null=True, blank=True)
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
        exp = self.expiry_date.strftime('%Y-%m-%d') if self.expiry_date else 'No expiry'
        return f"{self.drug.name} - Batch {self.batch_number} ({exp})"

    def save(self, *args, **kwargs):
        # Lock quantity_received after initial creation — cannot be modified
        if self.pk:
            try:
                orig = DrugStock.objects.get(pk=self.pk)
                if orig.quantity_received != self.quantity_received:
                    self.quantity_received = orig.quantity_received  # revert
            except DrugStock.DoesNotExist:
                pass
        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        if not self.expiry_date:
            return False
        return self.expiry_date < timezone.localdate()

    @property
    def days_to_expiry(self):
        if not self.expiry_date:
            return None
        delta = self.expiry_date - timezone.localdate()
        return delta.days


class DispensingStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    PARTIAL = 'PARTIAL', 'Partially Dispensed'
    CONFIRMED = 'CONFIRMED', 'Confirmed — Sent to Cashier'
    DISPENSED = 'DISPENSED', 'Fully Dispensed'
    CANCELLED = 'CANCELLED', 'Cancelled'


class UnavailableReason(models.TextChoices):
    OUT_OF_STOCK   = 'OUT_OF_STOCK',   'Out of Stock'
    EXPIRED        = 'EXPIRED',        'All Batches Expired'
    DISCONTINUED   = 'DISCONTINUED',   'Drug Discontinued'
    NOT_IN_FORMULARY = 'NOT_FORMULARY', 'Not in Formulary'
    PATIENT_DECLINED = 'DECLINED',     'Patient Declined'
    OTHER          = 'OTHER',          'Other'


class Dispensing(AuditModel):
    """Dispensing record linked to a prescription"""
    dispensing_number = models.CharField(max_length=30, unique=True)
    patient = models.ForeignKey(
        'patients.Patient', on_delete=models.PROTECT, related_name='dispensings',
        null=True, blank=True,
    )
    walk_in_name = models.CharField(
        max_length=150, blank=True,
        help_text='Customer name for walk-in OTC sales (no patient record needed)',
    )
    walk_in_code = models.CharField(
        max_length=20, blank=True,
        help_text='Auto-generated unique code for walk-in customers (WLK-YYYYMMDD-NNNN)',
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
    discount_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text='Discount percentage (0-100)',
    )
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    is_otc = models.BooleanField(
        default=False,
        help_text='True for over-the-counter / walk-in sales without a prescription'
    )
    service_tier = models.CharField(
        max_length=20, blank=True,
        help_text='Service tier for walk-in OTC pricing (STANDARD, EXPRESS, VIP). '
                  'If blank, resolved from patient visit.',
    )
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

    @property
    def net_amount(self):
        """Total after applying flat discount and percentage discount."""
        from decimal import Decimal
        subtotal = self.total_amount or Decimal('0')
        if self.discount_pct and self.discount_pct > 0:
            subtotal -= subtotal * self.discount_pct / Decimal('100')
        if self.discount and self.discount > 0:
            subtotal -= self.discount
        return max(subtotal, Decimal('0'))

    @property
    def customer_name(self):
        if self.patient:
            return self.patient.full_name
        return self.walk_in_name or 'Walk-in Customer'

    def __str__(self):
        return f"Dispensing {self.dispensing_number} - {self.customer_name}"

    def save(self, *args, **kwargs):
        if not self.dispensing_number:
            today = timezone.localdate()
            count = Dispensing.objects.filter(
                dispensed_at__date=today
            ).count() + 1
            self.dispensing_number = f"DISP-{today.strftime('%Y%m%d')}-{count:04d}"
        # Auto-generate walk_in_code for OTC / walk-in sales
        if not self.walk_in_code and (self.is_otc or not self.patient):
            today = timezone.localdate()
            wlk_count = Dispensing.objects.filter(
                walk_in_code__startswith=f"WLK-{today.strftime('%Y%m%d')}",
            ).count() + 1
            self.walk_in_code = f"WLK-{today.strftime('%Y%m%d')}-{wlk_count:04d}"
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

    @property
    def remaining(self):
        return self.quantity_ordered - self.quantity_received

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


# ── Rx Line Unavailable Tracking ─────────────────────────────────────────────

class RxLineUnavailable(AuditModel):
    """
    Tracks prescription items the pharmacy cannot fulfil.
    One record per DrugPrescriptionItem — pharmacist marks it with a reason.
    """
    rx_item = models.OneToOneField(
        'prescriptions.DrugPrescriptionItem',
        on_delete=models.CASCADE,
        related_name='unavailable',
    )
    prescription = models.ForeignKey(
        'prescriptions.DrugPrescription',
        on_delete=models.CASCADE,
        related_name='unavailable_lines',
    )
    reason = models.CharField(max_length=20, choices=UnavailableReason.choices)
    notes = models.TextField(blank=True)
    marked_by = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT,
        related_name='rx_lines_marked_unavailable',
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Unavailable Rx Line'

    def __str__(self):
        return f"{self.rx_item.drug_name} — {self.get_reason_display()}"


# ══════════════════════════════════════════════════════════════════════════════
# HEAD PHARMACIST MODULE — WHO GPP, FIP, JCI MMU Standards
# ══════════════════════════════════════════════════════════════════════════════

class PharmacyLocation(AuditModel):
    """
    Multiple pharmacy service points within the facility.
    WHO GPP 6.2 — adequate premises and equipment at each location.
    """
    name = models.CharField(max_length=100)
    location_type = models.CharField(max_length=20, choices=[
        ('MAIN', 'Main Pharmacy'),
        ('SATELLITE', 'Satellite Pharmacy'),
        ('WARD', 'Ward Pharmacy'),
        ('THEATRE', 'Theatre Pharmacy'),
        ('EMERGENCY', 'Emergency Pharmacy'),
        ('OUTPATIENT', 'Outpatient Pharmacy'),
    ])
    address = models.TextField(blank=True, help_text='Physical location within facility')
    phone_ext = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)
    manager = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='managed_pharmacy_locations',
    )
    # WHO GPP 6.2 — storage condition tracking per location
    storage_conditions = models.CharField(
        max_length=20, blank=True,
        choices=[
            ('AMBIENT', 'Ambient (15-25 °C)'),
            ('COOL', 'Cool Room (2-8 °C)'),
            ('FROZEN', 'Frozen (< -15 °C)'),
            ('CONTROLLED', 'Controlled Room (20-25 °C)'),
        ],
        help_text='Primary storage temperature range',
    )
    license_number = models.CharField(
        max_length=50, blank=True,
        help_text='Regulatory license/permit for this location',
    )
    has_controlled_access = models.BooleanField(
        default=False, help_text='Restricted access for controlled substances',
    )

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.get_location_type_display()})"


# ── Inter-Store Transfers ───────────────────────────────────────────────────

class TransferStatus(models.TextChoices):
    PENDING   = 'PENDING',   'Pending — Awaiting Acceptance'
    IN_TRANSIT = 'IN_TRANSIT', 'In Transit'
    RECEIVED  = 'RECEIVED',  'Received — Stock Updated'
    REJECTED  = 'REJECTED',  'Rejected by Receiver'
    CANCELLED = 'CANCELLED', 'Cancelled by Sender'


class StockTransfer(AuditModel):
    """
    Inter-location stock movement.
    WHO GPP — stock transfers between pharmacy locations must be documented.
    """
    transfer_number = models.CharField(max_length=30, unique=True)
    from_location = models.ForeignKey(
        PharmacyLocation, on_delete=models.PROTECT, related_name='transfers_out',
    )
    to_location = models.ForeignKey(
        PharmacyLocation, on_delete=models.PROTECT, related_name='transfers_in',
    )
    status = models.CharField(max_length=15, choices=TransferStatus.choices, default=TransferStatus.PENDING)
    initiated_by = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='transfers_initiated',
    )
    received_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='transfers_received',
    )
    initiated_at = models.DateTimeField(default=timezone.now)
    received_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)
    # WHO GPP 3.4 — authorization and cold chain
    approved_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='transfers_approved',
        help_text='Manager who authorized this transfer',
    )
    transport_conditions = models.CharField(
        max_length=20, blank=True,
        choices=[
            ('AMBIENT', 'Ambient'),
            ('COLD_CHAIN', 'Cold Chain (2-8 °C)'),
            ('FROZEN', 'Frozen'),
        ],
        help_text='Temperature conditions during transit',
    )

    class Meta:
        ordering = ['-initiated_at']

    def __str__(self):
        return f"{self.transfer_number}: {self.from_location} → {self.to_location}"

    def save(self, *args, **kwargs):
        if not self.transfer_number:
            today = timezone.localdate()
            count = StockTransfer.objects.filter(initiated_at__date=today).count() + 1
            self.transfer_number = f"TRF-{today.strftime('%Y%m%d')}-{count:04d}"
        super().save(*args, **kwargs)


class StockTransferItem(TimeStampedModel):
    """Individual drug line on a stock transfer."""
    transfer = models.ForeignKey(StockTransfer, on_delete=models.CASCADE, related_name='items')
    drug = models.ForeignKey(Drug, on_delete=models.PROTECT, related_name='transfer_items')
    stock_batch = models.ForeignKey(DrugStock, on_delete=models.PROTECT, related_name='transfer_items')
    quantity = models.PositiveIntegerField()
    quantity_received = models.PositiveIntegerField(default=0, help_text='Actual qty confirmed by receiver')

    def __str__(self):
        return f"{self.drug.name} × {self.quantity}"


# ── Stock Exit (Non-Dispensing) ─────────────────────────────────────────────

class StockExitReason(models.TextChoices):
    EXPIRED     = 'EXPIRED',     'Expired — Destruction'
    DAMAGED     = 'DAMAGED',     'Damaged / Broken'
    DONATION    = 'DONATION',    'Donation / Sample'
    THEFT       = 'THEFT',       'Theft / Loss'
    RECALL      = 'RECALL',      'Manufacturer Recall'
    QUALITY     = 'QUALITY',     'Quality Failure'
    OTHER       = 'OTHER',       'Other'


class StockExit(AuditModel):
    """
    Non-dispensing stock removal.
    FIP Guidelines — all stock exits must be documented with reason and authorization.
    """
    exit_number = models.CharField(max_length=30, unique=True)
    drug = models.ForeignKey(Drug, on_delete=models.PROTECT, related_name='stock_exits')
    stock_batch = models.ForeignKey(DrugStock, on_delete=models.PROTECT, related_name='stock_exits')
    quantity = models.PositiveIntegerField()
    reason = models.CharField(max_length=15, choices=StockExitReason.choices)
    notes = models.TextField(blank=True)
    authorized_by = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='stock_exits_authorized',
    )
    exit_date = models.DateTimeField(default=timezone.now)
    disposal_method = models.CharField(max_length=100, blank=True, help_text='e.g. Incineration, Return to supplier')
    witness = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='stock_exits_witnessed',
    )
    # FIP / WHO GPP 2.3 — disposal documentation
    waste_classification = models.CharField(
        max_length=20, blank=True,
        choices=[
            ('HAZARDOUS', 'Hazardous Pharmaceutical Waste'),
            ('NON_HAZARDOUS', 'Non-Hazardous Waste'),
            ('CYTOTOXIC', 'Cytotoxic Waste'),
            ('CONTROLLED', 'Controlled Substance Waste'),
        ],
    )
    destruction_certificate = models.CharField(
        max_length=100, blank=True,
        help_text='Certificate of Destruction reference number',
    )
    financial_impact = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text='Value of destroyed stock (cost price × quantity)',
    )

    class Meta:
        ordering = ['-exit_date']

    def __str__(self):
        return f"{self.exit_number}: {self.drug.name} × {self.quantity} ({self.get_reason_display()})"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        if not self.exit_number:
            today = timezone.localdate()
            count = StockExit.objects.filter(exit_date__date=today).count() + 1
            self.exit_number = f"EXIT-{today.strftime('%Y%m%d')}-{count:04d}"
        super().save(*args, **kwargs)
        # Deduct from stock on first save
        if is_new and self.stock_batch:
            self.stock_batch.quantity_remaining = max(
                0, self.stock_batch.quantity_remaining - self.quantity
            )
            self.stock_batch.save(update_fields=['quantity_remaining'])


# ── Drug Recall Management ──────────────────────────────────────────────────

class RecallStatus(models.TextChoices):
    ACTIVE      = 'ACTIVE',      'Active — Quarantine in Effect'
    COMPLETED   = 'COMPLETED',   'Completed — All Stock Removed'
    CANCELLED   = 'CANCELLED',   'Cancelled — False Alarm'


class DrugRecall(AuditModel):
    """
    Manufacturer or regulatory drug recall.
    JCI MMU.5.1 — medication recall process.
    """
    recall_number = models.CharField(max_length=30, unique=True)
    drug = models.ForeignKey(Drug, on_delete=models.PROTECT, related_name='recalls')
    batch_numbers = models.TextField(help_text='Comma-separated batch numbers affected')
    reason = models.TextField(help_text='Reason for recall (contamination, labeling error, etc.)')
    severity = models.CharField(max_length=10, choices=[
        ('CLASS_I', 'Class I — Life-threatening'),
        ('CLASS_II', 'Class II — Temporary health risk'),
        ('CLASS_III', 'Class III — Unlikely to cause harm'),
    ])
    recall_source = models.CharField(max_length=100, help_text='Manufacturer, WHO, MINSANTE, etc.')
    recall_date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=15, choices=RecallStatus.choices, default=RecallStatus.ACTIVE)
    quarantined_qty = models.PositiveIntegerField(default=0, help_text='Total units quarantined')
    patients_affected = models.PositiveIntegerField(default=0, help_text='Patients who received recalled batch')
    reported_by = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='drug_recalls_reported',
    )
    notes = models.TextField(blank=True)
    # JCI MMU.5.1 — regulatory and patient safety tracking
    recall_type = models.CharField(
        max_length=20, blank=True,
        choices=[
            ('MANUFACTURER', 'Manufacturer Initiated'),
            ('REGULATORY', 'Regulatory Authority (MINSANTE/WHO)'),
            ('HOSPITAL', 'Hospital Initiated (Internal QC)'),
        ],
    )
    regulatory_reference = models.CharField(
        max_length=100, blank=True,
        help_text='FDA/MINSANTE/WHO reference number',
    )
    patients_notified = models.BooleanField(
        default=False,
        help_text='Have affected patients been contacted?',
    )
    corrective_action = models.TextField(
        blank=True,
        help_text='Corrective/preventive action taken or planned',
    )

    class Meta:
        ordering = ['-recall_date']

    def __str__(self):
        return f"RECALL-{self.recall_number}: {self.drug.name} ({self.get_severity_display()})"

    def save(self, *args, **kwargs):
        if not self.recall_number:
            today = timezone.localdate()
            count = DrugRecall.objects.filter(recall_date__year=today.year).count() + 1
            self.recall_number = f"RCL-{today.year}-{count:04d}"
        super().save(*args, **kwargs)

    def get_affected_batches(self):
        """Return DrugStock queryset for batches listed in this recall."""
        batch_list = [b.strip() for b in self.batch_numbers.split(',') if b.strip()]
        return DrugStock.objects.filter(
            drug=self.drug, batch_number__in=batch_list, is_deleted=False
        )

    def get_affected_patients(self):
        """Return patients who received any of the recalled batches."""
        affected_batches = self.get_affected_batches()
        from apps.patients.models import Patient
        patient_ids = DispensingItem.objects.filter(
            stock_batch__in=affected_batches
        ).values_list('dispensing__patient_id', flat=True).distinct()
        return Patient.objects.filter(id__in=patient_ids)


# ── Drug VEN Classification ─────────────────────────────────────────────────

class VENClassification(models.TextChoices):
    VITAL     = 'V', 'Vital — Life-saving, always in stock'
    ESSENTIAL = 'E', 'Essential — Important but alternatives exist'
    NON_ESSENTIAL = 'N', 'Non-essential — Nice to have'


# ══════════════════════════════════════════════════════════════════════════════
# ADR — Adverse Drug Reaction Reporting (Pharmacovigilance)
# WHO Uppsala Monitoring Centre & ICH E2B
# ══════════════════════════════════════════════════════════════════════════════

class ADRSeverity(models.TextChoices):
    MILD     = 'MILD',     'Mild — no treatment change needed'
    MODERATE = 'MODERATE', 'Moderate — required intervention'
    SEVERE   = 'SEVERE',   'Severe — hospitalisation / life-threatening'
    FATAL    = 'FATAL',    'Fatal'


class ADROutcome(models.TextChoices):
    RECOVERED      = 'RECOVERED',      'Recovered / Resolved'
    RECOVERING     = 'RECOVERING',     'Recovering'
    NOT_RECOVERED  = 'NOT_RECOVERED',  'Not Yet Recovered'
    SEQUELAE       = 'SEQUELAE',       'Recovered with Sequelae'
    FATAL          = 'FATAL',          'Fatal'
    UNKNOWN        = 'UNKNOWN',        'Unknown'


class ADRCausality(models.TextChoices):
    CERTAIN    = 'CERTAIN',    'Certain'
    PROBABLE   = 'PROBABLE',   'Probable / Likely'
    POSSIBLE   = 'POSSIBLE',   'Possible'
    UNLIKELY   = 'UNLIKELY',   'Unlikely'
    UNRELATED  = 'UNRELATED',  'Unrelated'
    UNASSESSED = 'UNASSESSED', 'Not Assessed'


class AdverseDrugReaction(AuditModel):
    """
    Pharmacovigilance — adverse drug reaction report.
    WHO/ICH guidelines for ADR reporting.
    """
    patient = models.ForeignKey(
        'patients.Patient', on_delete=models.PROTECT, related_name='adverse_reactions',
    )
    drug = models.ForeignKey(Drug, on_delete=models.PROTECT, related_name='adverse_reactions')
    dispensing = models.ForeignKey(
        Dispensing, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='adverse_reactions',
    )
    reaction_date = models.DateField()
    reaction_description = models.TextField(help_text='Describe the adverse reaction in detail')
    severity = models.CharField(max_length=10, choices=ADRSeverity.choices)
    outcome = models.CharField(max_length=15, choices=ADROutcome.choices, default=ADROutcome.UNKNOWN)
    causality = models.CharField(
        max_length=15, choices=ADRCausality.choices, default=ADRCausality.UNASSESSED,
        help_text='WHO-UMC causality assessment',
    )
    action_taken = models.TextField(blank=True, help_text='Drug withdrawn, dose reduced, etc.')
    treatment_given = models.TextField(blank=True, help_text='Treatment for the adverse reaction')
    rechallenge = models.CharField(
        max_length=20, blank=True,
        choices=[('YES_POS', 'Yes — Reaction recurred'), ('YES_NEG', 'Yes — No recurrence'),
                 ('NO', 'Not re-administered'), ('NA', 'Not applicable')],
    )
    reported_by = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='adr_reports',
    )
    reported_to_authority = models.BooleanField(
        default=False, help_text='Reported to MINSANTE / national pharmacovigilance centre',
    )
    authority_reference = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-reaction_date']
        verbose_name = 'Adverse Drug Reaction'

    def __str__(self):
        return f"ADR: {self.patient.full_name} — {self.drug.name} ({self.get_severity_display()})"


# ══════════════════════════════════════════════════════════════════════════════
# Physical Inventory Count / Stocktake
# ══════════════════════════════════════════════════════════════════════════════

class StocktakeStatus(models.TextChoices):
    IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
    FINALIZED   = 'FINALIZED',   'Finalized — Adjustments Applied'
    CANCELLED   = 'CANCELLED',   'Cancelled'


class Stocktake(AuditModel):
    """
    Physical inventory count session. Head pharmacist initiates,
    staff count, then finalize to apply variances as StockAdjustments.
    """
    reference = models.CharField(max_length=30, unique=True)
    title = models.CharField(max_length=200, blank=True, help_text='e.g. Monthly Full Count — September 2026')
    status = models.CharField(max_length=15, choices=StocktakeStatus.choices, default=StocktakeStatus.IN_PROGRESS)
    count_date = models.DateField(default=timezone.localdate)
    initiated_by = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='stocktakes_initiated',
    )
    finalized_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='stocktakes_finalized',
    )
    finalized_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-count_date']

    def __str__(self):
        return f"{self.reference} — {self.count_date}"

    def save(self, *args, **kwargs):
        if not self.reference:
            today = timezone.localdate()
            count = Stocktake.objects.filter(count_date__year=today.year).count() + 1
            self.reference = f"STK-{today.year}-{count:04d}"
        super().save(*args, **kwargs)

    @property
    def total_items(self):
        return self.items.count()

    @property
    def variance_count(self):
        return self.items.exclude(variance=0).count()


class StocktakeItem(TimeStampedModel):
    """Individual count line within a stocktake."""
    stocktake = models.ForeignKey(Stocktake, on_delete=models.CASCADE, related_name='items')
    drug = models.ForeignKey(Drug, on_delete=models.PROTECT, related_name='stocktake_items')
    batch = models.ForeignKey(DrugStock, on_delete=models.PROTECT, related_name='stocktake_items')
    system_quantity = models.IntegerField(help_text='System stock at time of count')
    counted_quantity = models.IntegerField(help_text='Physical count by staff')
    variance = models.IntegerField(default=0, help_text='counted - system (positive=surplus, negative=shortage)')
    counted_by = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='stocktake_counts',
    )
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ('stocktake', 'batch')

    def save(self, *args, **kwargs):
        self.variance = self.counted_quantity - self.system_quantity
        super().save(*args, **kwargs)

    def __str__(self):
        sign = '+' if self.variance >= 0 else ''
        return f"{self.drug.name} Batch {self.batch.batch_number}: {sign}{self.variance}"
