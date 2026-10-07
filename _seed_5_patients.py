"""
Seed 5 test patients on the production server for flow testing.
All STANDARD tier, realistic Cameroonian data.
"""
import os, sys, django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.base')
sys.path.insert(0, os.path.dirname(__file__))
django.setup()

from apps.patients.models import Patient, Visit
from apps.accounts.models import User
from django.utils import timezone

receptionist = User.objects.filter(role='RECEPTIONIST', is_active=True).first()
if not receptionist:
    receptionist = User.objects.filter(is_superuser=True, is_active=True).first()

PATIENTS = [
    {
        'first_name': 'Emmanuel',
        'last_name': 'Ngassa',
        'date_of_birth': '1988-03-15',
        'gender': 'M',
        'phone_number': '+237670112233',
        'region': 'South West',
        'village_town': 'Buea',
        'address': 'Molyko, Buea',
    },
    {
        'first_name': 'Christelle',
        'last_name': 'Fotso',
        'date_of_birth': '1995-07-22',
        'gender': 'F',
        'phone_number': '+237691223344',
        'region': 'Littoral',
        'village_town': 'Douala',
        'address': 'Akwa, Douala',
    },
    {
        'first_name': 'Alain',
        'last_name': 'Tchinda',
        'date_of_birth': '1972-11-08',
        'gender': 'M',
        'phone_number': '+237655443322',
        'region': 'West',
        'village_town': 'Bafoussam',
        'address': 'Quartier Kamkop, Bafoussam',
    },
    {
        'first_name': 'Grace',
        'last_name': 'Etundi',
        'date_of_birth': '2001-01-30',
        'gender': 'F',
        'phone_number': '+237680998877',
        'region': 'Centre',
        'village_town': 'Yaounde',
        'address': 'Bastos, Yaounde',
    },
    {
        'first_name': 'Samuel',
        'last_name': 'Mbarga',
        'date_of_birth': '1960-06-14',
        'gender': 'M',
        'phone_number': '+237677665544',
        'region': 'North West',
        'village_town': 'Bamenda',
        'address': 'Up Station, Bamenda',
    },
]

now = timezone.now()
today = timezone.localdate()
created = []

for data in PATIENTS:
    dob = data.pop('date_of_birth')
    p = Patient(
        date_of_birth=dob,
        created_by=receptionist,
        **data,
    )
    p.save()

    # Create today's visit at STANDARD tier
    visit = Visit.objects.create(
        patient=p,
        visit_date=now,
        status='REGISTERED',
        service_tier='STANDARD',
        chief_complaint='Routine eye check-up',
        created_by=receptionist,
    )
    created.append((p, visit))
    print(f'  Created: {p.full_name} (ID: {p.patient_id}) — Visit: {visit.status}')

print(f'\n  {len(created)} patients created and registered. Ready for triage.')
