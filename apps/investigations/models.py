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
    unit_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text='Price charged per investigation (FCFA)'
    )
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

    class Location(models.TextChoices):
        CLINIC   = 'CLINIC',   _('Clinic')
        OUTREACH = 'OUTREACH', _('Outreach / Field')

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
    location = models.CharField(
        max_length=10, choices=Location.choices, default=Location.CLINIC,
        db_index=True, help_text='Where the investigation was performed'
    )
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


class ImagingModality(models.TextChoices):
    OCT        = 'OCT',        'OCT (Optical Coherence Tomography)'
    FFA        = 'FFA',        'Fundus Fluorescein Angiography'
    FUNDUS     = 'FUNDUS',     'Fundus Photography'
    PENTACAM   = 'PENTACAM',   'Pentacam / Corneal Topography'
    BIOMETRY   = 'BIOMETRY',   'Biometry (IOL Master / A-Scan)'
    BSCAN      = 'BSCAN',      'B-Scan Ultrasound'
    PERIMETRY  = 'PERIMETRY',  'Visual Field / Perimetry'
    XRAY       = 'XRAY',       'X-Ray'
    CT         = 'CT',         'CT Scan'
    MRI        = 'MRI',        'MRI'
    OTHER      = 'OTHER',      'Other'


class ImagingStudy(AuditModel):
    """
    DICOM imaging study linked to a patient / consultation.
    Stores the study UID and a viewer URL so clinicians can open
    the study in OHIF Viewer, Orthanc, or any web-based DICOM viewer.

    Set DICOM_VIEWER_BASE_URL in .env to your OHIF / Orthanc base URL.
    The system auto-builds viewer_url = base + study_uid when blank.
    """
    patient = models.ForeignKey(
        'patients.Patient', on_delete=models.PROTECT, related_name='imaging_studies'
    )
    consultation = models.ForeignKey(
        'consultations.Consultation', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='imaging_studies'
    )
    order = models.ForeignKey(
        InvestigationOrder, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='imaging_studies'
    )
    modality       = models.CharField(max_length=20, choices=ImagingModality.choices)
    study_date     = models.DateField(default=None, null=True, blank=True)
    description    = models.CharField(max_length=255)
    study_uid      = models.CharField(
        max_length=200, blank=True,
        help_text='DICOM Study Instance UID (e.g. 1.2.840.10008.5.1.4.1.1.4)'
    )
    accession_number = models.CharField(max_length=50, blank=True)
    series_count   = models.PositiveSmallIntegerField(default=1)
    viewer_url     = models.URLField(
        max_length=500, blank=True,
        help_text='Full URL to open study in viewer. Auto-built from DICOM_VIEWER_BASE_URL if blank.'
    )
    report         = models.TextField(blank=True, help_text='Imaging report / radiologist findings')
    is_reported    = models.BooleanField(default=False)
    reported_by    = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='imaging_reports'
    )
    ordered_by     = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ordered_imaging'
    )

    class Meta:
        ordering = ['-study_date', '-created_at']
        verbose_name = 'Imaging Study'
        verbose_name_plural = 'Imaging Studies'

    def __str__(self):
        return f"{self.get_modality_display()} — {self.patient.full_name} ({self.study_date})"

    def save(self, *args, **kwargs):
        # Auto-build viewer URL from base URL + study UID if not set
        if not self.viewer_url and self.study_uid:
            from django.conf import settings
            base = getattr(settings, 'DICOM_VIEWER_BASE_URL', '').rstrip('/')
            if base:
                self.viewer_url = f"{base}?StudyInstanceUIDs={self.study_uid}"
        if not self.study_date:
            from django.utils import timezone as _tz
            self.study_date = _tz.localdate()
        super().save(*args, **kwargs)

    @property
    def can_view_in_browser(self):
        return bool(self.viewer_url)


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
