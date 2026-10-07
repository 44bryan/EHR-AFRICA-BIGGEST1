"""
Create additional dry run demo accounts for EHR Africa.
Run on server: python create_extra_dry_run_accounts.py
Adds accounts that are missing from the first batch.
"""
import os, sys, django

os.chdir('/opt/ehr-africa')
sys.path.insert(0, '/opt/ehr-africa')
os.environ['DJANGO_SETTINGS_MODULE'] = 'ehr_project.settings.production'
django.setup()

from apps.accounts.models import User

NEW_ACCOUNTS = [
    # (first, last, username, password, role, cashier_station, consultation_unit)

    # ── Standard OPD — 4 more General Ophthalmologists (doctor01 exists) ─────
    ('Demo', 'GenOph2',     'doctor02',   'Demo@2026!', 'ophthalmologist', 'ALL', 'GENERAL'),
    ('Demo', 'GenOph3',     'doctor03',   'Demo@2026!', 'ophthalmologist', 'ALL', 'GENERAL'),
    ('Demo', 'GenOph4',     'doctor04',   'Demo@2026!', 'ophthalmologist', 'ALL', 'GENERAL'),
    ('Demo', 'GenOph5',     'doctor05',   'Demo@2026!', 'ophthalmologist', 'ALL', 'GENERAL'),

    # ── Express / Fast Track Clinic ───────────────────────────────────────────
    ('Demo', 'ExpressDoc1', 'expdoc01',   'Demo@2026!', 'ophthalmologist', 'ALL', 'EXP_CONSULT'),
    ('Demo', 'ExpressDoc2', 'expdoc02',   'Demo@2026!', 'ophthalmologist', 'ALL', 'EXP_CONSULT'),
    ('Demo', 'ExpressNurse','expnurse01', 'Demo@2026!', 'opd_nurse',       'ALL', 'GENERAL'),

    # ── VIP Clinic ────────────────────────────────────────────────────────────
    ('Demo', 'VIPDoc1',     'vipdoc01',   'Demo@2026!', 'ophthalmologist', 'ALL', 'VIP_CONSULT'),
    ('Demo', 'VIPDoc2',     'vipdoc02',   'Demo@2026!', 'ophthalmologist', 'ALL', 'VIP_CONSULT'),
    ('Demo', 'VIPNurse',    'vipnurse01', 'Demo@2026!', 'opd_nurse',       'ALL', 'GENERAL'),

    # ── Insured / HMO Clinic ──────────────────────────────────────────────────
    ('Demo', 'InsDoc1',     'insdoc01',   'Demo@2026!', 'ophthalmologist', 'ALL', 'INSUR_CONSULT'),
    ('Demo', 'InsDoc2',     'insdoc02',   'Demo@2026!', 'ophthalmologist', 'ALL', 'INSUR_CONSULT'),
    ('Demo', 'InsNurse',    'insnurse01', 'Demo@2026!', 'opd_nurse',       'ALL', 'GENERAL'),

    # ── Standard OPD — 2 more Triage Nurses (nurse01 exists) ─────────────────
    ('Demo', 'TriageNurse2','nurse02',    'Demo@2026!', 'opd_nurse',       'ALL', 'GENERAL'),
    ('Demo', 'TriageNurse3','nurse03',    'Demo@2026!', 'opd_nurse',       'ALL', 'GENERAL'),

    # ── Standard OPD — 1 more Consultation Nurse (cnurse01 exists) ───────────
    ('Demo', 'ConsNurse2',  'cnurse02',   'Demo@2026!', 'consultation_nurse','ALL','GENERAL'),

    # ── Standard OPD — 2 more General Cashiers (cashier01 exists) ────────────
    ('Demo', 'Cashier2',    'cashier02',  'Demo@2026!', 'cashier',         'GEN', 'GENERAL'),
    ('Demo', 'Cashier3',    'cashier03',  'Demo@2026!', 'cashier',         'GEN', 'GENERAL'),

    # ── Optometry — 2 more (optom01 exists) ──────────────────────────────────
    ('Demo', 'Optometrist2','optom02',    'Demo@2026!', 'optometrist',     'ALL', 'GENERAL'),
    ('Demo', 'Optometrist3','optom03',    'Demo@2026!', 'optometrist',     'ALL', 'GENERAL'),
]

created = skipped = 0
for fname, lname, uname, pwd, role, station, unit in NEW_ACCOUNTS:
    if User.objects.filter(username=uname).exists():
        print(f'  EXISTS : {uname}')
        skipped += 1
        continue
    u = User(
        first_name=fname, last_name=lname,
        username=uname, email=f'{uname}@demo.ehr',
        role=role, cashier_station=station, consultation_unit=unit,
        must_change_password=False, is_active=True, employee_id=None,
    )
    u.set_password(pwd)
    u.save()
    print(f'  CREATED: {uname} ({role} / {unit})')
    created += 1

print(f'\nDone — {created} created, {skipped} already existed.')
