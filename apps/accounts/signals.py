"""
Auto-create a QMS ServiceCounter whenever a staff account is created or role changes.
Counter codes are auto-incremented so adding a second cashier creates CASH-03, etc.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver


# Role → (service_type, serves_tiers, name_template)
# serves_tiers: comma-separated tier codes, or '' for all tiers
_ROLE_COUNTER_MAP = {
    # Both billing_officer and cashier get a CASHIER counter
    'billing_officer': ('CASHIER',      'STANDARD,VIP', 'Cashier'),
    'cashier':         ('CASHIER',      'STANDARD,VIP', 'Cashier'),
    'receptionist':    ('RECEPTIONIST', '',             'Receptionist'),
    'nurse':           ('PARAMETERS',   'STANDARD',     'Parameters / Triage'),
    'optical_dispenser':('OPTICAL',     '',             'Optical Shop'),
    'pharmacist':      ('PHARMACY',     '',             'Pharmacy'),
}

# Special prefixes per service type
_SERVICE_CODE_PREFIX = {
    'CASHIER':       'CASH',
    'RECEPTIONIST':  'RECEP',
    'PARAMETERS':    'PARAM',
    'PARAMS_VIP':    'PVIP',
    'OPTICAL':       'OPT',
    'PHARMACY':      'RX',
    'LABORATORY':    'LAB',
    'INVEST':        'INV',
    'BILLING':       'BILL',
}


def _next_counter_code(service_type: str) -> str:
    from apps.qms.models import ServiceCounter
    prefix = _SERVICE_CODE_PREFIX.get(service_type, service_type[:4].upper())
    # Find all existing codes starting with this prefix
    existing = (
        ServiceCounter.objects
        .filter(code__startswith=f'{prefix}-')
        .values_list('code', flat=True)
    )
    used_numbers = set()
    for code in existing:
        try:
            n = int(code.split('-', 1)[1])
            used_numbers.add(n)
        except (ValueError, IndexError):
            pass
    n = 1
    while n in used_numbers:
        n += 1
    return f'{prefix}-{n:02d}'


@receiver(post_save, sender='accounts.User')
def auto_create_counter(sender, instance, created, **kwargs):
    """
    When a new staff account is saved, create the matching ServiceCounter
    if one is not already assigned to this user.
    """
    if not created:
        return  # only on account creation

    role = getattr(instance, 'role', None)
    if role not in _ROLE_COUNTER_MAP:
        return

    from apps.qms.models import ServiceCounter
    # Don't create duplicate if user already has a counter
    if ServiceCounter.objects.filter(staff_assigned=instance).exists():
        return

    service_type, serves_tiers, name_template = _ROLE_COUNTER_MAP[role]
    code = _next_counter_code(service_type)
    name = f'{name_template} {code.split("-")[-1]}'

    ServiceCounter.objects.create(
        name=name,
        code=code,
        service_type=service_type,
        serves_tiers=serves_tiers,
        staff_assigned=instance,
        is_active=True,
    )
