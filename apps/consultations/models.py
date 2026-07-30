"""
Clinical consultation models — history, examination, diagnosis, plan.
Department-specific data is stored in JSON fields for flexibility.
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.core.models import AuditModel, TimeStampedModel


class ConsultationStatus(models.TextChoices):
    PENDING = 'PENDING', _('Pending')
    IN_PROGRESS = 'IN_PROGRESS', _('In Progress')
    COMPLETED = 'COMPLETED', _('Completed')
    REFERRED = 'REFERRED', _('Referred')


class Diagnosis(models.Model):
    """ICD-10 diagnosis catalogue — pre-seeded with common ophthalmic diagnoses."""
    icd10_code = models.CharField(max_length=10, unique=True)
    description = models.CharField(max_length=255)
    is_ophthalmic = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Diagnosis'
        verbose_name_plural = 'Diagnoses'
        ordering = ['icd10_code']

    def __str__(self):
        return f"{self.icd10_code} — {self.description}"


class Consultation(AuditModel):
    """
    A single doctor–patient consultation within a visit.
    One visit may have multiple consultations (e.g. referred across departments).
    """
    visit = models.ForeignKey(
        'patients.Visit',
        on_delete=models.CASCADE,
        related_name='consultations',
    )
    patient = models.ForeignKey(
        'patients.Patient',
        on_delete=models.CASCADE,
        related_name='consultations',
    )
    department = models.ForeignKey(
        'departments.Department',
        on_delete=models.SET_NULL,
        null=True,
        related_name='consultations',
    )
    consulting_doctor = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='consultations',
    )
    consultation_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=20,
        choices=ConsultationStatus.choices,
        default=ConsultationStatus.IN_PROGRESS,
    )

    # ── History ──────────────────────────────────────────────────────────────
    presenting_complaint = models.TextField(blank=True, help_text='Chief complaint in patient\'s words')
    history_of_presenting_complaint = models.TextField(blank=True)
    ocular_history = models.TextField(blank=True)
    systemic_history = models.TextField(blank=True)
    drug_history = models.TextField(blank=True, help_text='Current and recent medications')
    family_history = models.TextField(blank=True)
    social_history = models.TextField(blank=True)

    # ── Examination ───────────────────────────────────────────────────────────
    # Standard ophthalmic examination fields as structured JSON
    examination_findings = models.JSONField(
        default=dict,
        help_text='Structured ophthalmic examination data'
    )

    # Department-specific structured data (retina, glaucoma, pediatric, etc.)
    department_specific_data = models.JSONField(
        default=dict,
        help_text='Department-specific clinical data'
    )

    # ── Assessment & Plan ─────────────────────────────────────────────────────
    diagnoses = models.ManyToManyField(
        Diagnosis,
        through='ConsultationDiagnosis',
        blank=True,
    )
    management_plan = models.TextField(blank=True)
    follow_up_date = models.DateField(null=True, blank=True)
    follow_up_instructions = models.TextField(blank=True)

    # Referral
    referral_department = models.ForeignKey(
        'departments.Department',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='received_referrals',
    )
    referral_reason = models.TextField(blank=True)

    # ── Intern supervision (JCI ACC.3 / COP) ─────────────────────────────────
    co_signed_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='cosigned_consultations',
    )
    co_signed_at = models.DateTimeField(null=True, blank=True)

    @property
    def needs_cosign(self):
        """True when written by an intern and not yet co-signed by a supervisor."""
        return (
            self.consulting_doctor_id is not None
            and getattr(self.consulting_doctor, 'role', None) == 'intern'
            and self.co_signed_by_id is None
        )

    class Meta:
        ordering = ['-consultation_date']
        verbose_name = 'Consultation'
        verbose_name_plural = 'Consultations'

    def __str__(self):
        return f"Consultation — {self.patient.full_name} [{self.department}] {self.consultation_date:%d/%m/%Y}"

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('consultations:detail', kwargs={'pk': self.pk})

    @property
    def primary_diagnosis(self):
        cd = self.consultation_diagnoses.filter(is_primary=True).first()
        return cd.diagnosis if cd else None

    def get_default_examination_template(self):
        """Return blank structured examination template."""
        return {
            "visual_acuity": {
                "right_unaided": "",
                "left_unaided": "",
                "right_pinhole": "",
                "left_pinhole": "",
                "right_best_corrected": "",
                "left_best_corrected": "",
            },
            "intraocular_pressure": {
                "right": "",
                "left": "",
                "method": "Non-Contact Tonometry",
            },
            "anterior_segment": {
                "right": "",
                "left": "",
            },
            "posterior_segment": {
                "right": "",
                "left": "",
            },
            "pupils": "",
            "ocular_motility": "",
            "cover_test": "",
            "color_vision": "",
            "confrontation_fields": "",
            "slit_lamp": {
                "lids_lashes": "",
                "conjunctiva": "",
                "cornea": "",
                "anterior_chamber": "",
                "iris": "",
                "lens": "",
            },
        }


class ConsultationDiagnosis(TimeStampedModel):
    consultation = models.ForeignKey(
        Consultation,
        on_delete=models.CASCADE,
        related_name='consultation_diagnoses',
    )
    diagnosis = models.ForeignKey(Diagnosis, on_delete=models.CASCADE)
    is_primary = models.BooleanField(default=False)
    laterality = models.CharField(
        max_length=10,
        choices=[('RE', 'Right Eye'), ('LE', 'Left Eye'), ('BE', 'Both Eyes'), ('NA', 'N/A')],
        default='NA',
    )
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = [('consultation', 'diagnosis')]
        verbose_name = 'Consultation Diagnosis'


class ConsultationNote(AuditModel):
    """Addendum / progress notes attached to a consultation."""

    class NoteType(models.TextChoices):
        PROGRESS = 'PROGRESS', _('Progress Note')
        ADDENDUM = 'ADDENDUM', _('Addendum')
        NURSING = 'NURSING', _('Nursing Note')
        INTERN = 'INTERN', _('Intern Note')

    consultation = models.ForeignKey(
        Consultation,
        on_delete=models.CASCADE,
        related_name='notes',
    )
    note_type = models.CharField(max_length=15, choices=NoteType.choices, default=NoteType.PROGRESS)
    content = models.TextField()
    is_locked = models.BooleanField(default=False)
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='locked_notes',
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Consultation Note'


class ProcedureRecord(AuditModel):
    """
    Clinical procedure / minor surgery performed during or after a consultation.
    Covers laser procedures, intravitreal injections, and minor OPD operations.
    """

    class EyeChoice(models.TextChoices):
        RIGHT = 'RE', _('Right Eye (OD)')
        LEFT  = 'LE', _('Left Eye (OS)')
        BOTH  = 'BE', _('Both Eyes (OU)')
        NA    = 'NA', _('Not Eye-specific')

    class ProcedureType(models.TextChoices):
        # Laser
        SLT          = 'SLT',       _('Selective Laser Trabeculoplasty (SLT)')
        ALT          = 'ALT',       _('Argon Laser Trabeculoplasty (ALT)')
        YAG_PI       = 'YAG_PI',    _('YAG Peripheral Iridotomy')
        YAG_CAP      = 'YAG_CAP',   _('YAG Posterior Capsulotomy')
        YAG_VIT      = 'YAG_VIT',   _('YAG Vitreolysis')
        PRP          = 'PRP',       _('Panretinal Photocoagulation (PRP)')
        FOCAL_LASER  = 'FOCAL',     _('Focal / Grid Laser (Retina)')
        PHOTOCOAG    = 'PHOTOCOAG', _('Laser Photocoagulation')
        CYCLO        = 'CYCLO',     _('Cyclophotcoagulation (CPC)')
        # Injection
        ANTI_VEGF    = 'ANTI_VEGF', _('Intravitreal Anti-VEGF')
        IVT_STEROID  = 'IVT_STER',  _('Intravitreal Steroid')
        SUBCONJ      = 'SUBCONJ',   _('Subconjunctival Injection')
        AC_PARA      = 'AC_PARA',   _('Anterior Chamber Paracentesis')
        # Minor OPD
        FB_REMOVAL   = 'FB_REM',    _('Foreign Body Removal')
        EPILATION    = 'EPIL',      _('Epilation')
        CHALAZION    = 'CHALAZION', _('Chalazion I&C')
        CONJ_BIOPSY  = 'CONJ_BX',  _('Conjunctival Biopsy')
        CORN_SCRAPING= 'CORN_SC',   _('Corneal Scraping / Swab')
        SUTURE_REM   = 'SUT_REM',   _('Suture Removal')
        PTERYG       = 'PTERYG',    _('Pterygium Excision')
        OTHER        = 'OTHER',     _('Other Procedure')

    class UrgencyChoice(models.TextChoices):
        ROUTINE   = 'ROUTINE',   _('Routine')
        URGENT    = 'URGENT',    _('Urgent')
        EMERGENCY = 'EMERGENCY', _('Emergency')

    consultation  = models.ForeignKey(Consultation,       on_delete=models.CASCADE, related_name='procedures')
    patient       = models.ForeignKey('patients.Patient', on_delete=models.CASCADE,  related_name='procedures')
    procedure_date= models.DateField(auto_now_add=True)
    procedure_type= models.CharField(max_length=15, choices=ProcedureType.choices)
    eye           = models.CharField(max_length=2,  choices=EyeChoice.choices, default=EyeChoice.NA)
    urgency       = models.CharField(max_length=10, choices=UrgencyChoice.choices, default=UrgencyChoice.ROUTINE)
    performed_by  = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True,
        related_name='procedures_performed',
    )
    # IOP before/after (relevant for laser/injection procedures)
    pre_iop_re    = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, help_text='Pre-procedure IOP OD mmHg')
    pre_iop_le    = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, help_text='Pre-procedure IOP OS mmHg')
    post_iop_re   = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, help_text='Post-procedure IOP OD mmHg')
    post_iop_le   = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, help_text='Post-procedure IOP OS mmHg')
    # Laser parameters
    laser_energy  = models.CharField(max_length=80, blank=True, help_text='e.g. 800 mW × 100 ms, 50 spots')
    drug_used     = models.CharField(max_length=200, blank=True, help_text='Drug/agent used (e.g. Bevacizumab 1.25 mg)')
    notes         = models.TextField(blank=True)
    complications = models.TextField(blank=True)

    class Meta:
        ordering = ['-procedure_date', '-created_at']
        verbose_name = 'Procedure Record'
        verbose_name_plural = 'Procedure Records'

    def __str__(self):
        return f"{self.get_procedure_type_display()} — {self.patient.full_name} [{self.procedure_date}]"
