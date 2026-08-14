"""
Seed 8 patients, 2 per service tier: STANDARD, FAST_TRACK, EXPRESS, VIP.
Run on server: cd /opt/ehr-africa && source venv/bin/activate && python seed_8patients_tiers.py
"""
import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.production')
sys.path.insert(0, '/opt/ehr-africa')
django.setup()

from django.utils import timezone
from apps.patients.models import Patient, Visit, ServiceTier
from apps.accounts.models import User
from datetime import date

today = timezone.localdate()
admin = User.objects.filter(is_superuser=True).first()

PATIENTS = [
    # (first, last, dob, gender, phone, tier)
    ('Amara',   'Nguetse',  date(1985, 3, 12),  'M', '670000001', ServiceTier.STANDARD),
    ('Fatima',  'Mbarga',   date(1992, 7, 25),  'F', '670000002', ServiceTier.STANDARD),
    ('Pierre',  'Tchamda',  date(1978, 11, 4),  'M', '670000003', ServiceTier.FAST_TRACK),
    ('Grace',   'Foning',   date(1990, 1, 18),  'F', '670000004', ServiceTier.FAST_TRACK),
    ('Samuel',  'Bello',    date(1965, 6, 30),  'M', '670000005', ServiceTier.EXPRESS),
    ('Carine',  'Abanda',   date(1988, 9, 14),  'F', '670000006', ServiceTier.EXPRESS),
    ('Jean',    'Etoa',     date(1955, 4, 7),   'M', '670000007', ServiceTier.VIP),
    ('Sylvie',  'Nkomo',    date(1970, 12, 22), 'F', '670000008', ServiceTier.VIP),
]

created = 0
for first, last, dob, gender, phone, tier in PATIENTS:
    # Skip if already exists (by phone)
    if Patient.objects.filter(phone_number=phone).exists():
        print(f'  SKIP (exists): {first} {last}')
        continue

    p = Patient.objects.create(
        first_name=first,
        last_name=last,
        date_of_birth=dob,
        gender=gender,
        phone_number=phone,
        nationality='Cameroonian',
        country='Cameroon',
        created_by=admin,
    )

    v = Visit.objects.create(
        patient=p,
        service_tier=tier,
        chief_complaint='Routine eye check',
        billing_type='SELF_PAY',
        created_by=admin,
        status='REGISTERED',
    )

    tier_label = {
        ServiceTier.STANDARD:   'STANDARD',
        ServiceTier.FAST_TRACK: 'FAST_TRACK',
        ServiceTier.EXPRESS:    'EXPRESS',
        ServiceTier.VIP:        'VIP',
    }.get(tier, tier)

    print(f'  Created: {p.full_name} ({p.patient_id}) — {tier_label} — Visit {v.visit_number}')
    created += 1

print(f'\nDone. {created} new patients registered.')
