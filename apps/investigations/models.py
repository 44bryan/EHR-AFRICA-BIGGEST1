"""
Eye investigation orders and results.
Covers: VA, IOP, Fundus Photography, OCT, Perimetry, Biometry, Refraction,
        Slit Lamp, Fluorescein Angiography, B-Scan, ERG, Pachymetry, etc.
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.core.models import AuditModel, TimeStampedModel


class InvestigationCategory(models.TextChoices):
    REFRACTION = 'REFRACTION', _('Refraction')
    TONOMETRY = 'TONOMETRY', _('Tonometry')
    IMAGING = 'IMAGING', _('Imaging')
    ELECTROPHYSIOLOGY = 'ELECTROPHYSIOLOGY', _('Electrophysiology')
    VISUAL_FIELD = 'VISUAL_FIELD', _('Visual Field')
    BIOMETRY = 'BIOMETRY', _('Biometry / A-Scan')
    PACHYMETRY = 'PACHYMETRY', _('Pachymetry')
    ANTERIOR_SEGMENT = 'ANT_SEG', _('Anterior Segment')
    OTHER = 'OTHER', _('Other')


class InvestigationType(TimeStampedModel):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, unique=True)
    category = models.CharField(max_length=30, choices=InvestigationCategory.choices)
    description = models.TextField(blank=True)
    requires_preparation = models.BooleanField(default=False)
    preparation_instructions = models.TextField(blank=True)
    # Template for structured result entry (JSON schema-like)
    result_template = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['category', 'name']
        verbose_name = 'Investigation Type'

    def __str__(self):
        return f"{self.code} — {self.name}"


class InvestigationOrder(AuditModel):
    class Urgency(models.TextChoices):
        ROUTINE = 'ROUTINE', _('Routine')
        URGENT = 'URGENT', _('Urgent')
        EMERGENCY = 'EMERGENCY', _('Emergency')

    class Status(models.TextChoices):
        ORDERED = 'ORDERED', _('Ordered')
        SCHEDULED = 'SCHEDULED', _('Scheduled')
        IN_PROGRESS = 'IN_PROGRESS', _('In Progress')
        COMPLETED = 'COMPLETED', _('Completed')
        CANCELLED = 'CANCELLED', _('Cancelled')

    class Eye(models.TextChoices):
        RIGHT = 'RE', _('Right Eye')
        LEFT = 'LE', _('Left Eye')
        BOTH = 'BE', _('Both Eyes')
        NA = 'NA', _('N/A')

    consultation = models.ForeignKey(
        'consultations.Consultation',
        on_delete=models.CASCADE,
        related_name='investigation_orders',
    )
    patient = models.ForeignKey(
        'patients.Patient',
        on_delete=models.CASCADE,
        related_name='investigation_orders',
    )
    ordered_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='ordered_investigations',
    )
    assigned_to = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_investigations',
    )
    investigation_type = models.ForeignKey(InvestigationType, on_delete=models.PROTECT)
    urgency = models.CharField(max_length=10, choices=Urgency.choices, default=Urgency.ROUTINE)
    clinical_indication = models.TextField()
    eye = models.CharField(max_length=5, choices=Eye.choices, default=Eye.BOTH)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.ORDERED)
    notes = models.TextField(blank=True)
    scheduled_time = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Investigation Order'

    def __str__(self):
        return f"{self.investigation_type.name} — {self.patient.full_name}"


class InvestigationResult(AuditModel):
    order = models.OneToOneField(InvestigationOrder, on_delete=models.CASCADE, related_name='result')
    performed_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='performed_investigations',
    )
    verified_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_investigations',
    )
    result_date = models.DateTimeField(auto_now_add=True)
    result_data = models.JSONField(default=dict, help_text='Structured result per investigation type')
    interpretation = models.TextField(blank=True)
    is_normal = models.BooleanField(null=True, blank=True)
    is_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    report_generated = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Investigation Result'

    def __str__(self):
        return f"Result: {self.order.investigation_type.name} — {self.order.patient.full_name}"


class InvestigationFile(TimeStampedModel):
    class FileType(models.TextChoices):
        IMAGE = 'IMAGE', _('Image')
        PDF = 'PDF', _('PDF')
        DATA = 'DATA', _('Data File')
        VIDEO = 'VIDEO', _('Video')

    result = models.ForeignKey(InvestigationResult, on_delete=models.CASCADE, related_name='files')
    file = models.FileField(upload_to='investigations/files/%Y/%m/')
    file_type = models.CharField(max_length=10, choices=FileType.choices)
    description = models.CharField(max_length=200, blank=True)
    uploaded_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return f"{self.file_type} — {self.result}"
