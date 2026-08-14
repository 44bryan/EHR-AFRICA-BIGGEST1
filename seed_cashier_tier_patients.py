"""
Delete previous test patients and create 8 fresh patients (2 per tier)
with CASHIER QMS tokens so they appear in the cashier queue.
Run: cd /opt/ehr-africa && source venv/bin/activate && python seed_cashier_tier_patients.py
"""
import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.production')
sys.path.insert(0, '/opt/ehr-africa')
django.setup()

from django.utils import timezone
from apps.patients.models import Patient, Visit
from apps.accounts.models import User
from datetime import date

# ── Delete previously seeded test patients ────────────────────────────────────
OLD_PHONES = [
    '670000001','670000002','670000003','670000004',
    '670000005','670000006','670000007','670000008',
]
deleted = 0
for ph in OLD_PHONES:
    p = Patient.objects.filter(phone_number=ph).first()
    if p:
        # Hard delete visits and patient
        p.visits.all().delete()
        p.delete()
        deleted += 1
print(f'Removed {deleted} old test patients.\n')

# ── Create 8 fresh patients with cashier tokens ───────────────────────────────
from apps.qms.models import QueueToken, TokenStatus, DailyTokenSequence, IssuancePoint

today = timezone.localdate()
admin = User.objects.filter(is_superuser=True).first()

TIER_PRIORITY = {'STANDARD': 0, 'FAST_TRACK': 5, 'EXPRESS': 5, 'VIP': 10}

PATIENTS = [
    # (first, last, dob, gender, phone, tier)
    ('Amara',   'Nguetse',  date(1985, 3, 12),  'M', '670000001', 'STANDARD'),
    ('Fatima',  'Mbarga',   date(1992, 7, 25),  'F', '670000002', 'STANDARD'),
    ('Pierre',  'Tchamda',  date(1978, 11, 4),  'M', '670000003', 'FAST_TRACK'),
    ('Grace',   'Foning',   date(1990, 1, 18),  'F', '670000004', 'FAST_TRACK'),
    ('Samuel',  'Bello',    date(1965, 6, 30),  'M', '670000005', 'EXPRESS'),
    ('Carine',  'Abanda',   date(1988, 9, 14),  'F', '670000006', 'EXPRESS'),
    ('Jean',    'Etoa',     date(1955, 4, 7),   'M', '670000007', 'VIP'),
    ('Sylvie',  'Nkomo',    date(1970, 12, 22), 'F', '670000008', 'VIP'),
]

for first, last, dob, gender, phone, tier in PATIENTS:
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
        status='AT_CASHIER',
    )

    # Issue a CASHIER QMS token so they appear in the cashier queue
    from django.db import transaction
    with transaction.atomic():
        token_number = DailyTokenSequence.next_dept_token('CASHIER')
    token = QueueToken.objects.create(
        token_number=token_number,
        service_type='CASHIER',
        patient=p,
        visit=v,
        service_tier=tier,
        issuance_point=IssuancePoint.SYSTEM,
        priority=TIER_PRIORITY.get(tier, 0),
        status=TokenStatus.WAITING,
        token_date=today,
        notes=f'Seeded test patient — {tier}',
    )

    print(f'  [{tier:12s}]  {p.full_name:20s} ({p.patient_id})  Token: {token.display_token_number}  Visit: {v.visit_number}')

print('\nDone. 8 patients ready in cashier queue.')
