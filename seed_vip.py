#!/usr/bin/env python
"""Seed 4 VIP patients and route them to the cashier queue."""
import os, sys, django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.production')
sys.path.insert(0, '/opt/ehr-africa')
django.setup()

from django.utils import timezone
from apps.patients.models import Patient, Visit, VisitStatus, ServiceTier

today = timezone.localdate()

patients_data = [
    {'first_name': 'Emmanuel', 'last_name': 'Fotso',   'gender': 'M', 'dob': '1980-03-15', 'phone': '677000001'},
    {'first_name': 'Grace',    'last_name': 'Ngum',    'gender': 'F', 'dob': '1990-07-22', 'phone': '677000002'},
    {'first_name': 'Bernard',  'last_name': 'Tchamba', 'gender': 'M', 'dob': '1975-11-08', 'phone': '677000003'},
    {'first_name': 'Solange',  'last_name': 'Mbarga',  'gender': 'F', 'dob': '1985-05-30', 'phone': '677000004'},
]

created = []
for p in patients_data:
    existing = Patient.objects.filter(first_name=p['first_name'], last_name=p['last_name']).first()
    if existing:
        pat = existing
        print(f"Patient exists: {pat.first_name} {pat.last_name} — ID {pat.patient_id}")
    else:
        pat = Patient.objects.create(
            first_name=p['first_name'],
            last_name=p['last_name'],
            gender=p['gender'],
            date_of_birth=p['dob'],
            phone_number=p['phone'],
        )
        print(f"Patient created: {pat.first_name} {pat.last_name} — ID {pat.patient_id}")
    created.append(pat)

for pat in created:
    # Check for an open visit today
    visit = Visit.objects.filter(patient=pat, visit_date__date=today).first()
    if not visit:
        visit = Visit.objects.create(
            patient=pat,
            service_tier=ServiceTier.VIP,
            status=VisitStatus.AT_CASHIER,
            chief_complaint='Routine VIP eye examination',
        )
        print(f"  Visit created: {visit.visit_number} (VIP, AT_CASHIER)")
    else:
        visit.status = VisitStatus.AT_CASHIER
        visit.service_tier = ServiceTier.VIP
        visit.save(update_fields=['status', 'service_tier'])
        print(f"  Visit updated: {visit.visit_number} → VIP / AT_CASHIER")

    # Issue cashier QMS token
    try:
        from apps.qms.models import QueueToken, TokenStatus, ServiceType, DailyTokenSequence
        existing_token = QueueToken.objects.filter(
            patient=pat,
            token_date=today,
            service_type=ServiceType.CASHIER,
            status=TokenStatus.WAITING,
            is_deleted=False,
        ).first()
        if existing_token:
            print(f"  Token already exists: #{existing_token.token_number}")
            continue

        try:
            token_number = DailyTokenSequence.next_dept_token(ServiceType.CASHIER)
        except Exception as e:
            import random
            print(f"  DailyTokenSequence error: {e} — using random")
            token_number = random.randint(100, 500)

        token = QueueToken.objects.create(
            patient=pat,
            visit=visit,
            token_date=today,
            token_number=token_number,
            service_type=ServiceType.CASHIER,
            service_tier=ServiceTier.VIP,
            status=TokenStatus.WAITING,
            priority=30,
        )
        print(f"  Token issued: #{token.token_number} (VIP, priority=30)")
    except ImportError:
        print("  QMS not available — skipping token")

print("\nDone — 4 VIP patients seeded and queued at cashier.")
