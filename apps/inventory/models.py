"""
Inventory Module — International Standard (JCI MMU.3 / ISO 9001:2015 §8.4 / WHO)
Hospital supplies, equipment, purchase orders, lot/batch tracking, FEFO dispensing,
department requisitions, automated reorder, supplier performance scoring.
"""
from django.db import models
from django.utils import timezone
from apps.core.models import TimeStampedModel, AuditModel


class ItemCategory(models.TextChoices):
    SURGICAL          = 'SURGICAL',           'Surgical Supplies'
    MEDICAL_CONSUMABLE= 'MEDICAL_CONSUMABLE', 'Medical Consumables'
    DIAGNOSTIC        = 'DIAGNOSTIC',         'Diagnostic Equipment'
    PHARMACEUTICAL    = 'PHARMACEUTICAL',     'Pharmaceuticals / Reagents'
    IMPLANT           = 'IMPLANT',            'Implants / Prosthetics'
    LENS              = 'LENS',               'Ophthalmic Lenses (Consignment)'
    OFFICE            = 'OFFICE',             'Office Supplies'
    CLEANING          = 'CLEANING',           'Cleaning / Housekeeping'
    IT                = 'IT',                 'IT Equipment'
    FURNITURE         = 'FURNITURE',          'Furniture'
    LINEN             = 'LINEN',              'Linen / Laundry'
    OTHER             = 'OTHER',              'Other'


class ABCClass(models.TextChoices):
    A = 'A', 'A — High Value (top 20% items = ~80% value)'
    B = 'B', 'B — Medium Value (next 30% items = ~15% value)'
    C = 'C', 'C — Low Value (bottom 50% items = ~5% value)'


class VENClass(models.TextChoices):
    VITAL     = 'V', 'Vital — Life-saving, must never stock out'
    ESSENTIAL = 'E', 'Essential — Important but short stock tolerable'
    NON_ESSENTIAL = 'N', 'Non-Essential — Desirable, substitutes available'


class InventoryItem(AuditModel):
    """Master item catalogue"""
    name             = models.CharField(max_length=200)
    item_code        = models.CharField(max_length=50, unique=True)
    category         = models.CharField(max_length=20, choices=ItemCategory.choices)
    description      = models.TextField(blank=True)
    unit             = models.CharField(max_length=50, default='unit')
    reorder_level    = models.PositiveIntegerField(default=5)
    max_stock_level  = models.PositiveIntegerField(default=0, help_text='Maximum stock level — 0 means no limit (ISO 9001 §8.5.4)')
    current_stock    = models.PositiveIntegerField(default=0)
    unit_cost        = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    location         = models.CharField(max_length=100, blank=True, help_text='Storage location (shelf/bin)')
    store_location   = models.ForeignKey(
        'StoreLocation', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='items',
        help_text='Which store this item belongs to (General, Pharmacy, Optical, Theatre)'
    )
    is_active        = models.BooleanField(default=True)
    barcode          = models.CharField(max_length=100, blank=True, unique=True, null=True,
                                         help_text='Auto-generated barcode for scanning')

    # ── ABC / VEN Classification (WHO Essential Medicines) ────────────────────
    abc_class = models.CharField(max_length=1, choices=ABCClass.choices, blank=True,
                                  help_text='ABC analysis classification by annual consumption value')
    ven_class = models.CharField(max_length=1, choices=VENClass.choices, blank=True,
                                  help_text='VEN analysis — Vital / Essential / Non-essential')

    # ── International Standard additions ──────────────────────────────────────
    requires_expiry_tracking = models.BooleanField(
        default=False,
        help_text='Track lot/batch and expiry date (JCI MMU.3)'
    )
    is_consignment = models.BooleanField(
        default=False,
        help_text='Consignment stock — not paid until used (e.g. lenses)'
    )
    udi_code = models.CharField(
        max_length=100, blank=True,
        help_text='Unique Device Identifier (FDA UDI / EU MDR — for implants/reusable devices)'
    )
    storage_conditions = models.CharField(
        max_length=100, blank=True,
        help_text='e.g. Room temperature, Refrigerate 2–8 °C, Freeze –20 °C'
    )
    preferred_vendor = models.ForeignKey(
        'Vendor', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='preferred_items',
        help_text='Default vendor for auto-reorder'
    )

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.item_code} - {self.name}"

    def save(self, *args, **kwargs):
        if not self.barcode:
            import uuid
            self.barcode = f"INV{uuid.uuid4().hex[:10].upper()}"
        super().save(*args, **kwargs)

    @property
    def needs_reorder(self):
        return self.current_stock <= self.reorder_level

    @property
    def is_overstocked(self):
        return self.max_stock_level > 0 and self.current_stock > self.max_stock_level

    @property
    def excess_qty(self):
        if self.is_overstocked:
            return self.current_stock - self.max_stock_level
        return 0

    @property
    def stock_status(self):
        if self.current_stock == 0:
            return 'OUT_OF_STOCK'
        if self.needs_reorder:
            return 'LOW'
        if self.is_overstocked:
            return 'OVER'
        return 'OK'

    @property
    def stock_value(self):
        return self.current_stock * self.unit_cost

    @property
    def available_batches(self):
        """Non-expired, non-quarantined batches with remaining stock, FEFO order."""
        today = timezone.localdate()
        return self.batches.filter(
            quantity_remaining__gt=0,
            is_quarantined=False,
            expiry_date__gt=today,
        ).order_by('expiry_date')


class Vendor(AuditModel):
    name           = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=200, blank=True)
    phone          = models.CharField(max_length=30, blank=True)
    email          = models.EmailField(blank=True)
    address        = models.TextField(blank=True)
    is_active      = models.BooleanField(default=True)

    # ── ISO 9001 §8.4 Supplier Performance Scoring ────────────────────────────
    total_orders        = models.PositiveIntegerField(default=0)
    on_time_deliveries  = models.PositiveIntegerField(default=0)
    late_deliveries     = models.PositiveIntegerField(default=0)
    quality_incidents   = models.PositiveIntegerField(default=0)
    notes               = models.TextField(blank=True)

    def __str__(self):
        return self.name

    @property
    def on_time_rate(self):
        if self.total_orders == 0:
            return None
        return round(self.on_time_deliveries / self.total_orders * 100, 1)

    @property
    def performance_rating(self):
        rate = self.on_time_rate
        if rate is None:
            return 'N/A'
        if rate >= 95:
            return 'EXCELLENT'
        elif rate >= 85:
            return 'GOOD'
        elif rate >= 70:
            return 'FAIR'
        return 'POOR'

    @property
    def performance_color(self):
        mapping = {'EXCELLENT': 'success', 'GOOD': 'info', 'FAIR': 'warning', 'POOR': 'danger', 'N/A': 'secondary'}
        return mapping.get(self.performance_rating, 'secondary')


class PurchaseOrderStatus(models.TextChoices):
    DRAFT     = 'DRAFT',     'Draft'
    SUBMITTED = 'SUBMITTED', 'Submitted'
    APPROVED  = 'APPROVED',  'Approved'
    RECEIVED  = 'RECEIVED',  'Received'
    CANCELLED = 'CANCELLED', 'Cancelled'


class PurchaseOrder(AuditModel):
    po_number    = models.CharField(max_length=30, unique=True)
    vendor       = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name='purchase_orders')
    status       = models.CharField(max_length=20, choices=PurchaseOrderStatus.choices, default=PurchaseOrderStatus.DRAFT)
    ordered_date = models.DateField(default=timezone.now)
    expected_date= models.DateField(null=True, blank=True)
    received_date= models.DateField(null=True, blank=True)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    notes        = models.TextField(blank=True)
    approved_by  = models.ForeignKey(
        'accounts.User', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='approved_pos'
    )
    is_auto_generated = models.BooleanField(default=False, help_text='Created by auto-reorder trigger')
    # Finance Director approval (separate from store approval)
    finance_approved_by = models.ForeignKey(
        'accounts.User', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='finance_approved_pos'
    )
    finance_approved_at = models.DateTimeField(null=True, blank=True)
    finance_notes = models.TextField(blank=True, help_text='Finance Director remarks on PO approval')

    class Meta:
        ordering = ['-ordered_date']

    def __str__(self):
        return f"PO-{self.po_number} ({self.vendor.name})"

    @property
    def is_finance_approved(self):
        return self.finance_approved_by is not None

    def save(self, *args, **kwargs):
        if not self.po_number:
            today = timezone.localdate()
            count = PurchaseOrder.objects.filter(ordered_date__year=today.year).count() + 1
            self.po_number = f"{today.year}-{count:04d}"
        super().save(*args, **kwargs)


class PurchaseOrderItem(TimeStampedModel):
    purchase_order    = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='items')
    item              = models.ForeignKey(InventoryItem, on_delete=models.PROTECT)
    quantity_ordered  = models.PositiveIntegerField()
    quantity_received = models.PositiveIntegerField(default=0)
    unit_price        = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal          = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # ── Lot / Batch fields captured at receiving ───────────────────────────────
    lot_number        = models.CharField(max_length=100, blank=True, help_text='Manufacturer lot/batch number')
    manufactured_date = models.DateField(null=True, blank=True)
    expiry_date       = models.DateField(null=True, blank=True)

    def save(self, *args, **kwargs):
        self.subtotal = self.quantity_ordered * self.unit_price
        super().save(*args, **kwargs)


class StockMovement(TimeStampedModel):
    """Audit trail of all stock movements"""
    item          = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name='movements')
    movement_type = models.CharField(max_length=20, choices=[
        ('IN', 'Stock In'), ('OUT', 'Stock Out'), ('ADJUST', 'Adjustment'),
        ('RETURN', 'Return'), ('EXPIRE', 'Expiry Write-off'), ('ISSUE', 'Dept. Issue'),
    ])
    quantity      = models.IntegerField()  # negative for OUT
    balance_after = models.PositiveIntegerField()
    reference     = models.CharField(max_length=100, blank=True)
    notes         = models.TextField(blank=True)
    performed_by  = models.ForeignKey(
        'accounts.User', null=True, blank=True, on_delete=models.SET_NULL
    )
    batch         = models.ForeignKey(
        'BatchStock', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='movements',
        help_text='Linked batch (for expiry-tracked items)'
    )

    class Meta:
        ordering = ['-created_at']


# ── Lot / Batch Stock ─────────────────────────────────────────────────────────

class BatchStock(TimeStampedModel):
    """
    Per-batch/lot tracking for expiry-managed items.
    Ordered by expiry_date ASC to implement FEFO (First Expired First Out).
    JCI MMU.3 / WHO storage standard compliance.
    """
    item               = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name='batches')
    lot_number         = models.CharField(max_length=100)
    manufactured_date  = models.DateField(null=True, blank=True)
    expiry_date        = models.DateField()
    quantity_received  = models.PositiveIntegerField()
    quantity_remaining = models.PositiveIntegerField()
    unit_cost          = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    purchase_order     = models.ForeignKey(
        PurchaseOrder, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='batch_stocks'
    )
    is_quarantined     = models.BooleanField(default=False, help_text='Failed QC — do not dispense')
    quarantine_reason  = models.CharField(max_length=200, blank=True)
    notes              = models.TextField(blank=True)

    class Meta:
        ordering = ['expiry_date']  # FEFO: oldest-expiry first

    def __str__(self):
        return f"{self.item.item_code} | Lot {self.lot_number} | Exp {self.expiry_date}"

    @property
    def is_expired(self):
        return self.expiry_date < timezone.localdate()

    @property
    def days_to_expiry(self):
        return (self.expiry_date - timezone.localdate()).days

    @property
    def expiry_status(self):
        days = self.days_to_expiry
        if days < 0:
            return 'EXPIRED'
        elif days <= 30:
            return 'CRITICAL'
        elif days <= 90:
            return 'WARNING'
        return 'OK'

    @property
    def expiry_badge_color(self):
        mapping = {'EXPIRED': 'danger', 'CRITICAL': 'danger', 'WARNING': 'warning', 'OK': 'success'}
        return mapping.get(self.expiry_status, 'secondary')


# ── Department Requisitions ───────────────────────────────────────────────────

class RequisitionStatus(models.TextChoices):
    PENDING  = 'PENDING',  'Pending Approval'
    APPROVED = 'APPROVED', 'Approved'
    ISSUED   = 'ISSUED',   'Fully Issued'
    PARTIAL  = 'PARTIAL',  'Partially Issued'
    REJECTED = 'REJECTED', 'Rejected'


class DepartmentRequisition(AuditModel):
    """
    Ward/department requests items from central store.
    Store manager approves, then issues via FEFO from BatchStock.
    """
    req_number    = models.CharField(max_length=30, unique=True, blank=True)
    department    = models.CharField(max_length=100)
    requested_by  = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='requisitions'
    )
    approved_by   = models.ForeignKey(
        'accounts.User', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='approved_requisitions'
    )
    issued_by     = models.ForeignKey(
        'accounts.User', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='issued_requisitions'
    )
    status        = models.CharField(
        max_length=20, choices=RequisitionStatus.choices, default=RequisitionStatus.PENDING
    )
    priority      = models.CharField(max_length=10, choices=[
        ('ROUTINE',    'Routine'),
        ('URGENT',     'Urgent'),
        ('EMERGENCY',  'Emergency'),
    ], default='ROUTINE')
    needed_by     = models.DateField(null=True, blank=True)
    notes         = models.TextField(blank=True)
    issued_at     = models.DateTimeField(null=True, blank=True)
    rejected_reason = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"REQ-{self.req_number} ({self.department})"

    def save(self, *args, **kwargs):
        if not self.req_number:
            today = timezone.localdate()
            count = DepartmentRequisition.objects.filter(
                created_at__year=today.year
            ).count() + 1
            self.req_number = f"{today.year}-{count:04d}"
        super().save(*args, **kwargs)


class RequisitionItem(TimeStampedModel):
    requisition        = models.ForeignKey(DepartmentRequisition, on_delete=models.CASCADE, related_name='items')
    item               = models.ForeignKey(InventoryItem, on_delete=models.PROTECT)
    quantity_requested = models.PositiveIntegerField()
    quantity_issued    = models.PositiveIntegerField(default=0)
    notes              = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"{self.item.name} × {self.quantity_requested}"


# ── Store Locations ──────────────────────────────────────────────────────────

class StoreLocation(AuditModel):
    """
    Physical store rooms within the facility.
    Each store maps to an OHADA Class 3 sub-account:
      - General Store  → 311 (Marchandises)
      - Pharmacy Store → 321 (Matieres premieres - pharmaceutiques)
      - Optical Store  → 322 (Marchandises - optique)
      - Theatre Store  → 323 (Fournitures chirurgicales)
      - Ward/Emergency → 331 (Autres approvisionnements)
    """
    store_code = models.CharField(
        max_length=10, unique=True, blank=True,
        help_text='Short code e.g. FD01, OP01, PH2 — auto-generated if blank'
    )
    name = models.CharField(max_length=100, unique=True)
    location_type = models.CharField(max_length=20, choices=[
        ('GENERAL', 'General Store'),
        ('PHARMACY', 'Pharmacy Store'),
        ('OPTICAL', 'Optical Store'),
        ('SHOWROOM', 'Optical Showroom'),
        ('THEATRE', 'Theatre / OT Store'),
        ('CENTRAL', 'Central Store'),
        ('SUB', 'Sub-Store'),
        ('WARD', 'Ward Store'),
        ('EMERGENCY', 'Emergency / Chariots d\'Urgence'),
        ('FRONT_DESK', 'Front Desk Store'),
        ('NON_MEDICAL', 'Non-Medical Consumables'),
        ('OUTREACH', 'Outreach Store'),
        ('OTN', 'OTN Store'),
    ])
    gl_account_code = models.CharField(
        max_length=10, blank=True,
        help_text='OHADA Class 3 GL account code for this store (e.g. 311000, 321000)'
    )
    address = models.TextField(blank=True, help_text='Physical location within facility')
    manager = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='managed_store_locations',
    )
    is_active = models.BooleanField(default=True)

    # Auto-assign GL account based on store type (OHADA SYSCEBNL Class 3)
    STORE_GL_MAP = {
        'GENERAL':     '311000',   # Marchandises — general
        'PHARMACY':    '321000',   # Matieres premieres — pharmaceutiques
        'OPTICAL':     '322000',   # Marchandises — optique (stock)
        'SHOWROOM':    '322000',   # Marchandises — optique (display = same GL)
        'THEATRE':     '323000',   # Fournitures chirurgicales
        'CENTRAL':     '311000',   # Marchandises — central
        'SUB':         '331000',   # Autres approvisionnements
        'WARD':        '331000',   # Autres approvisionnements — ward
        'EMERGENCY':   '331000',   # Autres approvisionnements — urgence
        'FRONT_DESK':  '332000',   # Fournitures de bureau — front desk
        'NON_MEDICAL': '333000',   # Fournitures non médicales
        'OUTREACH':    '334000',   # Stock en transit — outreach
        'OTN':         '335000',   # Stock — OTN
    }

    # Prefix map for auto-generating store_code
    CODE_PREFIX_MAP = {
        'GENERAL': 'GS', 'PHARMACY': 'PH', 'OPTICAL': 'OP', 'SHOWROOM': 'OP',
        'THEATRE': 'OT', 'CENTRAL': 'CS', 'SUB': 'SS', 'WARD': 'WD',
        'EMERGENCY': 'EM', 'FRONT_DESK': 'FD', 'NON_MEDICAL': 'NM',
        'OUTREACH': 'OR', 'OTN': 'OT',
    }

    def save(self, *args, **kwargs):
        if not self.gl_account_code:
            self.gl_account_code = self.STORE_GL_MAP.get(self.location_type, '331000')
        if not self.store_code:
            prefix = self.CODE_PREFIX_MAP.get(self.location_type, 'ST')
            existing = StoreLocation.objects.filter(
                store_code__startswith=prefix
            ).count()
            self.store_code = f"{prefix}{existing + 1:02d}"
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['store_code', 'name']

    def __str__(self):
        return f"{self.store_code}: {self.name}"


# ── Physical Stock Count ─────────────────────────────────────────────────────

class StockCountStatus(models.TextChoices):
    IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
    COMPLETED   = 'COMPLETED',   'Completed'
    APPROVED    = 'APPROVED',    'Approved — Adjustments Applied'


class StockCount(AuditModel):
    """Periodic physical inventory count."""
    count_number = models.CharField(max_length=30, unique=True, blank=True)
    count_date   = models.DateField(default=timezone.localdate)
    status       = models.CharField(max_length=15, choices=StockCountStatus.choices,
                                     default=StockCountStatus.IN_PROGRESS)
    counted_by   = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='stock_counts',
    )
    approved_by  = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='approved_stock_counts',
    )
    notes        = models.TextField(blank=True)

    class Meta:
        ordering = ['-count_date']

    def __str__(self):
        return f"Count {self.count_number} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        if not self.count_number:
            today = timezone.localdate()
            count = StockCount.objects.filter(count_date__year=today.year).count() + 1
            self.count_number = f"SC-{today.strftime('%Y%m%d')}-{count:04d}"
        super().save(*args, **kwargs)


class StockCountItem(TimeStampedModel):
    """Individual item line in a stock count."""
    stock_count      = models.ForeignKey(StockCount, on_delete=models.CASCADE, related_name='items')
    item             = models.ForeignKey(InventoryItem, on_delete=models.PROTECT)
    system_quantity  = models.PositiveIntegerField(help_text='Quantity per system at time of count')
    physical_quantity = models.PositiveIntegerField(help_text='Actual count found')
    variance         = models.IntegerField(default=0, help_text='physical - system')
    notes            = models.CharField(max_length=200, blank=True)

    def save(self, *args, **kwargs):
        self.variance = self.physical_quantity - self.system_quantity
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.item.name}: sys={self.system_quantity} phys={self.physical_quantity} var={self.variance}"


# ── Department Returns ───────────────────────────────────────────────────────

class DepartmentReturn(AuditModel):
    """Items returned from departments back to central store."""
    return_number = models.CharField(max_length=30, unique=True, blank=True)
    department    = models.CharField(max_length=100)
    returned_by   = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='store_returns',
    )
    received_by   = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='received_store_returns',
    )
    status        = models.CharField(max_length=15, choices=[
        ('PENDING', 'Pending Acceptance'),
        ('ACCEPTED', 'Accepted — Stock Restored'),
        ('REJECTED', 'Rejected'),
    ], default='PENDING')
    notes         = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"RET-{self.return_number} ({self.department})"

    def save(self, *args, **kwargs):
        if not self.return_number:
            today = timezone.localdate()
            count = DepartmentReturn.objects.filter(created_at__year=today.year).count() + 1
            self.return_number = f"RET-{today.strftime('%Y')}-{count:04d}"
        super().save(*args, **kwargs)


class DepartmentReturnItem(TimeStampedModel):
    department_return = models.ForeignKey(DepartmentReturn, on_delete=models.CASCADE, related_name='items')
    item              = models.ForeignKey(InventoryItem, on_delete=models.PROTECT)
    quantity          = models.PositiveIntegerField()
    condition         = models.CharField(max_length=20, choices=[
        ('GOOD', 'Good — Restock'),
        ('DAMAGED', 'Damaged — Write Off'),
        ('EXPIRED', 'Expired'),
    ], default='GOOD')
    notes             = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"{self.item.name} × {self.quantity} ({self.get_condition_display()})"


# ── Inter-Store Transfers (ISO 9001 §8.5.4) ─────────────────────────────────

class StoreTransferStatus(models.TextChoices):
    REQUESTED = 'REQUESTED', 'Requested'
    APPROVED  = 'APPROVED',  'Approved'
    IN_TRANSIT = 'IN_TRANSIT', 'In Transit'
    RECEIVED  = 'RECEIVED',  'Received'
    CANCELLED = 'CANCELLED', 'Cancelled'


class StoreTransfer(AuditModel):
    """Transfer stock between store locations."""
    transfer_number = models.CharField(max_length=30, unique=True, blank=True)
    from_location   = models.ForeignKey(StoreLocation, on_delete=models.PROTECT, related_name='transfers_out')
    to_location     = models.ForeignKey(StoreLocation, on_delete=models.PROTECT, related_name='transfers_in')
    status          = models.CharField(max_length=15, choices=StoreTransferStatus.choices,
                                        default=StoreTransferStatus.REQUESTED)
    requested_by    = models.ForeignKey('accounts.User', on_delete=models.PROTECT, related_name='store_transfer_requests')
    approved_by     = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
                                         related_name='store_transfer_approvals')
    received_by     = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
                                         related_name='store_transfers_received')
    transfer_date   = models.DateField(default=timezone.localdate)
    notes           = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"TRF-{self.transfer_number} ({self.from_location} → {self.to_location})"

    def save(self, *args, **kwargs):
        if not self.transfer_number:
            today = timezone.localdate()
            count = StoreTransfer.objects.filter(created_at__year=today.year).count() + 1
            self.transfer_number = f"TRF-{today.strftime('%Y%m%d')}-{count:04d}"
        super().save(*args, **kwargs)


class StoreTransferItem(TimeStampedModel):
    transfer  = models.ForeignKey(StoreTransfer, on_delete=models.CASCADE, related_name='items')
    item      = models.ForeignKey(InventoryItem, on_delete=models.PROTECT)
    quantity  = models.PositiveIntegerField()
    notes     = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"{self.item.name} × {self.quantity}"


# ── Goods Received Note (JCI FMS.5 / ISO 9001 §8.6) ────────────────────────

class GRNStatus(models.TextChoices):
    PENDING   = 'PENDING',   'Pending Inspection'
    INSPECTED = 'INSPECTED', 'Inspected'
    ACCEPTED  = 'ACCEPTED',  'Accepted — Stock Updated'
    AWAITING_VALIDATION = 'AWAITING_VALIDATION', 'Awaiting Finance Validation'
    VALIDATED = 'VALIDATED', 'Validated — GL Posted'
    REJECTED  = 'REJECTED',  'Rejected'


class GoodsReceivedNote(AuditModel):
    """Formal goods receipt with quality inspection checklist."""
    grn_number     = models.CharField(max_length=30, unique=True, blank=True)
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name='grns')
    status         = models.CharField(max_length=25, choices=GRNStatus.choices, default=GRNStatus.PENDING)
    received_date  = models.DateField(default=timezone.localdate)
    received_by    = models.ForeignKey('accounts.User', on_delete=models.PROTECT, related_name='grns_received')
    inspected_by   = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
                                        related_name='grns_inspected')
    # Inspection checklist (JCI FMS.5)
    packaging_intact    = models.BooleanField(default=False, help_text='Packaging undamaged and sealed')
    labels_correct      = models.BooleanField(default=False, help_text='Labels match PO and are legible')
    quantity_matches_po = models.BooleanField(default=False, help_text='Delivered qty matches PO qty')
    expiry_acceptable   = models.BooleanField(default=False, help_text='Expiry dates within acceptable range')
    storage_temp_ok     = models.BooleanField(default=False, help_text='Cold chain maintained (if applicable)')
    certificates_present = models.BooleanField(default=False, help_text='COA / Batch certificates provided')
    visual_inspection_ok = models.BooleanField(default=False, help_text='No visible damage, discoloration, leakage')
    inspection_notes    = models.TextField(blank=True)
    notes               = models.TextField(blank=True)
    # Signature fields (requester who raised the PO + logistics assistant who received)
    requester_name      = models.CharField(max_length=100, blank=True,
                                            help_text='Name of person who raised the requisition/PO')
    logistics_assistant = models.CharField(max_length=100, blank=True,
                                            help_text='Name of logistics assistant who physically received goods')
    requester_signature_date  = models.DateField(null=True, blank=True)
    logistics_signature_date  = models.DateField(null=True, blank=True)
    # Environmental compliance
    environmental_certificate = models.BooleanField(default=False, help_text='Environmental compliance certificate')
    # 4-Eyes Principle: Finance Director validation (Cameroon store-keeping law)
    validated_by   = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='grns_validated',
                                       help_text='Finance Director who validated this receipt')
    validated_at   = models.DateTimeField(null=True, blank=True)
    validation_notes = models.TextField(blank=True, help_text='Finance Director notes on validation')
    journal_entry  = models.ForeignKey('billing.JournalEntry', on_delete=models.SET_NULL,
                                       null=True, blank=True, related_name='grn_source',
                                       help_text='GL journal entry created on validation')

    class Meta:
        ordering = ['-received_date']

    def __str__(self):
        return f"GRN-{self.grn_number} (PO {self.purchase_order.po_number})"

    def save(self, *args, **kwargs):
        if not self.grn_number:
            today = timezone.localdate()
            count = GoodsReceivedNote.objects.filter(received_date__year=today.year).count() + 1
            self.grn_number = f"GRN-{today.strftime('%Y%m%d')}-{count:04d}"
        super().save(*args, **kwargs)

    @property
    def inspection_score(self):
        checks = [
            self.packaging_intact, self.labels_correct, self.quantity_matches_po,
            self.expiry_acceptable, self.storage_temp_ok, self.certificates_present,
            self.visual_inspection_ok,
        ]
        passed = sum(1 for c in checks if c)
        return f"{passed}/7"

    @property
    def all_checks_passed(self):
        return all([
            self.packaging_intact, self.labels_correct, self.quantity_matches_po,
            self.expiry_acceptable, self.certificates_present, self.visual_inspection_ok,
        ])


class GRNItem(TimeStampedModel):
    grn               = models.ForeignKey(GoodsReceivedNote, on_delete=models.CASCADE, related_name='items')
    po_item           = models.ForeignKey(PurchaseOrderItem, on_delete=models.PROTECT)
    quantity_received  = models.PositiveIntegerField()
    quantity_accepted  = models.PositiveIntegerField(default=0)
    quantity_rejected  = models.PositiveIntegerField(default=0)
    rejection_reason   = models.CharField(max_length=200, blank=True)
    lot_number         = models.CharField(max_length=100, blank=True)
    expiry_date        = models.DateField(null=True, blank=True)
    notes              = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"{self.po_item.item.name} × {self.quantity_received}"


# ── Wastage / Disposal Workflow (JCI MMU.3.2 / WHO) ─────────────────────────

class DisposalStatus(models.TextChoices):
    PENDING  = 'PENDING',  'Pending Authorization'
    APPROVED = 'APPROVED', 'Authorized for Disposal'
    DISPOSED = 'DISPOSED', 'Disposed'
    REJECTED = 'REJECTED', 'Rejected — Return to Stock'


class DisposalMethod(models.TextChoices):
    INCINERATION = 'INCINERATION', 'Incineration'
    CHEMICAL     = 'CHEMICAL',     'Chemical Treatment'
    LANDFILL     = 'LANDFILL',     'Sanitary Landfill'
    RETURN_VENDOR = 'RETURN_VENDOR', 'Return to Vendor'
    DONATION     = 'DONATION',     'Donation (if still usable)'
    OTHER        = 'OTHER',        'Other'


class DisposalRecord(AuditModel):
    """Formal disposal of expired / damaged / obsolete stock."""
    disposal_number = models.CharField(max_length=30, unique=True, blank=True)
    status          = models.CharField(max_length=15, choices=DisposalStatus.choices,
                                        default=DisposalStatus.PENDING)
    reason          = models.CharField(max_length=20, choices=[
        ('EXPIRED', 'Expired'),
        ('DAMAGED', 'Damaged'),
        ('RECALLED', 'Recalled by Manufacturer'),
        ('OBSOLETE', 'Obsolete / Discontinued'),
        ('CONTAMINATED', 'Contaminated'),
        ('OTHER', 'Other'),
    ])
    disposal_method = models.CharField(max_length=20, choices=DisposalMethod.choices, blank=True)
    requested_by    = models.ForeignKey('accounts.User', on_delete=models.PROTECT,
                                         related_name='disposal_requests')
    authorized_by   = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
                                         related_name='disposal_authorizations')
    witness         = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
                                         related_name='disposal_witnessed',
                                         help_text='Second person present during disposal (JCI requirement)')
    disposal_date   = models.DateField(null=True, blank=True)
    notes           = models.TextField(blank=True)
    environmental_certificate = models.BooleanField(
        default=False, help_text='Environmental disposal certificate obtained')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"DSP-{self.disposal_number} ({self.get_reason_display()})"

    def save(self, *args, **kwargs):
        if not self.disposal_number:
            today = timezone.localdate()
            count = DisposalRecord.objects.filter(created_at__year=today.year).count() + 1
            self.disposal_number = f"DSP-{today.strftime('%Y')}-{count:04d}"
        super().save(*args, **kwargs)

    @property
    def total_value(self):
        return sum(di.value for di in self.items.all())


class DisposalItem(TimeStampedModel):
    disposal  = models.ForeignKey(DisposalRecord, on_delete=models.CASCADE, related_name='items')
    item      = models.ForeignKey(InventoryItem, on_delete=models.PROTECT)
    batch     = models.ForeignKey(BatchStock, on_delete=models.SET_NULL, null=True, blank=True)
    quantity  = models.PositiveIntegerField()
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    notes     = models.CharField(max_length=200, blank=True)

    @property
    def value(self):
        return self.quantity * self.unit_cost

    def __str__(self):
        return f"{self.item.name} × {self.quantity}"


# ── Stock Take Schedule ─────────────────────────────────────────────────────

class StockTakeSchedule(AuditModel):
    """Recurring stock count schedule — ISO 9001 §8.5.4."""
    name       = models.CharField(max_length=100, help_text='e.g. Monthly Full Count, Weekly High-Value')
    frequency  = models.CharField(max_length=20, choices=[
        ('WEEKLY', 'Weekly'),
        ('MONTHLY', 'Monthly'),
        ('QUARTERLY', 'Quarterly'),
        ('SEMI_ANNUAL', 'Semi-Annual'),
        ('ANNUAL', 'Annual'),
    ])
    category_filter = models.CharField(
        max_length=20, choices=ItemCategory.choices, blank=True,
        help_text='Only count items in this category (blank = all items)',
    )
    abc_filter = models.CharField(
        max_length=1, choices=ABCClass.choices, blank=True,
        help_text='Only count items with this ABC class (blank = all)',
    )
    assigned_to = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assigned_stock_takes',
    )
    next_due    = models.DateField()
    last_completed = models.DateField(null=True, blank=True)
    is_active   = models.BooleanField(default=True)
    notes       = models.TextField(blank=True)

    class Meta:
        ordering = ['next_due']

    def __str__(self):
        return f"{self.name} ({self.get_frequency_display()}) — next {self.next_due}"

    @property
    def is_overdue(self):
        return self.next_due < timezone.localdate()

    @property
    def days_until_due(self):
        return (self.next_due - timezone.localdate()).days


# ── Supplier Quotation (ISO 9001 §8.4 — Vendor Selection) ───────────────────

class QuotationStatus(models.TextChoices):
    REQUESTED = 'REQUESTED', 'Requested'
    RECEIVED  = 'RECEIVED',  'Received'
    ACCEPTED  = 'ACCEPTED',  'Accepted'
    REJECTED  = 'REJECTED',  'Rejected'
    EXPIRED   = 'EXPIRED',   'Expired'


class SupplierQuotation(AuditModel):
    """Request for Quotation (RFQ) from a vendor."""
    rfq_number      = models.CharField(max_length=30, unique=True, blank=True)
    vendor          = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name='quotations')
    status          = models.CharField(max_length=15, choices=QuotationStatus.choices,
                                        default=QuotationStatus.REQUESTED)
    requested_date  = models.DateField(default=timezone.localdate)
    valid_until     = models.DateField(null=True, blank=True)
    total_amount    = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    linked_po       = models.ForeignKey(
        PurchaseOrder, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='quotations', help_text='PO created from this quotation',
    )
    notes           = models.TextField(blank=True)
    requested_by    = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='store_quotations_requested',
    )

    class Meta:
        ordering = ['-requested_date']

    def __str__(self):
        return f"RFQ-{self.rfq_number} ({self.vendor.name})"

    def save(self, *args, **kwargs):
        if not self.rfq_number:
            today = timezone.localdate()
            count = SupplierQuotation.objects.filter(requested_date__year=today.year).count() + 1
            self.rfq_number = f"RFQ-{today.year}-{count:04d}"
        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        return self.valid_until and self.valid_until < timezone.localdate()


class QuotationItem(TimeStampedModel):
    quotation      = models.ForeignKey(SupplierQuotation, on_delete=models.CASCADE, related_name='items')
    item           = models.ForeignKey(InventoryItem, on_delete=models.PROTECT)
    quantity       = models.PositiveIntegerField()
    quoted_price   = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    notes          = models.CharField(max_length=200, blank=True)

    @property
    def subtotal(self):
        return self.quantity * self.quoted_price

    def __str__(self):
        return f"{self.item.name} × {self.quantity} @ {self.quoted_price}"


# ── Store Budget (ISO 9001 §7.1 — Resource Management) ──────────────────────

class StoreBudget(AuditModel):
    """Annual or periodic budget for store procurement."""
    name          = models.CharField(max_length=100)
    fiscal_year   = models.PositiveIntegerField()
    category      = models.CharField(max_length=20, choices=ItemCategory.choices, blank=True,
                                      help_text='Budget for specific category (blank = all)')
    allocated     = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                         help_text='Total budget allocated')
    spent         = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                         help_text='Amount spent (auto-updated from POs)')
    notes         = models.TextField(blank=True)

    class Meta:
        ordering = ['-fiscal_year', 'name']
        unique_together = [('fiscal_year', 'category')]

    def __str__(self):
        return f"{self.name} — {self.fiscal_year}"

    @property
    def remaining(self):
        return self.allocated - self.spent

    @property
    def utilization_pct(self):
        if self.allocated == 0:
            return 0
        return round(float(self.spent) / float(self.allocated) * 100, 1)

    @property
    def is_over_budget(self):
        return self.spent > self.allocated


# ═══════════════════════════════════════════════════════════════════════════════
# 4-EYES STOCK VALIDATION (Cameroon store-keeping law)
# Store Keeper enters stock → Finance Director reviews & validates → GL posts
# ═══════════════════════════════════════════════════════════════════════════════

class StockValidationStatus(models.TextChoices):
    PENDING   = 'PENDING',   'Pending Finance Validation'
    VALIDATED = 'VALIDATED', 'Validated — GL Posted'
    REJECTED  = 'REJECTED',  'Rejected by Finance'


class StockValidationType(models.TextChoices):
    GRN        = 'GRN',        'Goods Received Note'
    ENTRY      = 'ENTRY',      'Direct Stock Entry'
    EXIT       = 'EXIT',       'Stock Exit'
    DISPOSAL   = 'DISPOSAL',   'Disposal / Wastage'
    ADJUSTMENT = 'ADJUSTMENT', 'Stock Adjustment'
    COUNT      = 'COUNT',      'Stock Count Variance'
    RETURN     = 'RETURN',     'Department Return'
    ISSUE      = 'ISSUE',      'Requisition Issue'


class StockValidation(AuditModel):
    """
    4-Eyes Principle: Every stock transaction with financial impact must be
    validated by the Finance Director before it posts to the GL.

    Flow: Store Keeper creates transaction → StockValidation auto-created (PENDING)
          → Finance Director reviews → validates or rejects
          → On validation: GL journal entry auto-posted
    """
    validation_type = models.CharField(max_length=15, choices=StockValidationType.choices)
    status         = models.CharField(max_length=15, choices=StockValidationStatus.choices,
                                      default=StockValidationStatus.PENDING)
    # Link to source transaction (polymorphic via type + id)
    source_id      = models.UUIDField(help_text='PK of the source transaction')
    reference      = models.CharField(max_length=50, help_text='Transaction reference number')
    description    = models.TextField(blank=True)
    total_value    = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                         help_text='Total financial value of this transaction (XAF)')
    # Who did what
    submitted_by   = models.ForeignKey('accounts.User', on_delete=models.PROTECT,
                                       related_name='stock_validations_submitted')
    submitted_at   = models.DateTimeField(auto_now_add=True)
    validated_by   = models.ForeignKey('accounts.User', on_delete=models.SET_NULL,
                                       null=True, blank=True,
                                       related_name='stock_validations_reviewed')
    validated_at   = models.DateTimeField(null=True, blank=True)
    validation_notes = models.TextField(blank=True)
    # Operation type (determines GL accounts for posting)
    operation_type = models.ForeignKey('billing.StockOperationType', on_delete=models.SET_NULL,
                                       null=True, blank=True, related_name='validations',
                                       help_text='Stock operation type — determines Dr/Cr GL accounts')
    # GL link
    journal_entry  = models.ForeignKey('billing.JournalEntry', on_delete=models.SET_NULL,
                                       null=True, blank=True, related_name='stock_validation_source')

    class Meta:
        ordering = ['-submitted_at']

    def __str__(self):
        return f"{self.get_validation_type_display()} — {self.reference} ({self.get_status_display()})"


# ═══════════════════════════════════════════════════════════════════════════════
# SUPPLIER INVOICE + 3-WAY MATCH
# ═══════════════════════════════════════════════════════════════════════════════

class SupplierInvoiceStatus(models.TextChoices):
    RECEIVED   = 'RECEIVED',   'Received'
    MATCHED    = 'MATCHED',    'Matched (3-Way OK)'
    DISPUTED   = 'DISPUTED',   'Disputed'
    PAID       = 'PAID',       'Paid'
    VOID       = 'VOID',       'Void'


class SupplierInvoice(AuditModel):
    """
    Vendor/supplier invoice received against a PO.
    Used for 3-way match: PO vs GRN vs Supplier Invoice.
    """
    invoice_number = models.CharField(max_length=100)
    vendor         = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name='supplier_invoices')
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='supplier_invoices')
    grn            = models.ForeignKey(GoodsReceivedNote, on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='supplier_invoices')
    invoice_date   = models.DateField()
    due_date       = models.DateField(null=True, blank=True)
    total_amount   = models.DecimalField(max_digits=14, decimal_places=2)
    status         = models.CharField(max_length=20, choices=SupplierInvoiceStatus.choices,
                                      default=SupplierInvoiceStatus.RECEIVED)
    notes          = models.TextField(blank=True)

    class Meta:
        ordering = ['-invoice_date']
        verbose_name = 'Supplier Invoice'

    def __str__(self):
        return f"SI-{self.invoice_number} — {self.vendor.name} ({self.total_amount:,.0f} XAF)"


class SupplierInvoiceItem(TimeStampedModel):
    """Line items on a supplier invoice."""
    supplier_invoice = models.ForeignKey(SupplierInvoice, on_delete=models.CASCADE, related_name='items')
    item             = models.ForeignKey(InventoryItem, on_delete=models.PROTECT)
    quantity         = models.PositiveIntegerField()
    unit_price       = models.DecimalField(max_digits=10, decimal_places=2)

    @property
    def line_total(self):
        return self.quantity * self.unit_price


class ThreeWayMatchStatus(models.TextChoices):
    PENDING  = 'PENDING',  'Pending Review'
    MATCHED  = 'MATCHED',  'Fully Matched'
    PARTIAL  = 'PARTIAL',  'Partial Match'
    MISMATCH = 'MISMATCH', 'Mismatch (Discrepancy)'
    RESOLVED = 'RESOLVED', 'Resolved'


class ThreeWayMatch(AuditModel):
    """
    3-Way Match: PO vs GRN vs Supplier Invoice.
    Ensures quantities and prices align across all three documents.
    Discrepancies flagged for Finance Director review.
    """
    match_number      = models.CharField(max_length=30, unique=True)
    purchase_order    = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name='three_way_matches')
    grn               = models.ForeignKey(GoodsReceivedNote, on_delete=models.PROTECT, related_name='three_way_matches')
    supplier_invoice  = models.ForeignKey(SupplierInvoice, on_delete=models.PROTECT, related_name='three_way_matches')
    status            = models.CharField(max_length=20, choices=ThreeWayMatchStatus.choices,
                                         default=ThreeWayMatchStatus.PENDING)
    po_total          = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    grn_total         = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    invoice_total     = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    qty_match         = models.BooleanField(default=False, help_text='Do PO/GRN/Invoice quantities match?')
    price_match       = models.BooleanField(default=False, help_text='Do PO/Invoice unit prices match?')
    total_match       = models.BooleanField(default=False, help_text='Do totals match within tolerance?')
    discrepancy_notes = models.TextField(blank=True)
    resolved_by       = models.ForeignKey('accounts.User', null=True, blank=True,
                                          on_delete=models.SET_NULL, related_name='resolved_matches')
    resolved_at       = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = '3-Way Match'
        verbose_name_plural = '3-Way Matches'

    def __str__(self):
        return f"{self.match_number} — {self.get_status_display()}"

    def save(self, *args, **kwargs):
        if not self.match_number:
            today = timezone.localdate()
            count = ThreeWayMatch.objects.filter(created_at__year=today.year).count() + 1
            self.match_number = f"3WM-{today.year}-{count:04d}"
        super().save(*args, **kwargs)

    def perform_match(self):
        """Run the 3-way match comparison and set flags."""
        from decimal import Decimal
        tolerance = Decimal('0.01')

        # Quantity match: compare PO ordered vs GRN received vs Invoice qty
        po_items = {pi.item_id: pi.quantity_ordered for pi in self.purchase_order.items.all()}
        grn_items = {}
        for gi in self.grn.items.select_related('po_item').all():
            item_id = gi.po_item.item_id if gi.po_item else None
            if item_id:
                grn_items[item_id] = grn_items.get(item_id, 0) + gi.quantity_accepted
        inv_items = {si.item_id: si.quantity for si in self.supplier_invoice.items.all()}

        self.qty_match = (po_items == grn_items == inv_items)

        # Price match: PO unit prices vs Invoice unit prices
        po_prices = {pi.item_id: pi.unit_price for pi in self.purchase_order.items.all()}
        inv_prices = {si.item_id: si.unit_price for si in self.supplier_invoice.items.all()}
        self.price_match = all(
            abs(po_prices.get(k, 0) - inv_prices.get(k, 0)) <= tolerance
            for k in set(po_prices) | set(inv_prices)
        )

        # Total match
        self.po_total = self.purchase_order.total_amount
        self.grn_total = sum(
            gi.quantity_accepted * (gi.po_item.unit_price if gi.po_item else 0)
            for gi in self.grn.items.select_related('po_item').all()
        )
        self.invoice_total = self.supplier_invoice.total_amount
        self.total_match = (
            abs(self.po_total - self.invoice_total) <= tolerance
            and abs(self.grn_total - self.invoice_total) <= tolerance
        )

        if self.qty_match and self.price_match and self.total_match:
            self.status = ThreeWayMatchStatus.MATCHED
        elif self.qty_match or self.price_match:
            self.status = ThreeWayMatchStatus.PARTIAL
        else:
            self.status = ThreeWayMatchStatus.MISMATCH

        self.save()
