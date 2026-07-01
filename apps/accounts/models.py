"""
Custom User model with role-based access control for the EHR system.
"""
import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _


class UserRole(models.TextChoices):
    # ── Super Admin ───────────────────────────────────────────────────────
    SUPER_ADMIN               = 'super_admin',               _('Super Administrator')
    # ── Executive leadership (full read access to everything) ─────────────
    CEO                       = 'ceo',                       _('Chief Executive Officer')
    FINANCE_DIRECTOR          = 'finance_director',          _('Finance Director')
    ADMIN_DIRECTOR            = 'admin_director',            _('Administrative Director')
    # ── Clinical / Doctors ───────────────────────────────────────────────
    MEDICAL_DIRECTOR          = 'medical_director',          _('Medical Director')
    OPHTHALMOLOGIST           = 'ophthalmologist',           _('Ophthalmologist (General)')
    RETINA_SPECIALIST         = 'retina_specialist',         _('Retina Specialist')
    GLAUCOMA_SPECIALIST       = 'glaucoma_specialist',       _('Glaucoma Specialist')
    PEDIATRIC_OPHTHALMOLOGIST = 'pediatric_ophthalmologist', _('Pediatric Ophthalmologist')
    PEDIATRIC_REFRACTIONIST   = 'pediatric_refractionist',   _('Pediatric Refractionist / Orthoptist')
    CATARACT_SURGEON          = 'cataract_surgeon',          _('Cataract Surgeon')
    CORNEA_SPECIALIST         = 'cornea_specialist',         _('Cornea Specialist')
    OCULOPLASTICS_SURGEON     = 'oculoplastics_surgeon',     _('Oculoplastics Surgeon')
    NEURO_OPHTHALMOLOGIST     = 'neuro_ophthalmologist',     _('Neuro-ophthalmologist')
    UVEITIS_SPECIALIST        = 'uveitis_specialist',        _('Uveitis Specialist')
    OPTOMETRIST               = 'optometrist',               _('Optometrist / Refractionist')
    LOW_VISION_SPECIALIST     = 'low_vision_specialist',     _('Low Vision Specialist / Rehabilitation')
    INTERN                    = 'intern',                    _('Intern / House Officer')
    # ── Allied Clinical ──────────────────────────────────────────────────
    ANAESTHETIST              = 'anaesthetist',              _('Anaesthetist')
    ORTHOPTIST                = 'orthoptist',                _('Orthoptist / Binocular Vision Therapist')
    # ── Nursing ──────────────────────────────────────────────────────────
    NURSE                     = 'nurse',                     _('OPD Nurse (Triage)')
    CONSULTATION_NURSE        = 'consultation_nurse',        _('Consultation Room Nurse')
    THEATRE_NURSE             = 'theatre_nurse',             _('Theatre Nurse')
    WARD_NURSE                = 'ward_nurse',                _('Ward Nurse (IPD)')
    COUNSELING_NURSE          = 'counseling_nurse',          _('Surgical Counseling Nurse')
    NURSE_DIRECTOR            = 'nurse_director',            _('Director of Nursing / Head Nurse')
    # ── Technical ────────────────────────────────────────────────────────
    INVESTIGATION_TECHNICIAN  = 'investigation_technician',  _('Investigation Technician')
    LAB_TECHNICIAN            = 'lab_technician',            _('Lab Technician')
    PHARMACIST                = 'pharmacist',                _('Pharmacist')
    OPTICAL_DISPENSER         = 'optical_dispenser',         _('Optical Dispenser')
    CSSD_TECHNICIAN           = 'cssd_technician',           _('CSSD Technician (Sterilization)')
    # ── Administrative ───────────────────────────────────────────────────
    RECEPTIONIST              = 'receptionist',              _('Receptionist')
    ADMISSION_OFFICER         = 'admission_officer',         _('Admission Officer')
    BILLING_OFFICER           = 'billing_officer',           _('Billing Officer')
    CASHIER                   = 'cashier',                   _('Cashier')
    CHIEF_CASHIER             = 'chief_cashier',             _('Chief Cashier')
    ACCOUNTANT                = 'accountant',                _('Accountant')
    SENIOR_ACCOUNTANT         = 'senior_accountant',         _('Senior Accountant')
    GATEKEEPER                = 'gatekeeper',                _('Gate Security / Ticket Issuer')
    MEDICAL_RECORDS           = 'medical_records',           _('Medical Records Officer')
    QUALITY_OFFICER           = 'quality_officer',           _('Quality / JCI Compliance Officer')
    ADMIN                     = 'admin',                     _('System Administrator')


class CashierStation(models.TextChoices):
    """
    Admin assigns this to each Cashier/Billing Officer user to indicate which
    consultation-nature desk they operate. Queue tokens are routed to the
    matching station only.
    """
    ALL        = 'ALL',        _('All Consultations')
    STANDARD   = 'STANDARD',   _('Standard Consultation')
    FAST_TRACK = 'FAST_TRACK', _('Fast Track Consultation')
    VIP        = 'VIP',        _('VIP Consultation')
    INSURED    = 'INSURED',    _('Insured / HMO')


class ConsultationUnit(models.TextChoices):
    """
    For OPHTHALMOLOGIST accounts only — indicates which consultation desk/unit
    this doctor is assigned to. This replaces the old EXPRESS_OPHTHALMOLOGIST
    and INSURANCE_OPHTHALMOLOGIST roles. One role (OPHTHALMOLOGIST), multiple
    possible desks. QMS queue is filtered by this unit.
    """
    GENERAL   = 'GENERAL',      _('General Consultation')
    EXPRESS   = 'EXP_CONSULT',  _('Express / Fast Track')
    VIP       = 'VIP_CONSULT',  _('VIP Consultation')
    INSURANCE = 'INSUR_CONSULT', _('Insurance Consultation')


class User(AbstractUser):
    """
    Extended user model — email is the primary identifier.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(_('email address'), unique=True)
    role = models.CharField(
        max_length=30,
        choices=UserRole.choices,
        default=UserRole.RECEPTIONIST,
    )
    cashier_station = models.CharField(
        max_length=20,
        choices=CashierStation.choices,
        default=CashierStation.ALL,
        blank=True,
        help_text='For Cashier/Billing Officer accounts only — indicates which consultation desk this cashier serves. QMS tokens are routed to the matching station.',
    )
    consultation_unit = models.CharField(
        max_length=20,
        choices=ConsultationUnit.choices,
        default=ConsultationUnit.GENERAL,
        blank=True,
        help_text='For Ophthalmologist accounts only — which consultation desk this doctor is assigned to (General, Express, VIP, Insurance). Determines which QMS queue they see.',
    )
    department = models.ForeignKey(
        'departments.Department',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='staff',
    )
    phone_number = models.CharField(max_length=20, blank=True)
    profile_photo = models.ImageField(
        upload_to='staff/photos/',
        null=True,
        blank=True,
    )
    employee_id = models.CharField(max_length=20, unique=True, null=True, blank=True)
    must_change_password = models.BooleanField(default=False)
    last_password_change = models.DateTimeField(null=True, blank=True)
    # ── Two-Factor Authentication (TOTP) ─────────────────────────────────
    totp_secret   = models.CharField(max_length=64, blank=True, default='')
    totp_enabled  = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email', 'first_name', 'last_name', 'employee_id']

    class Meta:
        verbose_name = _('User')
        verbose_name_plural = _('Users')
        ordering = ['last_name', 'first_name']

    def save(self, *args, **kwargs):
        # Super Admin always gets Django staff + superuser flags automatically
        if self.role == UserRole.SUPER_ADMIN:
            self.is_staff = True
            self.is_superuser = True
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_full_name()} ({self.get_role_display()})"

    @property
    def full_name(self):
        return self.get_full_name() or self.email

    # ── Role groups ──────────────────────────────────────────────────────
    DOCTOR_ROLES = (
        UserRole.MEDICAL_DIRECTOR,
        UserRole.OPHTHALMOLOGIST,
        UserRole.RETINA_SPECIALIST,
        UserRole.GLAUCOMA_SPECIALIST,
        UserRole.PEDIATRIC_OPHTHALMOLOGIST,
        UserRole.PEDIATRIC_REFRACTIONIST,
        UserRole.CATARACT_SURGEON,
        UserRole.CORNEA_SPECIALIST,
        UserRole.OCULOPLASTICS_SURGEON,
        UserRole.NEURO_OPHTHALMOLOGIST,
        UserRole.UVEITIS_SPECIALIST,
        UserRole.OPTOMETRIST,
        UserRole.LOW_VISION_SPECIALIST,
        UserRole.ORTHOPTIST,
        UserRole.INTERN,
    )
    NURSE_ROLES = (
        UserRole.NURSE,
        UserRole.CONSULTATION_NURSE,
        UserRole.THEATRE_NURSE,
        UserRole.WARD_NURSE,
        UserRole.COUNSELING_NURSE,
        UserRole.NURSE_DIRECTOR,
    )
    ADMIN_ROLES = (
        UserRole.RECEPTIONIST,
        UserRole.ADMISSION_OFFICER,
        UserRole.BILLING_OFFICER,
        UserRole.CASHIER,
        UserRole.CHIEF_CASHIER,
        UserRole.ACCOUNTANT,
        UserRole.SENIOR_ACCOUNTANT,
        UserRole.GATEKEEPER,
        UserRole.MEDICAL_RECORDS,
        UserRole.ADMIN,
    )

    # ── Role convenience properties ──────────────────────────────────────
    @property
    def is_super_admin(self):
        return self.role == UserRole.SUPER_ADMIN

    @property
    def is_ceo(self):
        return self.role == UserRole.CEO

    @property
    def is_admin_director(self):
        return self.role == UserRole.ADMIN_DIRECTOR

    @property
    def is_finance_director(self):
        return self.role == UserRole.FINANCE_DIRECTOR

    @property
    def is_executive(self):
        """CEO, Finance Director, Admin Director — see everything, control nothing clinically."""
        return self.role in (UserRole.CEO, UserRole.ADMIN_DIRECTOR, UserRole.FINANCE_DIRECTOR, UserRole.SUPER_ADMIN)

    @property
    def is_medical_director(self):
        """Medical Director controls all clinical operations."""
        return self.role in (UserRole.MEDICAL_DIRECTOR, UserRole.SUPER_ADMIN)

    @property
    def can_see_everything(self):
        """CEO, Finance Director, Admin Director, Medical Director, Super Admin — full read access."""
        return self.role in (
            UserRole.CEO, UserRole.FINANCE_DIRECTOR, UserRole.ADMIN_DIRECTOR,
            UserRole.MEDICAL_DIRECTOR, UserRole.SUPER_ADMIN,
        )

    @property
    def is_doctor(self):
        return self.role in self.DOCTOR_ROLES or self.is_super_admin

    @property
    def is_nurse(self):
        return self.role in self.NURSE_ROLES

    @property
    def is_opd_nurse(self):
        """Can perform triage and dispatch."""
        return self.role == UserRole.NURSE

    @property
    def is_consultation_nurse(self):
        """Nurse assigned to a specific consultation room — assists doctor, calls patients."""
        return self.role == UserRole.CONSULTATION_NURSE

    @property
    def is_theatre_nurse(self):
        return self.role == UserRole.THEATRE_NURSE

    @property
    def is_ward_nurse(self):
        return self.role == UserRole.WARD_NURSE

    @property
    def is_counseling_nurse(self):
        return self.role == UserRole.COUNSELING_NURSE

    @property
    def is_lab_tech(self):
        return self.role == UserRole.LAB_TECHNICIAN

    @property
    def is_investigation_tech(self):
        return self.role == UserRole.INVESTIGATION_TECHNICIAN

    @property
    def is_pharmacist(self):
        return self.role == UserRole.PHARMACIST

    @property
    def is_optical_dispenser(self):
        return self.role == UserRole.OPTICAL_DISPENSER

    @property
    def is_cssd_technician(self):
        return self.role == UserRole.CSSD_TECHNICIAN

    @property
    def is_anaesthetist(self):
        return self.role == UserRole.ANAESTHETIST

    @property
    def is_orthoptist(self):
        return self.role == UserRole.ORTHOPTIST

    @property
    def is_nurse_director(self):
        return self.role == UserRole.NURSE_DIRECTOR

    @property
    def is_quality_officer(self):
        return self.role == UserRole.QUALITY_OFFICER

    @property
    def is_receptionist(self):
        return self.role == UserRole.RECEPTIONIST

    @property
    def is_admission_officer(self):
        return self.role == UserRole.ADMISSION_OFFICER

    @property
    def is_billing_officer(self):
        return self.role == UserRole.BILLING_OFFICER

    @property
    def is_chief_cashier(self):
        return self.role == UserRole.CHIEF_CASHIER

    @property
    def is_accountant(self):
        return self.role in (UserRole.ACCOUNTANT, UserRole.SENIOR_ACCOUNTANT)

    @property
    def is_senior_accountant(self):
        return self.role == UserRole.SENIOR_ACCOUNTANT

    @property
    def is_cashier(self):
        return self.role in (UserRole.CASHIER, UserRole.CHIEF_CASHIER, UserRole.BILLING_OFFICER)

    @property
    def is_gatekeeper(self):
        return self.role == UserRole.GATEKEEPER

    @property
    def is_admin_staff(self):
        """Administrative / management roles — excludes clinical leadership."""
        return self.role in (
            UserRole.ADMIN, UserRole.SUPER_ADMIN,
            UserRole.CEO, UserRole.ADMIN_DIRECTOR,
        )

    @property
    def is_uveitis_specialist(self):
        return self.role == UserRole.UVEITIS_SPECIALIST

    @property
    def is_retina_specialist(self):
        return self.role == UserRole.RETINA_SPECIALIST

    @property
    def is_glaucoma_specialist(self):
        return self.role == UserRole.GLAUCOMA_SPECIALIST

    @property
    def is_cataract_surgeon(self):
        return self.role == UserRole.CATARACT_SURGEON

    @property
    def is_cornea_specialist(self):
        return self.role == UserRole.CORNEA_SPECIALIST

    @property
    def is_neuro_ophthalmologist(self):
        return self.role == UserRole.NEURO_OPHTHALMOLOGIST

    @property
    def is_oculoplastics_surgeon(self):
        return self.role == UserRole.OCULOPLASTICS_SURGEON

    @property
    def is_specialist(self):
        """Doctor assigned to a specific specialty unit."""
        return self.role in (
            UserRole.RETINA_SPECIALIST,
            UserRole.GLAUCOMA_SPECIALIST,
            UserRole.PEDIATRIC_OPHTHALMOLOGIST,
            UserRole.CATARACT_SURGEON,
            UserRole.CORNEA_SPECIALIST,
            UserRole.OCULOPLASTICS_SURGEON,
            UserRole.NEURO_OPHTHALMOLOGIST,
            UserRole.UVEITIS_SPECIALIST,
        )

    @property
    def role_department_code(self):
        """Maps doctor role → expected department code for queue filtering."""
        mapping = {
            UserRole.RETINA_SPECIALIST:         'RETINA',
            UserRole.GLAUCOMA_SPECIALIST:       'GLAUC',
            UserRole.PEDIATRIC_OPHTHALMOLOGIST: 'PEDS_OPH',
            UserRole.CATARACT_SURGEON:          'CATARACT',
            UserRole.CORNEA_SPECIALIST:         'CORNEA',
            UserRole.OCULOPLASTICS_SURGEON:     'OCULOPLASTY',
            UserRole.NEURO_OPHTHALMOLOGIST:     'NEURO_OPH',
            UserRole.UVEITIS_SPECIALIST:        'UVEITIS',
            UserRole.OPTOMETRIST:               'REFRAC',
            UserRole.PEDIATRIC_REFRACTIONIST:   'PEDS_REFRAC',
            UserRole.LOW_VISION_SPECIALIST:     'LOW_VIS',
            UserRole.OPHTHALMOLOGIST:           'GEN_OPH',
            UserRole.INTERN:                    'GEN_OPH',   # interns work under general ophthalmology
            UserRole.INVESTIGATION_TECHNICIAN:  'INVEST',
        }
        return mapping.get(self.role)

    # ── Permission methods ────────────────────────────────────────────────
    def can_create_consultation(self):
        return self.role in self.DOCTOR_ROLES or self.is_super_admin

    def can_do_triage(self):
        # Counseling nurses do counseling only — not triage/vitals
        if self.role == UserRole.COUNSELING_NURSE:
            return False
        return self.role in self.NURSE_ROLES or self.is_medical_director

    def can_dispatch_patient(self):
        """Any clinical staff can route/dispatch a patient to any unit."""
        # Counseling nurses do counseling only — patient dispatch is not their function
        if self.role == UserRole.COUNSELING_NURSE:
            return False
        return (
            self.role in self.DOCTOR_ROLES
            or self.role in self.NURSE_ROLES
            or self.role in (
                UserRole.INVESTIGATION_TECHNICIAN,
                UserRole.LAB_TECHNICIAN,
                UserRole.PHARMACIST,
                UserRole.OPTICAL_DISPENSER,
                UserRole.CSSD_TECHNICIAN,
                UserRole.RECEPTIONIST,
                UserRole.ADMISSION_OFFICER,
                UserRole.ANAESTHETIST,
            )
            or self.is_super_admin
        )

    def can_order_investigations(self):
        return self.is_super_admin or self.is_executive or self.role in self.DOCTOR_ROLES

    def can_record_investigation_results(self):
        return self.role in (
            UserRole.INVESTIGATION_TECHNICIAN,
            UserRole.LAB_TECHNICIAN,
            UserRole.MEDICAL_DIRECTOR,
        )

    def can_dispense_pharmacy(self):
        return self.role in (
            UserRole.PHARMACIST,
            UserRole.MEDICAL_DIRECTOR,
        )

    def can_dispense_optical(self):
        return self.role in (
            UserRole.OPTICAL_DISPENSER,
            UserRole.OPTOMETRIST,
            UserRole.MEDICAL_DIRECTOR,
        )

    def can_manage_billing(self):
        return self.role in (
            UserRole.BILLING_OFFICER,
            UserRole.CASHIER,
            UserRole.RECEPTIONIST,
            UserRole.ADMIN,
            UserRole.MEDICAL_DIRECTOR,
            UserRole.FINANCE_DIRECTOR,
        ) or self.is_super_admin or self.is_ceo

    def can_admit_patient(self):
        return self.role in (
            UserRole.ADMISSION_OFFICER,
            UserRole.MEDICAL_DIRECTOR,
        ) or self.is_doctor

    def can_use_ai_assistant(self):
        return self.is_super_admin or self.is_executive or self.role in self.DOCTOR_ROLES or self.role in (
            UserRole.ADMIN, UserRole.MEDICAL_DIRECTOR,
        )


class QueueBoardType(models.TextChoices):
    TOKEN = 'token', 'Token Board (shows number called)'
    NAMES = 'names', 'Names Board (shows live patient list)'


class SystemTheme(models.TextChoices):
    TEAL    = 'theme-teal',   'Teal (default)'
    NAVY    = 'theme-navy',   'Navy Blue'
    GREEN   = 'theme-green',  'Forest Green'
    PURPLE  = 'theme-purple', 'Deep Purple'
    SLATE   = 'theme-slate',  'Slate Gray'
    CRIMSON = 'theme-crimson','Crimson Red'


class HospitalConfig(models.Model):
    """
    Singleton model — one row, managed by Super Admin.
    Controls which optional modules are active for this hospital installation.
    Think of it as the licence/feature-flag control panel.
    """
    # ── Display & Appearance ─────────────────────────────
    system_theme     = models.CharField(
        max_length=30, choices=SystemTheme.choices, default=SystemTheme.TEAL,
        verbose_name='System Theme',
    )
    queue_board_type = models.CharField(
        max_length=10, choices=QueueBoardType.choices, default=QueueBoardType.TOKEN,
        verbose_name='Queue Display Board Type',
    )

    # ── Core modules (always on) ─────────────────────────
    # patients, consultations, billing, reception are NOT toggleable.

    # ── Optional clinical modules ────────────────────────
    module_ai           = models.BooleanField(default=True,  verbose_name='AI Assistant')
    module_qms          = models.BooleanField(default=True,  verbose_name='Queue Management System')
    module_pharmacy     = models.BooleanField(default=True,  verbose_name='Pharmacy')
    module_laboratory   = models.BooleanField(default=True,  verbose_name='Laboratory')
    module_ipd          = models.BooleanField(default=True,  verbose_name='Inpatient (IPD / Surgical)')
    module_opticals     = models.BooleanField(default=True,  verbose_name='Optical Dispensary')

    # ── Optional operational modules ────────────────────
    module_cssd         = models.BooleanField(default=True,  verbose_name='CSSD (Sterilization)')
    module_inventory    = models.BooleanField(default=True,  verbose_name='Inventory & Pilferage Protection')
    module_hrms         = models.BooleanField(default=True,  verbose_name='HR Management (HRMS)')

    # ── Optional engagement modules ─────────────────────
    module_outreach     = models.BooleanField(default=True,  verbose_name='Outreach & Community')
    module_feedback     = models.BooleanField(default=True,  verbose_name='Patient Feedback & NPS')
    module_leads        = models.BooleanField(default=True,  verbose_name='Lead Management (CRM)')

    # ── Consultation validity threshold ──────────────────
    consultation_days   = models.PositiveSmallIntegerField(
        default=15,
        verbose_name='Consultation Validity (days)',
        help_text='Consultation window. After this, patient must pay a new consultation fee.',
    )

    # ── Hospital Identity ─────────────────────────────
    hospital_name    = models.CharField(max_length=200, default='EHR Africa Hospital', verbose_name='Hospital Name')
    hospital_address = models.TextField(blank=True, default='', verbose_name='Address')
    hospital_phone   = models.CharField(max_length=30,  blank=True, default='', verbose_name='Phone')
    hospital_email   = models.EmailField(blank=True, default='', verbose_name='Email')
    hospital_website = models.URLField(blank=True, default='', verbose_name='Website')
    hospital_tax_id  = models.CharField(max_length=60,  blank=True, default='', verbose_name='Tax ID / NIU')

    # ── Security ──────────────────────────────────────
    session_timeout_hours   = models.PositiveSmallIntegerField(default=8,  verbose_name='Session Timeout (hours)')
    max_failed_logins       = models.PositiveSmallIntegerField(default=5,  verbose_name='Max Failed Login Attempts')
    account_lockout_minutes = models.PositiveSmallIntegerField(default=30, verbose_name='Account Lockout (minutes)')

    # ── Backup ────────────────────────────────────────
    backup_keep_days = models.PositiveSmallIntegerField(default=30, verbose_name='Keep Backups (days)')

    class Meta:
        verbose_name = 'Hospital Configuration'

    def __str__(self):
        return 'Hospital Configuration'

    @classmethod
    def get(cls):
        """Always returns the singleton config row (creates if missing)."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def get_module_flags(self):
        """Return list of (field_name, verbose_name, value) for all module BooleanFields."""
        flags = []
        for f in self._meta.get_fields():
            if hasattr(f, 'get_internal_type') and f.get_internal_type() == 'BooleanField' and f.name.startswith('module_'):
                flags.append((f.name, f.verbose_name, getattr(self, f.name)))
        return flags


class UserAuditLog(models.Model):
    """Records every significant action taken by users."""

    class Action(models.TextChoices):
        LOGIN = 'LOGIN', _('Login')
        LOGOUT = 'LOGOUT', _('Logout')
        VIEW_RECORD = 'VIEW_RECORD', _('View Record')
        CREATE_RECORD = 'CREATE_RECORD', _('Create Record')
        UPDATE_RECORD = 'UPDATE_RECORD', _('Update Record')
        DELETE_RECORD = 'DELETE_RECORD', _('Delete Record')
        GENERATE_REPORT = 'GENERATE_REPORT', _('Generate Report')
        AI_QUERY = 'AI_QUERY', _('AI Query')
        PASSWORD_CHANGE = 'PASSWORD_CHANGE', _('Password Change')
        FAILED_LOGIN = 'FAILED_LOGIN', _('Failed Login')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='audit_logs',
    )
    action = models.CharField(max_length=30, choices=Action.choices)
    target_model = models.CharField(max_length=100, blank=True)
    target_id = models.CharField(max_length=100, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    extra_data = models.JSONField(default=dict)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'

    def __str__(self):
        return f"{self.user} — {self.action} at {self.timestamp}"

    @classmethod
    def log(cls, user, action, target_model='', target_id='', extra_data=None, request=None):
        """Convenience method to write an audit entry from any view."""
        ip = None
        if request:
            xff = request.META.get('HTTP_X_FORWARDED_FOR')
            ip = xff.split(',')[0].strip() if xff else request.META.get('REMOTE_ADDR')
        try:
            cls.objects.create(
                user=user,
                action=action,
                target_model=target_model,
                target_id=str(target_id),
                ip_address=ip,
                extra_data=extra_data or {},
            )
        except Exception:
            pass  # Never let audit logging crash a user-facing request
