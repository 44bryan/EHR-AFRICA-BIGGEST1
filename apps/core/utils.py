"""
Shared utility functions.
"""
import random
import string
from datetime import date


def generate_patient_id():
    """Generate unique patient ID: EHR-YYYY-XXXXXX"""
    from apps.patients.models import Patient
    year = date.today().year
    while True:
        suffix = ''.join(random.choices(string.digits, k=6))
        pid = f"EHR-{year}-{suffix}"
        if not Patient.objects.filter(patient_id=pid).exists():
            return pid


def generate_visit_number():
    """Generate unique visit number: VIS-YYYY-XXXXXX"""
    from apps.patients.models import Visit
    year = date.today().year
    while True:
        suffix = ''.join(random.choices(string.digits, k=6))
        vnum = f"VIS-{year}-{suffix}"
        if not Visit.objects.filter(visit_number=vnum).exists():
            return vnum


def generate_appointment_number():
    """Generate unique appointment number: APT-YYYY-XXXXXX"""
    from apps.appointments.models import Appointment
    year = date.today().year
    while True:
        suffix = ''.join(random.choices(string.digits, k=6))
        anum = f"APT-{year}-{suffix}"
        if not Appointment.objects.filter(appointment_number=anum).exists():
            return anum


def calculate_age(date_of_birth):
    """Return age in years from a date of birth."""
    today = date.today()
    age = today.year - date_of_birth.year
    if (today.month, today.day) < (date_of_birth.month, date_of_birth.day):
        age -= 1
    return age


def format_visual_acuity(va_string):
    """Normalise a visual acuity string — e.g. '6/6', 'CF', 'HM', 'LP', 'NPL'."""
    if not va_string:
        return ''
    va = va_string.strip().upper()
    special = ['CF', 'HM', 'LP', 'NPL', 'NLP', 'PL', 'FC']
    if va in special:
        return va
    return va_string.strip()
