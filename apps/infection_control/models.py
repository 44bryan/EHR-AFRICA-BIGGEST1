"""
Infection Control & Antibiogram Module

Covers:
- HAI (Hospital-Acquired Infection) incident reporting
- Antibiotic susceptibility tracking (antibiogram)
- Outbreak alerts
"""
import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from apps.core.models import AuditModel, TimeStampedModel


# ── HAI Report ────────────────────────────────────────────────────────────────

class HAIType(models.TextChoices):
    SSI    = 'SSI',    'Surgical Site Infection (SSI)'
    UTI    = 'UTI',    'Catheter-Associated UTI (CAUTI)'
    BSI    = 'BSI',    'Central Line BSI (CLABSI)'
    VAP    = 'VAP',    'Ventilator-Associated Pneumonia (VAP)'
    CDI    = 'CDI',    'C. difficile Infection (CDI)'
    MRSA   = 'MRSA',   'MRSA Bacteraemia'
    SKIN   = 'SKIN',   'Pressure Ulcer / Skin Breakdown'
    OTHER  = 'OTHER',  'Other HAI'


class HAIStatus(models.TextChoices):
    REPORTED     = 'REPORTED',     'Reported'
    INVESTIGATING = 'INVESTIGATING', 'Under Investigation'
    RESOLVED     = 'RESOLVED',     'Resolved'
    CLOSED       = 'CLOSED',       'Closed'


class HAIReport(AuditModel):
    """Healthcare-Associated Infection incident report."""
    report_number    = models.CharField(max_length=20, unique=True)
    patient          = models.ForeignKey('patients.Patient', on_delete=models.PROTECT,
                                          related_name='hai_reports')
    visit            = models.ForeignKey('patients.Visit', on_delete=models.PROTECT,
                                          related_name='hai_reports', null=True, blank=True)
    admission        = models.ForeignKey('ipd.Admission', on_delete=models.PROTECT,
                                          related_name='hai_reports', null=True, blank=True)
    hai_type         = models.CharField(max_length=10, choices=HAIType.choices)
    organism         = models.CharField(max_length=100, blank=True,
                                         help_text='e.g. E. coli, MRSA, Pseudomonas aeruginosa')
    onset_date       = models.DateField(default=timezone.localdate)
    status           = models.CharField(max_length=20, choices=HAIStatus.choices,
                                         default=HAIStatus.REPORTED)
    ward             = models.ForeignKey('ipd.Ward', on_delete=models.SET_NULL,
                                          null=True, blank=True, related_name='hai_reports')
    clinical_details = models.TextField(blank=True)
    root_cause       = models.TextField(blank=True)
    corrective_action = models.TextField(blank=True)
    reported_by      = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                          related_name='hai_reports_filed')
    reviewed_by      = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                          null=True, blank=True, related_name='hai_reports_reviewed')
    resolved_date    = models.DateField(null=True, blank=True)
    notes            = models.TextField(blank=True)

    class Meta:
        ordering = ['-onset_date']
        verbose_name = 'HAI Report'
        verbose_name_plural = 'HAI Reports'

    def __str__(self):
        return f'{self.report_number} — {self.patient.full_name} ({self.get_hai_type_display()})'


# ── Antibiogram / Susceptibility ─────────────────────────────────────────────

class SusceptibilityResult(models.TextChoices):
    SENSITIVE    = 'S', 'Sensitive (S)'
    INTERMEDIATE = 'I', 'Intermediate (I)'
    RESISTANT    = 'R', 'Resistant (R)'
    NOT_TESTED   = 'NT', 'Not Tested'


class AntibioticSensitivity(TimeStampedModel):
    """
    Antibiogram record — culture & sensitivity result for an organism
    isolated from a patient or environmental sample.
    """
    patient          = models.ForeignKey('patients.Patient', on_delete=models.PROTECT,
                                          related_name='sensitivity_records', null=True, blank=True)
    organism         = models.CharField(max_length=100,
                                         help_text='e.g. Staphylococcus aureus, E. coli')
    sample_type      = models.CharField(max_length=60, blank=True,
                                         help_text='e.g. Urine, Blood, Wound Swab, Sputum')
    collection_date  = models.DateField(default=timezone.localdate)
    ward             = models.ForeignKey('ipd.Ward', on_delete=models.SET_NULL,
                                          null=True, blank=True, related_name='sensitivity_records')
    # Antibiotic panel — common antibiotics used in Cameroon ophthalmic/general hospitals
    amoxicillin      = models.CharField(max_length=2, choices=SusceptibilityResult.choices,
                                         default=SusceptibilityResult.NOT_TESTED)
    ampicillin       = models.CharField(max_length=2, choices=SusceptibilityResult.choices,
                                         default=SusceptibilityResult.NOT_TESTED)
    ciprofloxacin    = models.CharField(max_length=2, choices=SusceptibilityResult.choices,
                                         default=SusceptibilityResult.NOT_TESTED)
    gentamicin       = models.CharField(max_length=2, choices=SusceptibilityResult.choices,
                                         default=SusceptibilityResult.NOT_TESTED)
    ceftriaxone      = models.CharField(max_length=2, choices=SusceptibilityResult.choices,
                                         default=SusceptibilityResult.NOT_TESTED)
    metronidazole    = models.CharField(max_length=2, choices=SusceptibilityResult.choices,
                                         default=SusceptibilityResult.NOT_TESTED)
    cotrimoxazole    = models.CharField(max_length=2, choices=SusceptibilityResult.choices,
                                         default=SusceptibilityResult.NOT_TESTED)
    erythromycin     = models.CharField(max_length=2, choices=SusceptibilityResult.choices,
                                         default=SusceptibilityResult.NOT_TESTED)
    tetracycline     = models.CharField(max_length=2, choices=SusceptibilityResult.choices,
                                         default=SusceptibilityResult.NOT_TESTED)
    meropenem        = models.CharField(max_length=2, choices=SusceptibilityResult.choices,
                                         default=SusceptibilityResult.NOT_TESTED)
    notes            = models.TextField(blank=True)
    recorded_by      = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                          related_name='sensitivity_records_entered',
                                          null=True, blank=True)

    ANTIBIOTIC_FIELDS = [
        'amoxicillin', 'ampicillin', 'ciprofloxacin', 'gentamicin',
        'ceftriaxone', 'metronidazole', 'cotrimoxazole', 'erythromycin',
        'tetracycline', 'meropenem',
    ]

    class Meta:
        ordering = ['-collection_date']
        verbose_name = 'Antibiotic Sensitivity'
        verbose_name_plural = 'Antibiogram Records'

    def __str__(self):
        return f'{self.organism} ({self.sample_type}) — {self.collection_date}'


# ── Outbreak Alert ────────────────────────────────────────────────────────────

class AlertLevel(models.TextChoices):
    WATCH    = 'WATCH',    'Watch'
    WARNING  = 'WARNING',  'Warning'
    OUTBREAK = 'OUTBREAK', 'Outbreak'
    RESOLVED = 'RESOLVED', 'Resolved'


class OutbreakAlert(AuditModel):
    """Outbreak / cluster alert issued by the Infection Control team."""
    title          = models.CharField(max_length=200)
    pathogen       = models.CharField(max_length=100, blank=True)
    alert_level    = models.CharField(max_length=10, choices=AlertLevel.choices,
                                       default=AlertLevel.WATCH)
    affected_areas = models.CharField(max_length=300, blank=True,
                                       help_text='e.g. Ward A, ICU, Outpatient OPD')
    onset_date     = models.DateField(default=timezone.localdate)
    resolved_date  = models.DateField(null=True, blank=True)
    case_count     = models.PositiveIntegerField(default=1)
    description    = models.TextField()
    actions_taken  = models.TextField(blank=True)
    is_active      = models.BooleanField(default=True)
    issued_by      = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                        related_name='outbreak_alerts_issued')

    class Meta:
        ordering = ['-onset_date']
        verbose_name = 'Outbreak Alert'
        verbose_name_plural = 'Outbreak Alerts'

    def __str__(self):
        return f'[{self.alert_level}] {self.title} — {self.onset_date}'
