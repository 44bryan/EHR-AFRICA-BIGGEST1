#!/usr/bin/env python
"""Seed 4 more fresh VIP patients for cashier queue testing."""
import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.production')
sys.path.insert(0, '/opt/ehr-africa')
django.setup()

from django.utils import timezone
from apps.patients.models import Patient, Visit, VisitStatus, ServiceTier

today = timezone.localdate()

patients_data = [
    {'first_name': 'Christelle', 'last_name': 'Nguimbous', 'gender': 'F', 'dob': '1988-04-12', 'phone': '677000011'},
    {'first_name': 'Patrick',    'last_name': 'Elong',     'gender': 'M', 'dob': '1972-09-05', 'phone': '677000012'},
    {'first_name': 'Martine',    'last_name': 'Kenfack',   'gender': 'F', 'dob': '1995-01-25', 'phone': '677000013'},
    {'first_name': 'Daniel',     'last_name': 'Bisseck',   'gender': 'M', 'dob': '1968-06-18', 'phone': '677000014'},
]

import random

created = []
for p in patients_data:
    existing = Patient.objects.filter(first_name=p['first_name'], last_name=p['last_name']).first()
    if existing:
        pat = existing
        print(f"Exists: {pat.first_name} {pat.last_name} — {pat.patient_id}")
    else:
        pat = Patient.objects.create(
            first_name=p['first_name'],
            last_name=p['last_name'],
            gender=p['gender'],
            date_of_birth=p['dob'],
            phone_number=p['phone'],
        )
        print(f"Created: {pat.first_name} {pat.last_name} — {pat.patient_id}")
    created.append(pat)

for pat in created:
    visit = Visit.objects.filter(patient=pat, visit_date__date=today).first()
    if not visit:
        visit = Visit.objects.create(
            patient=pat,
            service_tier=ServiceTier.VIP,
            status=VisitStatus.AT_CASHIER,
            chief_complaint='VIP eye examination',
        )
        print(f"  Visit: {visit.visit_number}")
    else:
        visit.status = VisitStatus.AT_CASHIER
        visit.service_tier = ServiceTier.VIP
        visit.save(update_fields=['status', 'service_tier'])
        print(f"  Visit updated: {visit.visit_number}")

    try:
        from apps.qms.models import QueueToken, TokenStatus, ServiceType, DailyTokenSequence
        existing_token = QueueToken.objects.filter(
            patient=pat, token_date=today,
            service_type=ServiceType.CASHIER,
            status=TokenStatus.WAITING, is_deleted=False,
        ).first()
        if existing_token:
            print(f"  Token exists: #{existing_token.token_number}")
            continue

        token_number = str(random.randint(400, 700))
        token = QueueToken.objects.create(
            patient=pat, visit=visit,
            token_date=today, token_number=token_number,
            service_type=ServiceType.CASHIER,
            service_tier=ServiceTier.VIP,
            status=TokenStatus.WAITING, priority=30,
        )
        print(f"  Token: #{token.token_number} VIP WAITING")
    except Exception as e:
        print(f"  Token error: {e}")

print("\nDone — 4 fresh VIP patients queued at cashier.")
