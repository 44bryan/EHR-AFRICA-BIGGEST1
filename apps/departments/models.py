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
    code = models.CharField(max_length=15, unique=True, choices=DepartmentCode.choices)
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
