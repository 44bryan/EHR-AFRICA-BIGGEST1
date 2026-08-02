"""
Outreach Department — community eye camps, school screenings, mobile clinics.
Supports offline field operations with full sync back to hospital server.
"""
import uuid, random, string
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from apps.core.models import TimeStampedModel, AuditModel


# ─── Choices ──────────────────────────────────────────────────────────────────

class OutreachType(models.TextChoices):
    EYE_CAMP         = 'EYE_CAMP',         _('Eye Camp (Community)')
    SCHOOL_SCREENING = 'SCHOOL_SCREENING',  _('School Screening')
    MOBILE_CLINIC    = 'MOBILE_CLINIC',     _('Mobile Eye Clinic')
    CORPORATE        = 'CORPORATE',         _('Corporate Health Screening')
    VILLAGE_VISIT    = 'VILLAGE_VISIT',     _('Village / Rural Visit')
    CHURCH_CAMP      = 'CHURCH_CAMP',       _('Church / Faith Community Camp')
    OTHER            = 'OTHER',             _('Other')


class OutreachStatus(models.TextChoices):
    PLANNED      = 'PLANNED',     _('Planned')
    IN_PROGRESS  = 'IN_PROGRESS', _('In Progress')
    COMPLETED    = 'COMPLETED',   _('Completed')
    CANCELLED    = 'CANCELLED',   _('Cancelled')
    POSTPONED    = 'POSTPONED',   _('Postponed')


class Sex(models.TextChoices):
    MALE    = 'M', _('Male')
    FEMALE  = 'F', _('Female')
    UNKNOWN = 'U', _('Not Specified')


class ReferralUrgency(models.TextChoices):
    ROUTINE   = 'ROUTINE',   _('Routine (within 1 month)')
    URGENT    = 'URGENT',    _('Urgent (within 1 week)')
    EMERGENCY = 'EMERGENCY', _('Emergency (same day)')


class ReferralStatus(models.TextChoices):
    PENDING         = 'PENDING',         _('Pending — Not Yet Arrived')
    ARRIVED         = 'ARRIVED',         _('Arrived at Hospital')
    IN_TREATMENT    = 'IN_TREATMENT',    _('Currently in Treatment')
    COMPLETED       = 'COMPLETED',       _('Treatment Completed')
    DID_NOT_ATTEND  = 'DID_NOT_ATTEND',  _('Did Not Attend')
    REFERRED_OUT    = 'REFERRED_OUT',    _('Referred to Another Facility')


class IOPMethod(models.TextChoices):
    NCT         = 'NCT',         _('Non-Contact (Air Puff)')
    APPLANATION = 'APPLANATION', _('Goldmann Applanation')
    TONOPEN     = 'TONOPEN',     _('Tono-Pen')
    ICARE       = 'ICARE',       _('iCare Rebound')
    SCHIOTZ     = 'SCHIOTZ',     _('Schiotz')


class SyncStatus(models.TextChoices):
    PENDING  = 'PENDING',  _('Pending Sync')
    SUCCESS  = 'SUCCESS',  _('Synced Successfully')
    FAILED   = 'FAILED',   _('Sync Failed')
    PARTIAL  = 'PARTIAL',  _('Partially Synced')


# ─── OutreachActivity ─────────────────────────────────────────────────────────

class OutreachActivity(TimeStampedModel):
    """A single outreach event (camp, school visit, mobile clinic, etc.)."""
    title         = models.CharField(max_length=200)
    activity_type = models.CharField(max_length=30, choices=OutreachType.choices,
                                     default=OutreachType.EYE_CAMP)
    status        = models.CharField(max_length=20, choices=OutreachStatus.choices,
                                     default=OutreachStatus.PLANNED)

    # Location
    location_name   = models.CharField(max_length=200, help_text='School, village, company name')
    region          = models.CharField(max_length=100, blank=True)
    town            = models.CharField(max_length=100, blank=True)
    gps_coordinates = models.CharField(max_length=60, blank=True)

    # Schedule
    activity_date = models.DateField()
    end_date      = models.DateField(null=True, blank=True)
    start_time    = models.TimeField(null=True, blank=True)
    end_time      = models.TimeField(null=True, blank=True)

    # Team
    team_leader = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='led_outreach', limit_choices_to={'is_active': True},
    )
    team_members = models.ManyToManyField(
        'accounts.User', blank=True, related_name='outreach_activities',
    )
    vehicle_details = models.CharField(max_length=200, blank=True)
    equipment_notes = models.TextField(blank=True)

    # Partner / Sponsor
    partner_org    = models.CharField(max_length=200, blank=True)
    sponsor        = models.CharField(max_length=200, blank=True)
    sponsor_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    budget_fcfa    = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                     help_text='Total approved budget for this activity (FCFA)')

    # Targets
    target_screened = models.PositiveIntegerField(default=0,
                      help_text='Target number of people to screen')

    # Notes
    objectives      = models.TextField(blank=True)
    notes           = models.TextField(blank=True)
    challenges      = models.TextField(blank=True)
    recommendations = models.TextField(blank=True)

    class Meta:
        ordering = ['-activity_date']
        verbose_name = 'Outreach Activity'
        verbose_name_plural = 'Outreach Activities'

    def __str__(self):
        return f'{self.title} — {self.activity_date}'

    @property
    def total_screened(self):
        return self.patients.count()

    @property
    def total_examined(self):
        return self.patients.filter(examination__isnull=False).count()

    @property
    def total_referred(self):
        return OutreachReferral.objects.filter(patient__activity=self).count()

    @property
    def total_arrived(self):
        return OutreachReferral.objects.filter(
            patient__activity=self,
            status__in=[ReferralStatus.ARRIVED, ReferralStatus.IN_TREATMENT, ReferralStatus.COMPLETED]
        ).count()

    @property
    def referral_conversion_rate(self):
        ref = self.total_referred
        if not ref:
            return 0
        return round(self.total_arrived / ref * 100, 1)

    @property
    def total_cost(self):
        from django.db.models import Sum
        agg = self.records.aggregate(
            d=Sum('drugs_cost'), t=Sum('transport_cost'), o=Sum('other_cost')
        )
        return (agg['d'] or 0) + (agg['t'] or 0) + (agg['o'] or 0)

    @property
    def cost_per_patient(self):
        n = self.total_screened
        if not n:
            return 0
        return round(float(self.total_cost) / n, 0)

    @property
    def days_duration(self):
        if self.end_date and self.end_date > self.activity_date:
            return (self.end_date - self.activity_date).days + 1
        return 1


# ─── OutreachRecord (aggregate daily stats — kept for backward compat) ────────

class OutreachRecord(TimeStampedModel):
    """Daily/session aggregate statistics for an outreach activity."""
    activity    = models.ForeignKey(OutreachActivity, on_delete=models.CASCADE,
                                    related_name='records')
    record_date = models.DateField()
    recorded_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='outreach_records',
    )

    total_screened    = models.PositiveIntegerField(default=0)
    male_screened     = models.PositiveIntegerField(default=0)
    female_screened   = models.PositiveIntegerField(default=0)
    children_screened = models.PositiveIntegerField(default=0)
    elderly_screened  = models.PositiveIntegerField(default=0)

    normal_vision        = models.PositiveIntegerField(default=0)
    refractive_errors    = models.PositiveIntegerField(default=0)
    cataract             = models.PositiveIntegerField(default=0)
    glaucoma_suspects    = models.PositiveIntegerField(default=0)
    diabetic_retinopathy = models.PositiveIntegerField(default=0)
    pterygium            = models.PositiveIntegerField(default=0)
    trachoma             = models.PositiveIntegerField(default=0)
    corneal_opacity      = models.PositiveIntegerField(default=0)
    other_pathology      = models.PositiveIntegerField(default=0)

    glasses_dispensed    = models.PositiveIntegerField(default=0)
    medications_given    = models.PositiveIntegerField(default=0)
    surgeries_performed  = models.PositiveIntegerField(default=0)
    total_treated        = models.PositiveIntegerField(default=0)
    total_referred       = models.PositiveIntegerField(default=0)

    referred_cataract = models.PositiveIntegerField(default=0)
    referred_glaucoma = models.PositiveIntegerField(default=0)
    referred_retina   = models.PositiveIntegerField(default=0)
    referred_other    = models.PositiveIntegerField(default=0)

    drugs_cost     = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    transport_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    other_cost     = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['record_date']
        unique_together = [['activity', 'record_date']]

    def __str__(self):
        return f'{self.activity.title} — {self.record_date}'

    @property
    def total_cost(self):
        return self.drugs_cost + self.transport_cost + self.other_cost


# ─── OutreachPatient ──────────────────────────────────────────────────────────

def _gen_patient_id():
    year = timezone.now().year
    suffix = ''.join(random.choices(string.digits, k=5))
    return f'OP-{year}-{suffix}'


class OutreachPatient(TimeStampedModel):
    """Individual patient seen during an outreach activity."""
    activity         = models.ForeignKey(OutreachActivity, on_delete=models.CASCADE,
                                         related_name='patients')
    outreach_patient_id = models.CharField(max_length=20, unique=True,
                          default=_gen_patient_id, editable=False,
                          help_text='Auto-generated field ID e.g. OP-2026-00123')
    registered_by    = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='outreach_registered',
    )

    # Demographics
    first_name   = models.CharField(max_length=100)
    last_name    = models.CharField(max_length=100)
    date_of_birth = models.DateField(null=True, blank=True)
    age_years    = models.PositiveSmallIntegerField(null=True, blank=True,
                   help_text='Age in years if DOB unknown')
    sex          = models.CharField(max_length=1, choices=Sex.choices, default=Sex.UNKNOWN)
    village      = models.CharField(max_length=150, blank=True)
    district     = models.CharField(max_length=150, blank=True)
    phone        = models.CharField(max_length=20, blank=True)
    next_of_kin  = models.CharField(max_length=200, blank=True)

    # Previous history (quick intake)
    known_diabetic    = models.BooleanField(default=False)
    known_hypertensive = models.BooleanField(default=False)
    previous_eye_surgery = models.BooleanField(default=False)
    chief_complaint   = models.CharField(max_length=300, blank=True)

    # Link to main hospital registry (set after patient arrives at hospital)
    hospital_patient = models.ForeignKey(
        'patients.Patient', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='outreach_records',
        help_text='Linked to main registry when patient arrives at hospital',
    )

    # Offline sync tracking
    is_synced       = models.BooleanField(default=False)
    field_device_id = models.CharField(max_length=100, blank=True,
                      help_text='Device that created this record (for conflict detection)')

    class Meta:
        ordering = ['last_name', 'first_name']
        verbose_name = 'Outreach Patient'

    def __str__(self):
        return f'{self.full_name} [{self.outreach_patient_id}]'

    @property
    def full_name(self):
        return f'{self.first_name} {self.last_name}'.strip()

    @property
    def age_display(self):
        if self.date_of_birth:
            from datetime import date
            delta = date.today() - self.date_of_birth
            return f'{delta.days // 365} yrs'
        if self.age_years:
            return f'{self.age_years} yrs'
        return '—'

    @property
    def has_examination(self):
        return hasattr(self, 'examination')

    @property
    def has_referral(self):
        return hasattr(self, 'referral')


# ─── OutreachExamination ──────────────────────────────────────────────────────

# VA choices — Snellen + qualifier values
VA_CHOICES = [
    ('6/6',  '6/6 (LogMAR 0.0)'),
    ('6/9',  '6/9 (LogMAR 0.18)'),
    ('6/12', '6/12 (LogMAR 0.3)'),
    ('6/18', '6/18 (LogMAR 0.48)'),
    ('6/24', '6/24 (LogMAR 0.6)'),
    ('6/36', '6/36 (LogMAR 0.78)'),
    ('6/60', '6/60 (LogMAR 1.0)'),
    ('3/60', '3/60 (LogMAR 1.3)'),
    ('2/60', '2/60 (LogMAR 1.48)'),
    ('1/60', '1/60 (LogMAR 1.78)'),
    ('HM',   'HM — Hand Movement'),
    ('PL',   'PL — Perception of Light'),
    ('NPL',  'NPL — No Perception of Light'),
    ('NT',   'NT — Not Tested'),
]

# LogMAR equivalents for WHO classification calculations
VA_LOGMAR = {
    '6/6': 0.00, '6/9': 0.18, '6/12': 0.30, '6/18': 0.48,
    '6/24': 0.60, '6/36': 0.78, '6/60': 1.00,
    '3/60': 1.30, '2/60': 1.48, '1/60': 1.78,
    'HM': 2.00, 'PL': 2.90, 'NPL': 3.00, 'NT': None,
}

# WHO 2019 Visual Impairment Grade (based on presenting VA, better eye)
# Grade 0=Normal, 1=Mild, 2=Moderate, 3=Severe, 4=Blind
def _va_to_who_grade(va_str):
    """Return WHO VI grade 0-4 from a Snellen VA string."""
    lm = VA_LOGMAR.get(va_str)
    if lm is None:
        return None
    if lm <= 0.30:  return 0   # Normal ≥6/12
    if lm <= 0.48:  return 1   # Mild <6/12 to ≥6/18
    if lm <= 1.00:  return 2   # Moderate <6/18 to ≥6/60
    if lm <= 1.30:  return 3   # Severe <6/60 to ≥3/60
    return 4                    # Blind <3/60


WHO_VI_GRADE_LABELS = {
    0: ('Normal Vision', 'success'),
    1: ('Mild Impairment', 'info'),
    2: ('Moderate Impairment', 'warning'),
    3: ('Severe Impairment', 'danger'),
    4: ('Blindness', 'dark'),
}

# ICD-11 codes alongside readable labels (WHO ICD-11 2022 release)
# Format: (internal_code, display_label, icd11_code)
DIAGNOSIS_ICD11 = [
    ('NORMAL',              'Normal / No Pathology',              '—'),
    ('REFRACTIVE_ERROR',    'Refractive Error',                   '9D00'),
    ('CATARACT',            'Cataract',                           '9B10'),
    ('GLAUCOMA_SUSPECT',    'Glaucoma Suspect',                   '9C61.Z'),
    ('GLAUCOMA',            'Glaucoma (Confirmed)',                '9C61'),
    ('DIABETIC_RETINOPATHY','Diabetic Retinopathy',               '9B71'),
    ('AMD',                 'Age-related Macular Degeneration',   '9B36'),
    ('PTERYGIUM',           'Pterygium',                          '9A84'),
    ('TRACHOMA',            'Trachoma',                           '1C23'),
    ('CORNEAL_OPACITY',     'Corneal Opacity / Scar',             '9A75'),
    ('DRY_EYE',             'Dry Eye Syndrome',                   '9A60'),
    ('CONJUNCTIVITIS',      'Conjunctivitis',                     '9A00'),
    ('AMBLYOPIA',           'Amblyopia (Lazy Eye)',               '9D40'),
    ('STRABISMUS',          'Strabismus',                         '9C80'),
    ('RETINAL_DETACHMENT',  'Retinal Detachment',                 '9B73'),
    ('UVEITIS',             'Uveitis',                            '9B50'),
    ('NYSTAGMUS',           'Nystagmus',                          '9C90'),
    ('ONCHOCERCIASIS',      'Onchocerciasis (River Blindness)',   '1F84'),
    ('CORNEAL_ULCER',       'Corneal Ulcer',                      '9A70'),
    ('OPTIC_ATROPHY',       'Optic Atrophy',                      '9C30'),
    ('RETINOPATHY_PREMATURITY', 'Retinopathy of Prematurity',    '9B60'),
    ('OTHER',               'Other — see notes',                  'QA00'),
]
# Backwards-compatible DIAGNOSIS_CHOICES tuple
DIAGNOSIS_CHOICES = [(c, l) for c, l, _ in DIAGNOSIS_ICD11]
# Map code → (label, icd11)
DIAGNOSIS_ICD11_MAP = {c: (l, icd) for c, l, icd in DIAGNOSIS_ICD11}

# WHO Principal Cause of Visual Impairment (World Report on Vision 2019)
class PrincipalCause(models.TextChoices):
    REFRACTIVE_ERROR    = 'REFRACTIVE_ERROR',    _('Uncorrected Refractive Error')
    CATARACT            = 'CATARACT',            _('Cataract (Unoperated)')
    GLAUCOMA            = 'GLAUCOMA',            _('Glaucoma')
    AMD                 = 'AMD',                 _('Age-related Macular Degeneration')
    DIABETIC_RETINOPATHY= 'DIABETIC_RETINOPATHY',_('Diabetic Retinopathy')
    CORNEAL_OPACITY     = 'CORNEAL_OPACITY',     _('Corneal Opacity')
    TRACHOMA            = 'TRACHOMA',            _('Trachoma')
    ONCHOCERCIASIS      = 'ONCHOCERCIASIS',      _('Onchocerciasis')
    OTHER               = 'OTHER',               _('Other / Undetermined')
    NORMAL              = 'NORMAL',              _('No Visual Impairment')

# Pupil reaction choices
class PupilReaction(models.TextChoices):
    NORMAL      = 'NORMAL',      _('Normal / Reactive')
    SLUGGISH    = 'SLUGGISH',    _('Sluggish')
    RAPD        = 'RAPD',        _('RAPD Present (Relative Afferent Pupillary Defect)')
    FIXED       = 'FIXED',       _('Fixed / Non-reactive')
    NOT_TESTED  = 'NT',          _('Not Tested')

# Confrontation Visual Field
class ConfVF(models.TextChoices):
    FULL        = 'FULL',        _('Full to Confrontation')
    CONSTRICTED = 'CONSTRICTED', _('Constricted')
    NASAL_DEFECT= 'NASAL',       _('Nasal Field Defect')
    TEMPORAL    = 'TEMPORAL',    _('Temporal Field Defect')
    HEMIANOPIA  = 'HEMIANOPIA',  _('Hemianopia')
    SCOTOMA     = 'SCOTOMA',     _('Central Scotoma')
    NOT_TESTED  = 'NT',          _('Not Tested')

# Color Vision
class ColorVision(models.TextChoices):
    NORMAL      = 'NORMAL',      _('Normal')
    DEFECTIVE   = 'DEFECTIVE',   _('Color Vision Defect')
    NOT_TESTED  = 'NT',          _('Not Tested')


class OutreachExamination(AuditModel):
    """
    Full ophthalmic examination for an outreach patient.
    One-to-one with OutreachPatient.
    """
    patient  = models.OneToOneField(OutreachPatient, on_delete=models.CASCADE,
                                    related_name='examination')
    examiner = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='outreach_examinations',
    )
    exam_date = models.DateField(default=timezone.localdate)

    # ── Visual Acuity ─────────────────────────────────────────
    va_re_distance         = models.CharField(max_length=10, blank=True, default='',
                             verbose_name='RE Distance (Unaided)')
    va_le_distance         = models.CharField(max_length=10, blank=True, default='',
                             verbose_name='LE Distance (Unaided)')
    va_re_distance_ph      = models.CharField(max_length=10, blank=True, default='',
                             verbose_name='RE Distance (Pinhole)')
    va_le_distance_ph      = models.CharField(max_length=10, blank=True, default='',
                             verbose_name='LE Distance (Pinhole)')
    va_re_distance_corrected = models.CharField(max_length=10, blank=True, default='',
                               verbose_name='RE Distance (Best Corrected)')
    va_le_distance_corrected = models.CharField(max_length=10, blank=True, default='',
                               verbose_name='LE Distance (Best Corrected)')
    va_re_near             = models.CharField(max_length=10, blank=True, default='',
                             verbose_name='RE Near')
    va_le_near             = models.CharField(max_length=10, blank=True, default='',
                             verbose_name='LE Near')

    # ── Refraction ────────────────────────────────────────────
    re_sphere = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True,
                verbose_name='RE Sphere (DS)')
    re_cylinder = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True,
                  verbose_name='RE Cylinder (DC)')
    re_axis   = models.PositiveSmallIntegerField(null=True, blank=True,
                verbose_name='RE Axis (°)')
    le_sphere = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True,
                verbose_name='LE Sphere (DS)')
    le_cylinder = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True,
                  verbose_name='LE Cylinder (DC)')
    le_axis   = models.PositiveSmallIntegerField(null=True, blank=True,
                verbose_name='LE Axis (°)')
    add_power = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True,
                verbose_name='Add Power (DS)')
    glasses_dispensed = models.BooleanField(default=False)
    rx_frame_type     = models.CharField(max_length=100, blank=True,
                        help_text='e.g. Single vision distance, Bifocal, Progressive')

    # ── IOP ───────────────────────────────────────────────────
    iop_re        = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True,
                    verbose_name='IOP RE (mmHg)')
    iop_le        = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True,
                    verbose_name='IOP LE (mmHg)')
    iop_method    = models.CharField(max_length=20, choices=IOPMethod.choices,
                    blank=True, default='')

    # ── Anterior Segment ──────────────────────────────────────
    ant_segment_re = models.TextField(blank=True, verbose_name='Anterior Segment RE')
    ant_segment_le = models.TextField(blank=True, verbose_name='Anterior Segment LE')

    # ── Posterior Segment ─────────────────────────────────────
    post_segment_re = models.TextField(blank=True, verbose_name='Posterior Segment RE')
    post_segment_le = models.TextField(blank=True, verbose_name='Posterior Segment LE')

    # ── Diagnoses (multi-select stored as comma-separated codes) ─
    diagnoses_re = models.CharField(max_length=500, blank=True,
                   help_text='Comma-separated diagnosis codes for RE')
    diagnoses_le = models.CharField(max_length=500, blank=True,
                   help_text='Comma-separated diagnosis codes for LE')

    # ── Interventions ─────────────────────────────────────────
    medications_given  = models.TextField(blank=True)
    surgery_performed  = models.BooleanField(default=False)
    surgery_type       = models.CharField(max_length=200, blank=True)

    # ── Referral recommendation ───────────────────────────────
    needs_referral     = models.BooleanField(default=False)
    referral_urgency   = models.CharField(max_length=20, choices=ReferralUrgency.choices,
                         blank=True, default='')
    referral_reason    = models.TextField(blank=True)

    # ── General ───────────────────────────────────────────────
    clinical_notes     = models.TextField(blank=True)

    # ── WHO-standard advanced fields ──────────────────────────
    # Principal cause of visual impairment (WHO World Report on Vision 2019)
    principal_cause_vi = models.CharField(
        max_length=30, choices=PrincipalCause.choices, blank=True, default='',
        verbose_name='Principal Cause of VI (WHO)',
        help_text='Primary cause driving visual impairment per WHO classification',
    )

    # Pupil reactions (RAPD detection)
    pupil_re = models.CharField(max_length=10, choices=PupilReaction.choices,
               blank=True, default='', verbose_name='Pupil RE')
    pupil_le = models.CharField(max_length=10, choices=PupilReaction.choices,
               blank=True, default='', verbose_name='Pupil LE')

    # Confrontation Visual Fields
    conf_vf_re = models.CharField(max_length=20, choices=ConfVF.choices,
                 blank=True, default='', verbose_name='Confrontation VF RE')
    conf_vf_le = models.CharField(max_length=20, choices=ConfVF.choices,
                 blank=True, default='', verbose_name='Confrontation VF LE')

    # Color vision (Ishihara / gross assessment)
    color_vision_re = models.CharField(max_length=10, choices=ColorVision.choices,
                      blank=True, default='', verbose_name='Color Vision RE')
    color_vision_le = models.CharField(max_length=10, choices=ColorVision.choices,
                      blank=True, default='', verbose_name='Color Vision LE')

    # External examination (lids, adnexa, orbit)
    external_exam = models.TextField(blank=True,
                    verbose_name='External Examination (lids, adnexa, orbit)')

    # JCI PFR.5 — Informed consent
    informed_consent = models.BooleanField(default=False,
                        help_text='Patient/guardian has given verbal/written consent')
    consent_date     = models.DateField(null=True, blank=True)

    # Low vision referral (separate pathway from standard hospital referral)
    low_vision_referral = models.BooleanField(default=False,
                          help_text='Refer for formal low vision assessment/rehabilitation')

    # Examiner role/designation (useful for field context where designation varies)
    examiner_designation = models.CharField(max_length=100, blank=True,
                           help_text='e.g. Ophthalmologist, Optometrist, Ophthalmic Nurse')

    class Meta:
        verbose_name = 'Outreach Examination'

    def __str__(self):
        return f'Exam — {self.patient.full_name} ({self.exam_date})'

    @property
    def diagnoses_re_list(self):
        return [d.strip() for d in self.diagnoses_re.split(',') if d.strip()]

    @property
    def diagnoses_le_list(self):
        return [d.strip() for d in self.diagnoses_le.split(',') if d.strip()]

    @property
    def iop_re_flag(self):
        """True if IOP RE is elevated (>21 mmHg)."""
        return self.iop_re and self.iop_re > 21

    @property
    def iop_le_flag(self):
        return self.iop_le and self.iop_le > 21

    # ── WHO Visual Impairment Classification ──────────────────

    @property
    def who_grade_re(self):
        """WHO VI grade for RE based on presenting (unaided) VA."""
        return _va_to_who_grade(self.va_re_distance)

    @property
    def who_grade_le(self):
        """WHO VI grade for LE based on presenting VA."""
        return _va_to_who_grade(self.va_le_distance)

    @property
    def who_grade_bcva_re(self):
        """WHO VI grade for RE based on best-corrected VA."""
        return _va_to_who_grade(self.va_re_distance_corrected or self.va_re_distance)

    @property
    def who_grade_bcva_le(self):
        """WHO VI grade for LE based on best-corrected VA."""
        return _va_to_who_grade(self.va_le_distance_corrected or self.va_le_distance)

    @property
    def who_grade_better_eye(self):
        """
        WHO VI grade based on presenting VA of the BETTER eye
        (i.e. the lower/better grade of the two eyes).
        This is the standard metric used in WHO population-level reporting.
        """
        g_re = self.who_grade_re
        g_le = self.who_grade_le
        if g_re is None and g_le is None:
            return None
        if g_re is None:
            return g_le
        if g_le is None:
            return g_re
        return min(g_re, g_le)  # lower grade = better vision

    @property
    def who_vi_label(self):
        """Human-readable label for WHO grade of better eye."""
        grade = self.who_grade_better_eye
        if grade is None:
            return 'Not Assessed'
        return WHO_VI_GRADE_LABELS.get(grade, ('Unknown', 'secondary'))[0]

    @property
    def who_vi_color(self):
        """Bootstrap color class for the WHO grade badge."""
        grade = self.who_grade_better_eye
        if grade is None:
            return 'secondary'
        return WHO_VI_GRADE_LABELS.get(grade, ('', 'secondary'))[1]

    @property
    def is_visually_impaired(self):
        """True if WHO grade ≥ 1 (mild or worse) in better eye."""
        g = self.who_grade_better_eye
        return g is not None and g >= 1

    @property
    def is_blind(self):
        """True if WHO grade 4 (blind) in better eye — VA <3/60."""
        g = self.who_grade_better_eye
        return g is not None and g >= 4

    @property
    def is_avoidably_blind(self):
        """
        Avoidable blindness = blind AND principal cause is treatable/preventable.
        Key WHO indicator — cataract, refractive error, trachoma, etc.
        """
        if not self.is_blind:
            return False
        avoidable_causes = {
            PrincipalCause.CATARACT, PrincipalCause.REFRACTIVE_ERROR,
            PrincipalCause.TRACHOMA, PrincipalCause.CORNEAL_OPACITY,
            PrincipalCause.DIABETIC_RETINOPATHY,
        }
        return self.principal_cause_vi in avoidable_causes

    @property
    def logmar_re(self):
        """LogMAR equivalent for RE presenting VA."""
        return VA_LOGMAR.get(self.va_re_distance)

    @property
    def logmar_le(self):
        """LogMAR equivalent for LE presenting VA."""
        return VA_LOGMAR.get(self.va_le_distance)

    @property
    def rapd_present(self):
        """True if RAPD detected in either eye."""
        return (self.pupil_re == PupilReaction.RAPD or
                self.pupil_le == PupilReaction.RAPD)


# ─── OutreachReferral ─────────────────────────────────────────────────────────

def _gen_referral_code():
    date_part = timezone.now().strftime('%Y%m%d')
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f'REF-{date_part}-{suffix}'


class OutreachReferral(TimeStampedModel):
    """
    Referral ticket generated at an outreach camp.
    Unique referral code links the field patient to the hospital when they arrive.
    """
    patient       = models.OneToOneField(OutreachPatient, on_delete=models.CASCADE,
                                         related_name='referral')
    referral_code = models.CharField(max_length=25, unique=True,
                    default=_gen_referral_code, editable=False)
    referred_by   = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='outreach_referrals',
    )
    urgency       = models.CharField(max_length=20, choices=ReferralUrgency.choices,
                    default=ReferralUrgency.ROUTINE)
    diagnosis     = models.CharField(max_length=300, blank=True)
    reason        = models.TextField()
    recommendations = models.TextField(blank=True)
    status        = models.CharField(max_length=20, choices=ReferralStatus.choices,
                    default=ReferralStatus.PENDING)

    # Hospital-side tracking (filled in when patient arrives)
    arrived_date  = models.DateField(null=True, blank=True)
    received_by   = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='received_outreach_referrals',
    )
    hospital_visit = models.ForeignKey(
        'patients.Visit', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='outreach_referral',
        help_text='Linked visit when patient registers at hospital',
    )
    outcome_notes = models.TextField(blank=True)
    is_synced     = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Outreach Referral'

    def __str__(self):
        return f'{self.referral_code} — {self.patient.full_name}'

    @property
    def urgency_color(self):
        return {'ROUTINE': 'success', 'URGENT': 'warning', 'EMERGENCY': 'danger'}.get(
            self.urgency, 'secondary')

    @property
    def status_color(self):
        return {
            'PENDING': 'secondary', 'ARRIVED': 'primary', 'IN_TREATMENT': 'info',
            'COMPLETED': 'success', 'DID_NOT_ATTEND': 'danger', 'REFERRED_OUT': 'warning',
        }.get(self.status, 'secondary')


# ─── OutreachSyncLog ──────────────────────────────────────────────────────────

class OutreachSyncLog(TimeStampedModel):
    """Audit trail for every sync event from a field device to the hospital server."""
    device_id          = models.CharField(max_length=100,
                         help_text='Hostname/device name of the field laptop')
    device_label       = models.CharField(max_length=200, blank=True,
                         help_text='Human-readable label e.g. "Outreach Laptop 1"')
    synced_by          = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='outreach_syncs',
    )
    sync_status        = models.CharField(max_length=10, choices=SyncStatus.choices,
                         default=SyncStatus.PENDING)

    # Counts
    activities_synced   = models.PositiveIntegerField(default=0)
    patients_synced     = models.PositiveIntegerField(default=0)
    examinations_synced = models.PositiveIntegerField(default=0)
    referrals_synced    = models.PositiveIntegerField(default=0)
    records_synced      = models.PositiveIntegerField(default=0)

    error_log    = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Outreach Sync Log'

    def __str__(self):
        return f'Sync {self.sync_status} from {self.device_id} at {self.created_at:%Y-%m-%d %H:%M}'

    @property
    def total_records(self):
        return (self.activities_synced + self.patients_synced +
                self.examinations_synced + self.referrals_synced + self.records_synced)
