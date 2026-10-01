"""
Procurement / Purchasing Module
Purchase Requests, Purchase Orders, and Goods Received Notes.
Follows standard procurement workflow: PR → PO → GRN → AP Bill.
"""
from django.db import models
from django.utils import timezone
from apps.core.models import AuditModel


class PRStatus(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft'
    PENDING = 'PENDING', 'Pending Approval'
    APPROVED = 'APPROVED', 'Approved'
    REJECTED = 'REJECTED', 'Rejected'
    ORDERED = 'ORDERED', 'PO Raised'
    CLOSED = 'CLOSED', 'Closed'


class POStatus(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft'
    SENT = 'SENT', 'Sent to Vendor'
    PARTIAL = 'PARTIAL', 'Partially Received'
    RECEIVED = 'RECEIVED', 'Fully Received'
    CANCELLED = 'CANCELLED', 'Cancelled'


class PurchaseCategory(models.TextChoices):
    MEDICAL_SUPPLIES = 'MEDICAL', 'Medical Supplies'
    DRUGS = 'DRUGS', 'Drugs & Pharmaceuticals'
    EQUIPMENT = 'EQUIPMENT', 'Medical Equipment'
    STATIONERY = 'STATIONERY', 'Stationery & Office'
    IT = 'IT', 'IT & Electronics'
    MAINTENANCE = 'MAINTENANCE', 'Maintenance & Repairs'
    FURNITURE = 'FURNITURE', 'Furniture & Fixtures'
    OTHER = 'OTHER', 'Other'


class PurchaseRequest(AuditModel):
    """A department's request to purchase goods or services."""
    pr_number = models.CharField(max_length=20, unique=True, blank=True)
    title = models.CharField(max_length=200)
    department = models.ForeignKey(
        'departments.Department', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='purchase_requests'
    )
    category = models.CharField(max_length=20, choices=PurchaseCategory.choices, default=PurchaseCategory.OTHER)
    requested_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, related_name='purchase_requests'
    )
    approved_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='pr_approvals'
    )
    status = models.CharField(max_length=20, choices=PRStatus.choices, default=PRStatus.DRAFT)
    urgency = models.CharField(max_length=10, choices=[('LOW', 'Low'), ('NORMAL', 'Normal'), ('URGENT', 'Urgent')],
                                default='NORMAL')
    justification = models.TextField(blank=True)
    required_by_date = models.DateField(null=True, blank=True)
    estimated_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    approved_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.pr_number} — {self.title}"

    def save(self, *args, **kwargs):
        if not self.pr_number:
            from django.utils import timezone as tz
            year = tz.now().year
            count = PurchaseRequest.objects.filter(
                created_at__year=year
            ).count() + 1
            self.pr_number = f"PR-{year}-{count:04d}"
        super().save(*args, **kwargs)


class PurchaseRequestItem(AuditModel):
    request = models.ForeignKey(PurchaseRequest, on_delete=models.CASCADE, related_name='items')
    description = models.CharField(max_length=300)
    specification = models.TextField(blank=True)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit = models.CharField(max_length=50, blank=True, default='pcs')
    estimated_unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    quantity_received = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        ordering = ['id']

    @property
    def estimated_subtotal(self):
        return self.quantity * self.estimated_unit_price

    def __str__(self):
        return f"{self.description} × {self.quantity}"


class PurchaseOrder(AuditModel):
    """Formal order issued to a vendor."""
    po_number = models.CharField(max_length=20, unique=True, blank=True)
    purchase_request = models.ForeignKey(
        PurchaseRequest, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='purchase_orders'
    )
    vendor = models.ForeignKey(
        'billing.APVendor', on_delete=models.PROTECT, related_name='purchase_orders'
    )
    status = models.CharField(max_length=20, choices=POStatus.choices, default=POStatus.DRAFT)
    created_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, related_name='pos_created'
    )
    delivery_address = models.TextField(blank=True, default='AEF/MICEI — Yaoundé, Cameroon')
    expected_delivery_date = models.DateField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    terms = models.TextField(blank=True, default='Payment within 30 days of delivery.')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.po_number} — {self.vendor}"

    def save(self, *args, **kwargs):
        if not self.po_number:
            from django.utils import timezone as tz
            year = tz.now().year
            count = PurchaseOrder.objects.filter(created_at__year=year).count() + 1
            self.po_number = f"PO-{year}-{count:04d}"
        super().save(*args, **kwargs)


class POItem(AuditModel):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='items')
    description = models.CharField(max_length=300)
    quantity_ordered = models.DecimalField(max_digits=10, decimal_places=2)
    quantity_received = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    unit = models.CharField(max_length=50, blank=True, default='pcs')
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    pr_item = models.ForeignKey(PurchaseRequestItem, null=True, blank=True,
                                 on_delete=models.SET_NULL, related_name='po_items')

    class Meta:
        ordering = ['id']

    @property
    def subtotal(self):
        return self.quantity_ordered * self.unit_price

    @property
    def remaining(self):
        return self.quantity_ordered - self.quantity_received

    def __str__(self):
        return f"{self.description} × {self.quantity_ordered}"


class GoodsReceivedNote(AuditModel):
    """Records actual goods/services received against a PO."""
    grn_number = models.CharField(max_length=20, unique=True, blank=True)
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name='grns')
    received_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, related_name='procurement_grns_received'
    )
    received_date = models.DateField(default=timezone.now)
    delivery_note_ref = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    is_verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='procurement_grns_verified'
    )

    class Meta:
        ordering = ['-received_date']

    def __str__(self):
        return f"{self.grn_number} — {self.purchase_order.po_number}"

    def save(self, *args, **kwargs):
        if not self.grn_number:
            from django.utils import timezone as tz
            year = tz.now().year
            count = GoodsReceivedNote.objects.filter(created_at__year=year).count() + 1
            self.grn_number = f"GRN-{year}-{count:04d}"
        super().save(*args, **kwargs)


class GRNItem(AuditModel):
    grn = models.ForeignKey(GoodsReceivedNote, on_delete=models.CASCADE, related_name='items')
    po_item = models.ForeignKey(POItem, on_delete=models.PROTECT, related_name='grn_items')
    quantity_received = models.DecimalField(max_digits=10, decimal_places=2)
    condition = models.CharField(max_length=20,
                                  choices=[('GOOD', 'Good'), ('DAMAGED', 'Damaged'), ('PARTIAL', 'Partial')],
                                  default='GOOD')
    remarks = models.TextField(blank=True)

    class Meta:
        ordering = ['id']
