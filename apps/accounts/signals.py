"""
Auto-create a QMS ServiceCounter whenever a staff account is created.
Counter codes are auto-incremented so adding a second cashier creates CASH-03, etc.
Admins can reassign counters later via /qms/counter-assign/.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver


# Role → (service_type, serves_tiers, name_template)  OR  '__CONSULT__' (resolved from consultation_unit)
_ROLE_COUNTER_MAP = {
    # Billing
    'cashier':              ('CASHIER',       'STANDARD',           'Cashier'),
    'chief_cashier':        ('CASHIER',       '',                   'Chief Cashier'),
    'billing_officer':      ('CASHIER',       '',                   'Billing Desk'),

    # Reception
    'receptionist':         ('RECEPTIONIST',  '',                   'Reception'),
    'medical_records':      ('RECEPTIONIST',  '',                   'Medical Records'),
    'admission_officer':    ('RECEPTIONIST',  '',                   'Admissions'),

    # Triage / Nursing
    'nurse':                ('PARAMETERS',    'STANDARD',           'Triage / Parameters'),
    'consultation_nurse':   ('PARAMETERS',    'STANDARD',           'Consult Room Nurse'),

    # Dispensing
    'optical_dispenser':    ('OPTICAL',       '',                   'Optical Shop'),
    'pharmacist':           ('PHARMACY',      '',                   'Pharmacy'),

    # Diagnostics
    'lab_technician':           ('LAB',       '',                   'Laboratory'),
    'investigation_technician': ('INVEST',    '',                   'Investigations'),

    # Doctors — consultation_unit drives service_type
    'ophthalmologist':          '__CONSULT__',
    'optometrist':              ('REFRACTION',    '',               'Refraction'),
    'retina_specialist':        ('RETINA',        '',               'Retina Clinic'),
    'glaucoma_specialist':      ('GLAUCOMA',      '',               'Glaucoma Clinic'),
    'cataract_surgeon':         ('CATARACT',      '',               'Cataract Clinic'),
    'pediatric_ophthalmologist':('PEDIATRIC',     '',               'Pediatric Clinic'),
    'pediatric_refractionist':  ('PEDIATRIC',     '',               'Pediatric Refraction'),
    'cornea_specialist':        ('CORNEA',        '',               'Cornea Clinic'),
    'oculoplastics_surgeon':    ('OCULOPLASTY',   '',               'Oculoplastics'),
    'neuro_ophthalmologist':    ('NEURO',         '',               'Neuro-Ophthalmology'),
    'uveitis_specialist':       ('UVEITIS',       '',               'Uveitis Clinic'),
    'low_vision_specialist':    ('REFRACTION',    '',               'Low Vision'),
    'orthoptist':               ('GENERAL',       '',               'Orthoptics'),
}

# consultation_unit value → (service_type, name_template, serves_tiers)
_CONSULT_UNIT_MAP = {
    'GENERAL':       ('GENERAL',      'Consulting Room',       'STANDARD'),
    'EXP_CONSULT':   ('EXP_CONSULT',  'Express Consult Room',  'EXPRESS,FAST_TRACK'),
    'VIP_CONSULT':   ('VIP_CONSULT',  'VIP Consult Room',      'VIP'),
    'INSUR_CONSULT': ('GENERAL',      'HMO Consult Room',      'STANDARD'),
    'ALL':           ('GENERAL',      'Consulting Room',        'STANDARD'),
    '':              ('GENERAL',      'Consulting Room',        'STANDARD'),
}

# service_type → counter code prefix
_SERVICE_CODE_PREFIX = {
    'CASHIER':       'CASH',
    'RECEPTIONIST':  'RECEP',
    'PARAMETERS':    'PARAM',
    'PARAMS_VIP':    'PVIP',
    'OPTICAL':       'OPT',
    'PHARMACY':      'RX',
    'LAB':           'LAB',
    'INVEST':        'INV',
    'GENERAL':       'DR',
    'EXP_CONSULT':   'EXP',
    'VIP_CONSULT':   'VIP',
    'RETINA':        'RET',
    'GLAUCOMA':      'GLC',
    'CATARACT':      'CAT',
    'PEDIATRIC':     'PED',
    'CORNEA':        'COR',
    'OCULOPLASTY':   'OCP',
    'NEURO':         'NEU',
    'UVEITIS':       'UVE',
    'REFRACTION':    'REF',
}


def _next_counter_code(service_type: str) -> str:
    from apps.qms.models import ServiceCounter
    prefix = _SERVICE_CODE_PREFIX.get(service_type, service_type[:4].upper())
    existing = (
        ServiceCounter.objects
        .filter(code__startswith=f'{prefix}-')
        .values_list('code', flat=True)
    )
    used = set()
    for code in existing:
        try:
            used.add(int(code.split('-', 1)[1]))
        except (ValueError, IndexError):
            pass
    n = 1
    while n in used:
        n += 1
    return f'{prefix}-{n:02d}'


@receiver(post_save, sender='accounts.User')
def auto_create_counter(sender, instance, created, **kwargs):
    """
    On new staff account creation: auto-create and assign a QMS ServiceCounter.
    Skipped when QMS module is disabled.
    Admin can reassign later via /qms/counter-assign/.
    """
    if not created:
        return

    role = getattr(instance, 'role', None)
    if role not in _ROLE_COUNTER_MAP:
        return

    from apps.core.context_processors import qms_active as _qms_active
    if not _qms_active():
        return

    from apps.qms.models import ServiceCounter

    # Don't create a duplicate counter for this user
    if ServiceCounter.objects.filter(staff_assigned=instance).exists():
        return

    mapping = _ROLE_COUNTER_MAP[role]

    if mapping == '__CONSULT__':
        # Ophthalmologists: resolve from consultation_unit
        unit = (getattr(instance, 'consultation_unit', '') or '').strip()
        service_type, name_template, serves_tiers = _CONSULT_UNIT_MAP.get(
            unit, _CONSULT_UNIT_MAP['']
        )
    else:
        service_type, serves_tiers, name_template = mapping

    code = _next_counter_code(service_type)
    number = code.split('-')[-1]

    ServiceCounter.objects.create(
        name=f'{name_template} {number}',
        code=code,
        service_type=service_type,
        serves_tiers=serves_tiers,
        staff_assigned=instance,
        is_active=True,
    )
