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

# Preset VA values for dropdown
VA_CHOICES = [
    ('6/6', '6/6'), ('6/9', '6/9'), ('6/12', '6/12'), ('6/18', '6/18'),
    ('6/24', '6/24'), ('6/36', '6/36'), ('6/60', '6/60'),
    ('3/60', '3/60'), ('2/60', '2/60'), ('1/60', '1/60'),
    ('HM', 'HM — Hand Movement'), ('PL', 'PL — Perception of Light'),
    ('NPL', 'NPL — No Perception of Light'), ('NT', 'NT — Not Tested'),
]

DIAGNOSIS_CHOICES = [
    ('NORMAL',             'Normal / No Pathology'),
    ('REFRACTIVE_ERROR',   'Refractive Error'),
    ('CATARACT',           'Cataract'),
    ('GLAUCOMA_SUSPECT',   'Glaucoma Suspect'),
    ('GLAUCOMA',           'Glaucoma (Confirmed)'),
    ('DIABETIC_RETINOPATHY','Diabetic Retinopathy'),
    ('AMD',                'Age-related Macular Degeneration'),
    ('PTERYGIUM',          'Pterygium'),
    ('TRACHOMA',           'Trachoma'),
    ('CORNEAL_OPACITY',    'Corneal Opacity / Scar'),
    ('DRY_EYE',            'Dry Eye Syndrome'),
    ('CONJUNCTIVITIS',     'Conjunctivitis'),
    ('AMBLYOPIA',          'Amblyopia (Lazy Eye)'),
    ('STRABISMUS',         'Strabismus'),
    ('RETINAL_DETACHMENT', 'Retinal Detachment'),
    ('UVEITIS',            'Uveitis'),
    ('NYSTAGMUS',          'Nystagmus'),
    ('ONCHOCERCIASIS',     'Onchocerciasis (River Blindness)'),
    ('OTHER',              'Other — see notes'),
]


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
