"""
Seed 4 Fast Track + 2 Express patients with today's cashier queue tokens.
Run on server: python seed_vip_express_demo.py
"""
import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.production')
sys.path.insert(0, '/opt/ehr-africa')
django.setup()

from datetime import date, timedelta
from django.utils import timezone
from apps.patients.models import Patient, Visit, VisitType, VisitStatus, ServiceTier
from apps.qms.models import QueueToken, TokenStatus, ServiceType, TIER_PRIORITY
from apps.qms.models import ServiceTier as QMSTier
from apps.accounts.models import User
from apps.core.utils import generate_patient_id, generate_visit_number

admin = User.objects.filter(is_superuser=True).first() or User.objects.first()
today = timezone.localdate()
now   = timezone.now()

PATIENTS = [
    # (first, last, dob, gender, phone, tier, complaint)
    # ── Fast Track (4) ────────────────────────────────────────────────────────
    ('Amara',    'Mbeki',    date(1978, 3, 12), 'M', '+237691000001', 'FAST_TRACK', 'Urgent eye pain and photophobia'),
    ('Fatima',   'Nkomo',    date(1985, 7, 22), 'F', '+237691000002', 'FAST_TRACK', 'Sudden vision loss in right eye'),
    ('Ibrahim',  'Diallo',   date(1960, 11, 5), 'M', '+237691000003', 'FAST_TRACK', 'Severe headache with blurred vision'),
    ('Bintou',   'Coulibaly', date(1990, 2, 18), 'F', '+237691000004', 'FAST_TRACK', 'Chemical splash to both eyes'),
    # ── Express (2) ───────────────────────────────────────────────────────────
    ('Emmanuel', 'Fofana',   date(1995, 9, 30), 'M', '+237691000005', 'EXPRESS',    'Routine glasses prescription check'),
    ('Celine',   'Awono',    date(1988, 4, 14), 'F', '+237691000006', 'EXPRESS',    'Follow-up glaucoma pressure check'),
]

# Token prefix counters for today
existing_ft  = QueueToken.objects.filter(token_date=today, service_tier='FAST_TRACK', service_type='CASHIER').count()
existing_exp = QueueToken.objects.filter(token_date=today, service_tier='EXPRESS',    service_type='CASHIER').count()
existing_vip = QueueToken.objects.filter(token_date=today, service_tier='VIP',        service_type='CASHIER').count()
counters = {'FAST_TRACK': existing_ft, 'EXPRESS': existing_exp, 'VIP': existing_vip}
prefix_map  = {'FAST_TRACK': 'FT', 'EXPRESS': 'E', 'VIP': 'V'}

created = []
for first, last, dob, gender, phone, tier, complaint in PATIENTS:
    # ── Create patient ────────────────────────────────────────────────────────
    p = Patient.objects.filter(phone_number=phone).first()
    if not p:
        p = Patient(
            first_name=first, last_name=last,
            date_of_birth=dob, gender=gender,
            phone_number=phone, phone_is_whatsapp=True,
            country='Cameroon', nationality='Cameroonian',
            occupation='Civil Servant',
            registered_by=admin,
        )
        p.save()
        print(f'  Created patient: {p.full_name} [{p.patient_id}]')
    else:
        print(f'  Existing patient: {p.full_name} [{p.patient_id}]')

    # ── Create today's visit ──────────────────────────────────────────────────
    visit = Visit.objects.filter(patient=p, visit_date__date=today).first()
    if not visit:
        visit = Visit(
            patient=p,
            visit_type=VisitType.NEW,
            chief_complaint=complaint,
            service_tier=tier,
            status=VisitStatus.WAITING,
        )
        visit.save()
        print(f'  Created visit:   {visit.visit_number} | tier={tier}')
    else:
        print(f'  Existing visit:  {visit.visit_number} | tier={tier}')

    # ── Create cashier queue token ────────────────────────────────────────────
    if QueueToken.objects.filter(visit=visit, service_type='CASHIER', token_date=today).exists():
        print(f'  Token already exists for {visit.visit_number}')
        continue

    counters[tier] = counters.get(tier, 0) + 1
    prefix = prefix_map.get(tier, 'S')
    token_num = f'{prefix}{counters[tier]:03d}'
    priority = TIER_PRIORITY.get(tier, 0)

    token = QueueToken(
        token_number=token_num,
        token_date=today,
        patient=p,
        visit=visit,
        patient_name=p.full_name,
        service_type='CASHIER',
        service_tier=tier,
        status='WAITING',
        priority=priority,
        issued_at=now,
        issued_by=admin,
        issuance_point='GATE',
    )
    token.save()
    print(f'  Cashier token:   {token_num} | priority={priority} | status=WAITING')
    created.append((p.full_name, tier, token_num))

print('\n' + '='*60)
print('CASHIER QUEUE TOKENS CREATED TODAY')
print('='*60)
for name, tier, tok in created:
    print(f'  {tok:8s}  [{tier:10s}]  {name}')
print(f'\nTotal created: {len(created)}')
print('Log into cashier account and check Cashier Queue.')
