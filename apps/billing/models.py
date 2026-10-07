"""
Billing Module
Invoices, line items, payments, and receipt generation.
"""
from django.db import models
from django.utils import timezone
from apps.core.models import AuditModel, TimeStampedModel


class InvoiceStatus(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft'
    ISSUED = 'ISSUED', 'Issued'
    PARTIALLY_PAID = 'PARTIAL', 'Partially Paid'
    PAID = 'PAID', 'Paid'
    CANCELLED = 'CANCELLED', 'Cancelled'
    WAIVED = 'WAIVED', 'Waived'


class PaymentMethod(models.TextChoices):
    CASH = 'CASH', 'Cash'
    CARD = 'CARD', 'POS / Card'
    TRANSFER = 'TRANSFER', 'Bank Transfer'
    MOBILE_MONEY = 'MOBILE', 'Mobile Money'
    INSURANCE = 'INSURANCE', 'Insurance'
    NHIS = 'NHIS', 'NHIS'
    WAIVER = 'WAIVER', 'Waiver'
    WALLET = 'WALLET', 'Patient Wallet'


class ServiceCategory(models.TextChoices):
    CONSULTATION = 'CONSULT', 'Consultation'
    CLINICAL_EXAM = 'CLINICAL', 'Clinical Exam'
    INVESTIGATION = 'INVEST', 'Investigation / Diagnostics'
    LABORATORY = 'LAB', 'Laboratory'
    PHARMACY = 'PHARMACY', 'Pharmacy'
    OPTICAL = 'OPTICAL', 'Opticals'
    SURGICAL = 'SURGICAL', 'Surgical Procedure'
    ADMISSION = 'ADMISSION', 'Inpatient Admission'
    REGISTRATION = 'REG', 'Registration'
    OTHER = 'OTHER', 'Other'


class ServiceTierFilter(models.TextChoices):
    """
    Controls which cashier desk tier can bill this service.
    Blank = visible to ALL cashier desks.
    """
    ALL        = '',          'All Tiers (No restriction)'
    STANDARD   = 'STANDARD',  'Standard Desk Only'
    EXPRESS    = 'EXPRESS',   'Express Desk Only'
    VIP        = 'VIP',       'VIP Desk Only'
    EVIP       = 'EVIP',      'Executive VIP Desk Only'
    INSURED    = 'INSURED',   'Insured / HMO Desk Only'


class DeskType(models.TextChoices):
    TIER      = 'TIER',      'Tier Desk (Standard / Express / VIP)'
    PHARMACY  = 'PHARMACY',  'Pharmacy Desk'
    OPTICAL   = 'OPTICAL',   'Optical Desk'
    INSURANCE = 'INSURANCE', 'Insurance / HMO Desk'


class InvoiceRoutingType(models.TextChoices):
    TIER      = 'TIER',      'Tier (Main Cashier)'
    PHARMACY  = 'PHARMACY',  'Pharmacy'
    OPTICAL   = 'OPTICAL',   'Optical'
    INSURANCE = 'INSURANCE', 'Insurance / HMO'


class SessionStatus(models.TextChoices):
    OPEN     = 'OPEN',     'Open'
    CLOSED   = 'CLOSED',   'Closed'
    VERIFIED = 'VERIFIED', 'Verified'


class DiscountApprovalStatus(models.TextChoices):
    PENDING  = 'PENDING',  'Pending Supervisor Review'
    APPROVED = 'APPROVED', 'Approved'
    REJECTED = 'REJECTED', 'Rejected'


class DiscountType(models.TextChoices):
    PERCENTAGE = 'PERCENTAGE', 'Percentage (%)'
    AMOUNT     = 'AMOUNT',     'Fixed Amount (FCFA)'
    REJECTED = 'REJECTED', 'Rejected'


class ServiceSubCategory(AuditModel):
    """
    Sub-category within a ServiceCategory — e.g. "Frames" under OPTICAL.
    Each sub-category links to a specific GL revenue account for precise posting.
    """
    category = models.CharField(max_length=20, choices=ServiceCategory.choices)
    name = models.CharField(max_length=100, help_text='e.g. Frames, Lenses, Prescription Drugs')
    code = models.CharField(max_length=20, blank=True, help_text='Short code e.g. FRM, LNS')
    gl_account = models.ForeignKey(
        'billing.GLAccount', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='service_sub_categories',
        help_text='GL revenue account for this sub-category (overrides category default)'
    )
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['category', 'sort_order', 'name']
        unique_together = [('category', 'name')]
        verbose_name = 'Service Sub-Category'
        verbose_name_plural = 'Service Sub-Categories'

    def __str__(self):
        return f"{self.get_category_display()} > {self.name}"


class EntryType(models.TextChoices):
    SERVICE = 'SERVICE', 'Service'
    ITEM    = 'ITEM',    'Item (Physical Good)'


class ServicePrice(AuditModel):
    """
    Charge Description Master (CDM) — DB-driven price list.
    Replaces hardcoded SERVICE_CATALOG in views.py.
    Managed via Django admin by Finance Manager / Super Admin.
    """
    entry_type = models.CharField(
        max_length=10, choices=EntryType.choices, default=EntryType.SERVICE,
        help_text='SERVICE = intangible billable service, ITEM = physical good with stock tracking'
    )
    name = models.CharField(max_length=200, help_text='Service/item name shown on invoice')
    code = models.CharField(
        max_length=30, blank=True,
        help_text='Internal billing code (e.g. CONS-STD, OPT-REFRAC)'
    )
    category = models.CharField(max_length=20, choices=ServiceCategory.choices)
    sub_category = models.ForeignKey(
        ServiceSubCategory, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='services',
        help_text='Sub-category within the family (e.g. Frames under Optical)'
    )
    tier = models.CharField(
        max_length=20, blank=True, default='',
        help_text='Leave blank = visible to ALL cashier desks. '
                  'Set to restrict this service to a specific desk tier only '
                  '(e.g. VIP consultation at a higher price for VIP desk).',
    )

    # ── ERP GL Account Linking ──
    gl_account = models.ForeignKey(
        'billing.GLAccount', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='service_prices',
        help_text='Sales GL — revenue account credited when sold'
    )
    purchase_gl_account = models.ForeignKey(
        'billing.GLAccount', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='purchase_prices',
        help_text='Purchase GL — expense/asset account debited when purchasing from suppliers'
    )
    stock_gl_account = models.ForeignKey(
        'billing.GLAccount', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='stock_prices',
        help_text='Stock GL — asset account representing inventory on hand'
    )
    stock_variation_gl_account = models.ForeignKey(
        'billing.GLAccount', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='stock_variation_prices',
        help_text='Stock Variation GL — COGS account tracking cost of goods consumed'
    )

    # ── Pricing ──
    price_ht = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text='Price Hors Taxe (before tax) in FCFA'
    )
    tax_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text='Tax rate % (e.g. 19.25 for Cameroon TVA). 0 = exempt.'
    )
    price = models.DecimalField(
        max_digits=10, decimal_places=2,
        help_text='Price TTC (tax-inclusive) in FCFA — the amount the patient pays'
    )
    nhis_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text='NHIS-negotiated rate (leave blank to use standard price)'
    )
    insurance_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text='Insurance-negotiated rate (leave blank to use standard price)'
    )

    # ── Item properties ──
    is_stockable = models.BooleanField(
        default=False,
        help_text='Tracks physical inventory (stock > 0). E.g. frames, lenses, drugs.'
    )
    is_taxable = models.BooleanField(
        default=False,
        help_text='Subject to TVA/VAT. If True, tax_rate applies.'
    )
    is_active = models.BooleanField(default=True)
    requires_price_entry = models.BooleanField(
        default=False,
        help_text='If True, cashier must enter price at point of sale (e.g. glasses frames)'
    )

    class Meta:
        ordering = ['category', 'name']
        verbose_name = 'Service Price'
        verbose_name_plural = 'Service Prices (Charge Master)'

    def __str__(self):
        return f"{self.name} — {self.price:,.0f} FCFA"

    def get_price_for_method(self, payment_method=None):
        """Return the appropriate price based on payment method."""
        if payment_method == PaymentMethod.NHIS and self.nhis_price is not None:
            return self.nhis_price
        if payment_method == PaymentMethod.INSURANCE and self.insurance_price is not None:
            return self.insurance_price
        return self.price

    def get_gl_code(self):
        """Resolve GL account: item → sub-category → category default."""
        if self.gl_account_id:
            return self.gl_account.code
        if self.sub_category_id and self.sub_category.gl_account_id:
            return self.sub_category.gl_account.code
        from apps.billing.gl_service import get_revenue_code
        return get_revenue_code(self.category)

    @property
    def tax_amount(self):
        """Computed tax amount."""
        if self.tax_rate and self.price_ht:
            return (self.price_ht * self.tax_rate / 100).quantize(self.price_ht.__class__('0.01'))
        return self.price_ht.__class__('0')


class InvoiceVoidReason(AuditModel):
    """
    Configurable reason codes for cancelling or reversing an invoice.
    Managed by Finance Director / Super Admin via Django admin.
    Mirrors TurboClinic's reason dropdown (001=Declination by Patient, etc.)
    """
    code  = models.CharField(max_length=10, unique=True, help_text='e.g. 001, 002')
    label = models.CharField(max_length=200, help_text='e.g. Declination by Patient')
    requires_supervisor = models.BooleanField(
        default=False,
        help_text='If True, a supervisor must confirm before this reason is accepted'
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['code']
        verbose_name = 'Invoice Void Reason'
        verbose_name_plural = 'Invoice Void Reasons'

    def __str__(self):
        return f"{self.code}: {self.label}"


class Invoice(AuditModel):
    invoice_number = models.CharField(max_length=30, unique=True)
    patient = models.ForeignKey(
        'patients.Patient', on_delete=models.PROTECT, related_name='invoices'
    )
    consultation = models.ForeignKey(
        'consultations.Consultation', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='invoices'
    )
    status = models.CharField(max_length=20, choices=InvoiceStatus.choices, default=InvoiceStatus.DRAFT)
    issue_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField(null=True, blank=True)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_reason = models.CharField(max_length=200, blank=True)
    corporate_account = models.ForeignKey(
        'billing.CorporateAccount', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='invoices',
        help_text='Set when this invoice is billed to a corporate/insurer account'
    )
    notes = models.TextField(blank=True)
    insurance_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text='Amount the insurer is expected to cover (set at billing time)'
    )
    insurance_scheme = models.ForeignKey(
        'hmo.InsuranceScheme', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='invoices',
        help_text='Insurance company / payer scheme for this invoice'
    )
    void_reason = models.ForeignKey(
        'billing.InvoiceVoidReason', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='voided_invoices',
        help_text='Required when cancelling or reversing an invoice'
    )
    # ── Tier-scoped billing fields ────────────────────────────────────────────
    service_tier = models.CharField(
        max_length=20, blank=True, default='',
        help_text='Patient service tier at time of billing (STANDARD/EXPRESS/VIP)'
    )
    routing_type = models.CharField(
        max_length=20, choices=InvoiceRoutingType.choices,
        blank=True, default='',
        help_text='Which desk type handles this invoice (TIER/PHARMACY/OPTICAL/INSURANCE)'
    )
    cash_desk = models.ForeignKey(
        'billing.CashDesk', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='invoices',
        help_text='The cash desk that processed this invoice'
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Invoice {self.invoice_number} — {self.patient.full_name}"

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            from django.db import IntegrityError, transaction as _tx
            year = timezone.now().year
            for _retry in range(20):
                count = Invoice.objects.filter(created_at__year=year).count() + 1 + _retry
                self.invoice_number = f"INV-{year}-{count:05d}"
                try:
                    with _tx.atomic():
                        super().save(*args, **kwargs)
                    return
                except IntegrityError:
                    self.invoice_number = ''
            raise RuntimeError('Unable to generate unique invoice number after 20 retries')
        super().save(*args, **kwargs)

    @property
    def subtotal(self):
        # Use prefetched cache when available (avoids N+1 on list pages)
        if hasattr(self, '_items_cache'):
            return sum(item.line_total for item in self._items_cache)
        return sum(item.line_total for item in self.items.filter(is_deleted=False))

    @property
    def total(self):
        return max(self.subtotal - self.discount_amount, 0)

    @property
    def patient_amount(self):
        """Patient share after insurance coverage is deducted."""
        return max(self.total - self.insurance_amount, 0)

    @property
    def amount_paid(self):
        if hasattr(self, '_payments_cache'):
            return sum(p.amount for p in self._payments_cache)
        return sum(p.amount for p in self.payments.filter(is_deleted=False))

    @property
    def refund_total(self):
        if hasattr(self, '_refunds_cache'):
            return sum(r.amount for r in self._refunds_cache)
        return sum(r.amount for r in self.refunds.filter(is_deleted=False))

    @property
    def net_paid(self):
        """Amount paid minus any refunds issued."""
        return self.amount_paid - self.refund_total

    @property
    def balance_due(self):
        return self.total - self.net_paid

    def update_status(self):
        if self.status in (InvoiceStatus.CANCELLED, InvoiceStatus.WAIVED):
            return
        net = self.net_paid   # amount_paid minus refunds
        total = self.total
        if net <= 0:
            if self.status != InvoiceStatus.DRAFT:
                self.status = InvoiceStatus.ISSUED
        elif net >= total:
            self.status = InvoiceStatus.PAID
        else:
            self.status = InvoiceStatus.PARTIALLY_PAID
        self.save(update_fields=['status'])


class InvoiceItem(AuditModel):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='items')
    service_price = models.ForeignKey(
        ServicePrice, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='invoice_items',
        help_text='Link to catalog item (for GL account resolution and reporting)'
    )
    category = models.CharField(max_length=20, choices=ServiceCategory.choices)
    description = models.CharField(max_length=255)
    quantity = models.PositiveSmallIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0,
        help_text='Tax portion of the line total (TVA)')
    gl_account_code = models.CharField(max_length=20, blank=True,
        help_text='GL revenue account code resolved at billing time')
    notes = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"{self.description} x{self.quantity}"

    @property
    def line_total(self):
        return self.quantity * self.unit_price

    def resolve_gl_code(self):
        """Get the GL account code for this line item."""
        if self.gl_account_code:
            return self.gl_account_code
        if self.service_price_id:
            return self.service_price.get_gl_code()
        from apps.billing.gl_service import get_revenue_code
        return get_revenue_code(self.category)


class Payment(AuditModel):
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name='payments')
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    receipt_number = models.CharField(
        max_length=30, blank=True, db_index=True,
        help_text='Auto-generated unique receipt number (RCT-YYYY-NNNNN)'
    )
    reference = models.CharField(
        max_length=100, blank=True,
        help_text='External transaction reference (e.g. Mobile Money TX ID, POS terminal ref)'
    )
    notes = models.CharField(max_length=200, blank=True)
    received_by = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='payments_received'
    )
    payment_date = models.DateTimeField(default=timezone.now)
    cashier_session = models.ForeignKey(
        'billing.CashierSession', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='payments',
        help_text='The cashier desk session during which this payment was collected'
    )

    class Meta:
        ordering = ['-payment_date']

    def __str__(self):
        return f"{self.receipt_number or self.id} — {self.amount:,.0f} FCFA on {self.invoice.invoice_number}"

    def save(self, *args, **kwargs):
        if not self.receipt_number:
            from django.db import IntegrityError, transaction as _tx
            # Derive receipt number from invoice number for traceability
            # INV-2026-00470 → RCT-2026-00470, RCT-2026-00470-2, etc.
            inv_num = self.invoice.invoice_number  # e.g. INV-2026-00470
            base = inv_num.replace('INV-', 'RCT-', 1)
            existing = Payment.objects.filter(
                invoice=self.invoice, is_deleted=False
            ).exclude(pk=self.pk).count()
            suffix = f"-{existing + 1}" if existing > 0 else ""
            candidate = f"{base}{suffix}"
            for _retry in range(10):
                self.receipt_number = candidate if _retry == 0 else f"{base}-{existing + 1 + _retry}"
                try:
                    with _tx.atomic():
                        super().save(*args, **kwargs)
                    break
                except IntegrityError:
                    self.receipt_number = ''
            else:
                raise RuntimeError('Unable to generate unique receipt number after 10 retries')
        else:
            super().save(*args, **kwargs)
        self.invoice.update_status()
        # Auto-create department work orders when invoice is fully paid
        try:
            self.invoice.refresh_from_db()
            if self.invoice.status == InvoiceStatus.PAID:
                ServiceWorkOrder.create_for_invoice(self.invoice, created_by=self.received_by)
        except Exception:
            pass
        # When first payment received on a visit-linked invoice,
        # open the 15-day consultation window for that patient's visit.
        try:
            visit = self.invoice.consultation.visit if (
                self.invoice.consultation and hasattr(self.invoice.consultation, 'visit')
            ) else None
            if not visit and self.invoice.consultation:
                # Try to find visit via patient's most recent visit
                pass
            if visit and not visit.consultation_valid_until:
                visit.mark_consultation_paid()
        except Exception:
            pass


class ShiftStatus(models.TextChoices):
    OPEN      = 'OPEN',      'Open'
    CLOSED    = 'CLOSED',    'Closed'
    SUBMITTED = 'SUBMITTED', 'Submitted to Chief Cashier'
    VERIFIED  = 'VERIFIED',  'Verified'


class CashierShift(AuditModel):
    """
    One row per cashier per working day.
    Lifecycle: OPEN → CLOSED → SUBMITTED → VERIFIED
    Cashier opens shift with opening cash float, collects payments all day,
    closes by declaring closing cash, then submits to chief cashier for sign-off.
    """
    cashier = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='cashier_shifts'
    )
    shift_date = models.DateField(default=timezone.localdate)
    opened_at = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(null=True, blank=True)
    opening_cash = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text='Cash float handed to cashier at shift start (FCFA)'
    )
    closing_cash_declared = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text='Physical cash in drawer as counted and declared by cashier'
    )
    status = models.CharField(
        max_length=20, choices=ShiftStatus.choices, default=ShiftStatus.OPEN
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='verified_shifts'
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-shift_date', '-opened_at']
        unique_together = [('cashier', 'shift_date')]
        verbose_name = 'Cashier Shift'
        verbose_name_plural = 'Cashier Shifts'

    def __str__(self):
        return f"Shift — {self.cashier.get_full_name() or self.cashier.username} ({self.shift_date})"

    @property
    def cash_collected(self):
        """CASH payments only — what should physically be in the drawer."""
        from django.db.models import Sum as _Sum
        return (
            Payment.objects.filter(
                received_by=self.cashier,
                payment_date__date=self.shift_date,
                payment_method=PaymentMethod.CASH,
                is_deleted=False,
            ).aggregate(t=_Sum('amount'))['t'] or 0
        )

    @property
    def total_collected(self):
        """All payment methods combined."""
        from django.db.models import Sum as _Sum
        return (
            Payment.objects.filter(
                received_by=self.cashier,
                payment_date__date=self.shift_date,
                is_deleted=False,
            ).aggregate(t=_Sum('amount'))['t'] or 0
        )

    @property
    def collections_by_method(self):
        from django.db.models import Sum as _Sum
        return (
            Payment.objects
            .filter(received_by=self.cashier, payment_date__date=self.shift_date, is_deleted=False)
            .values('payment_method')
            .annotate(total=_Sum('amount'))
            .order_by('payment_method')
        )

    @property
    def expected_cash_in_hand(self):
        """Opening float + cash collected during shift."""
        return self.opening_cash + self.cash_collected

    @property
    def cash_variance(self):
        """Positive = cashier has MORE than expected (overage). Negative = shortage."""
        if self.closing_cash_declared is None:
            return None
        return self.closing_cash_declared - self.expected_cash_in_hand

    @property
    def refunds_issued(self):
        from django.db.models import Sum as _Sum
        return (
            Refund.objects
            .filter(processed_by=self.cashier, refund_date__date=self.shift_date, is_deleted=False)
            .aggregate(t=_Sum('amount'))['t'] or 0
        )

    @property
    def transaction_count(self):
        return Payment.objects.filter(
            received_by=self.cashier,
            payment_date__date=self.shift_date,
            is_deleted=False,
        ).count()


class Refund(AuditModel):
    """
    Refund / credit note against a paid invoice.
    Used when a patient overpays, a service is cancelled after payment,
    or a billing error must be corrected.
    Processed by Cashier; audited by Finance Manager.
    """
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name='refunds')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.CharField(max_length=300)
    payment_method = models.CharField(
        max_length=20, choices=PaymentMethod.choices,
        help_text='How the refund is returned to the patient'
    )
    reference = models.CharField(max_length=100, blank=True)
    processed_by = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT,
        related_name='processed_refunds'
    )
    refund_date = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-refund_date']

    def __str__(self):
        return f"Refund {self.amount:,.0f} FCFA — {self.invoice.invoice_number}"


# ── Work Order System ─────────────────────────────────────────────────────────

class WorkOrderStatus(models.TextChoices):
    PENDING_PAYMENT = 'PENDING_PAYMENT', 'Waiting for Payment'
    PENDING         = 'PENDING',         'Paid — Pending Service'
    DONE            = 'DONE',            'Done'
    CANCELLED       = 'CANCELLED',       'Cancelled'


# Categories that require a department to act after payment
_ACTIONABLE_CATEGORIES = frozenset({
    ServiceCategory.CONSULTATION,
    ServiceCategory.INVESTIGATION,
    ServiceCategory.LABORATORY,
    ServiceCategory.PHARMACY,
    ServiceCategory.OPTICAL,
    ServiceCategory.SURGICAL,
})


class ServiceWorkOrder(AuditModel):
    """
    Auto-created when an invoice is fully PAID.
    One row per invoice line item that requires department action.
    Each department filters by category to see their own queue.
    """
    invoice = models.ForeignKey(
        Invoice, on_delete=models.PROTECT, related_name='work_orders',
        null=True, blank=True,
        help_text='Set when cashier bills the order. Null = not yet billed.'
    )
    invoice_item = models.ForeignKey(
        InvoiceItem, on_delete=models.PROTECT, related_name='work_orders',
        null=True, blank=True
    )
    consultation = models.ForeignKey(
        'consultations.Consultation', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='work_orders',
        help_text='Set when doctor creates the order during a consultation.'
    )
    lab_order_item = models.ForeignKey(
        'laboratory.LabOrderItem', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='work_orders',
        help_text='Links this work order to a specific lab test item for per-test payment tracking.'
    )
    patient = models.ForeignKey(
        'patients.Patient', on_delete=models.PROTECT, related_name='work_orders'
    )
    category = models.CharField(max_length=20, choices=ServiceCategory.choices)
    description = models.CharField(max_length=255)
    status = models.CharField(
        max_length=20, choices=WorkOrderStatus.choices, default=WorkOrderStatus.PENDING
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='completed_work_orders'
    )
    notes = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = 'Service Work Order'
        verbose_name_plural = 'Service Work Orders'

    def __str__(self):
        return f"{self.description} — {self.patient.full_name} [{self.status}]"

    @classmethod
    def create_for_invoice(cls, invoice, created_by=None):
        """
        Called automatically by Payment.save() when invoice transitions to PAID.
        1. Activates any PENDING_PAYMENT doctor orders for this patient → PENDING.
        2. Creates new PENDING work orders for invoice items not already tracked.
        Idempotent — safe to call multiple times.
        """
        if not invoice.patient:
            return
        from django.utils import timezone as _tz
        today = _tz.localdate()

        # Step 1: activate pre-created doctor orders for this patient today
        pending_payment_qs = cls.objects.filter(
            patient=invoice.patient,
            status=WorkOrderStatus.PENDING_PAYMENT,
            is_deleted=False,
            created_at__date=today,
        )
        for wo in pending_payment_qs:
            wo.invoice = invoice
            wo.status = WorkOrderStatus.PENDING
            wo.save(update_fields=['invoice', 'status', 'updated_at'])

        # Step 2: create work orders for invoice items that don't have one yet
        tracked_item_ids = set(
            cls.objects.filter(invoice=invoice, is_deleted=False)
            .exclude(invoice_item__isnull=True)
            .values_list('invoice_item_id', flat=True)
        )
        for item in invoice.items.filter(is_deleted=False):
            if item.category in _ACTIONABLE_CATEGORIES and item.pk not in tracked_item_ids:
                cls.objects.create(
                    invoice=invoice,
                    invoice_item=item,
                    patient=invoice.patient,
                    category=item.category,
                    description=item.description,
                    status=WorkOrderStatus.PENDING,
                    created_by=created_by,
                )


# ═══════════════════════════════════════════════════════════════════════════════
# FINANCIAL MODULE — Expenses, Corporate Accounts, Petty Cash
# ═══════════════════════════════════════════════════════════════════════════════

class ExpenseCategory(models.TextChoices):
    SUPPLIES    = 'SUPPLIES',    'Medical Supplies'
    UTILITIES   = 'UTILITIES',   'Utilities (Electricity / Water)'
    SALARY      = 'SALARY',      'Salaries & Staff Costs'
    RENT        = 'RENT',        'Rent & Facilities'
    EQUIPMENT   = 'EQUIPMENT',   'Equipment & Maintenance'
    DRUGS       = 'DRUGS',       'Drug / Pharmacy Stock'
    TRANSPORT   = 'TRANSPORT',   'Transport & Logistics'
    ADMIN       = 'ADMIN',       'Administrative'
    MARKETING   = 'MARKETING',   'Marketing & Outreach'
    OTHER       = 'EXP_OTHER',   'Other'


class Expense(AuditModel):
    """
    Operational expense incurred by the hospital.
    Recorded by Finance / Admin staff; approved by Finance Director.
    Used to calculate net P&L in financial reports.
    """
    date        = models.DateField(default=timezone.localdate)
    category    = models.CharField(max_length=20, choices=ExpenseCategory.choices)
    description = models.CharField(max_length=300)
    amount      = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(
        max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.CASH
    )
    vendor      = models.CharField(max_length=200, blank=True, help_text='Supplier / vendor name')
    reference   = models.CharField(max_length=100, blank=True, help_text='Vendor receipt / invoice #')
    department  = models.CharField(max_length=100, blank=True)
    approved_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='approved_expenses'
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name = 'Expense'
        verbose_name_plural = 'Expenses'

    def __str__(self):
        return f"{self.description} — {self.amount:,.0f} FCFA ({self.date})"


class CorporateAccount(AuditModel):
    """
    An employer, insurer, or government agency billed on credit.
    Patients linked via CorporateAccountMember.
    Finance generates a monthly statement; company pays in bulk.
    """
    name            = models.CharField(max_length=200, unique=True)
    account_code    = models.CharField(max_length=30, blank=True, unique=True, null=True)
    contact_name    = models.CharField(max_length=150, blank=True)
    phone           = models.CharField(max_length=20, blank=True)
    email           = models.EmailField(blank=True)
    address         = models.TextField(blank=True)
    credit_limit    = models.DecimalField(
        max_digits=14, decimal_places=2, default=0,
        help_text='Max outstanding balance in FCFA (0 = no limit)'
    )
    payment_terms_days = models.PositiveSmallIntegerField(
        default=30, help_text='Net payment days (e.g. 30 for Net-30)'
    )
    discount_pct    = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text='Flat discount % applied to all invoices for this account'
    )
    is_active       = models.BooleanField(default=True)
    notes           = models.TextField(blank=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Corporate Account'
        verbose_name_plural = 'Corporate Accounts'

    def __str__(self):
        return self.name

    @property
    def outstanding_balance(self):
        from django.db.models import Sum as _S, F as _F, ExpressionWrapper, DecimalField as _D
        inv_qs = Invoice.objects.filter(
            corporate_account=self, is_deleted=False
        ).exclude(status__in=[InvoiceStatus.PAID, InvoiceStatus.CANCELLED, InvoiceStatus.WAIVED])
        gross = InvoiceItem.objects.filter(
            invoice__in=inv_qs, is_deleted=False
        ).aggregate(
            t=_S(ExpressionWrapper(_F('unit_price') * _F('quantity'), output_field=_D(max_digits=14, decimal_places=2)))
        )['t'] or 0
        disc  = inv_qs.aggregate(d=_S('discount_amount'))['d'] or 0
        paid  = Payment.objects.filter(invoice__in=inv_qs, is_deleted=False).aggregate(p=_S('amount'))['p'] or 0
        return max(0, float(gross) - float(disc) - float(paid))

    @property
    def member_count(self):
        return self.members.filter(is_active=True, is_deleted=False).count()


class CorporateAccountMember(AuditModel):
    """Links a patient to a corporate account (employee / insured member)."""
    corporate_account = models.ForeignKey(
        CorporateAccount, on_delete=models.PROTECT, related_name='members'
    )
    patient     = models.ForeignKey(
        'patients.Patient', on_delete=models.PROTECT, related_name='corporate_memberships'
    )
    employee_id = models.CharField(max_length=50, blank=True, help_text='Employee or membership number')
    coverage_limit = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text='Annual coverage limit per member (0 = use account default)'
    )
    is_active   = models.BooleanField(default=True)

    class Meta:
        unique_together = [('corporate_account', 'patient')]
        verbose_name = 'Corporate Account Member'

    def __str__(self):
        return f"{self.patient.full_name} — {self.corporate_account.name}"


class PettyCashFund(AuditModel):
    """A named petty cash fund held by a custodian (e.g. reception petty cash)."""
    name       = models.CharField(max_length=100)
    custodian  = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='petty_cash_funds'
    )
    opening_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_active  = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Petty Cash Fund'

    def __str__(self):
        return f"{self.name} — {self.custodian.get_full_name() or self.custodian.username}"

    @property
    def current_balance(self):
        from django.db.models import Sum as _S
        credits = self.entries.filter(entry_type='CREDIT', is_deleted=False).aggregate(s=_S('amount'))['s'] or 0
        debits  = self.entries.filter(entry_type='DEBIT',  is_deleted=False).aggregate(s=_S('amount'))['s'] or 0
        return self.opening_balance + credits - debits

    @property
    def total_spent(self):
        from django.db.models import Sum as _S
        return self.entries.filter(entry_type='DEBIT', is_deleted=False).aggregate(s=_S('amount'))['s'] or 0

    @property
    def total_topups(self):
        from django.db.models import Sum as _S
        return self.entries.filter(entry_type='CREDIT', is_deleted=False).aggregate(s=_S('amount'))['s'] or 0


class PettyCashEntry(AuditModel):
    """A single debit (payment/expense) or credit (top-up) on a petty cash fund."""
    ENTRY_TYPES = [('DEBIT', 'Payment / Expense'), ('CREDIT', 'Top-up / Replenishment')]
    fund        = models.ForeignKey(PettyCashFund, on_delete=models.PROTECT, related_name='entries')
    entry_type  = models.CharField(max_length=10, choices=ENTRY_TYPES)
    date        = models.DateField(default=timezone.localdate)
    description = models.CharField(max_length=300)
    amount      = models.DecimalField(max_digits=10, decimal_places=2)
    category    = models.CharField(max_length=20, choices=ExpenseCategory.choices, blank=True)
    reference   = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name = 'Petty Cash Entry'

    def __str__(self):
        return f"{self.entry_type} {self.amount:,.0f} FCFA — {self.description}"


# ═══════════════════════════════════════════════════════════════════════════════
# BUDGET MODULE
# ═══════════════════════════════════════════════════════════════════════════════

class BudgetType(models.TextChoices):
    REVENUE  = 'REVENUE',  'Revenue Target'
    EXPENSE  = 'EXPENSE',  'Expense Budget'


class Budget(AuditModel):
    """
    Monthly budget line — one row per category/department per month.
    Finance Director sets targets; system calculates actual vs budget.
    """
    year            = models.PositiveSmallIntegerField()
    month           = models.PositiveSmallIntegerField(help_text='1–12')
    budget_type     = models.CharField(max_length=10, choices=BudgetType.choices)
    category        = models.CharField(
        max_length=30,
        help_text='ServiceCategory code for revenue budgets; ExpenseCategory code for expense budgets'
    )
    department      = models.CharField(max_length=100, blank=True, help_text='Department name (optional)')
    budgeted_amount = models.DecimalField(max_digits=14, decimal_places=2)
    notes           = models.TextField(blank=True)

    class Meta:
        ordering = ['-year', '-month', 'budget_type', 'category']
        unique_together = [('year', 'month', 'budget_type', 'category', 'department')]
        verbose_name = 'Budget Line'
        verbose_name_plural = 'Budgets'

    def __str__(self):
        import calendar
        return f"{calendar.month_name[self.month]} {self.year} — {self.budget_type} {self.category}: {self.budgeted_amount:,.0f} FCFA"

    @property
    def month_label(self):
        import calendar
        return f"{calendar.month_name[self.month]} {self.year}"


# ═══════════════════════════════════════════════════════════════════════════════
# PROFORMA INVOICE
# Pre-billing estimate given to patient before payment.
# Cashier creates → patient confirms → converts to real Invoice.
# ═══════════════════════════════════════════════════════════════════════════════

class ProformaStatus(models.TextChoices):
    DRAFT     = 'DRAFT',     'Draft'
    ISSUED    = 'ISSUED',    'Issued to Patient'
    CONVERTED = 'CONVERTED', 'Converted to Invoice'
    CANCELLED = 'CANCELLED', 'Cancelled / Expired'


class Proforma(AuditModel):
    """
    Pre-billing quote given to patient before services are rendered.
    Can be converted to a real Invoice once patient confirms.
    """
    proforma_number = models.CharField(max_length=30, unique=True)
    patient = models.ForeignKey(
        'patients.Patient', on_delete=models.PROTECT, related_name='proformas'
    )
    issued_by = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='issued_proformas'
    )
    status = models.CharField(
        max_length=15, choices=ProformaStatus.choices, default=ProformaStatus.DRAFT
    )
    issue_date  = models.DateField(default=timezone.localdate)
    valid_days  = models.PositiveSmallIntegerField(
        default=3, help_text='Days before this proforma expires'
    )
    insurance_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text='Estimated insurer share'
    )
    invoice = models.OneToOneField(
        Invoice, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='proforma',
        help_text='Set when converted to a real invoice'
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Proforma Invoice'
        verbose_name_plural = 'Proforma Invoices'

    def __str__(self):
        return f"Proforma {self.proforma_number} — {self.patient.full_name}"

    def save(self, *args, **kwargs):
        if not self.proforma_number:
            year = timezone.now().year
            count = Proforma.objects.filter(created_at__year=year).count() + 1
            self.proforma_number = f"PRO-{year}-{count:05d}"
        super().save(*args, **kwargs)

    @property
    def subtotal(self):
        return sum(item.line_total for item in self.items.filter(is_deleted=False))

    @property
    def patient_amount(self):
        return max(self.subtotal - self.insurance_amount, 0)

    @property
    def is_expired(self):
        from datetime import timedelta
        return (
            self.status == ProformaStatus.ISSUED
            and timezone.localdate() > self.issue_date + timedelta(days=self.valid_days)
        )


class ProformaItem(AuditModel):
    proforma    = models.ForeignKey(Proforma, on_delete=models.CASCADE, related_name='items')
    category    = models.CharField(max_length=20, choices=ServiceCategory.choices)
    description = models.CharField(max_length=255)
    quantity    = models.PositiveSmallIntegerField(default=1)
    unit_price  = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.description} x{self.quantity}"

    @property
    def line_total(self):
        return self.quantity * self.unit_price


# ─────────────────────────────────────────────────────────────────────────────
# Patient Prepayment Wallet
# ─────────────────────────────────────────────────────────────────────────────

class WalletTransactionType(models.TextChoices):
    DEPOSIT    = 'DEPOSIT',    'Deposit (Top-up)'
    DEDUCTION  = 'DEDUCTION',  'Payment Deducted'
    REFUND     = 'REFUND',     'Refund to Wallet'
    WITHDRAWAL = 'WITHDRAWAL', 'Cash Withdrawal'
    ADJUSTMENT = 'ADJUSTMENT', 'Manual Adjustment'


class PatientWallet(AuditModel):
    """
    Pre-payment account for a patient.
    Patient deposits money; cashier deducts per invoice.
    Balance is always current_balance = sum of DEPOSIT+REFUND - sum of DEDUCTION+WITHDRAWAL.
    """
    patient = models.OneToOneField(
        'patients.Patient', on_delete=models.PROTECT, related_name='wallet'
    )
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes   = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Patient Wallet'

    def __str__(self):
        return f"Wallet — {self.patient.full_name} ({self.balance:,.0f} XAF)"

    def deposit(self, amount, received_by, reference='', notes=''):
        from decimal import Decimal
        amount = Decimal(str(amount))
        self.balance += amount
        self.save(update_fields=['balance', 'updated_at'])
        return WalletTransaction.objects.create(
            wallet=self,
            transaction_type=WalletTransactionType.DEPOSIT,
            amount=amount,
            balance_after=self.balance,
            reference=reference,
            notes=notes,
            processed_by=received_by,
            created_by=received_by,
        )

    def deduct(self, amount, processed_by, invoice=None, notes=''):
        from decimal import Decimal
        amount = Decimal(str(amount))
        if amount > self.balance:
            raise ValueError(f'Insufficient wallet balance ({self.balance:,.0f} XAF)')
        self.balance -= amount
        self.save(update_fields=['balance', 'updated_at'])
        return WalletTransaction.objects.create(
            wallet=self,
            transaction_type=WalletTransactionType.DEDUCTION,
            amount=amount,
            balance_after=self.balance,
            invoice=invoice,
            notes=notes,
            processed_by=processed_by,
            created_by=processed_by,
        )

    def refund(self, amount, processed_by, notes=''):
        from decimal import Decimal
        amount = Decimal(str(amount))
        self.balance += amount
        self.save(update_fields=['balance', 'updated_at'])
        return WalletTransaction.objects.create(
            wallet=self,
            transaction_type=WalletTransactionType.REFUND,
            amount=amount,
            balance_after=self.balance,
            notes=notes,
            processed_by=processed_by,
            created_by=processed_by,
        )


class WalletTransaction(AuditModel):
    wallet           = models.ForeignKey(PatientWallet, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=WalletTransactionType.choices)
    amount           = models.DecimalField(max_digits=12, decimal_places=2)
    balance_after    = models.DecimalField(max_digits=12, decimal_places=2)
    invoice          = models.ForeignKey(
        Invoice, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='wallet_transactions'
    )
    reference  = models.CharField(max_length=100, blank=True)
    notes      = models.TextField(blank=True)
    processed_by = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='wallet_transactions'
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_transaction_type_display()} {self.amount:,.0f} XAF — {self.wallet.patient.full_name}"


# ─────────────────────────────────────────────────────────────────────────────
# Asset Register
# ─────────────────────────────────────────────────────────────────────────────

class AssetCategory(models.TextChoices):
    MEDICAL_EQUIPMENT = 'MEDICAL',    'Medical Equipment'
    IT_EQUIPMENT      = 'IT',         'IT / Computer Equipment'
    FURNITURE         = 'FURNITURE',  'Furniture & Fixtures'
    VEHICLE           = 'VEHICLE',    'Vehicle'
    BUILDING          = 'BUILDING',   'Building / Infrastructure'
    OTHER             = 'OTHER',      'Other'


class AssetStatus(models.TextChoices):
    ACTIVE       = 'ACTIVE',       'Active / In Use'
    MAINTENANCE  = 'MAINTENANCE',  'Under Maintenance'
    DISPOSED     = 'DISPOSED',     'Disposed / Written Off'
    STOLEN       = 'STOLEN',       'Stolen / Lost'


class AssetRegister(AuditModel):
    """
    Hospital equipment and fixed asset tracking with straight-line depreciation.
    """
    asset_number   = models.CharField(max_length=30, unique=True, editable=False)
    name           = models.CharField(max_length=200)
    category       = models.CharField(max_length=20, choices=AssetCategory.choices)
    description    = models.TextField(blank=True)
    serial_number  = models.CharField(max_length=100, blank=True)
    make_model     = models.CharField(max_length=200, blank=True, help_text='Manufacturer and model')
    location       = models.CharField(max_length=100, blank=True, help_text='Ward, room, or department')
    status         = models.CharField(max_length=20, choices=AssetStatus.choices, default=AssetStatus.ACTIVE)

    # Financial
    purchase_date  = models.DateField()
    purchase_cost  = models.DecimalField(max_digits=14, decimal_places=2)
    supplier       = models.CharField(max_length=200, blank=True)
    useful_life_years = models.PositiveSmallIntegerField(default=5,
        help_text='Expected useful life in years for depreciation')
    residual_value = models.DecimalField(max_digits=12, decimal_places=2, default=0,
        help_text='Estimated scrap/salvage value at end of life')

    # Maintenance
    last_service_date = models.DateField(null=True, blank=True)
    next_service_date = models.DateField(null=True, blank=True)
    warranty_expiry   = models.DateField(null=True, blank=True)
    maintenance_notes = models.TextField(blank=True)

    # Recorded by
    recorded_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assets_recorded'
    )

    class Meta:
        ordering = ['category', 'name']
        verbose_name = 'Asset'
        verbose_name_plural = 'Asset Register'

    def __str__(self):
        return f"{self.asset_number} — {self.name}"

    def save(self, *args, **kwargs):
        if not self.asset_number:
            count = AssetRegister.objects.count() + 1
            self.asset_number = f"AST-{count:04d}"
        super().save(*args, **kwargs)

    @property
    def annual_depreciation(self):
        """Straight-line annual depreciation."""
        if self.useful_life_years <= 0:
            return 0
        return (self.purchase_cost - self.residual_value) / self.useful_life_years

    @property
    def accumulated_depreciation(self):
        """Total depreciation to date."""
        from django.utils import timezone
        years = (timezone.localdate() - self.purchase_date).days / 365.25
        years = min(years, self.useful_life_years)
        return round(self.annual_depreciation * years, 2)

    @property
    def net_book_value(self):
        """Current book value after depreciation."""
        nbv = self.purchase_cost - self.accumulated_depreciation
        return max(nbv, self.residual_value)

    @property
    def is_fully_depreciated(self):
        return self.net_book_value <= self.residual_value


# ═══════════════════════════════════════════════════════════════════════════════
# GENERAL LEDGER  —  Chart of Accounts, Journal Entries, Double-Entry Posting
# OHADA/SYSCOHADA account structure for Cameroon
# ═══════════════════════════════════════════════════════════════════════════════

class AccountType(models.TextChoices):
    ASSET     = 'ASSET',     'Asset'
    LIABILITY = 'LIABILITY', 'Liability'
    EQUITY    = 'EQUITY',    'Equity'
    REVENUE   = 'REVENUE',   'Revenue'
    EXPENSE   = 'EXPENSE',   'Expense'


class GLAccount(AuditModel):
    """
    Chart of Accounts — one row per GL account.
    OHADA account codes: 1-5 = Balance Sheet, 6 = Expenses, 7 = Revenue.
    """
    code        = models.CharField(max_length=10, unique=True, db_index=True,
                    help_text='OHADA account code e.g. 572000')
    name        = models.CharField(max_length=200)
    account_type = models.CharField(max_length=15, choices=AccountType.choices)
    parent      = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='children', help_text='Parent account for sub-account grouping'
    )
    description = models.TextField(blank=True)
    is_active   = models.BooleanField(default=True)
    is_summary  = models.BooleanField(
        default=False,
        help_text='Summary/parent account — aggregates children, never receives journal lines directly'
    )
    allow_manual_posting = models.BooleanField(
        default=True, help_text='Allow manual journal entries to post to this account'
    )

    class Meta:
        ordering = ['code']
        verbose_name = 'GL Account'
        verbose_name_plural = 'Chart of Accounts'

    def __str__(self):
        return f"{self.code} — {self.name}"

    @property
    def balance(self):
        """Running balance: sum of debits minus credits (for assets/expenses) or reverse."""
        from django.db.models import Sum as _S
        lines = self.journal_lines.filter(entry__is_deleted=False)
        debits  = lines.aggregate(t=_S('debit_amount'))['t']  or 0
        credits = lines.aggregate(t=_S('credit_amount'))['t'] or 0
        if self.account_type in (AccountType.ASSET, AccountType.EXPENSE):
            return debits - credits
        else:  # LIABILITY, EQUITY, REVENUE
            return credits - debits


class CostCenter(AuditModel):
    """
    Cost Center — department or project for cost allocation.
    Every journal entry can be tagged with a cost center for
    departmental P&L, budget tracking, and management reporting.
    """
    code   = models.CharField(max_length=20, unique=True, help_text='e.g. CC-OPD, CC-SURG, CC-ADMIN')
    name   = models.CharField(max_length=200)
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True,
                               related_name='children')
    manager = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='managed_cost_centers')
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f"{self.code} — {self.name}"


class JournalType(AuditModel):
    """
    OHADA Journal Type — categorises every journal entry for audit & reporting.
    Standard types: AC (Achats), VE (Ventes), CA (Caisse), BQ (Banque),
    ST (Stocks), SA (Salaires), OD (Opérations Diverses), AN (À-Nouveau).
    Finance Director can create custom types.
    """
    code = models.CharField(max_length=10, unique=True, help_text='e.g. AC, VE, CA, BQ, ST')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f"{self.code} — {self.name}"


class StockOperationCategory(models.TextChoices):
    ENTRY = 'ENTRY', 'Stock Entry'
    EXIT  = 'EXIT',  'Stock Exit'


class StockOperationType(AuditModel):
    """
    Types of stock entry/exit — each linked to specific GL accounts for auto-posting.
    e.g. EN-ACH (Purchase) → Dr 31x / Cr 6031
         EX-CON (Consumption) → Dr 6031 / Cr 31x
         EX-DIS (Disposal) → Dr 6591 / Cr 31x
    """
    code = models.CharField(max_length=10, unique=True, help_text='e.g. EN-ACH, EX-CON, EX-DIS')
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=5, choices=StockOperationCategory.choices)
    debit_account = models.ForeignKey(
        GLAccount, on_delete=models.PROTECT, related_name='op_type_debits',
        help_text='GL account to DEBIT for this operation type',
    )
    credit_account = models.ForeignKey(
        GLAccount, on_delete=models.PROTECT, related_name='op_type_credits',
        help_text='GL account to CREDIT for this operation type',
    )
    description = models.TextField(blank=True, help_text='OHADA accounting rule explanation')
    location_types = models.CharField(
        max_length=200, blank=True, default='',
        help_text=(
            'Comma-separated StoreLocation.location_type codes this op type applies to. '
            'Leave blank = applies to ALL stores. '
            'e.g. "GENERAL,PHARMACY" or "PHARMACY" or "OPTICAL,SHOWROOM"'
        ),
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['category', 'code']

    def __str__(self):
        return f"{self.code} — {self.name}"

    def applies_to_store_type(self, store_type):
        """Return True if this op type is available for the given store location_type."""
        if not self.location_types:
            return True  # blank = all stores
        return store_type in [t.strip() for t in self.location_types.split(',') if t.strip()]


class JournalEntryStatus(models.TextChoices):
    DRAFT     = 'DRAFT',     'Draft — Recorded by Accountant'
    REVIEWED  = 'REVIEWED',  'Reviewed by Senior Accountant'
    POSTED    = 'POSTED',    'Posted by Finance Director'
    REJECTED  = 'REJECTED',  'Rejected'


class JournalEntry(AuditModel):
    """
    A double-entry journal entry header.
    Each entry has 2+ lines; total debits must equal total credits.

    3-Tier Approval Workflow (manual entries):
      1. Accountant RECORDS (status=DRAFT, is_posted=False)
      2. Senior Accountant REVIEWS (status=REVIEWED)
      3. Finance Director POSTS (status=POSTED, is_posted=True)

    Auto-generated entries (from payments, stock, etc.) are posted immediately.
    """
    entry_number = models.CharField(max_length=20, unique=True, editable=False)
    entry_date   = models.DateField(default=timezone.localdate)
    reference    = models.CharField(max_length=100, blank=True,
                    help_text='Source reference: receipt number, expense ID, payroll batch')
    description  = models.CharField(max_length=500)
    is_posted    = models.BooleanField(default=True,
                    help_text='Posted entries are locked and affect account balances')
    is_reversal  = models.BooleanField(default=False)
    reversed_entry = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reversals'
    )
    # Journal Type (OHADA classification)
    journal_type = models.ForeignKey(JournalType, on_delete=models.SET_NULL, null=True, blank=True,
                    related_name='entries', help_text='OHADA journal type: AC, VE, CA, BQ, ST, SA, OD, AN')
    # Source tracking — which model generated this entry
    source_type  = models.CharField(max_length=30, blank=True,
                    help_text='payment | expense | payroll | petty_cash | manual')
    source_id    = models.CharField(max_length=50, blank=True,
                    help_text='UUID/ID of the source record')
    # Cost Center
    cost_center  = models.ForeignKey(CostCenter, on_delete=models.SET_NULL, null=True, blank=True,
                    related_name='journal_entries',
                    help_text='Cost center for departmental cost allocation')
    # 3-Tier Approval Workflow
    status       = models.CharField(max_length=10, choices=JournalEntryStatus.choices,
                    default=JournalEntryStatus.POSTED,
                    help_text='Approval status — auto entries are POSTED, manual entries start as DRAFT')
    recorded_by  = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
                    related_name='journal_entries_recorded',
                    help_text='Accountant who recorded this entry')
    reviewed_by  = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
                    related_name='journal_entries_reviewed',
                    help_text='Senior Accountant who reviewed this entry')
    reviewed_at  = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)
    posted_by    = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
                    related_name='journal_entries_posted',
                    help_text='Finance Director who approved and posted this entry')
    posted_at    = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    class Meta:
        ordering = ['-entry_date', '-created_at']
        verbose_name = 'Journal Entry'
        verbose_name_plural = 'Journal Entries'

    def __str__(self):
        return f"{self.entry_number} — {self.description}"

    def save(self, *args, **kwargs):
        if not self.entry_number:
            from django.db import transaction as _tx
            year = timezone.now().year
            for attempt in range(20):
                count = JournalEntry.objects.filter(created_at__year=year).count() + 1 + attempt
                candidate = f"JNL-{year}-{count:05d}"
                try:
                    with _tx.atomic():
                        self.entry_number = candidate
                        super().save(*args, **kwargs)
                    return
                except Exception:
                    self.entry_number = ''
                    continue
            raise RuntimeError('Unable to generate unique entry_number after 20 attempts')
        super().save(*args, **kwargs)

    @property
    def total_debits(self):
        from django.db.models import Sum as _S
        return self.lines.aggregate(t=_S('debit_amount'))['t'] or 0

    @property
    def total_credits(self):
        from django.db.models import Sum as _S
        return self.lines.aggregate(t=_S('credit_amount'))['t'] or 0

    @property
    def is_balanced(self):
        return abs(self.total_debits - self.total_credits) < 0.01


class JournalLine(models.Model):
    """A single debit or credit line within a journal entry."""
    entry         = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name='lines')
    account       = models.ForeignKey(GLAccount, on_delete=models.PROTECT, related_name='journal_lines')
    description   = models.CharField(max_length=300, blank=True)
    debit_amount  = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    credit_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    sequence      = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ['sequence', 'id']

    def __str__(self):
        if self.debit_amount:
            return f"Dr {self.account.code} {self.debit_amount:,.0f}"
        return f"Cr {self.account.code} {self.credit_amount:,.0f}"


# ═══════════════════════════════════════════════════════════════════════════════
# ACCOUNTS PAYABLE  —  Vendor Bills & Payments
# ═══════════════════════════════════════════════════════════════════════════════

class APVendor(AuditModel):
    """A supplier or service provider the hospital owes money to."""
    name         = models.CharField(max_length=200, unique=True)
    vendor_code  = models.CharField(max_length=20, unique=True, blank=True)
    contact_name = models.CharField(max_length=150, blank=True)
    phone        = models.CharField(max_length=20, blank=True)
    email        = models.EmailField(blank=True)
    address      = models.TextField(blank=True)
    tax_id       = models.CharField(max_length=50, blank=True, help_text='NIU / Tax ID number')
    payment_terms_days = models.PositiveSmallIntegerField(default=30)
    bank_name    = models.CharField(max_length=100, blank=True)
    bank_account = models.CharField(max_length=50, blank=True)
    is_active    = models.BooleanField(default=True)
    notes        = models.TextField(blank=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Vendor'
        verbose_name_plural = 'AP Vendors'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.vendor_code:
            count = APVendor.objects.count() + 1
            self.vendor_code = f"VEN-{count:04d}"
        super().save(*args, **kwargs)

    @property
    def outstanding_balance(self):
        from django.db.models import Sum as _S
        total = self.bills.filter(is_deleted=False).exclude(
            status=APBillStatus.PAID
        ).aggregate(t=_S('amount_due'))['t'] or 0
        paid = APPayment.objects.filter(
            bill__vendor=self, is_deleted=False
        ).aggregate(p=_S('amount'))['p'] or 0
        return max(0, float(total) - float(paid))


class APBillStatus(models.TextChoices):
    DRAFT   = 'DRAFT',   'Draft'
    PENDING = 'PENDING', 'Awaiting Payment'
    PARTIAL = 'PARTIAL', 'Partially Paid'
    PAID    = 'PAID',    'Fully Paid'
    OVERDUE = 'OVERDUE', 'Overdue'
    VOID    = 'VOID',    'Void / Cancelled'


class APBill(AuditModel):
    """A vendor bill / supplier invoice — money the hospital OWES."""
    bill_number  = models.CharField(max_length=30, unique=True, editable=False)
    vendor       = models.ForeignKey(APVendor, on_delete=models.PROTECT, related_name='bills')
    vendor_ref   = models.CharField(max_length=100, blank=True,
                    help_text='Vendor invoice number / reference')
    category     = models.CharField(max_length=20, choices=ExpenseCategory.choices)
    description  = models.CharField(max_length=500)
    amount_due   = models.DecimalField(max_digits=14, decimal_places=2)
    tax_amount   = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    bill_date    = models.DateField(default=timezone.localdate)
    due_date     = models.DateField(null=True, blank=True)
    status       = models.CharField(max_length=10, choices=APBillStatus.choices,
                    default=APBillStatus.PENDING)
    gl_account   = models.ForeignKey(
        GLAccount, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ap_bills', help_text='Expense GL account to debit'
    )
    attachment_ref = models.CharField(max_length=200, blank=True,
                      help_text='Physical receipt / invoice filing reference')
    approved_by  = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='approved_bills'
    )
    notes        = models.TextField(blank=True)

    class Meta:
        ordering = ['-bill_date', '-created_at']
        verbose_name = 'AP Bill'
        verbose_name_plural = 'AP Bills (Payables)'

    def __str__(self):
        return f"{self.bill_number} — {self.vendor.name} ({self.amount_due:,.0f} XAF)"

    def save(self, *args, **kwargs):
        if not self.bill_number:
            year = timezone.now().year
            count = APBill.objects.filter(created_at__year=year).count() + 1
            self.bill_number = f"APB-{year}-{count:05d}"
        super().save(*args, **kwargs)

    @property
    def total_paid(self):
        from django.db.models import Sum as _S
        return self.payments.filter(is_deleted=False).aggregate(t=_S('amount'))['t'] or 0

    @property
    def balance_due(self):
        return self.amount_due - self.total_paid

    def update_status(self):
        paid = self.total_paid
        if paid <= 0:
            status = APBillStatus.PENDING
        elif paid >= self.amount_due:
            status = APBillStatus.PAID
        else:
            status = APBillStatus.PARTIAL
        if self.status not in (APBillStatus.VOID,):
            self.status = status
            self.save(update_fields=['status', 'updated_at'])


class APPayment(AuditModel):
    """Payment made to a vendor against a bill."""
    bill           = models.ForeignKey(APBill, on_delete=models.PROTECT, related_name='payments')
    payment_date   = models.DateField(default=timezone.localdate)
    amount         = models.DecimalField(max_digits=14, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices,
                      default=PaymentMethod.TRANSFER)
    reference      = models.CharField(max_length=100, blank=True,
                      help_text='Bank transfer ref / cheque number')
    paid_by        = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='ap_payments_made'
    )
    notes          = models.TextField(blank=True)

    class Meta:
        ordering = ['-payment_date']
        verbose_name = 'AP Payment'

    def __str__(self):
        return f"{self.amount:,.0f} XAF to {self.bill.vendor.name} ({self.payment_date})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.bill.update_status()


# ═══════════════════════════════════════════════════════════════════════════════
# ADVANCED TIER-SCOPED CASHIER DESK MODULE
# CashDesk → CashierSession → per-desk receipt sequences
# Supervisor discount approvals, invoice tier-change audit log
# ═══════════════════════════════════════════════════════════════════════════════

class CashDesk(AuditModel):
    """
    A physical or logical cashier desk.
    desk_type=TIER  → bound to a specific patient service tier (STANDARD/EXPRESS/VIP).
    desk_type=PHARMACY/OPTICAL/INSURANCE → shared service desks independent of patient tier.
    """
    name           = models.CharField(max_length=100)
    desk_type      = models.CharField(
        max_length=20, choices=DeskType.choices, default=DeskType.TIER
    )
    tier           = models.CharField(
        max_length=20, blank=True, default='',
        help_text='Required when desk_type=TIER. Values: STANDARD, EXPRESS, VIP'
    )
    location       = models.CharField(max_length=200, blank=True,
                      help_text='Physical location / room number')
    receipt_prefix = models.CharField(
        max_length=10, default='RCT',
        help_text='Receipt number prefix e.g. VIP, STD, PHM, OPT'
    )
    is_active      = models.BooleanField(default=True)

    class Meta:
        ordering  = ['desk_type', 'name']
        verbose_name        = 'Cash Desk'
        verbose_name_plural = 'Cash Desks'

    def __str__(self):
        if self.desk_type == DeskType.TIER and self.tier:
            return f"{self.name} [{self.tier}]"
        return f"{self.name} [{self.get_desk_type_display()}]"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.desk_type == DeskType.TIER and not self.tier:
            raise ValidationError({'tier': 'Tier desk requires a tier value (STANDARD/EXPRESS/VIP).'})

    @property
    def active_session(self):
        """Return the currently open session for this desk, or None."""
        return self.sessions.filter(status=SessionStatus.OPEN, is_deleted=False).first()


class DeskReceiptSequence(models.Model):
    """
    Per-desk, per-day receipt counter.
    Generates desk-scoped receipt numbers like VIP-2026-000123.
    Uses SELECT FOR UPDATE to prevent duplicate numbers under concurrent load.
    """
    desk          = models.ForeignKey(
        CashDesk, on_delete=models.CASCADE, related_name='receipt_sequences'
    )
    sequence_date = models.DateField(default=timezone.localdate)
    last_number   = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = [('desk', 'sequence_date')]
        verbose_name = 'Desk Receipt Sequence'

    def __str__(self):
        return f"{self.desk.receipt_prefix} — {self.sequence_date} — #{self.last_number}"

    @classmethod
    def next_number(cls, desk):
        """
        Atomically increment and return the next receipt number for a desk.
        Returns a full receipt string like  VIP-2026-000042.
        """
        from django.db import transaction as _tx
        today = timezone.localdate()
        with _tx.atomic():
            seq, _ = cls.objects.select_for_update().get_or_create(
                desk=desk, sequence_date=today,
                defaults={'last_number': 0},
            )
            seq.last_number += 1
            seq.save(update_fields=['last_number'])
            return f"{desk.receipt_prefix}-{today.year}-{seq.last_number:06d}"


class CashierSession(AuditModel):
    """
    One open session per cashier per desk per day.
    Replaces the blunt daily CashierShift when desks are enabled.
    Lifecycle: OPEN → CLOSED → VERIFIED
    Z-report is computed from payments linked to this session.
    """
    cashier   = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='cashier_sessions'
    )
    cash_desk = models.ForeignKey(
        CashDesk, on_delete=models.PROTECT, related_name='sessions'
    )
    opened_at = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(null=True, blank=True)
    opening_float = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text='Cash float handed to cashier at session start (XAF)'
    )
    closing_declared_cash = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text='Physical cash counted by cashier at close'
    )
    status       = models.CharField(
        max_length=20, choices=SessionStatus.choices, default=SessionStatus.OPEN
    )
    variance_flag  = models.BooleanField(default=False)
    variance_notes = models.CharField(max_length=300, blank=True)
    verified_by    = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='verified_cashier_sessions'
    )
    verified_at    = models.DateTimeField(null=True, blank=True)
    notes          = models.TextField(blank=True)

    class Meta:
        ordering = ['-opened_at']
        verbose_name        = 'Cashier Session'
        verbose_name_plural = 'Cashier Sessions'

    def __str__(self):
        name = self.cashier.get_full_name() or self.cashier.username
        return f"Session — {name} @ {self.cash_desk.name} ({self.opened_at.date()})"

    # ── Z-report aggregates ────────────────────────────────────────────────────

    @property
    def cash_collected(self):
        from django.db.models import Sum as _S
        return (
            self.payments.filter(payment_method=PaymentMethod.CASH, is_deleted=False)
            .aggregate(t=_S('amount'))['t'] or 0
        )

    @property
    def mobile_collected(self):
        from django.db.models import Sum as _S
        return (
            self.payments.filter(payment_method=PaymentMethod.MOBILE_MONEY, is_deleted=False)
            .aggregate(t=_S('amount'))['t'] or 0
        )

    @property
    def card_collected(self):
        from django.db.models import Sum as _S
        return (
            self.payments.filter(payment_method=PaymentMethod.CARD, is_deleted=False)
            .aggregate(t=_S('amount'))['t'] or 0
        )

    @property
    def total_collected(self):
        from django.db.models import Sum as _S
        return (
            self.payments.filter(is_deleted=False)
            .aggregate(t=_S('amount'))['t'] or 0
        )

    @property
    def expected_cash_in_hand(self):
        """Opening float + all cash payments during session."""
        return self.opening_float + self.cash_collected

    @property
    def cash_variance(self):
        """Positive = overage (cashier has more). Negative = shortage."""
        if self.closing_declared_cash is None:
            return None
        return self.closing_declared_cash - self.expected_cash_in_hand

    @property
    def transaction_count(self):
        return self.payments.filter(is_deleted=False).count()

    @property
    def collections_by_method(self):
        from django.db.models import Sum as _S
        return (
            self.payments.filter(is_deleted=False)
            .values('payment_method')
            .annotate(total=_S('amount'))
            .order_by('payment_method')
        )


class DiscountApproval(AuditModel):
    """
    Supervisor sign-off required when a cashier requests a discount above threshold.
    Cashier submits request → Chief Cashier / Finance approves / rejects.
    Invoice discount is only applied after approval.
    """
    invoice          = models.ForeignKey(
        Invoice, on_delete=models.PROTECT, related_name='discount_approvals'
    )
    requested_by     = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='discount_requests'
    )
    approved_by      = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='approved_discounts'
    )
    discount_type    = models.CharField(
        max_length=20, choices=DiscountType.choices, default=DiscountType.AMOUNT,
        help_text='Percentage (%) or Fixed Amount (FCFA)'
    )
    requested_amount = models.DecimalField(max_digits=10, decimal_places=2,
        help_text='FCFA amount if AMOUNT type; computed FCFA value if PERCENTAGE type')
    requested_pct    = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True,
        help_text='Percentage entered by cashier (only set when discount_type=PERCENTAGE)')
    approved_amount  = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text='May differ from requested if supervisor partially approves'
    )
    reason           = models.CharField(max_length=300)
    status           = models.CharField(
        max_length=20, choices=DiscountApprovalStatus.choices,
        default=DiscountApprovalStatus.PENDING
    )
    decision_at      = models.DateTimeField(null=True, blank=True)
    decision_notes   = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name        = 'Discount Approval'
        verbose_name_plural = 'Discount Approvals'

    def __str__(self):
        return (
            f"Discount {self.requested_amount:,.0f} XAF on "
            f"{self.invoice.invoice_number} [{self.status}]"
        )


class InvoiceTierChange(AuditModel):
    """
    Audit log entry created whenever an invoice is re-routed to a different
    tier desk mid-visit (e.g. patient upgrades from Standard → VIP after registration).
    Immutable record — never deleted or edited.
    """
    invoice    = models.ForeignKey(
        Invoice, on_delete=models.PROTECT, related_name='tier_changes'
    )
    old_tier   = models.CharField(max_length=20)
    new_tier   = models.CharField(max_length=20)
    old_desk   = models.ForeignKey(
        CashDesk, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='outgoing_tier_changes'
    )
    new_desk   = models.ForeignKey(
        CashDesk, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='incoming_tier_changes'
    )
    changed_by = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='invoice_tier_changes'
    )
    reason     = models.CharField(max_length=300)

    class Meta:
        ordering = ['-created_at']
        verbose_name        = 'Invoice Tier Change'
        verbose_name_plural = 'Invoice Tier Changes'

    def __str__(self):
        return (
            f"{self.invoice.invoice_number}: "
            f"{self.old_tier} → {self.new_tier} by {self.changed_by.username}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# BANK OPERATIONS  —  Bank Accounts, Statements, Reconciliation, Cash-to-Bank
# ═══════════════════════════════════════════════════════════════════════════════

class BankAccount(AuditModel):
    """Bank account linked to OHADA GL account (class 521)."""
    account_name   = models.CharField(max_length=200)
    bank_name      = models.CharField(max_length=200)
    account_number = models.CharField(max_length=50, unique=True)
    branch         = models.CharField(max_length=200, blank=True)
    swift_code     = models.CharField(max_length=20, blank=True)
    currency       = models.CharField(max_length=5, default='XAF')
    gl_account     = models.ForeignKey(
        GLAccount, on_delete=models.PROTECT, null=True, blank=True,
        related_name='bank_accounts',
        help_text='Maps to GL class 521xxx'
    )
    opening_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    is_active       = models.BooleanField(default=True)
    notes           = models.TextField(blank=True)

    class Meta:
        ordering = ['bank_name', 'account_name']
        verbose_name = 'Bank Account'
        verbose_name_plural = 'Bank Accounts'

    def __str__(self):
        return f"{self.bank_name} — {self.account_number}"


class BankStatement(AuditModel):
    """Imported bank statement line for reconciliation."""
    bank_account   = models.ForeignKey(
        BankAccount, on_delete=models.CASCADE, related_name='statements'
    )
    statement_date = models.DateField()
    reference      = models.CharField(max_length=100, blank=True)
    description    = models.CharField(max_length=300)
    debit_amount   = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    credit_amount  = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    balance        = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    value_date     = models.DateField(null=True, blank=True)
    is_reconciled  = models.BooleanField(default=False)
    reconciled_with = models.ForeignKey(
        JournalEntry, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reconciled_statements'
    )
    imported_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-statement_date', '-imported_at']
        verbose_name = 'Bank Statement Line'
        verbose_name_plural = 'Bank Statement Lines'

    def __str__(self):
        return f"{self.bank_account} {self.statement_date} — {self.description[:50]}"


class BankReconciliationStatus(models.TextChoices):
    DRAFT     = 'DRAFT',     'Draft'
    COMPLETED = 'COMPLETED', 'Completed'
    REVIEWED  = 'REVIEWED',  'Reviewed by Finance Manager'


class ReconciliationItemType(models.TextChoices):
    OUTSTANDING_CHEQUE = 'OUT_CHQ',    'Outstanding Cheque'
    DEPOSIT_IN_TRANSIT = 'DEP_TRANSIT', 'Deposit in Transit'
    BANK_CHARGE        = 'BANK_CHG',   'Bank Charge'
    INTEREST_EARNED    = 'INTEREST',   'Interest Earned'
    ERROR_CORRECTION   = 'ERROR',      'Error Correction'
    OTHER              = 'OTHER',      'Other'


class BankReconciliation(AuditModel):
    """Monthly bank reconciliation per MICEI finance policy."""
    bank_account         = models.ForeignKey(
        BankAccount, on_delete=models.PROTECT, related_name='reconciliations'
    )
    period_start         = models.DateField()
    period_end           = models.DateField()
    bank_statement_balance = models.DecimalField(max_digits=14, decimal_places=2)
    book_balance           = models.DecimalField(max_digits=14, decimal_places=2)
    adjusted_bank_balance  = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    adjusted_book_balance  = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=BankReconciliationStatus.choices,
        default=BankReconciliationStatus.DRAFT
    )
    prepared_by = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='reconciliations_prepared'
    )
    reviewed_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reconciliations_reviewed'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    notes       = models.TextField(blank=True)

    class Meta:
        ordering = ['-period_end']
        unique_together = [('bank_account', 'period_end')]
        verbose_name = 'Bank Reconciliation'
        verbose_name_plural = 'Bank Reconciliations'

    def __str__(self):
        return f"Recon {self.bank_account} — {self.period_end:%b %Y}"


class BankReconciliationItem(TimeStampedModel):
    """Individual reconciling item within a bank reconciliation."""
    reconciliation = models.ForeignKey(
        BankReconciliation, on_delete=models.CASCADE, related_name='items'
    )
    item_type   = models.CharField(max_length=20, choices=ReconciliationItemType.choices)
    date        = models.DateField()
    reference   = models.CharField(max_length=100, blank=True)
    description = models.CharField(max_length=300)
    amount      = models.DecimalField(max_digits=14, decimal_places=2)
    side        = models.CharField(max_length=10, choices=[
        ('BANK', 'Bank Adjustment'),
        ('BOOK', 'Book Adjustment'),
    ])

    class Meta:
        ordering = ['date']

    def __str__(self):
        return f"{self.get_item_type_display()} — {self.amount:,.0f} XAF"


class CashToBankStatus(models.TextChoices):
    PENDING   = 'PENDING',   'Pending Deposit'
    DEPOSITED = 'DEPOSITED', 'Deposited at Bank'
    CONFIRMED = 'CONFIRMED', 'Confirmed by Accountant'


class CashToBank(AuditModel):
    """Records physical cash deposit from safe to bank account."""
    bank_account  = models.ForeignKey(
        BankAccount, on_delete=models.PROTECT, related_name='cash_deposits'
    )
    deposit_date  = models.DateField()
    amount        = models.DecimalField(max_digits=14, decimal_places=2)
    reference     = models.CharField(max_length=100, blank=True, help_text='Deposit slip number')
    status = models.CharField(
        max_length=20, choices=CashToBankStatus.choices,
        default=CashToBankStatus.PENDING
    )
    prepared_by  = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='bank_deposits_prepared'
    )
    confirmed_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='bank_deposits_confirmed'
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    journal_entry = models.ForeignKey(
        JournalEntry, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cash_to_bank_records'
    )
    notes        = models.TextField(blank=True)

    class Meta:
        ordering = ['-deposit_date']
        verbose_name = 'Cash-to-Bank Deposit'
        verbose_name_plural = 'Cash-to-Bank Deposits'

    def __str__(self):
        return f"Deposit {self.amount:,.0f} XAF → {self.bank_account} ({self.deposit_date})"


# ═══════════════════════════════════════════════════════════════════════════════
# CHEQUE MANAGEMENT  —  Cheque Books, Issuance Register
# ═══════════════════════════════════════════════════════════════════════════════

class ChequeBook(AuditModel):
    """Tracks cheque booklets per bank account."""
    bank_account   = models.ForeignKey(
        BankAccount, on_delete=models.PROTECT, related_name='chequebooks'
    )
    series_prefix  = models.CharField(max_length=20, blank=True)
    start_number   = models.PositiveIntegerField()
    end_number     = models.PositiveIntegerField()
    current_number = models.PositiveIntegerField(help_text='Next available cheque number')
    received_date  = models.DateField()
    is_exhausted   = models.BooleanField(default=False)
    notes          = models.TextField(blank=True)

    class Meta:
        ordering = ['-received_date']
        verbose_name = 'Cheque Book'
        verbose_name_plural = 'Cheque Books'

    def __str__(self):
        return f"{self.bank_account.bank_name} #{self.start_number}-{self.end_number}"

    @property
    def total_cheques(self):
        return self.end_number - self.start_number + 1

    @property
    def used_cheques(self):
        return self.cheques.exclude(status=ChequeStatus.VOIDED).count()

    @property
    def remaining_cheques(self):
        return self.total_cheques - self.used_cheques


class ChequeStatus(models.TextChoices):
    ISSUED  = 'ISSUED',  'Issued'
    CLEARED = 'CLEARED', 'Cleared'
    BOUNCED = 'BOUNCED', 'Bounced / Returned'
    VOIDED  = 'VOIDED',  'Voided / Cancelled'
    STALE   = 'STALE',   'Stale (Expired)'


class ChequeRegister(AuditModel):
    """Individual cheque issuance and tracking."""
    cheque_book    = models.ForeignKey(
        ChequeBook, on_delete=models.PROTECT, related_name='cheques'
    )
    cheque_number  = models.CharField(max_length=30)
    bank_account   = models.ForeignKey(
        BankAccount, on_delete=models.PROTECT, related_name='cheques_issued'
    )
    payee          = models.CharField(max_length=200)
    amount         = models.DecimalField(max_digits=14, decimal_places=2)
    issue_date     = models.DateField()
    cleared_date   = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=ChequeStatus.choices,
        default=ChequeStatus.ISSUED
    )
    ap_payment     = models.ForeignKey(
        APPayment, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cheques'
    )
    reason         = models.CharField(max_length=300, blank=True)
    issued_by      = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='cheques_issued_by'
    )
    voided_by      = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cheques_voided'
    )
    voided_at      = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-issue_date', '-cheque_number']
        unique_together = [('cheque_book', 'cheque_number')]
        verbose_name = 'Cheque'
        verbose_name_plural = 'Cheque Register'

    def __str__(self):
        return f"Cheque #{self.cheque_number} — {self.payee} ({self.amount:,.0f} XAF)"


# ═══════════════════════════════════════════════════════════════════════════════
# STAFF ADVANCES  —  Salary & Business Advances per AEF Finance Policy
# ═══════════════════════════════════════════════════════════════════════════════

class AdvanceType(models.TextChoices):
    SALARY   = 'SALARY',   'Salary Advance'
    BUSINESS = 'BUSINESS', 'Business Advance'


class AdvanceStatus(models.TextChoices):
    REQUESTED  = 'REQUESTED',  'Requested'
    APPROVED   = 'APPROVED',   'Approved'
    DISBURSED  = 'DISBURSED',  'Disbursed'
    SETTLED    = 'SETTLED',    'Settled'
    REJECTED   = 'REJECTED',   'Rejected'


class StaffAdvance(AuditModel):
    """
    Staff salary/business advance tracking.
    Business advances: max 1 outstanding per staff, settle within 5 working days.
    """
    staff = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='advances'
    )
    advance_type = models.CharField(max_length=20, choices=AdvanceType.choices)
    amount_requested = models.DecimalField(max_digits=12, decimal_places=2)
    amount_approved  = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    purpose          = models.TextField()
    status = models.CharField(
        max_length=20, choices=AdvanceStatus.choices,
        default=AdvanceStatus.REQUESTED
    )
    requested_date   = models.DateField(default=timezone.localdate)
    approved_by      = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='approved_advances'
    )
    approved_at      = models.DateTimeField(null=True, blank=True)
    disbursed_date   = models.DateField(null=True, blank=True)
    settlement_due   = models.DateField(null=True, blank=True,
        help_text='Auto-set: disbursed_date + 5 working days for business advances')
    settled_date     = models.DateField(null=True, blank=True)
    payment_method   = models.CharField(
        max_length=20, choices=PaymentMethod.choices, blank=True
    )
    reference        = models.CharField(max_length=100, blank=True)
    notes            = models.TextField(blank=True)

    class Meta:
        ordering = ['-requested_date']
        verbose_name = 'Staff Advance'
        verbose_name_plural = 'Staff Advances'

    def __str__(self):
        return f"{self.get_advance_type_display()} — {self.staff.get_full_name()} ({self.amount_requested:,.0f} XAF)"

    @property
    def is_overdue(self):
        if self.settlement_due and self.status == AdvanceStatus.DISBURSED:
            return timezone.localdate() > self.settlement_due
        return False

    @property
    def amount_outstanding(self):
        amt = self.amount_approved or self.amount_requested
        if self.status == AdvanceStatus.SETTLED:
            return 0
        return amt


# ═══════════════════════════════════════════════════════════════════════════════
# CASH TRANSFER & SAFE MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

class TransferType(models.TextChoices):
    DESK_TO_TELLER = 'DESK_TELLER', 'Cash Desk → Head Teller'
    DESK_TO_SAFE   = 'DESK_SAFE',   'Cash Desk → Safe'
    SAFE_TO_BANK   = 'SAFE_BANK',   'Safe → Bank'
    DESK_TO_DESK   = 'DESK_DESK',   'Desk → Desk'
    FLOAT_ISSUE    = 'FLOAT',       'Float Issued to Desk'


class TransferStatus(models.TextChoices):
    PENDING   = 'PENDING',   'Pending Confirmation'
    CONFIRMED = 'CONFIRMED', 'Confirmed'
    REJECTED  = 'REJECTED',  'Rejected'


class CashTransfer(AuditModel):
    """
    Physical cash movement between desks, to safe, or to bank.
    Main cashier collects cash from cashiers per AEF daily close procedure.
    """
    transfer_type = models.CharField(max_length=20, choices=TransferType.choices)
    from_desk     = models.ForeignKey(
        CashDesk, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='transfers_out'
    )
    to_desk       = models.ForeignKey(
        CashDesk, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='transfers_in'
    )
    amount        = models.DecimalField(max_digits=14, decimal_places=2)
    transfer_date = models.DateTimeField(default=timezone.now)
    initiated_by  = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='cash_transfers_initiated'
    )
    confirmed_by  = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cash_transfers_confirmed'
    )
    confirmed_at  = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=TransferStatus.choices,
        default=TransferStatus.PENDING
    )
    reference     = models.CharField(max_length=100, blank=True)
    notes         = models.TextField(blank=True)

    class Meta:
        ordering = ['-transfer_date']
        verbose_name = 'Cash Transfer'
        verbose_name_plural = 'Cash Transfers'

    def __str__(self):
        return f"{self.get_transfer_type_display()} — {self.amount:,.0f} XAF"


class SafeBalance(AuditModel):
    """
    Daily safe balance snapshot.
    Policy: max 5,000,000 FCFA in safe at any time; deposit to bank 3x/week.
    """
    SAFE_MAX_BALANCE = 5_000_000

    date             = models.DateField(unique=True)
    opening_balance  = models.DecimalField(max_digits=14, decimal_places=2)
    total_deposits   = models.DecimalField(max_digits=14, decimal_places=2, default=0,
        help_text='Cash received from desks')
    total_withdrawals = models.DecimalField(max_digits=14, decimal_places=2, default=0,
        help_text='Sent to bank or floats issued')
    closing_balance  = models.DecimalField(max_digits=14, decimal_places=2)
    counted_by       = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='safe_counts'
    )
    notes            = models.TextField(blank=True)

    class Meta:
        ordering = ['-date']
        verbose_name = 'Safe Balance'
        verbose_name_plural = 'Safe Balances'

    def __str__(self):
        return f"Safe {self.date} — {self.closing_balance:,.0f} XAF"

    @property
    def exceeds_limit(self):
        return self.closing_balance > self.SAFE_MAX_BALANCE


# ═══════════════════════════════════════════════════════════════════════════════
# CASH VARIANCE REGISTER  —  Shortage / Overage Tracking
# ═══════════════════════════════════════════════════════════════════════════════

class CashVarianceRegister(AuditModel):
    """
    Dedicated register for cash shortages and overages.
    Auto-created when session/shift verified with non-zero variance.
    Per policy: both shortages and overages must be declared;
    shortages are deducted from salary; overages investigated.
    """
    session       = models.ForeignKey(
        CashierSession, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='variance_records'
    )
    shift         = models.ForeignKey(
        CashierShift, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='variance_records'
    )
    cashier       = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='cash_variances'
    )
    variance_date = models.DateField()
    expected_amount  = models.DecimalField(max_digits=14, decimal_places=2)
    declared_amount  = models.DecimalField(max_digits=14, decimal_places=2)
    variance_amount  = models.DecimalField(max_digits=14, decimal_places=2,
        help_text='Positive = overage, negative = shortage')
    explanation      = models.TextField(blank=True)
    resolution       = models.TextField(blank=True)
    resolved_by      = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='variances_resolved'
    )
    resolved_at      = models.DateTimeField(null=True, blank=True)
    is_resolved      = models.BooleanField(default=False)

    class Meta:
        ordering = ['-variance_date']
        verbose_name = 'Cash Variance'
        verbose_name_plural = 'Cash Variance Register'

    def __str__(self):
        kind = 'Overage' if self.variance_amount > 0 else 'Shortage'
        return f"{kind} {abs(self.variance_amount):,.0f} XAF — {self.cashier.get_full_name()}"


# ═══════════════════════════════════════════════════════════════════════════════
# ASSET DISPOSAL  —  Formal disposal workflow with GL posting
# ═══════════════════════════════════════════════════════════════════════════════

class DisposalMethod(models.TextChoices):
    SOLD     = 'SOLD',     'Sold'
    DONATED  = 'DONATED',  'Donated'
    SCRAPPED = 'SCRAPPED', 'Scrapped / Discarded'
    LOST     = 'LOST',     'Lost / Missing'
    STOLEN   = 'STOLEN',   'Stolen'


class DisposalStatus(models.TextChoices):
    REQUESTED = 'REQUESTED', 'Disposal Requested'
    APPROVED  = 'APPROVED',  'Approved'
    COMPLETED = 'COMPLETED', 'Completed'
    REJECTED  = 'REJECTED',  'Rejected'


class AssetDisposal(AuditModel):
    """
    Formal asset disposal request and approval.
    On completion: sets asset.status=DISPOSED and posts GL entry.
    """
    asset = models.ForeignKey(
        AssetRegister, on_delete=models.PROTECT, related_name='disposals'
    )
    disposal_method = models.CharField(max_length=20, choices=DisposalMethod.choices)
    status = models.CharField(
        max_length=20, choices=DisposalStatus.choices,
        default=DisposalStatus.REQUESTED
    )
    reason          = models.TextField()
    estimated_value = models.DecimalField(max_digits=14, decimal_places=2, default=0,
        help_text='Expected sale proceeds (0 for scrapped/donated)')
    actual_proceeds = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    disposal_date   = models.DateField(null=True, blank=True)
    requested_by    = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='asset_disposal_requests'
    )
    approved_by     = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='asset_disposal_approvals'
    )
    approved_at     = models.DateTimeField(null=True, blank=True)
    buyer_info      = models.CharField(max_length=300, blank=True,
        help_text='Purchaser details if sold')
    journal_entry   = models.ForeignKey(
        JournalEntry, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='asset_disposals'
    )
    notes           = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Asset Disposal'
        verbose_name_plural = 'Asset Disposals'

    def __str__(self):
        return f"Dispose {self.asset.name} ({self.get_disposal_method_display()})"


# ═══════════════════════════════════════════════════════════════════════════════
# BUDGET AMENDMENT  —  Track changes to approved budgets
# ═══════════════════════════════════════════════════════════════════════════════

class BudgetAmendment(TimeStampedModel):
    """Audit trail for budget amendments."""
    budget          = models.ForeignKey(
        Budget, on_delete=models.CASCADE, related_name='amendments'
    )
    previous_amount = models.DecimalField(max_digits=14, decimal_places=2)
    new_amount      = models.DecimalField(max_digits=14, decimal_places=2)
    reason          = models.TextField()
    amended_by      = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='budget_amendments'
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Budget {self.budget} amended: {self.previous_amount:,.0f} → {self.new_amount:,.0f}"


# ═══════════════════════════════════════════════════════════════════════════════
# FISCAL PERIOD  —  Monthly period closing/locking for GL integrity
# ═══════════════════════════════════════════════════════════════════════════════

class FiscalPeriodStatus(models.TextChoices):
    OPEN   = 'OPEN',   'Open'
    CLOSED = 'CLOSED', 'Closed'
    LOCKED = 'LOCKED', 'Locked (Final)'

class FiscalPeriod(AuditModel):
    """
    Monthly fiscal period — controls whether journal entries can be posted.
    OPEN = normal operations; CLOSED = soft-close (reversible by Finance Director);
    LOCKED = permanent close (irreversible, for audited periods).
    """
    year   = models.PositiveIntegerField()
    month  = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=10, choices=FiscalPeriodStatus.choices,
                              default=FiscalPeriodStatus.OPEN)
    closed_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='closed_periods'
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='locked_periods'
    )
    locked_at = models.DateTimeField(null=True, blank=True)
    notes     = models.TextField(blank=True)

    class Meta:
        unique_together = [('year', 'month')]
        ordering = ['-year', '-month']
        verbose_name = 'Fiscal Period'
        verbose_name_plural = 'Fiscal Periods'

    def __str__(self):
        import calendar
        return f"{calendar.month_abbr[self.month]} {self.year} — {self.get_status_display()}"

    @property
    def is_open(self):
        return self.status == FiscalPeriodStatus.OPEN

    @property
    def can_post(self):
        """Can journal entries be posted to this period?"""
        return self.status == FiscalPeriodStatus.OPEN


# ══════════════════════════════════════════════════════════════════════════════
# GL MAPPING — configurable link between transactions and GL accounts
# ══════════════════════════════════════════════════════════════════════════════

class GLMappingCategory(models.TextChoices):
    REVENUE  = 'REVENUE',  'Revenue (Service → GL)'
    PAYMENT  = 'PAYMENT',  'Payment Method (Cash/Card → GL)'
    EXPENSE  = 'EXPENSE',  'Expense Category (Type → GL)'
    SYSTEM   = 'SYSTEM',   'System Accounts (AR, AP, Cash, etc.)'


class GLMapping(AuditModel):
    """
    Configurable mapping between business transaction types and GL accounts.
    Replaces hardcoded dicts in gl_service.py — editable from Finance Director GUI.
    """
    category    = models.CharField(max_length=10, choices=GLMappingCategory.choices,
                    help_text='Which mapping group this belongs to')
    source_key  = models.CharField(max_length=30,
                    help_text='Transaction type key (e.g. CONSULT, CASH, SUPPLIES, AR_PATIENT)')
    label       = models.CharField(max_length=100,
                    help_text='Human-readable label for this mapping')
    gl_account  = models.ForeignKey(GLAccount, on_delete=models.PROTECT,
                    related_name='mappings',
                    help_text='Target GL account for this transaction type')
    is_active   = models.BooleanField(default=True)
    notes       = models.CharField(max_length=200, blank=True)

    class Meta:
        unique_together = [('category', 'source_key')]
        ordering = ['category', 'source_key']
        verbose_name = 'GL Mapping'
        verbose_name_plural = 'GL Mappings'

    def __str__(self):
        return f"{self.get_category_display()}: {self.label} → {self.gl_account.code}"

    @classmethod
    def get_code(cls, category, source_key, fallback=None):
        """Look up GL account code. Returns fallback if not found."""
        try:
            m = cls.objects.select_related('gl_account').get(
                category=category, source_key=source_key, is_active=True,
            )
            return m.gl_account.code
        except cls.DoesNotExist:
            return fallback


# ── Asset Maintenance ─────────────────────────────────────────────────────────

class MaintenanceFrequency(models.TextChoices):
    MONTHLY = 'MONTHLY', 'Monthly'
    QUARTERLY = 'QUARTERLY', 'Quarterly'
    BIANNUAL = 'BIANNUAL', 'Every 6 Months'
    ANNUAL = 'ANNUAL', 'Annual'
    AS_NEEDED = 'AS_NEEDED', 'As Needed'


class MaintenanceStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
    DONE = 'DONE', 'Completed'
    DEFERRED = 'DEFERRED', 'Deferred'


class MaintenanceType(models.TextChoices):
    PREVENTIVE = 'PREVENTIVE', 'Preventive'
    CORRECTIVE = 'CORRECTIVE', 'Corrective'
    INSPECTION = 'INSPECTION', 'Inspection'
    CALIBRATION = 'CALIBRATION', 'Calibration'


class MaintenanceSchedule(AuditModel):
    """Recurring maintenance schedule for an asset."""
    asset = models.ForeignKey(
        'AssetRegister', on_delete=models.CASCADE, related_name='maintenance_schedules'
    )
    frequency = models.CharField(max_length=20, choices=MaintenanceFrequency.choices,
                                  default=MaintenanceFrequency.ANNUAL)
    next_due = models.DateField()
    last_done = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True)
    assigned_to = models.ForeignKey(
        'accounts.User', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='maintenance_assignments'
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['next_due']

    def __str__(self):
        return f"{self.asset.asset_name} — {self.get_frequency_display()} (due {self.next_due})"

    @property
    def is_overdue(self):
        from django.utils import timezone
        return self.next_due < timezone.now().date() and self.is_active


class MaintenanceWorkOrder(AuditModel):
    """A specific maintenance work order for an asset."""
    asset = models.ForeignKey(
        'AssetRegister', on_delete=models.CASCADE, related_name='work_orders'
    )
    schedule = models.ForeignKey(
        MaintenanceSchedule, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='work_orders'
    )
    wo_number = models.CharField(max_length=20, unique=True, blank=True)
    maintenance_type = models.CharField(max_length=20, choices=MaintenanceType.choices,
                                         default=MaintenanceType.PREVENTIVE)
    status = models.CharField(max_length=20, choices=MaintenanceStatus.choices,
                               default=MaintenanceStatus.PENDING)
    description = models.TextField()
    estimated_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    actual_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    findings = models.TextField(blank=True)
    parts_used = models.TextField(blank=True)
    created_by = models.ForeignKey(
        'accounts.User', null=True, on_delete=models.SET_NULL, related_name='maintenance_wos_created'
    )
    performed_by = models.ForeignKey(
        'accounts.User', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='maintenance_wos_performed'
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.wo_number} — {self.asset.asset_name}"

    def save(self, *args, **kwargs):
        if not self.wo_number:
            from django.utils import timezone as tz
            year = tz.now().year
            count = MaintenanceWorkOrder.objects.filter(created_at__year=year).count() + 1
            self.wo_number = f"WO-{year}-{count:04d}"
        super().save(*args, **kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# Month-End Close
# ─────────────────────────────────────────────────────────────────────────────
class MonthEndCloseStatus(models.TextChoices):
    OPEN       = 'OPEN',       'Open'
    IN_PROGRESS= 'IN_PROGRESS','In Progress'
    CLOSED     = 'CLOSED',     'Closed'


class MonthEndClose(AuditModel):
    """Monthly accounting close checklist."""
    period_month  = models.PositiveSmallIntegerField()   # 1-12
    period_year   = models.PositiveSmallIntegerField()
    status        = models.CharField(max_length=20, choices=MonthEndCloseStatus.choices, default=MonthEndCloseStatus.OPEN)
    started_by    = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name='month_closes_started')
    closed_by     = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name='month_closes_approved')
    closed_at     = models.DateTimeField(null=True, blank=True)
    notes         = models.TextField(blank=True)

    class Meta:
        unique_together = [('period_month', 'period_year')]
        ordering = ['-period_year', '-period_month']

    def __str__(self):
        import calendar
        return f"Month-End Close {calendar.month_name[self.period_month]} {self.period_year}"

    @property
    def period_label(self):
        import calendar
        return f"{calendar.month_name[self.period_month]} {self.period_year}"

    @property
    def completion_pct(self):
        tasks = self.tasks.all()
        if not tasks:
            return 0
        done = tasks.filter(is_completed=True).count()
        return round(done / tasks.count() * 100)


class MonthEndCloseTask(models.Model):
    close       = models.ForeignKey(MonthEndClose, on_delete=models.CASCADE, related_name='tasks')
    task_name   = models.CharField(max_length=200)
    task_order  = models.PositiveSmallIntegerField(default=0)
    is_completed= models.BooleanField(default=False)
    completed_by= models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='close_tasks_done')
    completed_at= models.DateTimeField(null=True, blank=True)
    notes       = models.TextField(blank=True)

    class Meta:
        ordering = ['task_order']

    def __str__(self):
        return self.task_name


# ─────────────────────────────────────────────────────────────────────────────
# Cash Count Sheet (end-of-day denomination breakdown)
# ─────────────────────────────────────────────────────────────────────────────
class CashCountSheet(AuditModel):
    """Physical cash count with FCFA denomination breakdown."""
    cashier       = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True,
                                      related_name='cash_count_sheets')
    session       = models.ForeignKey('CashierSession', on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name='count_sheets')
    count_date    = models.DateField()
    # FCFA denominations (count of notes/coins)
    denom_10000   = models.PositiveIntegerField(default=0)
    denom_5000    = models.PositiveIntegerField(default=0)
    denom_2000    = models.PositiveIntegerField(default=0)
    denom_1000    = models.PositiveIntegerField(default=0)
    denom_500     = models.PositiveIntegerField(default=0)
    denom_200     = models.PositiveIntegerField(default=0)
    denom_100     = models.PositiveIntegerField(default=0)
    denom_50      = models.PositiveIntegerField(default=0)
    denom_25      = models.PositiveIntegerField(default=0)
    denom_10      = models.PositiveIntegerField(default=0)
    # Totals
    total_counted  = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_expected = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    variance       = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    verified_by    = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='count_sheets_verified')
    notes          = models.TextField(blank=True)

    class Meta:
        ordering = ['-count_date', '-created_at']

    def __str__(self):
        return f"Cash Count {self.count_date} — {self.cashier}"

    def compute_total(self):
        return (
            self.denom_10000 * 10000 +
            self.denom_5000  * 5000  +
            self.denom_2000  * 2000  +
            self.denom_1000  * 1000  +
            self.denom_500   * 500   +
            self.denom_200   * 200   +
            self.denom_100   * 100   +
            self.denom_50    * 50    +
            self.denom_25    * 25    +
            self.denom_10    * 10
        )


# ─────────────────────────────────────────────────────────────────────────────
# Depreciation Run (monthly auto-posting)
# ─────────────────────────────────────────────────────────────────────────────
class DepreciationRunStatus(models.TextChoices):
    DRAFT  = 'DRAFT',  'Draft'
    POSTED = 'POSTED', 'Posted'


class DepreciationRun(AuditModel):
    """Monthly depreciation batch — one per accounting period."""
    period_month   = models.PositiveSmallIntegerField()
    period_year    = models.PositiveSmallIntegerField()
    status         = models.CharField(max_length=10, choices=DepreciationRunStatus.choices, default=DepreciationRunStatus.DRAFT)
    total_depreciation = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    journal_entry  = models.OneToOneField('JournalEntry', on_delete=models.SET_NULL, null=True, blank=True,
                                           related_name='depreciation_run')
    run_by         = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True,
                                       related_name='depreciation_runs')

    class Meta:
        unique_together = [('period_month', 'period_year')]
        ordering = ['-period_year', '-period_month']

    def __str__(self):
        import calendar
        return f"Depreciation {calendar.month_name[self.period_month]} {self.period_year}"

    @property
    def period_label(self):
        import calendar
        return f"{calendar.month_name[self.period_month]} {self.period_year}"


class DepreciationEntry(models.Model):
    """Per-asset depreciation line within a DepreciationRun."""
    run                  = models.ForeignKey(DepreciationRun, on_delete=models.CASCADE, related_name='entries')
    asset                = models.ForeignKey('AssetRegister', on_delete=models.PROTECT, related_name='depreciation_entries')
    depreciation_amount  = models.DecimalField(max_digits=12, decimal_places=2)
    accumulated_before   = models.DecimalField(max_digits=12, decimal_places=2)
    accumulated_after    = models.DecimalField(max_digits=12, decimal_places=2)
    net_book_value       = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"{self.asset.asset_name} — {self.depreciation_amount}"


# ─────────────────────────────────────────────────────────────────────────────
# Withholding Tax (Retenues à la source on supplier payments)
# ─────────────────────────────────────────────────────────────────────────────
class WHTType(models.TextChoices):
    IRC  = 'IRC',  'IRC — Impôt sur Revenu des Capitaux'
    IRCM = 'IRCM', 'IRCM — Impôt sur Revenu des Capitaux Mobiliers'
    TSR  = 'TSR',  'TSR — Taxe Spéciale sur les Revenus'
    OTHER= 'OTHER','Other'


class WithholdingTax(AuditModel):
    """Tracks withholding taxes deducted from supplier/service payments."""
    transaction_date = models.DateField()
    supplier_name    = models.CharField(max_length=200)
    ap_bill          = models.ForeignKey('APBill', on_delete=models.SET_NULL, null=True, blank=True,
                                         related_name='withholding_taxes')
    tax_type         = models.CharField(max_length=10, choices=WHTType.choices, default=WHTType.TSR)
    gross_amount     = models.DecimalField(max_digits=14, decimal_places=2)
    wht_rate         = models.DecimalField(max_digits=5, decimal_places=2, help_text='e.g. 5.50 for 5.5%')
    wht_amount       = models.DecimalField(max_digits=12, decimal_places=2)
    net_paid         = models.DecimalField(max_digits=14, decimal_places=2)
    reference        = models.CharField(max_length=100, blank=True)
    is_remitted      = models.BooleanField(default=False, help_text='Paid to DGI?')
    remittance_date  = models.DateField(null=True, blank=True)
    remittance_ref   = models.CharField(max_length=100, blank=True)
    notes            = models.TextField(blank=True)

    class Meta:
        ordering = ['-transaction_date']

    def __str__(self):
        return f"WHT {self.tax_type} — {self.supplier_name} {self.wht_amount}"

    def save(self, *args, **kwargs):
        self.net_paid = self.gross_amount - self.wht_amount
        super().save(*args, **kwargs)

