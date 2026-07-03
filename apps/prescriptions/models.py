"""
Drug prescriptions and optical (spectacle) prescriptions.
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.core.models import AuditModel, TimeStampedModel


class DrugForm(models.TextChoices):
    EYE_DROP = 'EYE_DROP', _('Eye Drop')
    EYE_OINTMENT = 'EYE_OINTMENT', _('Eye Ointment')
    EYE_GEL = 'EYE_GEL', _('Eye Gel')
    TABLET = 'TABLET', _('Tablet')
    CAPSULE = 'CAPSULE', _('Capsule')
    INJECTION = 'INJECTION', _('Injection')
    SYRUP = 'SYRUP', _('Syrup / Suspension')
    CREAM = 'CREAM', _('Cream')
    PATCH = 'PATCH', _('Patch')
    OTHER = 'OTHER', _('Other')


class RouteOfAdmin(models.TextChoices):
    TOPICAL = 'TOPICAL', _('Topical')
    ORAL = 'ORAL', _('Oral')
    IV = 'IV', _('Intravenous')
    IM = 'IM', _('Intramuscular')
    SC = 'SC', _('Subcutaneous')
    INTRAVITREAL = 'IVT', _('Intravitreal')
    SUBCONJUNCTIVAL = 'SCJ', _('Subconjunctival')
    PERIOCULAR = 'PERIOCULAR', _('Periocular')


class EyeChoice(models.TextChoices):
    RIGHT = 'RE', _('Right Eye (OD)')
    LEFT = 'LE', _('Left Eye (OS)')
    BOTH = 'BE', _('Both Eyes (OU)')
    NA = 'NA', _('N/A')


class DrugPrescription(AuditModel):
    consultation = models.ForeignKey(
        'consultations.Consultation',
        on_delete=models.CASCADE,
        related_name='drug_prescriptions',
    )
    patient = models.ForeignKey('patients.Patient', on_delete=models.CASCADE)
    prescribed_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='drug_prescriptions',
    )
    prescription_date = models.DateField(auto_now_add=True)
    is_dispensed = models.BooleanField(default=False)
    dispensed_at = models.DateTimeField(null=True, blank=True)
    dispensed_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='dispensed_prescriptions',
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-prescription_date']
        verbose_name = 'Drug Prescription'

    def __str__(self):
        return f"Rx — {self.patient.full_name} [{self.prescription_date}]"


class DrugPrescriptionItem(TimeStampedModel):
    prescription = models.ForeignKey(DrugPrescription, on_delete=models.CASCADE, related_name='items')
    drug_name = models.CharField(max_length=200)
    drug_form = models.CharField(max_length=20, choices=DrugForm.choices)
    concentration = models.CharField(max_length=50, blank=True, help_text='e.g. 0.5%, 5mg')
    dose = models.CharField(max_length=50, help_text='e.g. 1 drop, 1 tablet')
    frequency = models.CharField(max_length=50, help_text='e.g. TDS, BD, QID, OD')
    duration = models.CharField(max_length=50, help_text='e.g. 7 days, 2 weeks')
    route = models.CharField(max_length=15, choices=RouteOfAdmin.choices, default=RouteOfAdmin.TOPICAL)
    eye = models.CharField(max_length=5, choices=EyeChoice.choices, default=EyeChoice.NA)
    quantity = models.PositiveSmallIntegerField(default=1)
    special_instructions = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Prescription Item'

    def __str__(self):
        return f"{self.drug_name} {self.concentration} — {self.dose} {self.frequency}"


class OpticalPrescription(AuditModel):
    """Spectacle or contact lens prescription."""

    class PrescriptionType(models.TextChoices):
        SPECTACLE = 'SPECTACLE', _('Spectacle')
        CONTACT_LENS = 'CONTACT_LENS', _('Contact Lens')
        READING = 'READING', _('Reading Glasses')

    consultation = models.ForeignKey(
        'consultations.Consultation',
        on_delete=models.CASCADE,
        related_name='optical_prescriptions',
    )
    patient = models.ForeignKey('patients.Patient', on_delete=models.CASCADE)
    prescribed_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='optical_prescriptions',
    )
    prescription_date = models.DateField(auto_now_add=True)
    prescription_type = models.CharField(
        max_length=15,
        choices=PrescriptionType.choices,
        default=PrescriptionType.SPECTACLE,
    )

    # Right Eye (OD) — Distance
    re_sphere = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    re_cylinder = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    re_axis = models.PositiveSmallIntegerField(null=True, blank=True, help_text='0–180 degrees')
    re_add = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    re_prism = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    re_prism_base = models.CharField(max_length=20, blank=True)
    re_visual_acuity = models.CharField(max_length=20, blank=True)
    # Right Eye (OD) — Near Vision
    re_sphere_near = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    re_cylinder_near = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    re_axis_near = models.PositiveSmallIntegerField(null=True, blank=True)
    re_va_near = models.CharField(max_length=20, blank=True)

    # Left Eye (OS) — Distance
    le_sphere = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    le_cylinder = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    le_axis = models.PositiveSmallIntegerField(null=True, blank=True)
    le_add = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    le_prism = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    le_prism_base = models.CharField(max_length=20, blank=True)
    le_visual_acuity = models.CharField(max_length=20, blank=True)
    # Left Eye (OS) — Near Vision
    le_sphere_near = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    le_cylinder_near = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    le_axis_near = models.PositiveSmallIntegerField(null=True, blank=True)
    le_va_near = models.CharField(max_length=20, blank=True)

    # General
    interpupillary_distance = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    near_ipd = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    lens_type = models.CharField(max_length=500, blank=True, help_text='Comma-separated list of lens types')
    frame_advice = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    is_dispensed = models.BooleanField(default=False)

    class Meta:
        ordering = ['-prescription_date']
        verbose_name = 'Optical Prescription'

    def __str__(self):
        return f"Optical Rx — {self.patient.full_name} [{self.prescription_date}]"

    def format_sphere(self, value):
        if value is None:
            return 'Plano'
        return f"{'+' if value > 0 else ''}{value:.2f}"


# ══════════════════════════════════════════════════════════════════════════════
# DRUG INTERACTION CHECKER — JCI MMU.7
# ══════════════════════════════════════════════════════════════════════════════

class DrugInteractionSeverity(models.TextChoices):
    CONTRAINDICATED = 'CONTRA',   'Contraindicated — Do NOT co-prescribe'
    MAJOR           = 'MAJOR',    'Major — Potentially life-threatening'
    MODERATE        = 'MODERATE', 'Moderate — Monitor closely'
    MINOR           = 'MINOR',    'Minor — Clinically insignificant in most cases'


class DrugInteraction(models.Model):
    """
    Lookup table of known drug-drug interactions.
    JCI MMU.7 — clinical decision support at point of prescribing.
    Seeded via: python manage.py seed_drug_interactions
    """
    drug_a      = models.CharField(max_length=200, db_index=True)
    drug_b      = models.CharField(max_length=200, db_index=True)
    severity    = models.CharField(max_length=15, choices=DrugInteractionSeverity.choices)
    description = models.TextField(help_text='Mechanism of interaction')
    clinical_effects = models.TextField(blank=True)
    management  = models.TextField(blank=True, help_text='Avoid / Monitor / Dose-adjust')
    is_active   = models.BooleanField(default=True)

    class Meta:
        ordering = ['severity', 'drug_a']
        verbose_name = 'Drug Interaction'
        verbose_name_plural = 'Drug Interactions'
        unique_together = ('drug_a', 'drug_b')

    def __str__(self):
        return f"{self.drug_a} ↔ {self.drug_b} ({self.get_severity_display()})"

    @classmethod
    def find_interactions(cls, drug_names: list) -> list:
        """Return all active interactions between any two drugs in the list."""
        drug_names_lower = [d.lower().strip() for d in drug_names if d]
        if len(drug_names_lower) < 2:
            return []
        hits = []
        seen = set()
        for interaction in cls.objects.filter(is_active=True):
            a = interaction.drug_a.lower()
            b = interaction.drug_b.lower()
            a_match = any(a in dn or dn in a for dn in drug_names_lower)
            b_match = any(b in dn or dn in b for dn in drug_names_lower)
            if a_match and b_match:
                key = tuple(sorted([a, b]))
                if key not in seen:
                    seen.add(key)
                    hits.append(interaction)
        return hits
