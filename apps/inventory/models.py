"""
Inventory Module
Hospital supplies, equipment, purchase orders, vendor management.
"""
from django.db import models
from django.utils import timezone
from apps.core.models import TimeStampedModel, AuditModel


class ItemCategory(models.TextChoices):
    SURGICAL = 'SURGICAL', 'Surgical Supplies'
    DIAGNOSTIC = 'DIAGNOSTIC', 'Diagnostic Equipment'
    OFFICE = 'OFFICE', 'Office Supplies'
    CLEANING = 'CLEANING', 'Cleaning/Housekeeping'
    IT = 'IT', 'IT Equipment'
    FURNITURE = 'FURNITURE', 'Furniture'
    LINEN = 'LINEN', 'Linen/Laundry'
    OTHER = 'OTHER', 'Other'


class InventoryItem(AuditModel):
    """Master item catalogue"""
    name = models.CharField(max_length=200)
    item_code = models.CharField(max_length=50, unique=True)
    category = models.CharField(max_length=20, choices=ItemCategory.choices)
    description = models.TextField(blank=True)
    unit = models.CharField(max_length=50, default='unit')
    reorder_level = models.PositiveIntegerField(default=5)
    current_stock = models.PositiveIntegerField(default=0)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    location = models.CharField(max_length=100, blank=True, help_text='Storage location')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.item_code} - {self.name}"

    @property
    def needs_reorder(self):
        return self.current_stock <= self.reorder_level


class Vendor(AuditModel):
    name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class PurchaseOrderStatus(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft'
    SUBMITTED = 'SUBMITTED', 'Submitted'
    APPROVED = 'APPROVED', 'Approved'
    RECEIVED = 'RECEIVED', 'Received'
    CANCELLED = 'CANCELLED', 'Cancelled'


class PurchaseOrder(AuditModel):
    po_number = models.CharField(max_length=30, unique=True)
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name='purchase_orders')
    status = models.CharField(max_length=20, choices=PurchaseOrderStatus.choices, default=PurchaseOrderStatus.DRAFT)
    ordered_date = models.DateField(default=timezone.now)
    expected_date = models.DateField(null=True, blank=True)
    received_date = models.DateField(null=True, blank=True)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    approved_by = models.ForeignKey(
        'accounts.User', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='approved_pos'
    )

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
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT)
    quantity_ordered = models.PositiveIntegerField()
    quantity_received = models.PositiveIntegerField(default=0)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def save(self, *args, **kwargs):
        self.subtotal = self.quantity_ordered * self.unit_price
        super().save(*args, **kwargs)


class StockMovement(TimeStampedModel):
    """Audit trail of stock movements"""
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name='movements')
    movement_type = models.CharField(max_length=20, choices=[
        ('IN', 'Stock In'), ('OUT', 'Stock Out'), ('ADJUST', 'Adjustment'), ('RETURN', 'Return')
    ])
    quantity = models.IntegerField()  # can be negative for OUT
    balance_after = models.PositiveIntegerField()
    reference = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    performed_by = models.ForeignKey(
        'accounts.User', null=True, blank=True, on_delete=models.SET_NULL
    )

    class Meta:
        ordering = ['-created_at']
