"""
Create all Demo Run 2 staff accounts on the production server
and generate a printable credentials HTML document locally.
"""
import paramiko, sys, os

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'
APP_DIR = '/opt/ehr-africa'

# ─── Account definitions ────────────────────────────────────────────────────
ACCOUNTS = [
    # ── CASHIERS ──
    dict(username='dr2_cash_vip',   first='VIP',      last='Cashier',       role='cashier',                 patient_tier='VIP',      cashier_station='VIP',       consultation_unit='GENERAL', email='dr2.cash.vip@demorun2.ehr'),
    dict(username='dr2_cash_std',   first='Standard', last='Cashier',       role='cashier',                 patient_tier='STANDARD', cashier_station='STANDARD',  consultation_unit='GENERAL', email='dr2.cash.std@demorun2.ehr'),
    dict(username='dr2_cash_exp',   first='Express',  last='Cashier',       role='cashier',                 patient_tier='EXPRESS',  cashier_station='FAST_TRACK',consultation_unit='GENERAL', email='dr2.cash.exp@demorun2.ehr'),
    # ── RECEPTIONISTS ──
    dict(username='dr2_recept_vip', first='VIP',      last='Receptionist',  role='receptionist',            patient_tier='VIP',      cashier_station='ALL',       consultation_unit='GENERAL', email='dr2.recept.vip@demorun2.ehr'),
    dict(username='dr2_recept_std', first='Standard', last='Receptionist',  role='receptionist',            patient_tier='STANDARD', cashier_station='ALL',       consultation_unit='GENERAL', email='dr2.recept.std@demorun2.ehr'),
    dict(username='dr2_recept_exp', first='Express',  last='Receptionist',  role='receptionist',            patient_tier='EXPRESS',  cashier_station='ALL',       consultation_unit='GENERAL', email='dr2.recept.exp@demorun2.ehr'),
    # ── TRIAGE NURSES ──
    dict(username='dr2_nurse_vip',  first='VIP',      last='Triage Nurse',  role='nurse',                   patient_tier='VIP',      cashier_station='ALL',       consultation_unit='GENERAL', email='dr2.nurse.vip@demorun2.ehr'),
    dict(username='dr2_nurse_std',  first='Standard', last='Triage Nurse',  role='nurse',                   patient_tier='STANDARD', cashier_station='ALL',       consultation_unit='GENERAL', email='dr2.nurse.std@demorun2.ehr'),
    dict(username='dr2_nurse_exp',  first='Express',  last='Triage Nurse',  role='nurse',                   patient_tier='EXPRESS',  cashier_station='ALL',       consultation_unit='GENERAL', email='dr2.nurse.exp@demorun2.ehr'),
    # ── REFRACTIONISTS ──
    dict(username='dr2_ref_vip1',   first='VIP',      last='Refractionist 1', role='optometrist',           patient_tier='VIP',      cashier_station='ALL',       consultation_unit='GENERAL', email='dr2.ref.vip1@demorun2.ehr'),
    dict(username='dr2_ref_vip2',   first='VIP',      last='Refractionist 2', role='optometrist',           patient_tier='VIP',      cashier_station='ALL',       consultation_unit='GENERAL', email='dr2.ref.vip2@demorun2.ehr'),
    dict(username='dr2_ref_std1',   first='Standard', last='Refractionist 1', role='optometrist',           patient_tier='STANDARD', cashier_station='ALL',       consultation_unit='GENERAL', email='dr2.ref.std1@demorun2.ehr'),
    dict(username='dr2_ref_std2',   first='Standard', last='Refractionist 2', role='optometrist',           patient_tier='STANDARD', cashier_station='ALL',       consultation_unit='GENERAL', email='dr2.ref.std2@demorun2.ehr'),
    dict(username='dr2_ref_exp1',   first='Express',  last='Refractionist 1', role='optometrist',           patient_tier='EXPRESS',  cashier_station='ALL',       consultation_unit='GENERAL', email='dr2.ref.exp1@demorun2.ehr'),
    dict(username='dr2_ref_exp2',   first='Express',  last='Refractionist 2', role='optometrist',           patient_tier='EXPRESS',  cashier_station='ALL',       consultation_unit='GENERAL', email='dr2.ref.exp2@demorun2.ehr'),
    # ── DOCTORS ──
    dict(username='dr2_dr_vip_ret', first='VIP',      last='Retina Specialist',   role='ophthalmologist',   patient_tier='VIP',      cashier_station='ALL',       consultation_unit='VIP_CONSULT', email='dr2.dr.vip.ret@demorun2.ehr'),
    dict(username='dr2_dr_vip_gla', first='VIP',      last='Glaucoma Specialist',  role='ophthalmologist',  patient_tier='VIP',      cashier_station='ALL',       consultation_unit='VIP_CONSULT', email='dr2.dr.vip.gla@demorun2.ehr'),
    dict(username='dr2_dr_std_ret', first='Standard', last='Retina Specialist',   role='ophthalmologist',   patient_tier='STANDARD', cashier_station='ALL',       consultation_unit='GENERAL', email='dr2.dr.std.ret@demorun2.ehr'),
    dict(username='dr2_dr_std_gla', first='Standard', last='Glaucoma Specialist',  role='ophthalmologist',  patient_tier='STANDARD', cashier_station='ALL',       consultation_unit='GENERAL', email='dr2.dr.std.gla@demorun2.ehr'),
    dict(username='dr2_dr_exp_ret', first='Express',  last='Retina Specialist',   role='ophthalmologist',   patient_tier='EXPRESS',  cashier_station='ALL',       consultation_unit='EXP_CONSULT', email='dr2.dr.exp.ret@demorun2.ehr'),
    dict(username='dr2_dr_exp_gla', first='Express',  last='Glaucoma Specialist',  role='ophthalmologist',  patient_tier='EXPRESS',  cashier_station='ALL',       consultation_unit='EXP_CONSULT', email='dr2.dr.exp.gla@demorun2.ehr'),
    dict(username='dr2_dr_general', first='General',  last='Doctor',              role='ophthalmologist',   patient_tier='ALL',      cashier_station='ALL',       consultation_unit='GENERAL', email='dr2.dr.general@demorun2.ehr'),
    # ── TECHNICAL / SHARED ──
    dict(username='dr2_invest',     first='Investigation', last='Technician',  role='investigation_technician', patient_tier='ALL', cashier_station='ALL',       consultation_unit='GENERAL', email='dr2.invest@demorun2.ehr'),
    dict(username='dr2_labtech',    first='Lab',           last='Technician',  role='lab_technician',           patient_tier='ALL', cashier_station='ALL',       consultation_unit='GENERAL', email='dr2.labtech@demorun2.ehr'),
    dict(username='dr2_opt_cash',   first='Optical',       last='Cashier',     role='cashier',                  patient_tier='ALL', cashier_station='ALL',       consultation_unit='GENERAL', email='dr2.opt.cash@demorun2.ehr'),
    dict(username='dr2_opt_disp',   first='Optical',       last='Dispenser',   role='optical_dispenser',        patient_tier='ALL', cashier_station='ALL',       consultation_unit='GENERAL', email='dr2.opt.disp@demorun2.ehr'),
    dict(username='dr2_pharma',     first='Pharmacy',      last='Staff',       role='pharmacist',               patient_tier='ALL', cashier_station='ALL',       consultation_unit='GENERAL', email='dr2.pharma@demorun2.ehr'),
    dict(username='dr2_counsel',    first='Counseling',    last='Nurse',       role='counseling_nurse',         patient_tier='ALL', cashier_station='ALL',       consultation_unit='GENERAL', email='dr2.counsel@demorun2.ehr'),
    dict(username='dr2_admission',  first='Admission',     last='Nurse',       role='ward_nurse',               patient_tier='ALL', cashier_station='ALL',       consultation_unit='GENERAL', email='dr2.admission@demorun2.ehr'),
]

PASSWORD = 'DemoRun2@2026'

# ─── Build server-side creation script ──────────────────────────────────────
lines = [
    "import django, os, sys",
    "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.production')",
    "sys.path.insert(0, '/opt/ehr-africa')",
    "django.setup()",
    "from apps.accounts.models import User",
    "created, skipped = [], []",
]
for a in ACCOUNTS:
    lines.append(
        f"if not User.objects.filter(username='{a['username']}').exists():\n"
        f"    u=User.objects.create_user(username='{a['username']}',password='{PASSWORD}',"
        f"email='{a['email']}',first_name='{a['first']}',last_name='{a['last']}',"
        f"role='{a['role']}',patient_tier='{a['patient_tier']}',"
        f"cashier_station='{a['cashier_station']}',consultation_unit='{a['consultation_unit']}')\n"
        f"    created.append('{a['username']}')\n"
        f"else:\n"
        f"    skipped.append('{a['username']}')"
    )
lines.append("print('CREATED:', len(created))")
lines.append("print('SKIPPED (already exist):', len(skipped))")
lines.append("[print(' +', u) for u in created]")

script = '\n'.join(lines)

# ─── Connect & run ───────────────────────────────────────────────────────────
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS)

sftp = ssh.open_sftp()
with sftp.open('/tmp/create_dr2.py', 'w') as f:
    f.write(script)
sftp.close()
print('Script uploaded. Running...')

_, stdout, stderr = ssh.exec_command(
    'cd /opt/ehr-africa && /opt/ehr-africa/venv/bin/python /tmp/create_dr2.py'
)
stdout.channel.recv_exit_status()
out = stdout.read().decode('utf-8', errors='replace')
err = stderr.read().decode('utf-8', errors='replace')
sys.stdout.buffer.write(out.encode('utf-8', errors='replace'))
if err:
    sys.stdout.buffer.write(('ERRORS: ' + err + '\n').encode('utf-8', errors='replace'))

ssh.close()

# ─── Generate printable credentials HTML ────────────────────────────────────
ROLE_LABELS = {
    'cashier': 'Cashier',
    'receptionist': 'Receptionist',
    'nurse': 'OPD Nurse (Triage)',
    'optometrist': 'Optometrist / Refractionist',
    'ophthalmologist': 'Ophthalmologist / Doctor',
    'investigation_technician': 'Investigation Technician',
    'lab_technician': 'Lab Technician',
    'optical_dispenser': 'Optical Dispenser',
    'pharmacist': 'Pharmacist',
    'counseling_nurse': 'Surgical Counseling Nurse',
    'ward_nurse': 'Ward / Admission Nurse',
}

TIER_BADGE = {
    'VIP': ('<span style="background:#7c3aed;color:#fff;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:700;">VIP</span>'),
    'EXPRESS': ('<span style="background:#d97706;color:#fff;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:700;">EXPRESS</span>'),
    'STANDARD': ('<span style="background:#2563eb;color:#fff;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:700;">STANDARD</span>'),
    'ALL': ('<span style="background:#374151;color:#fff;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:700;">ALL TIERS</span>'),
}

SECTIONS = [
    ('CASHIERS', [a for a in ACCOUNTS if a['role'] == 'cashier' and a['last'] == 'Cashier']),
    ('RECEPTIONISTS', [a for a in ACCOUNTS if a['role'] == 'receptionist']),
    ('TRIAGE NURSES', [a for a in ACCOUNTS if a['role'] == 'nurse']),
    ('REFRACTIONISTS', [a for a in ACCOUNTS if a['role'] == 'optometrist']),
    ('DOCTORS', [a for a in ACCOUNTS if a['role'] == 'ophthalmologist']),
    ('INVESTIGATION & LAB', [a for a in ACCOUNTS if a['role'] in ('investigation_technician', 'lab_technician')]),
    ('OPTICAL SHOP', [a for a in ACCOUNTS if a['role'] in ('optical_dispenser',) or (a['role'] == 'cashier' and a['last'] == 'Cashier' and a['username'] == 'dr2_opt_cash')]),
    ('PHARMACY', [a for a in ACCOUNTS if a['role'] == 'pharmacist']),
    ('NURSING (SHARED)', [a for a in ACCOUNTS if a['role'] in ('counseling_nurse', 'ward_nurse')]),
]

# Rebuild sections cleanly
SECTIONS = [
    ('CASHIERS',           [a for a in ACCOUNTS if 'cash' in a['username'] and a['role'] == 'cashier' and 'opt' not in a['username']]),
    ('RECEPTIONISTS',      [a for a in ACCOUNTS if a['role'] == 'receptionist']),
    ('TRIAGE NURSES',      [a for a in ACCOUNTS if a['role'] == 'nurse']),
    ('REFRACTIONISTS',     [a for a in ACCOUNTS if a['role'] == 'optometrist']),
    ('DOCTORS',            [a for a in ACCOUNTS if a['role'] == 'ophthalmologist']),
    ('INVESTIGATION & LAB',[a for a in ACCOUNTS if a['role'] in ('investigation_technician', 'lab_technician')]),
    ('OPTICAL SHOP',       [a for a in ACCOUNTS if 'opt' in a['username']]),
    ('PHARMACY',           [a for a in ACCOUNTS if a['role'] == 'pharmacist']),
    ('NURSING (SHARED)',   [a for a in ACCOUNTS if a['role'] in ('counseling_nurse', 'ward_nurse')]),
]

def card(a):
    tier = a.get('patient_tier', 'ALL')
    cu = a.get('consultation_unit', 'GENERAL')
    cu_note = ''
    if a['role'] == 'ophthalmologist':
        cu_map = {'VIP_CONSULT': 'VIP Consultation', 'EXP_CONSULT': 'Express Consultation', 'GENERAL': 'General / Standard Consultation'}
        cu_note = f'<div style="font-size:10px;color:#6b7280;margin-top:2px;">Unit: {cu_map.get(cu, cu)}</div>'
    return f'''
    <div style="border:1px solid #e5e7eb;border-radius:8px;padding:12px 16px;margin:6px 0;page-break-inside:avoid;background:#fff;">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;">
        <div>
          <div style="font-size:13px;font-weight:700;color:#111;">{a['first']} {a['last']}</div>
          <div style="font-size:11px;color:#4b5563;margin-top:1px;">{ROLE_LABELS.get(a['role'], a['role'])}</div>
          {cu_note}
        </div>
        <div style="text-align:right;">{TIER_BADGE.get(tier, tier)}</div>
      </div>
      <div style="margin-top:10px;display:flex;gap:20px;font-size:11px;">
        <div><span style="color:#6b7280;">Username</span><br><code style="font-size:12px;font-weight:700;color:#1d4ed8;">{a['username']}</code></div>
        <div><span style="color:#6b7280;">Password</span><br><code style="font-size:12px;font-weight:700;color:#1d4ed8;">{PASSWORD}</code></div>
      </div>
    </div>'''

sections_html = ''
for title, accts in SECTIONS:
    if not accts:
        continue
    cards = ''.join(card(a) for a in accts)
    sections_html += f'''
    <div style="margin-bottom:24px;page-break-inside:avoid;">
      <div style="background:#1e3a5f;color:#fff;padding:8px 16px;border-radius:6px 6px 0 0;font-size:12px;font-weight:700;letter-spacing:.08em;">{title}</div>
      <div style="border:1px solid #1e3a5f;border-top:none;border-radius:0 0 6px 6px;padding:8px 8px 4px;">
        {cards}
      </div>
    </div>'''

html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>EHR Africa — Demo Run 2 Staff Credentials</title>
<style>
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ font-family: Arial, sans-serif; background:#f9fafb; padding:20px; }}
  @media print {{
    body {{ background:#fff; padding:10px; }}
    .no-print {{ display:none !important; }}
  }}
  code {{ font-family: "Courier New", monospace; }}
</style>
</head>
<body>

<div class="no-print" style="background:#1e3a5f;color:#fff;padding:12px 20px;border-radius:8px;margin-bottom:20px;display:flex;justify-content:space-between;align-items:center;">
  <span style="font-weight:700;">EHR Africa — Demo Run 2 Credentials Sheet</span>
  <button onclick="window.print()" style="background:#fff;color:#1e3a5f;border:none;padding:8px 20px;border-radius:6px;font-weight:700;cursor:pointer;">🖨 Print</button>
</div>

<!-- Header -->
<div style="text-align:center;margin-bottom:24px;border-bottom:3px solid #1e3a5f;padding-bottom:16px;">
  <div style="font-size:20px;font-weight:800;color:#1e3a5f;letter-spacing:.04em;">EHR AFRICA — DEMO RUN 2</div>
  <div style="font-size:14px;color:#374151;margin-top:4px;">Staff Login Credentials — Confidential — Do Not Share</div>
  <div style="font-size:12px;color:#6b7280;margin-top:4px;">System URL: <strong>http://192.168.30.169</strong> &nbsp;|&nbsp; Total Accounts: <strong>{len(ACCOUNTS)}</strong></div>
</div>

<!-- Global notice -->
<div style="background:#fef3c7;border:1px solid #fbbf24;border-radius:6px;padding:10px 16px;margin-bottom:20px;font-size:11px;color:#92400e;">
  <strong>INSTRUCTIONS FOR ALL STAFF:</strong> Open a browser and go to <strong>http://192.168.30.169</strong>.
  Enter your username and password below. You will be taken directly to your dashboard.
  Please do not share your credentials. Report any issues to the IT team immediately.
</div>

<!-- Tier legend -->
<div style="display:flex;gap:12px;margin-bottom:20px;flex-wrap:wrap;">
  <div style="font-size:11px;font-weight:600;color:#374151;display:flex;align-items:center;gap:6px;">
    {TIER_BADGE['VIP']} VIP Tier — Premium patients
  </div>
  <div style="font-size:11px;font-weight:600;color:#374151;display:flex;align-items:center;gap:6px;">
    {TIER_BADGE['EXPRESS']} Express Tier — Fast track patients
  </div>
  <div style="font-size:11px;font-weight:600;color:#374151;display:flex;align-items:center;gap:6px;">
    {TIER_BADGE['STANDARD']} Standard Tier — Regular patients
  </div>
  <div style="font-size:11px;font-weight:600;color:#374151;display:flex;align-items:center;gap:6px;">
    {TIER_BADGE['ALL']} All Tiers — Shared departments
  </div>
</div>

{sections_html}

<!-- Footer -->
<div style="text-align:center;margin-top:20px;padding-top:12px;border-top:1px solid #e5e7eb;font-size:10px;color:#9ca3af;">
  EHR Africa — Demo Run 2 &nbsp;|&nbsp; IT Department &nbsp;|&nbsp; Confidential &nbsp;|&nbsp; {len(ACCOUNTS)} accounts issued
</div>

</body>
</html>'''

out_path = r'c:\Users\GROD\Desktop\EHR AFRICA BACKUP\DemoRun2_Credentials.html'
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(html)

print(f'\nCredentials sheet generated: {out_path}')
print(f'Total accounts: {len(ACCOUNTS)}')
print('Open the HTML file in Chrome and use Ctrl+P to print.')
