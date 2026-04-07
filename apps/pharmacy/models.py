"""
Pharmacy Module
Drug formulary, stock management, dispensing, reorder alerts.
"""
from django.db import models
from django.utils import timezone
from apps.core.models import TimeStampedModel, AuditModel


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
    received_date = models.DateField(default=timezone.now)
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
    drug = models.ForeignKey(Drug, on_delete=models.PROTECT)
    stock_batch = models.ForeignKey(DrugStock, null=True, blank=True, on_delete=models.SET_NULL)
    quantity_dispensed = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    instructions = models.TextField(blank=True)

    def save(self, *args, **kwargs):
        self.subtotal = self.quantity_dispensed * self.unit_price
        super().save(*args, **kwargs)
        # Deduct from stock
        if self.stock_batch:
            self.stock_batch.quantity_remaining = max(
                0, self.stock_batch.quantity_remaining - self.quantity_dispensed
            )
            self.stock_batch.save()
