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

    # Right Eye (OD)
    re_sphere = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    re_cylinder = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    re_axis = models.PositiveSmallIntegerField(null=True, blank=True, help_text='0–180 degrees')
    re_add = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    re_prism = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    re_prism_base = models.CharField(max_length=20, blank=True)
    re_visual_acuity = models.CharField(max_length=20, blank=True)

    # Left Eye (OS)
    le_sphere = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    le_cylinder = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    le_axis = models.PositiveSmallIntegerField(null=True, blank=True)
    le_add = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    le_prism = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    le_prism_base = models.CharField(max_length=20, blank=True)
    le_visual_acuity = models.CharField(max_length=20, blank=True)

    # General
    interpupillary_distance = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    near_ipd = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    lens_type = models.CharField(max_length=100, blank=True, help_text='e.g. Single Vision, Bifocal, Progressive')
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
