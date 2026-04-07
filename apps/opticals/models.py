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

    def save(self, *args, **kwargs):
        if not self.order_number:
            today = timezone.localdate()
            count = OpticalOrder.objects.filter(ordered_date__year=today.year).count() + 1
            self.order_number = f"OPT-{today.strftime('%Y')}-{count:04d}"
        self.total_amount = self.frame_price + self.lens_price + self.fitting_charge
        super().save(*args, **kwargs)
