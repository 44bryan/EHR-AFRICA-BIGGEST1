"""
Laboratory test orders and results.
Covers haematology, biochemistry, microbiology, serology, urinalysis.
"""
import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.core.models import AuditModel, TimeStampedModel


class LabTestCategory(models.TextChoices):
    HAEMATOLOGY  = 'HAEMATOLOGY',  _('Haematology')
    BIOCHEMISTRY = 'BIOCHEMISTRY', _('Biochemistry')
    LIPID        = 'LIPID',        _('Lipid Profile')
    RENAL        = 'RENAL',        _('Renal Profile')
    ELECTROLYTES = 'ELECTROLYTES', _('Electrolytes')
    THYROID      = 'THYROID',      _('Thyroid Functions')
    MICROBIOLOGY = 'MICROBIOLOGY', _('Microbiology')
    PARASITOLOGY = 'PARASITOLOGY', _('Parasitology')
    SEROLOGY     = 'SEROLOGY',     _('Serology')
    RHEUMATOID   = 'RHEUMATOID',   _('Rheumatoid Profile')
    FEBRILE      = 'FEBRILE',      _('Febrile Profile')
    URINALYSIS   = 'URINALYSIS',   _('Urinalysis / Pathology')
    HISTOLOGY    = 'HISTOLOGY',    _('Histology / Cytology')
    OCULAR       = 'OCULAR',       _('Ocular Specimens')


class ResultType(models.TextChoices):
    QUANTITATIVE   = 'QUANTITATIVE',   _('Quantitative — numeric value with unit')
    QUALITATIVE    = 'QUALITATIVE',    _('Qualitative — e.g. Positive / Negative')
    SEMI_QUANT     = 'SEMI_QUANT',     _('Semi-quantitative — e.g. + / ++ / +++')
    TEXT           = 'TEXT',           _('Text / Narrative finding')
    PANEL          = 'PANEL',          _('Panel — multiple sub-results (e.g. CBC)')


class LabTestType(TimeStampedModel):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, unique=True)
    category = models.CharField(max_length=20, choices=LabTestCategory.choices)
    result_type = models.CharField(
        max_length=15, choices=ResultType.choices,
        default=ResultType.QUANTITATIVE,
        help_text='Determines the input format on the result entry form.',
    )
    result_options = models.JSONField(
        default=list, blank=True,
        help_text='For QUALITATIVE/SEMI_QUANT: list of valid result values. '
                  'e.g. ["Positive","Negative"] or ["Negative","+","++","+++","++++"]',
    )
    description = models.TextField(blank=True)
    normal_range = models.JSONField(
        default=dict,
        help_text='e.g. {"male": {"min": 13.5, "max": 17.5, "unit": "g/dL"}, "female": {...}}'
    )
    sample_type = models.CharField(max_length=30, blank=True,
        help_text='Default sample type e.g. Blood-EDTA, Urine, Swab')
    turnaround_hours = models.PositiveSmallIntegerField(default=24)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['category', 'name']
        verbose_name = 'Lab Test Type'

    def __str__(self):
        return f"{self.code} — {self.name}"


class LabOrder(AuditModel):
    class Urgency(models.TextChoices):
        ROUTINE = 'ROUTINE', _('Routine')
        URGENT = 'URGENT', _('Urgent')
        EMERGENCY = 'EMERGENCY', _('Emergency')

    class Status(models.TextChoices):
        ORDERED = 'ORDERED', _('Ordered')
        SAMPLE_COLLECTED = 'SAMPLE_COLLECTED', _('Sample Collected')
        PROCESSING = 'PROCESSING', _('Processing')
        COMPLETED = 'COMPLETED', _('Completed')
        CANCELLED = 'CANCELLED', _('Cancelled')

    consultation = models.ForeignKey(
        'consultations.Consultation',
        on_delete=models.CASCADE,
        related_name='lab_orders',
    )
    patient = models.ForeignKey(
        'patients.Patient',
        on_delete=models.CASCADE,
        related_name='lab_orders',
    )
    ordered_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='ordered_lab_tests',
    )
    urgency = models.CharField(max_length=10, choices=Urgency.choices, default=Urgency.ROUTINE)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ORDERED)
    clinical_indication = models.TextField()
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Lab Order'

    def __str__(self):
        return f"Lab Order — {self.patient.full_name} [{self.created_at:%d/%m/%Y}]"


class LabOrderItem(TimeStampedModel):
    order = models.ForeignKey(LabOrder, on_delete=models.CASCADE, related_name='items')
    test_type = models.ForeignKey(LabTestType, on_delete=models.PROTECT)
    status = models.CharField(
        max_length=20,
        choices=LabOrder.Status.choices,
        default=LabOrder.Status.ORDERED,
    )

    class Meta:
        unique_together = [('order', 'test_type')]
        verbose_name = 'Lab Order Item'

    def __str__(self):
        return f"{self.test_type.name} — {self.order.patient.full_name}"


class SampleCollection(AuditModel):
    class SampleType(models.TextChoices):
        BLOOD_EDTA = 'BLOOD_EDTA', _('Blood — EDTA')
        BLOOD_PLAIN = 'BLOOD_PLAIN', _('Blood — Plain')
        BLOOD_FLUORIDE = 'BLOOD_FLUORIDE', _('Blood — Fluoride Oxalate')
        URINE = 'URINE', _('Urine')
        SWAB = 'SWAB', _('Swab')
        AQUEOUS = 'AQUEOUS', _('Aqueous Humour')
        VITREOUS = 'VITREOUS', _('Vitreous')
        OTHER = 'OTHER', _('Other')

    order = models.OneToOneField(LabOrder, on_delete=models.CASCADE, related_name='sample_collection')
    collected_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True)
    collection_date = models.DateTimeField(auto_now_add=True)
    sample_type = models.CharField(max_length=20, choices=SampleType.choices)
    sample_id = models.CharField(max_length=30, unique=True)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Sample Collection'

    def save(self, *args, **kwargs):
        if not self.sample_id:
            # ISO 15189 §5.4.2 — sequential, traceable sample ID (LAB-YYYYMMDD-NNNN)
            from django.utils import timezone as _tz
            today = _tz.localdate()
            prefix = f'LAB-{today.strftime("%Y%m%d")}-'
            last = (SampleCollection.objects
                    .filter(sample_id__startswith=prefix)
                    .order_by('-sample_id')
                    .values_list('sample_id', flat=True)
                    .first())
            try:
                seq = int(last.split('-')[-1]) + 1 if last else 1
            except (ValueError, AttributeError, IndexError):
                seq = 1
            self.sample_id = f'{prefix}{seq:04d}'
        super().save(*args, **kwargs)


class SampleRejection(AuditModel):
    """ISO 15189 §5.4.5 — Record when a sample cannot be processed."""

    class Reason(models.TextChoices):
        HAEMOLYSED      = 'HAEMOLYSED',      _('Haemolysed sample')
        INSUFFICIENT    = 'INSUFFICIENT',     _('Insufficient volume')
        WRONG_CONTAINER = 'WRONG_CONTAINER',  _('Wrong container / tube')
        UNLABELLED      = 'UNLABELLED',       _('Unlabelled / mislabelled')
        CLOTTED         = 'CLOTTED',          _('Clotted sample')
        CONTAMINATED    = 'CONTAMINATED',     _('Contaminated')
        DELAYED         = 'DELAYED',          _('Excessive transport delay')
        OTHER           = 'OTHER',            _('Other — see notes')

    order = models.ForeignKey(LabOrder, on_delete=models.CASCADE, related_name='rejections')
    rejected_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True)
    reason = models.CharField(max_length=20, choices=Reason.choices)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Sample Rejection'

    def __str__(self):
        return f"Rejection — {self.order.patient.full_name} [{self.get_reason_display()}]"


class LabResult(AuditModel):
    order_item = models.OneToOneField(LabOrderItem, on_delete=models.CASCADE, related_name='result')
    performed_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True,
        related_name='performed_lab_tests',
    )
    verified_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='verified_lab_tests',
    )
    result_value = models.CharField(max_length=200)
    result_unit = models.CharField(max_length=50, blank=True)
    reference_range = models.CharField(max_length=100, blank=True)
    is_abnormal = models.BooleanField(default=False)
    is_critical = models.BooleanField(default=False)
    result_date = models.DateTimeField(auto_now_add=True)
    is_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    comment = models.TextField(blank=True)
    # JCI IPSG.2 — Critical value read-back acknowledgement
    critical_acknowledged_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='acknowledged_critical_results',
    )
    critical_acknowledged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Lab Result'

    def __str__(self):
        flag = ' [CRITICAL]' if self.is_critical else (' [ABNORMAL]' if self.is_abnormal else '')
        return f"{self.order_item.test_type.name}: {self.result_value} {self.result_unit}{flag}"


class LabResultAmendment(TimeStampedModel):
    """ISO 15189 §5.8.3 — Audit trail whenever a result value is corrected after saving."""
    result = models.ForeignKey(LabResult, on_delete=models.CASCADE, related_name='amendments')
    original_value = models.CharField(max_length=200)
    amended_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True)
    reason = models.TextField()

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Lab Result Amendment'

    def __str__(self):
        return f"Amendment — {self.result} (was: {self.original_value})"
