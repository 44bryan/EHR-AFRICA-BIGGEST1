"""
Laboratory module — ISO 15189 compliant.
Four independent state machines: Order, Payment, Specimen, Result.
Sub-modules: Microbiology (staged reporting + antibiogram), Histopathology.
"""
import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from apps.core.models import AuditModel, TimeStampedModel


# ═══════════════════════════════════════════════════════════════════════════════
# CHOICES / ENUMS
# ═══════════════════════════════════════════════════════════════════════════════

class LabTestCategory(models.TextChoices):
    HAEMATOLOGY   = 'HAEMATOLOGY',   _('Haematology')
    BIOCHEMISTRY  = 'BIOCHEMISTRY',  _('Biochemistry')
    LIPID         = 'LIPID',         _('Lipid Profile')
    RENAL         = 'RENAL',         _('Renal Profile')
    ELECTROLYTES  = 'ELECTROLYTES',  _('Electrolytes')
    THYROID       = 'THYROID',       _('Thyroid Functions')
    MICROBIOLOGY  = 'MICROBIOLOGY',  _('Microbiology')
    PARASITOLOGY  = 'PARASITOLOGY',  _('Parasitology')
    SEROLOGY      = 'SEROLOGY',      _('Serology')
    RHEUMATOID    = 'RHEUMATOID',    _('Rheumatoid Profile')
    FEBRILE       = 'FEBRILE',       _('Febrile Profile')
    URINALYSIS    = 'URINALYSIS',    _('Urinalysis / Pathology')
    HISTOLOGY     = 'HISTOLOGY',     _('Histology / Cytology')
    OCULAR        = 'OCULAR',        _('Ocular Specimens')
    COAGULATION   = 'COAGULATION',   _('Coagulation')
    BLOOD_BANK    = 'BLOOD_BANK',    _('Blood Bank / Transfusion')
    IMMUNOLOGY    = 'IMMUNOLOGY',    _('Immunology')
    GENETICS      = 'GENETICS',      _('Genetics / Molecular')


class ResultType(models.TextChoices):
    QUANTITATIVE = 'QUANTITATIVE', _('Quantitative — numeric value with unit')
    QUALITATIVE  = 'QUALITATIVE',  _('Qualitative — e.g. Positive / Negative')
    SEMI_QUANT   = 'SEMI_QUANT',   _('Semi-quantitative — e.g. + / ++ / +++')
    TEXT         = 'TEXT',          _('Text / Narrative finding')
    PANEL        = 'PANEL',        _('Panel — multiple sub-results (e.g. CBC)')


class ContainerType(models.TextChoices):
    EDTA_PURPLE   = 'EDTA_PURPLE',   _('EDTA (Purple top)')
    PLAIN_RED     = 'PLAIN_RED',     _('Plain / SST (Red top)')
    CITRATE_BLUE  = 'CITRATE_BLUE',  _('Citrate (Blue top)')
    FLUORIDE_GREY = 'FLUORIDE_GREY', _('Fluoride Oxalate (Grey top)')
    HEPARIN_GREEN = 'HEPARIN_GREEN', _('Heparin (Green top)')
    URINE_CUP    = 'URINE_CUP',     _('Urine Cup')
    SWAB_TUBE    = 'SWAB_TUBE',      _('Swab / Transport tube')
    STERILE_CONT = 'STERILE_CONT',   _('Sterile Container')
    SLIDE        = 'SLIDE',          _('Glass Slide')
    FORMALIN_POT = 'FORMALIN_POT',   _('Formalin Pot (Histology)')
    OTHER        = 'OTHER',          _('Other')


class SpecimenStatus(models.TextChoices):
    PENDING      = 'PENDING',      _('Pending Collection')
    COLLECTED    = 'COLLECTED',    _('Collected')
    IN_TRANSIT   = 'IN_TRANSIT',   _('In Transit')
    RECEIVED     = 'RECEIVED',     _('Received at Lab')
    REJECTED     = 'REJECTED',     _('Rejected')
    RE_COLLECT   = 'RE_COLLECT',   _('Re-collection Required')


class PaymentStatus(models.TextChoices):
    UNPAID        = 'UNPAID',        _('Unpaid')
    PAID          = 'PAID',          _('Paid')
    INSURED       = 'INSURED',       _('Insurance / Third-party')
    WAIVED        = 'WAIVED',        _('Waived (Indigent)')
    STAT_OVERRIDE = 'STAT_OVERRIDE', _('STAT Override — Bill Later')
    PREPAID       = 'PREPAID',       _('Pre-paid Package / Deposit')
    BILL_LATER    = 'BILL_LATER',    _('Bill Later (Authorised)')


class ResultStatus(models.TextChoices):
    PENDING       = 'PENDING',       _('Pending')
    IN_PROGRESS   = 'IN_PROGRESS',   _('In Progress')
    PRELIMINARY   = 'PRELIMINARY',   _('Preliminary')
    TECH_VALID    = 'TECH_VALID',    _('Technically Validated')
    AUTHORIZED    = 'AUTHORIZED',    _('Authorised (Biologist)')
    RELEASED      = 'RELEASED',      _('Released to Clinician')
    AMENDED       = 'AMENDED',       _('Amended (see version history)')


# ═══════════════════════════════════════════════════════════════════════════════
# TEST CATALOGUE
# ═══════════════════════════════════════════════════════════════════════════════

class LabTestType(TimeStampedModel):
    """Master test catalogue — ISO 15189 §5.4."""
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, unique=True)
    loinc_code = models.CharField(
        max_length=20, blank=True, db_index=True,
        help_text='LOINC code for interoperability (e.g. 718-7 for Hemoglobin)',
    )
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

    # Specimen requirements
    sample_type = models.CharField(max_length=30, blank=True,
        help_text='Default sample type e.g. Blood-EDTA, Urine, Swab')
    container_type = models.CharField(
        max_length=20, choices=ContainerType.choices, blank=True,
        help_text='Required container / tube type and colour',
    )
    min_volume_ml = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text='Minimum specimen volume in mL',
    )
    patient_prep = models.TextField(
        blank=True, help_text='Patient preparation instructions (e.g. 12h fasting)',
    )
    method = models.CharField(
        max_length=100, blank=True,
        help_text='Analytical method (e.g. Spectrophotometry, ELISA, PCR)',
    )

    # Work organisation
    work_area = models.CharField(
        max_length=50, blank=True,
        help_text='Bench / section (e.g. Chemistry Bench, Haematology, Microbiology)',
    )
    turnaround_hours = models.PositiveSmallIntegerField(default=24)

    # Send-out / referral
    is_send_out = models.BooleanField(
        default=False, help_text='Test is performed by an external referral lab',
    )
    default_referral_lab = models.CharField(max_length=200, blank=True)

    # Critical value thresholds (auto-flag)
    critical_low = models.DecimalField(
        max_digits=10, decimal_places=3, null=True, blank=True,
        help_text='Panic value — low threshold (auto-flags critical)',
    )
    critical_high = models.DecimalField(
        max_digits=10, decimal_places=3, null=True, blank=True,
        help_text='Panic value — high threshold (auto-flags critical)',
    )

    # Delta check config
    delta_check_percent = models.DecimalField(
        max_digits=5, decimal_places=1, null=True, blank=True,
        help_text='% change from previous result that triggers delta check flag',
    )
    delta_check_hours = models.PositiveIntegerField(
        default=168, help_text='How far back (hours) to look for previous result',
    )

    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['category', 'name']
        verbose_name = 'Lab Test Type'

    def __str__(self):
        return f"{self.code} — {self.name}"


class OrderSet(TimeStampedModel):
    """Pre-defined test panels / workups (e.g. Pre-op workup, Uveitis screen)."""
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True)
    tests = models.ManyToManyField(LabTestType, related_name='order_sets')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Order Set / Panel'

    def __str__(self):
        return self.name


# ═══════════════════════════════════════════════════════════════════════════════
# LAB ORDER (CPOE)
# ═══════════════════════════════════════════════════════════════════════════════

class LabOrder(AuditModel):
    class Urgency(models.TextChoices):
        ROUTINE   = 'ROUTINE',   _('Routine')
        URGENT    = 'URGENT',    _('Urgent')
        STAT      = 'STAT',      _('STAT (Immediate)')
        EMERGENCY = 'EMERGENCY', _('Emergency')

    class Status(models.TextChoices):
        DRAFT     = 'DRAFT',     _('Draft')
        ORDERED   = 'ORDERED',   _('Ordered')
        SAMPLE_COLLECTED = 'SAMPLE_COLLECTED', _('Sample Collected')
        PROCESSING = 'PROCESSING', _('Processing')
        COMPLETED  = 'COMPLETED',  _('Completed')
        CANCELLED  = 'CANCELLED',  _('Cancelled')

    consultation = models.ForeignKey(
        'consultations.Consultation', on_delete=models.CASCADE,
        related_name='lab_orders',
    )
    patient = models.ForeignKey(
        'patients.Patient', on_delete=models.CASCADE,
        related_name='lab_orders',
    )
    ordered_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True,
        related_name='ordered_lab_tests',
    )
    urgency = models.CharField(max_length=10, choices=Urgency.choices, default=Urgency.ROUTINE)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ORDERED)
    clinical_indication = models.TextField()
    notes = models.TextField(blank=True)

    # ── Payment state machine (independent of order status) ──────────────
    payment_status = models.CharField(
        max_length=15, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID,
    )
    payment_authorized_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='authorized_lab_payments',
    )
    payment_authorization_reason = models.TextField(blank=True)
    payment_authorized_at = models.DateTimeField(null=True, blank=True)

    # ── Check-in tracking ─────────────────────────────────────────────
    checked_in_at = models.DateTimeField(null=True, blank=True,
        help_text='When patient physically arrived at lab for sample collection')
    checked_in_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='lab_checkins',
    )

    # ── Specimen state machine (independent of order status) ─────────────
    specimen_status = models.CharField(
        max_length=15, choices=SpecimenStatus.choices, default=SpecimenStatus.PENDING,
    )

    # ── CPOE enhancements ────────────────────────────────────────────────
    icd10_code = models.CharField(
        max_length=10, blank=True,
        help_text='ICD-10 code for clinical indication',
    )
    duplicate_warning_acknowledged = models.BooleanField(default=False)
    order_set = models.ForeignKey(
        OrderSet, on_delete=models.SET_NULL, null=True, blank=True,
        help_text='If ordered as part of a panel / workup',
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Lab Order'

    def __str__(self):
        return f"Lab Order — {self.patient.full_name} [{self.created_at:%d/%m/%Y}]"

    def can_proceed_without_payment(self):
        """STAT/Emergency bypass or authorised non-payment."""
        return self.payment_status in (
            PaymentStatus.PAID, PaymentStatus.INSURED,
            PaymentStatus.WAIVED, PaymentStatus.STAT_OVERRIDE,
            PaymentStatus.PREPAID, PaymentStatus.BILL_LATER,
        )


class LabOrderItem(TimeStampedModel):
    order = models.ForeignKey(LabOrder, on_delete=models.CASCADE, related_name='items')
    test_type = models.ForeignKey(LabTestType, on_delete=models.PROTECT)
    status = models.CharField(
        max_length=20, choices=LabOrder.Status.choices,
        default=LabOrder.Status.ORDERED,
    )

    class Meta:
        unique_together = [('order', 'test_type')]
        verbose_name = 'Lab Order Item'

    def __str__(self):
        return f"{self.test_type.name} — {self.order.patient.full_name}"


# ═══════════════════════════════════════════════════════════════════════════════
# SPECIMEN COLLECTION & RECEIPT — ISO 15189 §5.4
# ═══════════════════════════════════════════════════════════════════════════════

class SampleCollection(AuditModel):
    class SampleType(models.TextChoices):
        BLOOD_EDTA     = 'BLOOD_EDTA',     _('Blood — EDTA')
        BLOOD_PLAIN    = 'BLOOD_PLAIN',    _('Blood — Plain')
        BLOOD_FLUORIDE = 'BLOOD_FLUORIDE', _('Blood — Fluoride Oxalate')
        BLOOD_CITRATE  = 'BLOOD_CITRATE',  _('Blood — Citrate')
        BLOOD_HEPARIN  = 'BLOOD_HEPARIN',  _('Blood — Heparin')
        URINE          = 'URINE',          _('Urine')
        SWAB           = 'SWAB',           _('Swab')
        AQUEOUS        = 'AQUEOUS',        _('Aqueous Humour')
        VITREOUS       = 'VITREOUS',       _('Vitreous')
        CORNEAL_SCRAPE = 'CORNEAL_SCRAPE', _('Corneal Scraping')
        CONJUNCTIVAL   = 'CONJUNCTIVAL',   _('Conjunctival Swab')
        CSF            = 'CSF',            _('Cerebrospinal Fluid')
        TISSUE         = 'TISSUE',         _('Tissue / Biopsy')
        OTHER          = 'OTHER',          _('Other')

    class ArrivalCondition(models.TextChoices):
        GOOD       = 'GOOD',       _('Good')
        HAEMOLYSED = 'HAEMOLYSED', _('Haemolysed')
        LIPEMIC    = 'LIPEMIC',    _('Lipemic')
        ICTERIC    = 'ICTERIC',    _('Icteric')
        CLOTTED    = 'CLOTTED',    _('Clotted')
        DAMAGED    = 'DAMAGED',    _('Damaged / Leaking')

    order = models.OneToOneField(LabOrder, on_delete=models.CASCADE, related_name='sample_collection')
    sample_id = models.CharField(max_length=30, unique=True)  # accession number
    collected_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True,
        related_name='collected_samples',
    )
    collection_date = models.DateTimeField(auto_now_add=True)
    sample_type = models.CharField(max_length=20, choices=SampleType.choices)
    notes = models.TextField(blank=True)

    # ── Enhanced specimen tracking ───────────────────────────────────────
    identity_verified = models.BooleanField(
        default=False,
        help_text='Two-identifier patient verification performed',
    )
    identity_method = models.CharField(
        max_length=30, blank=True,
        help_text='Verification method (e.g. wristband + verbal, photo ID)',
    )
    container_used = models.CharField(
        max_length=20, choices=ContainerType.choices, blank=True,
    )
    volume_ml = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text='Volume collected in mL',
    )
    collection_site = models.CharField(
        max_length=50, blank=True,
        help_text='e.g. Left antecubital fossa, Right hand',
    )
    fasting_status = models.BooleanField(
        null=True, blank=True,
        help_text='Was patient fasting? (null = not applicable)',
    )

    # ── Lab receipt (separate from collection) ───────────────────────────
    received_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='received_samples',
    )
    received_at = models.DateTimeField(null=True, blank=True)
    condition_on_arrival = models.CharField(
        max_length=15, choices=ArrivalCondition.choices,
        default=ArrivalCondition.GOOD,
    )

    class Meta:
        verbose_name = 'Sample Collection'

    def save(self, *args, **kwargs):
        if not self.sample_id:
            today = timezone.localdate()
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

    def __str__(self):
        return f"{self.sample_id} — {self.order.patient.full_name}"


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
        WRONG_PATIENT   = 'WRONG_PATIENT',    _('Wrong patient / mismatch')
        WRONG_VOLUME    = 'WRONG_VOLUME',     _('Wrong fill volume')
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


# ═══════════════════════════════════════════════════════════════════════════════
# RESULTS & VALIDATION — ISO 15189 §5.7 / §5.8
# ═══════════════════════════════════════════════════════════════════════════════

class LabResult(AuditModel):
    order_item = models.OneToOneField(LabOrderItem, on_delete=models.CASCADE, related_name='result')
    performed_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True,
        related_name='performed_lab_tests',
    )

    # Two-stage validation
    verified_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='verified_lab_tests',
        help_text='Technical validator (senior tech)',
    )
    is_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)

    # Biologist / pathologist authorization (separate from tech validation)
    authorized_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='authorized_lab_results',
        help_text='Biologist / pathologist who authorised release',
    )
    authorized_at = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)

    # Result data
    result_value = models.CharField(max_length=200)
    result_unit = models.CharField(max_length=50, blank=True)
    reference_range = models.CharField(max_length=100, blank=True)
    is_abnormal = models.BooleanField(default=False)
    is_critical = models.BooleanField(default=False)
    result_date = models.DateTimeField(auto_now_add=True)
    comment = models.TextField(blank=True)

    # ── Result state machine ─────────────────────────────────────────────
    result_status = models.CharField(
        max_length=15, choices=ResultStatus.choices, default=ResultStatus.PENDING,
    )
    auto_verified = models.BooleanField(
        default=False, help_text='Result passed autoverification rules',
    )
    version_number = models.PositiveIntegerField(default=1)

    # ── Delta check ──────────────────────────────────────────────────────
    delta_check_value = models.CharField(
        max_length=200, blank=True,
        help_text='Previous result value for comparison',
    )
    delta_check_flagged = models.BooleanField(default=False)
    delta_check_percent = models.DecimalField(
        max_digits=6, decimal_places=1, null=True, blank=True,
        help_text='Calculated % change from previous',
    )

    # ── Critical value notification — JCI IPSG.2 ────────────────────────
    critical_acknowledged_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='acknowledged_critical_results',
    )
    critical_acknowledged_at = models.DateTimeField(null=True, blank=True)
    critical_notified_to = models.CharField(
        max_length=200, blank=True,
        help_text='Name of person notified of critical value',
    )
    critical_read_back_confirmed = models.BooleanField(default=False)
    critical_read_back_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Lab Result'

    def __str__(self):
        flag = ' [CRITICAL]' if self.is_critical else (' [ABNORMAL]' if self.is_abnormal else '')
        return f"{self.order_item.test_type.name}: {self.result_value} {self.result_unit}{flag}"

    def save(self, **kwargs):
        # Auto-invoke delta check and critical flag before saving
        if self.result_value and self.order_item_id:
            self.perform_delta_check()
            self.auto_flag_critical()
        super().save(**kwargs)

    def perform_delta_check(self):
        """Compare with most recent previous result for same test + patient."""
        test = self.order_item.test_type
        if not test.delta_check_percent:
            return
        cutoff = timezone.now() - timezone.timedelta(hours=test.delta_check_hours)
        prev = (
            LabResult.objects.filter(
                order_item__test_type=test,
                order_item__order__patient=self.order_item.order.patient,
                is_deleted=False,
                result_date__gte=cutoff,
            )
            .exclude(pk=self.pk)
            .order_by('-result_date')
            .first()
        )
        if not prev:
            return
        self.delta_check_value = prev.result_value
        try:
            old_val = float(prev.result_value)
            new_val = float(self.result_value)
            if old_val != 0:
                pct = abs((new_val - old_val) / old_val) * 100
                self.delta_check_percent = round(pct, 1)
                if pct > float(test.delta_check_percent):
                    self.delta_check_flagged = True
        except (ValueError, TypeError):
            pass

    def auto_flag_critical(self):
        """Auto-flag critical based on test type thresholds."""
        test = self.order_item.test_type
        try:
            val = float(self.result_value)
            if test.critical_low is not None and val < float(test.critical_low):
                self.is_critical = True
            elif test.critical_high is not None and val > float(test.critical_high):
                self.is_critical = True
        except (ValueError, TypeError):
            pass


class LabResultAmendment(AuditModel):
    """ISO 15189 §5.8.3 — Audit trail whenever a result value is corrected."""
    result = models.ForeignKey(LabResult, on_delete=models.CASCADE, related_name='amendments')
    original_value = models.CharField(max_length=200)
    new_value = models.CharField(max_length=200, blank=True)
    amended_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True)
    reason = models.TextField()
    version_number = models.PositiveIntegerField(default=1)
    doctor_re_notified = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Lab Result Amendment'

    def __str__(self):
        return f"Amendment v{self.version_number} — {self.result} (was: {self.original_value})"


class ResultAcknowledgment(TimeStampedModel):
    """Track whether the ordering doctor has seen / acknowledged a result."""
    result = models.ForeignKey(LabResult, on_delete=models.CASCADE, related_name='acknowledgments')
    acknowledged_by = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE,
        related_name='acknowledged_results',
    )
    acknowledged_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = [('result', 'acknowledged_by')]
        ordering = ['-acknowledged_at']
        verbose_name = 'Result Acknowledgment'

    def __str__(self):
        return f"{self.acknowledged_by.get_full_name()} → {self.result}"


# ═══════════════════════════════════════════════════════════════════════════════
# QUALITY CONTROL — ISO 15189 §5.6
# ═══════════════════════════════════════════════════════════════════════════════

class QCRecord(AuditModel):
    """Internal QC run record — Levey-Jennings / Westgard compliance."""
    class Level(models.TextChoices):
        LOW    = 'LOW',    _('Low')
        NORMAL = 'NORMAL', _('Normal')
        HIGH   = 'HIGH',   _('High')

    class WestgardRule(models.TextChoices):
        NONE   = 'NONE',   _('No violation')
        R_1_2S = '1_2S',   _('1-2s warning')
        R_1_3S = '1_3S',   _('1-3s rejection')
        R_2_2S = '2_2S',   _('2-2s rejection')
        R_R_4S = 'R_4S',   _('R-4s rejection')
        R_4_1S = '4_1S',   _('4-1s rejection')
        R_10X  = '10X',    _('10x rejection')

    test_type = models.ForeignKey(LabTestType, on_delete=models.PROTECT, related_name='qc_records')
    run_date = models.DateTimeField()
    qc_material = models.CharField(max_length=100, help_text='QC material name')
    lot_number = models.CharField(max_length=50)
    level = models.CharField(max_length=10, choices=Level.choices)

    # Values
    target_value = models.DecimalField(max_digits=10, decimal_places=3)
    observed_value = models.DecimalField(max_digits=10, decimal_places=3)
    target_sd = models.DecimalField(max_digits=8, decimal_places=3, help_text='Target SD')
    calculated_z_score = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
    )

    # Westgard
    westgard_rule = models.CharField(
        max_length=10, choices=WestgardRule.choices, default=WestgardRule.NONE,
    )
    is_acceptable = models.BooleanField(default=True)

    # Reagent tracking
    reagent_lot = models.CharField(max_length=50, blank=True)
    reagent_expiry = models.DateField(null=True, blank=True)
    calibration_date = models.DateField(null=True, blank=True)

    performed_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True)
    notes = models.TextField(blank=True)
    corrective_action = models.TextField(blank=True)

    class Meta:
        ordering = ['-run_date']
        verbose_name = 'QC Record'

    def save(self, *args, **kwargs):
        # Auto-calculate z-score
        if self.target_sd and self.target_sd != 0:
            z = (self.observed_value - self.target_value) / self.target_sd
            self.calculated_z_score = round(z, 2)
            # Auto Westgard 1-3s check
            if abs(z) > 3 and self.westgard_rule == self.WestgardRule.NONE:
                self.westgard_rule = self.WestgardRule.R_1_3S
                self.is_acceptable = False
            elif abs(z) > 2 and self.westgard_rule == self.WestgardRule.NONE:
                self.westgard_rule = self.WestgardRule.R_1_2S
        super().save(*args, **kwargs)

    def __str__(self):
        return f"QC {self.test_type.code} — {self.run_date:%d/%m/%Y} [{self.get_level_display()}]"


class AutoverificationRule(TimeStampedModel):
    """Rules for auto-releasing normal, in-range, QC-passed results."""
    test_type = models.OneToOneField(
        LabTestType, on_delete=models.CASCADE, related_name='autoverification_rule',
    )
    is_active = models.BooleanField(default=False)
    min_value = models.DecimalField(
        max_digits=10, decimal_places=3, null=True, blank=True,
        help_text='Minimum acceptable value for auto-release',
    )
    max_value = models.DecimalField(
        max_digits=10, decimal_places=3, null=True, blank=True,
        help_text='Maximum acceptable value for auto-release',
    )
    max_delta_percent = models.DecimalField(
        max_digits=5, decimal_places=1, null=True, blank=True,
        help_text='Max delta check % for auto-release',
    )
    require_qc_pass = models.BooleanField(
        default=True, help_text='Block auto-release if latest QC run failed',
    )
    require_no_flags = models.BooleanField(
        default=True, help_text='Block if result is abnormal or critical',
    )

    class Meta:
        verbose_name = 'Autoverification Rule'

    def check_result(self, result):
        """Return True if result passes all autoverification criteria."""
        if not self.is_active:
            return False

        # Must not be flagged
        if self.require_no_flags and (result.is_abnormal or result.is_critical):
            return False

        # Must be in range
        try:
            val = float(result.result_value)
            if self.min_value is not None and val < float(self.min_value):
                return False
            if self.max_value is not None and val > float(self.max_value):
                return False
        except (ValueError, TypeError):
            return False  # Non-numeric results can't be auto-verified

        # Delta check
        if self.max_delta_percent and result.delta_check_flagged:
            if result.delta_check_percent and result.delta_check_percent > self.max_delta_percent:
                return False

        # QC check
        if self.require_qc_pass:
            latest_qc = QCRecord.objects.filter(
                test_type=self.test_type, is_acceptable=True,
            ).order_by('-run_date').first()
            if not latest_qc:
                return False
            # QC must be from today
            if latest_qc.run_date.date() != timezone.localdate():
                return False

        return True

    def __str__(self):
        return f"AutoVerify — {self.test_type.code}"


# ═══════════════════════════════════════════════════════════════════════════════
# SEND-OUT / REFERRAL TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class SendOutTest(AuditModel):
    """Track tests sent to external referral laboratories."""
    class Status(models.TextChoices):
        PENDING     = 'PENDING',     _('Pending Dispatch')
        DISPATCHED  = 'DISPATCHED',  _('Dispatched')
        IN_TRANSIT  = 'IN_TRANSIT',  _('In Transit')
        RECEIVED    = 'RECEIVED',    _('Received by Ref Lab')
        RESULTED    = 'RESULTED',    _('Result Received')
        CANCELLED   = 'CANCELLED',   _('Cancelled')

    order_item = models.OneToOneField(
        LabOrderItem, on_delete=models.CASCADE, related_name='send_out',
    )
    referral_lab_name = models.CharField(max_length=200)
    referral_lab_address = models.TextField(blank=True)
    referral_lab_phone = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PENDING)

    # Dispatch
    dispatch_date = models.DateTimeField(null=True, blank=True)
    dispatched_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='dispatched_sendouts',
    )
    courier = models.CharField(max_length=100, blank=True)
    tracking_number = models.CharField(max_length=100, blank=True)

    # Returns
    expected_return_date = models.DateField(null=True, blank=True)
    actual_return_date = models.DateField(null=True, blank=True)
    external_accession_number = models.CharField(max_length=50, blank=True)
    external_report_file = models.FileField(
        upload_to='lab/sendout_reports/%Y/%m/', blank=True,
    )

    # Costing
    external_cost = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text='Cost charged by referral lab (FCFA)',
    )
    markup_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Send-Out Test'

    @property
    def is_overdue(self):
        if self.expected_return_date and not self.actual_return_date:
            return timezone.localdate() > self.expected_return_date
        return False

    def __str__(self):
        return f"SendOut — {self.order_item.test_type.name} → {self.referral_lab_name}"


# ═══════════════════════════════════════════════════════════════════════════════
# MICROBIOLOGY — Staged reporting + Antibiogram
# ═══════════════════════════════════════════════════════════════════════════════

class CultureResult(AuditModel):
    """Microbiology culture — staged reporting (Gram/KOH → 24h → 48h → 72h)."""
    class GrowthStatus(models.TextChoices):
        PENDING          = 'PENDING',          _('Pending')
        NO_GROWTH_24H    = 'NO_GROWTH_24H',    _('No Growth at 24h')
        NO_GROWTH_48H    = 'NO_GROWTH_48H',    _('No Growth at 48h')
        NO_GROWTH_FINAL  = 'NO_GROWTH_FINAL',  _('No Growth (Final)')
        GROWTH_24H       = 'GROWTH_24H',       _('Growth at 24h')
        GROWTH_48H       = 'GROWTH_48H',       _('Growth at 48h')
        GROWTH_72H       = 'GROWTH_72H',       _('Growth at 72h')
        GROWTH_EXTENDED  = 'GROWTH_EXTENDED',   _('Growth (Extended Culture)')

    order_item = models.OneToOneField(
        LabOrderItem, on_delete=models.CASCADE, related_name='culture',
    )
    specimen_source = models.CharField(
        max_length=50,
        help_text='e.g. Corneal scraping, Conjunctival swab, Vitreous tap',
    )

    # Immediate microscopy (reported within 1 hour)
    gram_stain_result = models.TextField(blank=True)
    gram_stain_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='gram_stains',
    )
    gram_stain_at = models.DateTimeField(null=True, blank=True)
    koh_mount_result = models.TextField(blank=True, help_text='KOH mount for fungal elements')
    koh_mount_at = models.DateTimeField(null=True, blank=True)

    # Culture setup
    culture_media = models.TextField(
        blank=True,
        help_text='Media used (e.g. Blood Agar, Chocolate Agar, SDA, BHI)',
    )
    incubation_temp = models.CharField(max_length=20, blank=True, help_text='e.g. 37°C, 25°C')
    incubation_atmosphere = models.CharField(
        max_length=30, blank=True,
        help_text='e.g. Aerobic, Anaerobic, CO2 enriched',
    )

    # Staged culture readings
    growth_status = models.CharField(
        max_length=20, choices=GrowthStatus.choices, default=GrowthStatus.PENDING,
    )
    culture_read_24h = models.TextField(blank=True)
    culture_read_24h_at = models.DateTimeField(null=True, blank=True)
    culture_read_48h = models.TextField(blank=True)
    culture_read_48h_at = models.DateTimeField(null=True, blank=True)
    culture_read_72h = models.TextField(blank=True)
    culture_read_72h_at = models.DateTimeField(null=True, blank=True)

    final_report = models.TextField(blank=True)
    final_report_at = models.DateTimeField(null=True, blank=True)
    is_preliminary = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Culture Result'

    def __str__(self):
        return f"Culture — {self.specimen_source} [{self.get_growth_status_display()}]"


class OrganismIdentification(TimeStampedModel):
    """Identified organism from a culture result."""
    culture = models.ForeignKey(CultureResult, on_delete=models.CASCADE, related_name='organisms')
    organism_name = models.CharField(max_length=200)
    organism_code = models.CharField(max_length=20, blank=True, help_text='SNOMED / local code')
    colony_count = models.CharField(max_length=30, blank=True, help_text='e.g. >10^5 CFU/mL')
    identification_method = models.CharField(
        max_length=50, blank=True,
        help_text='e.g. Biochemical, VITEK, API, Molecular',
    )
    is_significant = models.BooleanField(default=True, help_text='Clinically significant isolate')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['organism_name']
        verbose_name = 'Organism Identification'

    def __str__(self):
        return f"{self.organism_name}"


class AntibioticSensitivity(TimeStampedModel):
    """Antibiotic sensitivity result for an identified organism."""
    class Sensitivity(models.TextChoices):
        SENSITIVE    = 'S', _('Sensitive')
        INTERMEDIATE = 'I', _('Intermediate')
        RESISTANT    = 'R', _('Resistant')
        NOT_TESTED   = 'NT', _('Not Tested')

    class Method(models.TextChoices):
        DISK_DIFFUSION = 'DISK',   _('Disk Diffusion (Kirby-Bauer)')
        ETEST          = 'ETEST',  _('E-test')
        VITEK          = 'VITEK',  _('VITEK / Automated')
        BROTH_MICRO    = 'BROTH',  _('Broth Microdilution')
        MANUAL         = 'MANUAL', _('Manual')

    organism = models.ForeignKey(
        OrganismIdentification, on_delete=models.CASCADE, related_name='sensitivities',
    )
    antibiotic_name = models.CharField(max_length=100)
    antibiotic_code = models.CharField(max_length=10, blank=True)
    sensitivity = models.CharField(max_length=2, choices=Sensitivity.choices)
    zone_diameter_mm = models.DecimalField(
        max_digits=5, decimal_places=1, null=True, blank=True,
    )
    mic_value = models.CharField(max_length=20, blank=True, help_text='MIC in µg/mL')
    method = models.CharField(
        max_length=10, choices=Method.choices, default=Method.DISK_DIFFUSION,
    )

    class Meta:
        ordering = ['antibiotic_name']
        verbose_name = 'Antibiotic Sensitivity'
        verbose_name_plural = 'Antibiotic Sensitivities'

    def __str__(self):
        return f"{self.antibiotic_name}: {self.get_sensitivity_display()}"


class CumulativeAntibiogram(TimeStampedModel):
    """Hospital-wide cumulative antibiogram — built from own isolates."""
    organism_name = models.CharField(max_length=200)
    antibiotic_name = models.CharField(max_length=100)
    period_start = models.DateField()
    period_end = models.DateField()
    total_isolates = models.PositiveIntegerField()
    sensitive_count = models.PositiveIntegerField()
    intermediate_count = models.PositiveIntegerField(default=0)
    resistant_count = models.PositiveIntegerField(default=0)

    @property
    def sensitivity_rate(self):
        if self.total_isolates:
            return round(self.sensitive_count / self.total_isolates * 100, 1)
        return 0

    @property
    def resistance_rate(self):
        if self.total_isolates:
            return round(self.resistant_count / self.total_isolates * 100, 1)
        return 0

    class Meta:
        unique_together = [('organism_name', 'antibiotic_name', 'period_start', 'period_end')]
        ordering = ['organism_name', 'antibiotic_name']
        verbose_name = 'Cumulative Antibiogram'

    def __str__(self):
        return f"{self.organism_name} vs {self.antibiotic_name} ({self.sensitivity_rate}% S)"


# ═══════════════════════════════════════════════════════════════════════════════
# HISTOPATHOLOGY — ISO 15189 §5.4 / §5.7
# ═══════════════════════════════════════════════════════════════════════════════

class HistopathologySpecimen(AuditModel):
    """Histopathology / cytology specimen with full reporting workflow."""
    class Status(models.TextChoices):
        ACCESSIONED = 'ACCESSIONED', _('Accessioned')
        GROSSING    = 'GROSSING',    _('Grossing')
        PROCESSING  = 'PROCESSING',  _('Tissue Processing')
        CUTTING     = 'CUTTING',     _('Microtomy / Cutting')
        STAINING    = 'STAINING',    _('Staining')
        REPORTING   = 'REPORTING',   _('Reporting')
        FINALIZED   = 'FINALIZED',   _('Finalized')
        ADDENDUM    = 'ADDENDUM',    _('Addendum Issued')

    order_item = models.OneToOneField(
        LabOrderItem, on_delete=models.CASCADE, related_name='histopath',
    )
    accession_number = models.CharField(max_length=30, unique=True)
    specimen_site = models.CharField(max_length=100, help_text='Anatomical site')
    specimen_type = models.CharField(
        max_length=50, blank=True,
        help_text='e.g. Excision, Biopsy, Curettage, Enucleation',
    )
    laterality = models.CharField(max_length=5, blank=True, help_text='OD / OS / OU / N/A')
    clinical_history = models.TextField()
    status = models.CharField(
        max_length=15, choices=Status.choices, default=Status.ACCESSIONED,
    )

    # Grossing
    gross_description = models.TextField(blank=True)
    gross_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='grossed_specimens',
    )
    gross_at = models.DateTimeField(null=True, blank=True)
    cassette_count = models.PositiveIntegerField(default=0)
    block_count = models.PositiveIntegerField(default=0)

    # Microscopy & reporting
    microscopic_description = models.TextField(blank=True)
    diagnosis = models.TextField(blank=True)
    snomed_code = models.CharField(max_length=20, blank=True, help_text='SNOMED morphology code')
    icd_o_code = models.CharField(max_length=20, blank=True, help_text='ICD-O topography/morphology')

    # Stains
    special_stains = models.JSONField(default=list, blank=True, help_text='e.g. ["PAS","GMS","ZN"]')
    ihc_stains = models.JSONField(default=list, blank=True, help_text='e.g. ["Ki-67","p53"]')

    # Pathologist sign-off
    pathologist = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='pathology_reports',
    )
    reported_at = models.DateTimeField(null=True, blank=True)

    # Storage
    storage_location = models.CharField(
        max_length=100, blank=True, help_text='Block/slide storage location for retrieval',
    )

    # Addendum
    addendum_text = models.TextField(blank=True)
    addendum_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='pathology_addenda',
    )
    addendum_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Histopathology Specimen'

    def save(self, *args, **kwargs):
        if not self.accession_number:
            today = timezone.localdate()
            prefix = f'HP-{today.strftime("%Y")}-'
            last = (HistopathologySpecimen.objects
                    .filter(accession_number__startswith=prefix)
                    .order_by('-accession_number')
                    .values_list('accession_number', flat=True)
                    .first())
            try:
                seq = int(last.split('-')[-1]) + 1 if last else 1
            except (ValueError, AttributeError, IndexError):
                seq = 1
            self.accession_number = f'{prefix}{seq:04d}'
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.accession_number} — {self.specimen_site}"


# ═══════════════════════════════════════════════════════════════════════════════
# TAT TRACKING — ISO 15189 §5.5
# ═══════════════════════════════════════════════════════════════════════════════

class TATTimestamp(TimeStampedModel):
    """Track every transition for turnaround time auditing."""
    class Event(models.TextChoices):
        ORDERED           = 'ORDERED',           _('Order Placed')
        PAYMENT_CLEARED   = 'PAYMENT_CLEARED',   _('Payment Cleared')
        COLLECTED         = 'COLLECTED',         _('Specimen Collected')
        RECEIVED_AT_LAB   = 'RECEIVED_AT_LAB',   _('Received at Lab')
        REJECTED          = 'REJECTED',          _('Specimen Rejected')
        ANALYSIS_STARTED  = 'ANALYSIS_STARTED',  _('Analysis Started')
        RESULT_ENTERED    = 'RESULT_ENTERED',    _('Result Entered')
        TECH_VALIDATED    = 'TECH_VALIDATED',     _('Technically Validated')
        AUTHORIZED        = 'AUTHORIZED',        _('Authorised')
        RELEASED          = 'RELEASED',          _('Released')
        DOCTOR_VIEWED     = 'DOCTOR_VIEWED',     _('Doctor Viewed')
        AMENDED           = 'AMENDED',           _('Amended')

    order = models.ForeignKey(LabOrder, on_delete=models.CASCADE, related_name='tat_timestamps')
    event = models.CharField(max_length=20, choices=Event.choices)
    timestamp = models.DateTimeField(default=timezone.now)
    user = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
    )
    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['timestamp']
        verbose_name = 'TAT Timestamp'

    def __str__(self):
        return f"{self.get_event_display()} — {self.timestamp:%H:%M %d/%m}"
