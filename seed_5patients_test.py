#!/usr/bin/env python
"""
Seed 5 test patients (3 Standard + 2 VIP) with today's visits at AT_CASHIER status.
Run: /opt/ehr-africa/venv/bin/python /tmp/seed_5patients_test.py
"""
import os, sys, django
sys.path.insert(0, '/opt/ehr-africa')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.production')
django.setup()

from django.utils import timezone
from apps.patients.models import Patient, Visit

# Get first admin user as registered_by
from apps.accounts.models import User
admin = User.objects.filter(is_superuser=True).first()
if not admin:
    admin = User.objects.filter(role='SUPER_ADMIN').first()

today = timezone.now()

patients_data = [
    # Standard tier patients
    dict(first_name='Amina', last_name='Bello', gender='F', date_of_birth='1990-03-15',
         phone_number='+237670000001', occupation='Teacher', tier='STANDARD',
         complaint='Eye pain and blurred vision'),
    dict(first_name='Emmanuel', last_name='Fouda', gender='M', date_of_birth='1985-07-22',
         phone_number='+237670000002', occupation='Farmer', tier='STANDARD',
         complaint='Redness in both eyes for 3 days'),
    dict(first_name='Grace', last_name='Nkeng', gender='F', date_of_birth='1975-11-08',
         phone_number='+237670000003', occupation='Trader', tier='STANDARD',
         complaint='Difficulty reading, headache'),
    # VIP tier patients
    dict(first_name='Dr. Michel', last_name='Atangana', gender='M', date_of_birth='1965-05-30',
         phone_number='+237670000004', occupation='Physician', tier='VIP',
         complaint='Annual eye check-up and IOP monitoring'),
    dict(first_name='Nadège', last_name='Mbarga', gender='F', date_of_birth='1980-09-12',
         phone_number='+237670000005', occupation='Business Executive', tier='VIP',
         complaint='Vision change, needs refraction assessment'),
]

created = []
for data in patients_data:
    tier = data.pop('tier')
    complaint = data.pop('complaint')

    # Check if phone already exists
    existing = Patient.objects.filter(phone_number=data['phone_number']).first()
    if existing:
        print(f"SKIP: {data['first_name']} {data['last_name']} already exists ({existing.patient_id})")
        # Still create visit if none today
        from django.utils.timezone import localdate
        today_visits = existing.visits.filter(visit_date__date=localdate())
        if not today_visits.exists():
            visit = Visit.objects.create(
                patient=existing,
                chief_complaint=complaint,
                status='AT_CASHIER',
                service_tier=tier,
                billing_type='SELF_PAY',
                visit_type='NEW',
            )
            print(f"  -> Created visit {visit.visit_number} ({tier})")
        created.append(existing)
        continue

    patient = Patient.objects.create(
        registered_by=admin,
        nationality='Cameroonian',
        country='Cameroon',
        **data
    )

    visit = Visit.objects.create(
        patient=patient,
        chief_complaint=complaint,
        status='AT_CASHIER',
        service_tier=tier,
        billing_type='SELF_PAY',
        visit_type='NEW',
    )

    print(f"OK: {patient.full_name} | {patient.patient_id} | {tier} | Visit: {visit.visit_number}")
    created.append(patient)

print(f"\nDone. {len(created)} patients processed.")
print("Login to cashier account to see and bill them.")
