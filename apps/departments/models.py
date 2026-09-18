"""
Department registry — all six clinical departments.
"""
import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _


class DepartmentCode(models.TextChoices):
    GENERAL_OPHTHALMOLOGY = 'GEN_OPH', _('General Ophthalmology')
    RETINA = 'RETINA', _('Retina')
    GLAUCOMA = 'GLAUC', _('Glaucoma')
    PEDIATRIC = 'PEDS_OPH', _('Pediatric Ophthalmology')
    PEDIATRIC_REFRACTION = 'PEDS_REFRAC', _('Pediatric Refraction & Orthoptics')
    REFRACTION = 'REFRAC', _('Refraction')
    CORNEA = 'CORNEA', _('Cornea & External Eye')
    OCULOPLASTICS = 'OCULOPLASTY', _('Oculoplastics & Orbit')
    NEURO_OPH = 'NEURO_OPH', _('Neuro-ophthalmology')
    LOW_VISION = 'LOW_VIS', _('Low Vision & Rehabilitation')
    CATARACT = 'CATARACT', _('Cataract & Surgical')
    UVEITIS = 'UVEITIS', _('Uveitis Clinic')
    INVESTIGATION = 'INVEST', _('Investigation')
    LABORATORY = 'LAB', _('Laboratory')


class Department(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(
        max_length=20, unique=True,
        help_text='Short unique code e.g. GEN_OPH, GEN_MED, CARDIO (no spaces)',
    )
    description = models.TextField(blank=True)
    head_of_department = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='headed_department',
    )
    location = models.CharField(max_length=100, blank=True, help_text='Room or floor')
    color_code = models.CharField(max_length=7, default='#0d6efd', help_text='Hex color for UI')
    icon = models.CharField(max_length=50, default='bi-eye', help_text='Bootstrap icon class')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Department'
        verbose_name_plural = 'Departments'

    def __str__(self):
        return self.name

    @classmethod
    def get_clinical_departments(cls):
        """Returns departments where consultations happen (excludes Lab & Investigation)."""
        non_clinical = [DepartmentCode.LABORATORY, DepartmentCode.INVESTIGATION]
        return cls.objects.filter(is_active=True).exclude(code__in=non_clinical)


class RoomTier(models.TextChoices):
    STANDARD   = 'STANDARD',   _('Standard')
    EXPRESS    = 'EXPRESS',    _('Express')
    VIP        = 'VIP',        _('VIP')
    ALL        = 'ALL',        _('All Tiers')  # doctor sees every patient tier


class ConsultationRoom(models.Model):
    """
    Physical consultation room/door within a department.
    Configured once by admin (room numbers match the actual door numbers).
    Doctor assignment is optional and can be updated daily.
    room_tier controls which QMS service_type is created when a patient is dispatched here.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='rooms')
    room_number = models.CharField(max_length=10, help_text='Door/room number as it appears on the door (e.g. 1, 2, 3)')
    label = models.CharField(max_length=80, blank=True, help_text='Custom label e.g. "Consulting Room 2" — auto-filled if blank')
    assigned_doctor = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assigned_room',
        help_text='Doctor currently assigned to this room (update daily as needed)',
    )
    room_tier = models.CharField(
        max_length=12,
        choices=RoomTier.choices,
        default=RoomTier.STANDARD,
        help_text='Service tier this room handles — determines QMS queue on dispatch',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['department', 'room_number']
        unique_together = [['department', 'room_number']]
        verbose_name = 'Consultation Room'
        verbose_name_plural = 'Consultation Rooms'

    def __str__(self):
        return f'{self.department.name} — {self.display_label}'

    @property
    def display_label(self):
        base = self.label or f'Room {self.room_number}'
        if self.assigned_doctor:
            return f'{base} — Dr. {self.assigned_doctor.last_name}'
        return base

    def tier_service_type(self, patient_tier=None):
        """Maps room_tier to the QMS service_type.
        For ALL-tier rooms the service type follows the patient's own tier."""
        if self.room_tier == 'ALL':
            return {
                'VIP':        'VIP_CONSULT',
                'EXPRESS':    'EXP_CONSULT',
                'STANDARD':   'GENERAL',
            }.get(patient_tier or 'STANDARD', 'GENERAL')
        return {
            'VIP':        'VIP_CONSULT',
            'EXPRESS':    'EXP_CONSULT',
            'STANDARD':   'GENERAL',
        }.get(self.room_tier, 'GENERAL')

    def save(self, *args, **kwargs):
        if not self.label:
            self.label = f'Room {self.room_number}'
        super().save(*args, **kwargs)


def create_default_departments():
    """Populate the six standard departments — called from a data migration."""
    defaults = [
        {
            'name': 'General Ophthalmology',
            'code': DepartmentCode.GENERAL_OPHTHALMOLOGY,
            'description': 'Comprehensive eye examinations and general ocular conditions.',
            'color_code': '#0d6efd',
            'icon': 'bi-eye',
        },
        {
            'name': 'Retina',
            'code': DepartmentCode.RETINA,
            'description': 'Diseases of the retina, vitreous, and macula including diabetic retinopathy.',
            'color_code': '#198754',
            'icon': 'bi-circle',
        },
        {
            'name': 'Glaucoma',
            'code': DepartmentCode.GLAUCOMA,
            'description': 'Diagnosis and management of glaucoma and optic nerve disorders.',
            'color_code': '#ffc107',
            'icon': 'bi-activity',
        },
        {
            'name': 'Pediatric Ophthalmology',
            'code': DepartmentCode.PEDIATRIC,
            'description': 'Eye care for children including amblyopia, strabismus and congenital conditions.',
            'color_code': '#0dcaf0',
            'icon': 'bi-person-hearts',
        },
        {
            'name': 'Pediatric Refraction & Orthoptics',
            'code': DepartmentCode.PEDIATRIC_REFRACTION,
            'description': 'Paediatric refraction, orthoptic assessment, amblyopia treatment and vision screening for children.',
            'color_code': '#0dcaf0',
            'icon': 'bi-person-hearts',
        },
        {
            'name': 'Refraction',
            'code': DepartmentCode.REFRACTION,
            'description': 'Subjective and objective refraction, spectacle and contact lens prescription.',
            'color_code': '#0dcaf0',
            'icon': 'bi-eyeglasses',
        },
        {
            'name': 'Cornea & External Eye',
            'code': DepartmentCode.CORNEA,
            'description': 'Corneal diseases, keratoconus, corneal transplantation, ocular surface disorders.',
            'color_code': '#20c997',
            'icon': 'bi-circle-half',
        },
        {
            'name': 'Oculoplastics & Orbit',
            'code': DepartmentCode.OCULOPLASTICS,
            'description': 'Eyelid, lacrimal, and orbital disorders including ptosis, entropion, ectropion.',
            'color_code': '#fd7e14',
            'icon': 'bi-eye-slash',
        },
        {
            'name': 'Neuro-ophthalmology',
            'code': DepartmentCode.NEURO_OPH,
            'description': 'Visual pathway disorders, optic neuritis, papilloedema, diplopia, nystagmus.',
            'color_code': '#6610f2',
            'icon': 'bi-lightning',
        },
        {
            'name': 'Low Vision & Rehabilitation',
            'code': DepartmentCode.LOW_VISION,
            'description': 'Low vision assessment, magnification aids, visual rehabilitation services.',
            'color_code': '#795548',
            'icon': 'bi-zoom-in',
        },
        {
            'name': 'Cataract & Surgical',
            'code': DepartmentCode.CATARACT,
            'description': 'Cataract surgery, IOL biometry, post-operative care and surgical follow-ups.',
            'color_code': '#17a2b8',
            'icon': 'bi-scissors',
        },
        {
            'name': 'Uveitis Clinic',
            'code': DepartmentCode.UVEITIS,
            'description': 'Uveitis, inflammatory eye disease, immunosuppression and ocular immunology.',
            'color_code': '#6f42c1',
            'icon': 'bi-droplet-half',
        },
        {
            'name': 'Investigation',
            'code': DepartmentCode.INVESTIGATION,
            'description': 'Ophthalmic investigations: OCT, Visual Fields, Fundus Photography, Biometry.',
            'color_code': '#6f42c1',
            'icon': 'bi-search',
        },
        {
            'name': 'Laboratory',
            'code': DepartmentCode.LABORATORY,
            'description': 'Haematology, biochemistry, microbiology, and serology laboratory services.',
            'color_code': '#dc3545',
            'icon': 'bi-droplet',
        },
    ]
    for dept_data in defaults:
        Department.objects.get_or_create(code=dept_data['code'], defaults=dept_data)
