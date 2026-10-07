"""
Create dry run demo accounts for EHR Africa.
Run on server: python create_dry_run_accounts.py
"""
import os, sys, django

os.chdir('/opt/ehr-africa')
sys.path.insert(0, '/opt/ehr-africa')
os.environ['DJANGO_SETTINGS_MODULE'] = 'ehr_project.settings.production'
django.setup()

from apps.accounts.models import User

ACCOUNTS = [
    # (first_name, last_name, username, password, role, cashier_station, consultation_unit)
    # ── Gate & Reception ──────────────────────────────────────────────────────
    ('Demo', 'Gatekeeper',    'gate01',    'Demo@2026!', 'gatekeeper',          'ALL',     'GENERAL'),
    ('Demo', 'Receptionist',  'recep01',   'Demo@2026!', 'receptionist',        'ALL',     'GENERAL'),
    ('Demo', 'MedRecords',    'medrec01',  'Demo@2026!', 'medical_records',     'ALL',     'GENERAL'),
    # ── Triage / OPD Nurses ──────────────────────────────────────────────────
    ('Demo', 'TriageNurse',   'nurse01',   'Demo@2026!', 'opd_nurse',           'ALL',     'GENERAL'),
    ('Demo', 'ConsultNurse',  'cnurse01',  'Demo@2026!', 'consultation_nurse',  'ALL',     'GENERAL'),
    ('Demo', 'WardNurse',     'wardnurse01','Demo@2026!','ward_nurse',          'ALL',     'GENERAL'),
    # ── Doctors ──────────────────────────────────────────────────────────────
    ('Demo', 'GenOphthalmol', 'doctor01',  'Demo@2026!', 'ophthalmologist',     'ALL',     'GENERAL'),
    ('Demo', 'RetinaSpec',    'retina01',  'Demo@2026!', 'ophthalmologist',     'ALL',     'RETINA'),
    ('Demo', 'GlaucomaSpec',  'glauco01',  'Demo@2026!', 'ophthalmologist',     'ALL',     'GLAUCOMA'),
    ('Demo', 'CataractSurg',  'cataract01','Demo@2026!', 'ophthalmologist',     'ALL',     'GENERAL'),
    ('Demo', 'Optometrist',   'optom01',   'Demo@2026!', 'optometrist',         'ALL',     'GENERAL'),
    ('Demo', 'PediatricOph',  'paedoph01', 'Demo@2026!', 'pediatric_refractionist','ALL',  'GENERAL'),
    ('Demo', 'LowVision',     'lowvis01',  'Demo@2026!', 'low_vision_specialist','ALL',    'GENERAL'),
    ('Demo', 'Anaesthetist',  'anaes01',   'Demo@2026!', 'anaesthetist',        'ALL',     'GENERAL'),
    ('Demo', 'MedDirector',   'meddir01',  'Demo@2026!', 'medical_director',    'ALL',     'GENERAL'),
    # ── Billing & Cashiers ────────────────────────────────────────────────────
    ('Demo', 'Cashier',       'cashier01', 'Demo@2026!', 'cashier',             'GEN',     'GENERAL'),
    ('Demo', 'CashierVIP',    'cashiervip','Demo@2026!', 'cashier',             'VIP',     'GENERAL'),
    ('Demo', 'CashierExpress','cashierexp','Demo@2026!', 'cashier',             'EXPRESS', 'GENERAL'),
    ('Demo', 'ChiefCashier',  'chiefcash01','Demo@2026!','chief_cashier',       'ALL',     'GENERAL'),
    ('Demo', 'BillingOfficer','billing01', 'Demo@2026!', 'billing_officer',     'ALL',     'GENERAL'),
    ('Demo', 'Accountant',    'account01', 'Demo@2026!', 'accountant',          'ALL',     'GENERAL'),
    # ── QMS ──────────────────────────────────────────────────────────────────
    ('Demo', 'TSO',           'tso01',     'Demo@2026!', 'gatekeeper',          'ALL',     'GENERAL'),
    # ── Pharmacy & Lab ────────────────────────────────────────────────────────
    ('Demo', 'Pharmacist',    'pharma01',  'Demo@2026!', 'pharmacist',          'ALL',     'GENERAL'),
    ('Demo', 'LabTech',       'labtech01', 'Demo@2026!', 'lab_technician',      'ALL',     'GENERAL'),
    ('Demo', 'InvestTech',    'invest01',  'Demo@2026!', 'investigation_tech',  'ALL',     'GENERAL'),
    # ── Opticals ─────────────────────────────────────────────────────────────
    ('Demo', 'OptDispenser',  'optics01',  'Demo@2026!', 'optical_dispenser',   'ALL',     'GENERAL'),
    # ── IPD / Surgical ────────────────────────────────────────────────────────
    ('Demo', 'TheatreNurse',  'theatre01', 'Demo@2026!', 'theatre_nurse',       'ALL',     'GENERAL'),
    ('Demo', 'AdmissionOfc',  'admiss01',  'Demo@2026!', 'admission_officer',   'ALL',     'GENERAL'),
    # ── Finance & Management ──────────────────────────────────────────────────
    ('Demo', 'FinanceDir',    'findir01',  'Demo@2026!', 'finance_director',    'ALL',     'GENERAL'),
    ('Demo', 'AdminDirector', 'admindir01','Demo@2026!', 'admin_director',      'ALL',     'GENERAL'),
    ('Demo', 'CEO',           'ceo01',     'Demo@2026!', 'ceo',                 'ALL',     'GENERAL'),
]

ROLE_LABELS = {
    'gatekeeper': 'Gatekeeper',
    'receptionist': 'Receptionist',
    'medical_records': 'Medical Records Officer',
    'opd_nurse': 'OPD / Triage Nurse',
    'consultation_nurse': 'Consultation Nurse',
    'ward_nurse': 'Ward Nurse',
    'theatre_nurse': 'Theatre Nurse',
    'ophthalmologist': 'Ophthalmologist / Doctor',
    'optometrist': 'Optometrist',
    'pediatric_refractionist': 'Pediatric Refractionist',
    'low_vision_specialist': 'Low Vision Specialist',
    'anaesthetist': 'Anaesthetist',
    'medical_director': 'Medical Director',
    'cashier': 'Cashier',
    'chief_cashier': 'Chief Cashier',
    'billing_officer': 'Billing Officer',
    'accountant': 'Accountant',
    'pharmacist': 'Pharmacist',
    'lab_technician': 'Lab Technician',
    'investigation_tech': 'Investigation Technician',
    'optical_dispenser': 'Optical Dispenser',
    'admission_officer': 'Admission Officer',
    'finance_director': 'Finance Director',
    'admin_director': 'Admin Director',
    'ceo': 'CEO',
}

created = []
for fname, lname, uname, pwd, role, station, unit in ACCOUNTS:
    if User.objects.filter(username=uname).exists():
        print(f'  EXISTS: {uname}')
        u = User.objects.get(username=uname)
        created.append((fname, lname, uname, pwd, role, station, unit))
        continue
    u = User(
        first_name=fname, last_name=lname,
        username=uname, email=f'{uname}@demo.ehr',
        role=role, cashier_station=station, consultation_unit=unit,
        must_change_password=False, is_active=True,
        employee_id=None,
    )
    u.set_password(pwd)
    u.save()
    print(f'  CREATED: {uname} ({role})')
    created.append((fname, lname, uname, pwd, role, station, unit))

print(f'\nTotal accounts: {len(created)}')

# Print credentials table
print('\n' + '='*80)
print(f'{"NAME":<22} {"USERNAME":<14} {"PASSWORD":<14} {"ROLE":<30} {"STATION":<10}')
print('-'*80)
for fname, lname, uname, pwd, role, station, unit in created:
    fullname = f'{fname} {lname}'
    rlabel = ROLE_LABELS.get(role, role)
    extra = f' [{unit}]' if unit not in ('GENERAL','ALL') else (f' [{station}]' if station not in ('ALL',) else '')
    print(f'{fullname:<22} {uname:<14} {pwd:<14} {rlabel+extra:<30}')
print('='*80)
