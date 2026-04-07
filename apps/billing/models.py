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


class ServiceCategory(models.TextChoices):
    CONSULTATION = 'CONSULT', 'Consultation'
    INVESTIGATION = 'INVEST', 'Investigation / Diagnostics'
    LABORATORY = 'LAB', 'Laboratory'
    PHARMACY = 'PHARMACY', 'Pharmacy'
    OPTICAL = 'OPTICAL', 'Opticals'
    SURGICAL = 'SURGICAL', 'Surgical Procedure'
    ADMISSION = 'ADMISSION', 'Inpatient Admission'
    REGISTRATION = 'REG', 'Registration'
    OTHER = 'OTHER', 'Other'


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
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Invoice {self.invoice_number} — {self.patient.full_name}"

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            year = timezone.now().year
            count = Invoice.objects.filter(created_at__year=year).count() + 1
            self.invoice_number = f"INV-{year}-{count:05d}"
        super().save(*args, **kwargs)

    @property
    def subtotal(self):
        return sum(item.line_total for item in self.items.filter(is_deleted=False))

    @property
    def total(self):
        return max(self.subtotal - self.discount_amount, 0)

    @property
    def amount_paid(self):
        return sum(
            p.amount for p in self.payments.filter(is_deleted=False)
        )

    @property
    def balance_due(self):
        return self.total - self.amount_paid

    def update_status(self):
        if self.status == InvoiceStatus.CANCELLED:
            return
        paid = self.amount_paid
        total = self.total
        if paid <= 0:
            if self.status != InvoiceStatus.DRAFT:
                self.status = InvoiceStatus.ISSUED
        elif paid >= total:
            self.status = InvoiceStatus.PAID
        else:
            self.status = InvoiceStatus.PARTIALLY_PAID
        self.save(update_fields=['status'])


class InvoiceItem(AuditModel):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='items')
    category = models.CharField(max_length=20, choices=ServiceCategory.choices)
    description = models.CharField(max_length=255)
    quantity = models.PositiveSmallIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    notes = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"{self.description} x{self.quantity}"

    @property
    def line_total(self):
        return self.quantity * self.unit_price


class Payment(AuditModel):
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name='payments')
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reference = models.CharField(max_length=100, blank=True, help_text='Transaction reference / receipt number')
    notes = models.CharField(max_length=200, blank=True)
    received_by = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='payments_received'
    )
    payment_date = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-payment_date']

    def __str__(self):
        return f"Payment {self.amount} on {self.invoice.invoice_number}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.invoice.update_status()
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
