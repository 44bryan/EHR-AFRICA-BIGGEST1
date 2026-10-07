"""Delete all existing QMS counters and create clean Demo Run 2 setup."""
import paramiko, sys

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'

script = """
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.production')
import sys; sys.path.insert(0, '/opt/ehr-africa')
django.setup()
from apps.qms.models import ServiceCounter, StationType
from apps.accounts.models import User

# ── Step 1: Delete all existing counters ─────────────────────────────────────
deleted = ServiceCounter.objects.all().delete()
print(f'Deleted all counters: {deleted}')
print()

# ── Helper ────────────────────────────────────────────────────────────────────
def get_user(username):
    try:
        return User.objects.get(username=username)
    except User.DoesNotExist:
        print(f'  WARNING: user {username} not found')
        return None

def make(code, name, service, tiers, username, station_type=''):
    staff = get_user(username) if username else None
    ServiceCounter.objects.create(
        code=code, name=name, service_type=service,
        serves_tiers=tiers, staff_assigned=staff,
        station_type=station_type, is_active=True,
    )
    print(f'  Created [{code}] {name}')

# ── Step 2: Create clean Demo Run 2 counters ─────────────────────────────────

print('--- RECEPTION & MEDICAL RECORDS ---')
make('DR2-REC-VIP',  'VIP Reception',      'RECEPTIONIST', 'VIP',              'dr2_recept_vip',  'RECEPTION')
make('DR2-REC-STD',  'Standard Reception', 'RECEPTIONIST', 'STANDARD',         'dr2_recept_std',  'RECEPTION')
make('DR2-REC-EXP',  'Express Reception',  'RECEPTIONIST', 'EXPRESS,FAST_TRACK','dr2_recept_exp', 'RECEPTION')
make('DR2-MED-REC',  'Medical Records',    'RECEPTIONIST', '',                 'dr2_med_records', 'RECEPTION')

print()
print('--- TRIAGE / PARAMETERS (Standard & Express only — VIP skips triage) ---')
make('DR2-TRIAGE-STD','Standard Triage',   'PARAMETERS',  'STANDARD',          'dr2_nurse_std',  'TRIAGE')
make('DR2-TRIAGE-EXP','Express Triage',    'PARAMETERS',  'EXPRESS,FAST_TRACK','dr2_nurse_exp',  'TRIAGE')

print()
print('--- REFRACTION (Standard & Express only — VIP doctor handles refraction in-room) ---')
make('DR2-REF-STD1', 'Standard Refraction Room 1', 'REFRACTION', 'STANDARD',          'dr2_ref_std1', 'REFRACTION')
make('DR2-REF-STD2', 'Standard Refraction Room 2', 'REFRACTION', 'STANDARD',          'dr2_ref_std2', 'REFRACTION')
make('DR2-REF-EXP1', 'Express Refraction Room 1',  'REFRACTION', 'EXPRESS,FAST_TRACK','dr2_ref_exp1', 'REFRACTION')
make('DR2-REF-EXP2', 'Express Refraction Room 2',  'REFRACTION', 'EXPRESS,FAST_TRACK','dr2_ref_exp2', 'REFRACTION')

print()
print('--- VIP CONSULTATION (doctor does parameters + refraction + consultation in one room) ---')
make('DR2-VIP-1',   'VIP Consulting Room 1',   'VIP_CONSULT', 'VIP', 'dr2_dr_vip_gen1', 'CONSULTATION')
make('DR2-VIP-2',   'VIP Consulting Room 2',   'VIP_CONSULT', 'VIP', 'dr2_dr_vip_gen2', 'CONSULTATION')
make('DR2-VIP-RET', 'VIP Retina Room',         'VIP_CONSULT', 'VIP', 'dr2_dr_vip_ret',  'SPECIALIST')
make('DR2-VIP-GLA', 'VIP Glaucoma Room',       'VIP_CONSULT', 'VIP', 'dr2_dr_vip_gla',  'SPECIALIST')

print()
print('--- STANDARD CONSULTATION ---')
make('DR2-STD-1',   'Standard Consulting Room 1', 'GENERAL', 'STANDARD', 'dr2_dr_std_gen1', 'CONSULTATION')
make('DR2-STD-2',   'Standard Consulting Room 2', 'GENERAL', 'STANDARD', 'dr2_dr_std_gen2', 'CONSULTATION')
make('DR2-STD-RET', 'Standard Retina Room',       'RETINA',  'STANDARD', 'dr2_dr_std_ret',  'SPECIALIST')
make('DR2-STD-GLA', 'Standard Glaucoma Room',     'GLAUCOMA','STANDARD', 'dr2_dr_std_gla',  'SPECIALIST')

print()
print('--- EXPRESS CONSULTATION ---')
make('DR2-EXP-1',   'Express Consulting Room 1', 'EXP_CONSULT', 'EXPRESS,FAST_TRACK', 'dr2_dr_exp_gen1', 'CONSULTATION')
make('DR2-EXP-2',   'Express Consulting Room 2', 'EXP_CONSULT', 'EXPRESS,FAST_TRACK', 'dr2_dr_exp_gen2', 'CONSULTATION')
make('DR2-EXP-RET', 'Express Retina Room',       'EXP_CONSULT', 'EXPRESS,FAST_TRACK', 'dr2_dr_exp_ret',  'SPECIALIST')
make('DR2-EXP-GLA', 'Express Glaucoma Room',     'EXP_CONSULT', 'EXPRESS,FAST_TRACK', 'dr2_dr_exp_gla',  'SPECIALIST')

print()
print('--- GENERAL / OVERFLOW (cross-tier) ---')
make('DR2-GEN', 'General Consulting Room', 'GENERAL', '', 'dr2_dr_general', 'CONSULTATION')

print()
print('--- INVESTIGATION & LABORATORY ---')
make('DR2-INV', 'Investigation Room', 'INVEST', '', 'dr2_invest',  'INVESTIGATION')
make('DR2-LAB', 'Laboratory',         'LAB',    '', 'dr2_labtech', 'LAB')

print()
print('--- OPTICAL SHOP ---')
make('DR2-OPT', 'Optical Shop', 'OPTICAL', '', 'dr2_opt_disp', 'OPTICAL')

print()
print('--- PHARMACY ---')
make('DR2-RX', 'Pharmacy', 'PHARMACY', '', 'dr2_pharma', 'PHARMACY')

print()
print('--- CASHIERS ---')
make('DR2-CASH-VIP', 'VIP Cashier',      'CASHIER', 'VIP',              'dr2_cash_vip',   'CASHIER')
make('DR2-CASH-STD', 'Standard Cashier', 'CASHIER', 'STANDARD',         'dr2_cash_std',   'CASHIER')
make('DR2-CASH-EXP', 'Express Cashier',  'CASHIER', 'EXPRESS,FAST_TRACK','dr2_cash_exp',  'CASHIER')
make('DR2-CASH-OPT', 'Optical Cashier',  'CASHIER', '',                 'dr2_opt_cash',   'CASHIER')
make('DR2-CHIEF',    'Chief Cashier',     'CASHIER', '',                 'dr2_chief_cash', 'CASHIER')

print()
print('--- NURSING (SHARED) ---')
make('DR2-COUNS', 'Counseling Room', 'COUNSEL',   '', 'dr2_counsel',    'COUNSELING')
make('DR2-ADM',   'Admission Desk',  'ADMISSION', '', 'dr2_admission',  'ADMISSION')

print()
total = ServiceCounter.objects.count()
print(f'DONE. Total counters now: {total}')
"""

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS)
sftp = ssh.open_sftp()
with sftp.open('/tmp/reset_counters.py', 'w') as f:
    f.write(script)
sftp.close()
_, stdout, stderr = ssh.exec_command('cd /opt/ehr-africa && /opt/ehr-africa/venv/bin/python /tmp/reset_counters.py')
stdout.channel.recv_exit_status()
out = stdout.read().decode('utf-8', errors='replace')
err = stderr.read().decode('utf-8', errors='replace')
sys.stdout.buffer.write(out.encode('utf-8', errors='replace'))
if err:
    sys.stdout.buffer.write(('ERR: ' + err + '\n').encode('utf-8', errors='replace'))
ssh.close()
