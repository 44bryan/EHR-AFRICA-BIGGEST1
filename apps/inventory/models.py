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


class InventoryItem(AuditModel):
    """Master item catalogue"""
    name             = models.CharField(max_length=200)
    item_code        = models.CharField(max_length=50, unique=True)
    category         = models.CharField(max_length=20, choices=ItemCategory.choices)
    description      = models.TextField(blank=True)
    unit             = models.CharField(max_length=50, default='unit')
    reorder_level    = models.PositiveIntegerField(default=5)
    current_stock    = models.PositiveIntegerField(default=0)
    unit_cost        = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    location         = models.CharField(max_length=100, blank=True, help_text='Storage location')
    is_active        = models.BooleanField(default=True)

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

    @property
    def needs_reorder(self):
        return self.current_stock <= self.reorder_level

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

    class Meta:
        ordering = ['-ordered_date']

    def __str__(self):
        return f"PO-{self.po_number} ({self.vendor.name})"

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
    """Physical store rooms within the facility."""
    name = models.CharField(max_length=100, unique=True)
    location_type = models.CharField(max_length=20, choices=[
        ('CENTRAL', 'Central Store'),
        ('SUB', 'Sub-Store'),
        ('WARD', 'Ward Store'),
        ('THEATRE', 'Theatre Store'),
        ('EMERGENCY', 'Emergency Store'),
    ])
    address = models.TextField(blank=True, help_text='Physical location within facility')
    manager = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='managed_store_locations',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.get_location_type_display()})"


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
