"""
Deploy latest changes + create unit test accounts + generate credentials PDF.
Run: python deploy_unit_accounts.py
"""
import paramiko, zipfile, io, os, sys
from pathlib import Path

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'
APP_DIR = '/opt/ehr-africa'
VENV_PY = f'{APP_DIR}/venv/bin/python'

PROJECT_ROOT = Path(r'c:\Users\GROD\Desktop\EHR AFRICA BACKUP')

# ── Files changed this session ────────────────────────────────────────────────
CHANGED_FILES = [
    'apps/ai_assistant/views.py',
    'apps/ai_assistant/groq_client.py',
    'templates/ai_assistant/drug_interactions.html',
    'templates/ai_assistant/home.html',
    'templates/ai_assistant/partials/voice_emr.html',
    'templates/billing/proforma_detail.html',
    'templates/components/sidebar.html',
]

# ── Unit accounts ─────────────────────────────────────────────────────────────
ACCOUNTS = [
    # ── VIP Unit ──
    {'first': 'VIP',      'last': 'Cashier',       'username': 'vip_cashier',  'password': 'VipCashier@2026',  'role': 'cashier',         'unit': 'VIP',        'display_role': 'Cashier'},
    {'first': 'VIP',      'last': 'Receptionist',  'username': 'vip_recept',   'password': 'VipRecept@2026',   'role': 'receptionist',    'unit': 'VIP',        'display_role': 'Receptionist'},
    {'first': 'VIP',      'last': 'Triage Nurse',  'username': 'vip_nurse',    'password': 'VipNurse@2026',    'role': 'triage_nurse',    'unit': 'VIP',        'display_role': 'Triage Nurse'},
    {'first': 'VIP',      'last': 'Refractionist', 'username': 'vip_refrac',   'password': 'VipRefrac@2026',   'role': 'optometrist',     'unit': 'VIP',        'display_role': 'Refractionist / Optometrist', 'cu': 'VIP'},
    {'first': 'VIP',      'last': 'Doctor',        'username': 'vip_doctor',   'password': 'VipDoctor@2026',   'role': 'ophthalmologist', 'unit': 'VIP',        'display_role': 'Ophthalmologist', 'cu': 'VIP'},
    # ── Fast Track Unit ──
    {'first': 'FastTrack','last': 'Cashier',       'username': 'ft_cashier',   'password': 'FtCashier@2026',   'role': 'cashier',         'unit': 'FAST_TRACK', 'display_role': 'Cashier'},
    {'first': 'FastTrack','last': 'Receptionist',  'username': 'ft_recept',    'password': 'FtRecept@2026',    'role': 'receptionist',    'unit': 'FAST_TRACK', 'display_role': 'Receptionist'},
    {'first': 'FastTrack','last': 'Triage Nurse',  'username': 'ft_nurse',     'password': 'FtNurse@2026',     'role': 'triage_nurse',    'unit': 'FAST_TRACK', 'display_role': 'Triage Nurse'},
    {'first': 'FastTrack','last': 'Refractionist', 'username': 'ft_refrac',    'password': 'FtRefrac@2026',    'role': 'optometrist',     'unit': 'FAST_TRACK', 'display_role': 'Refractionist / Optometrist', 'cu': 'FAST_TRACK'},
    {'first': 'FastTrack','last': 'Doctor',        'username': 'ft_doctor',    'password': 'FtDoctor@2026',    'role': 'ophthalmologist', 'unit': 'FAST_TRACK', 'display_role': 'Ophthalmologist', 'cu': 'FAST_TRACK'},
    # ── Express Unit ──
    {'first': 'Express',  'last': 'Cashier',       'username': 'exp_cashier',  'password': 'ExpCashier@2026',  'role': 'cashier',         'unit': 'EXPRESS',    'display_role': 'Cashier'},
    {'first': 'Express',  'last': 'Receptionist',  'username': 'exp_recept',   'password': 'ExpRecept@2026',   'role': 'receptionist',    'unit': 'EXPRESS',    'display_role': 'Receptionist'},
    {'first': 'Express',  'last': 'Triage Nurse',  'username': 'exp_nurse',    'password': 'ExpNurse@2026',    'role': 'triage_nurse',    'unit': 'EXPRESS',    'display_role': 'Triage Nurse'},
    {'first': 'Express',  'last': 'Refractionist', 'username': 'exp_refrac',   'password': 'ExpRefrac@2026',   'role': 'optometrist',     'unit': 'EXPRESS',    'display_role': 'Refractionist / Optometrist', 'cu': 'EXPRESS'},
    {'first': 'Express',  'last': 'Doctor',        'username': 'exp_doctor',   'password': 'ExpDoctor@2026',   'role': 'ophthalmologist', 'unit': 'EXPRESS',    'display_role': 'Ophthalmologist', 'cu': 'EXPRESS'},
    # ── Standard Unit ──
    {'first': 'Standard', 'last': 'Cashier',       'username': 'std_cashier',  'password': 'StdCashier@2026',  'role': 'cashier',         'unit': 'STANDARD',   'display_role': 'Cashier'},
    {'first': 'Standard', 'last': 'Receptionist',  'username': 'std_recept',   'password': 'StdRecept@2026',   'role': 'receptionist',    'unit': 'STANDARD',   'display_role': 'Receptionist'},
    {'first': 'Standard', 'last': 'Triage Nurse',  'username': 'std_nurse',    'password': 'StdNurse@2026',    'role': 'triage_nurse',    'unit': 'STANDARD',   'display_role': 'Triage Nurse'},
    {'first': 'Standard', 'last': 'Refractionist', 'username': 'std_refrac',   'password': 'StdRefrac@2026',   'role': 'optometrist',     'unit': 'STANDARD',   'display_role': 'Refractionist / Optometrist', 'cu': 'GENERAL'},
    {'first': 'Standard', 'last': 'Doctor',        'username': 'std_doctor',   'password': 'StdDoctor@2026',   'role': 'ophthalmologist', 'unit': 'STANDARD',   'display_role': 'Ophthalmologist', 'cu': 'GENERAL'},
]


def run(ssh, cmd, desc=''):
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if desc:
        print(f'  {desc}')
    return out, err


def step(msg):
    print(f'\n{"="*60}\n>>  {msg}\n{"="*60}')


# ═══════════════════════════════════════════════════════════════
# STEP 1: Build patch zip
# ═══════════════════════════════════════════════════════════════
step('Building patch zip')
zip_buf = io.BytesIO()
with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
    for rel in CHANGED_FILES:
        fp = PROJECT_ROOT / rel
        if fp.exists():
            zf.write(fp, rel)
            print(f'  + {rel}')
        else:
            print(f'  ! MISSING: {rel}')
zip_buf.seek(0)
print(f'  Zip size: {zip_buf.getbuffer().nbytes:,} bytes')

# ═══════════════════════════════════════════════════════════════
# STEP 2: Connect + deploy
# ═══════════════════════════════════════════════════════════════
step('Connecting to server')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS, timeout=15)
sftp = ssh.open_sftp()
print(f'  Connected to {HOST}')

step('Uploading patch')
sftp.putfo(zip_buf, '/tmp/ehr_patch.zip')
print('  Uploaded /tmp/ehr_patch.zip')

out, err = run(ssh, f'cd {APP_DIR} && unzip -o /tmp/ehr_patch.zip 2>&1 && rm /tmp/ehr_patch.zip', 'Extracting files')
print(f'  {out[:300]}')

# collectstatic for new template
run(ssh, f'cd {APP_DIR} && {VENV_PY} manage.py collectstatic --noinput -v 0 2>&1', 'collectstatic')
print('  Static files collected')

# ═══════════════════════════════════════════════════════════════
# STEP 3: Create unit accounts on server
# ═══════════════════════════════════════════════════════════════
step('Creating unit accounts on server')

acct_lines = []
for a in ACCOUNTS:
    cu = a.get('cu', '')
    acct_lines.append(
        f"  create_user({repr(a['username'])}, {repr(a['first'])}, {repr(a['last'])}, "
        f"{repr(a['password'])}, {repr(a['role'])}, {repr(cu)})"
    )

django_script = r'''
import os, sys, django
sys.path.insert(0, '/opt/ehr-africa')
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ehr_project.settings.production")
django.setup()

from apps.accounts.models import User

ACCOUNTS = ''' + repr(ACCOUNTS) + r'''

def create_user(username, first, last, password, role, cu=''):
    if User.objects.filter(username=username).exists():
        u = User.objects.get(username=username)
        u.set_password(password)
        u.role = role
        if cu:
            u.consultation_unit = cu
        u.save()
        return f"UPDATED  {username}"
    u = User(
        username=username,
        first_name=first,
        last_name=last,
        role=role,
        is_active=True,
    )
    u.set_password(password)
    if cu:
        u.consultation_unit = cu
    u.save()
    return f"CREATED  {username}"

for a in ACCOUNTS:
    cu = a.get('cu', '')
    print(create_user(a['username'], a['first'], a['last'], a['password'], a['role'], cu))

print("DONE")
'''

# write script to server
sftp.putfo(io.BytesIO(django_script.encode()), '/tmp/create_unit_accounts.py')
out, err = run(ssh, f'cd {APP_DIR} && {VENV_PY} /tmp/create_unit_accounts.py 2>&1', 'Running account creation')
print(out)
if 'DONE' not in out:
    print(f'  STDERR: {err[:500]}')
run(ssh, 'rm /tmp/create_unit_accounts.py')

# ═══════════════════════════════════════════════════════════════
# STEP 4: Restart gunicorn
# ═══════════════════════════════════════════════════════════════
step('Restarting gunicorn')
out, err = run(ssh, 'sudo systemctl restart ehr-gunicorn 2>&1', 'Restarting ehr-gunicorn')
import time; time.sleep(3)
out, _ = run(ssh, 'sudo systemctl is-active ehr-gunicorn')
print(f'  ehr-gunicorn status: {out}')

sftp.close()
ssh.close()
print('\n  Server deployment complete.')

# ═══════════════════════════════════════════════════════════════
# STEP 5: Generate credentials HTML/PDF
# ═══════════════════════════════════════════════════════════════
step('Generating credentials document')

UNITS = [
    ('VIP',        'VIP',        '#7c3aed', '#f5f3ff', [a for a in ACCOUNTS if a['unit'] == 'VIP']),
    ('FAST_TRACK', 'Fast Track', '#d97706', '#fffbeb', [a for a in ACCOUNTS if a['unit'] == 'FAST_TRACK']),
    ('EXPRESS',    'Express',    '#0891b2', '#ecfeff', [a for a in ACCOUNTS if a['unit'] == 'EXPRESS']),
    ('STANDARD',   'Standard',   '#16a34a', '#f0fdf4', [a for a in ACCOUNTS if a['unit'] == 'STANDARD']),
]

role_icons = {
    'cashier':         '[Cash]',
    'receptionist':    '[Rcpt]',
    'triage_nurse':    '[Nrse]',
    'optometrist':     '[Rfrc]',
    'ophthalmologist': '[Doct]',
}

cards_html = ''
for unit_key, unit_label, color, bg, accts in UNITS:
    rows = ''
    for a in accts:
        icon = role_icons.get(a['role'], '👤')
        rows += f'''
        <tr>
          <td style="padding:10px 14px; border-bottom:1px solid #e5e7eb;">
            <span style="font-size:1.15em;">{icon}</span>
            <strong style="margin-left:6px;">{a['display_role']}</strong>
          </td>
          <td style="padding:10px 14px; border-bottom:1px solid #e5e7eb; font-family:monospace; font-size:0.95em; color:#374151;">{a['username']}</td>
          <td style="padding:10px 14px; border-bottom:1px solid #e5e7eb; font-family:monospace; font-size:0.95em; color:#374151;">{a['password']}</td>
        </tr>'''

    cards_html += f'''
    <div style="break-inside:avoid; margin-bottom:28px; border-radius:10px; overflow:hidden;
                border:1.5px solid {color}; box-shadow:0 2px 8px rgba(0,0,0,0.07);">
      <div style="background:{color}; color:#fff; padding:14px 20px;
                  font-size:1.15em; font-weight:700; letter-spacing:.03em;">
        ● {unit_label} Unit — Login Credentials
      </div>
      <table style="width:100%; border-collapse:collapse; background:{bg};">
        <thead>
          <tr style="background:rgba(0,0,0,0.04);">
            <th style="padding:8px 14px; text-align:left; font-size:.82em; color:#6b7280; font-weight:600; border-bottom:2px solid {color};">ROLE</th>
            <th style="padding:8px 14px; text-align:left; font-size:.82em; color:#6b7280; font-weight:600; border-bottom:2px solid {color};">USERNAME</th>
            <th style="padding:8px 14px; text-align:left; font-size:.82em; color:#6b7280; font-weight:600; border-bottom:2px solid {color};">PASSWORD</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
    </div>'''

html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>GLUDD EHR — Unit Test Credentials</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: 'Segoe UI', Arial, sans-serif;
    background: #f8fafc;
    color: #111827;
    padding: 40px 32px;
    max-width: 860px;
    margin: 0 auto;
  }}
  @media print {{
    body {{ background: #fff; padding: 20px; }}
    .no-print {{ display: none !important; }}
  }}
  h1 {{ font-size: 1.6em; font-weight: 800; color: #1e293b; }}
  .subtitle {{ color: #64748b; font-size: .9em; margin-top: 4px; margin-bottom: 28px; }}
  .header {{ border-bottom: 3px solid #7c3aed; padding-bottom: 16px; margin-bottom: 32px; display: flex; justify-content: space-between; align-items: flex-end; }}
  .logo {{ font-size: 2em; }}
  .notice {{ background: #fef3c7; border: 1px solid #f59e0b; border-radius: 7px; padding: 10px 16px; margin-bottom: 28px; font-size: .85em; color: #92400e; }}
  .print-btn {{ background: #7c3aed; color: #fff; border: none; padding: 8px 18px; border-radius: 6px; cursor: pointer; font-size: .9em; float: right; }}
  .footer {{ margin-top: 36px; padding-top: 16px; border-top: 1px solid #e5e7eb; font-size: .78em; color: #9ca3af; text-align: center; }}
</style>
</head>
<body>

<div class="no-print" style="text-align:right; margin-bottom:16px;">
  <button class="print-btn" onclick="window.print()">Print / Save as PDF</button>
</div>

<div class="header">
  <div>
    <div style="display:flex; align-items:center; gap:12px;">
      <div class="logo">&#128065;</div>
      <div>
        <h1>GLUDD Specialist Eye Hospital</h1>
        <div class="subtitle">EHR System — Unit Test Login Credentials &nbsp;|&nbsp; CONFIDENTIAL</div>
      </div>
    </div>
  </div>
  <div style="text-align:right; font-size:.82em; color:#6b7280;">
    Generated: {__import__('datetime').date.today().strftime('%d %B %Y')}<br>
    System: EHR Africa v1.0<br>
    Server: 192.168.30.169
  </div>
</div>

<div class="notice">
  <strong>CONFIDENTIAL.</strong> These credentials are for internal testing and demonstration only.
  Change all passwords before production handover.
  After logging in, assign each cashier to their counter via <em>Settings → My Profile</em> or through the Admin panel.
</div>

{cards_html}

<div style="background:#f1f5f9; border-radius:8px; padding:14px 18px; margin-top:8px; font-size:.85em;">
  <strong>System URL:</strong> <code>http://192.168.30.169</code> &nbsp;|&nbsp;
  <strong>Admin:</strong> <code>admin / Admin2026</code> &nbsp;|&nbsp;
  <strong>After login:</strong> Each user will be directed to their role-specific dashboard automatically.
</div>

<div class="footer">
  GLUDD Specialist Eye Hospital · EHR Africa System · {__import__('datetime').date.today().year}<br>
  This document contains sensitive credentials — store securely and destroy after use.
</div>

</body>
</html>
'''

out_path = PROJECT_ROOT / 'Unit_Test_Credentials.html'
out_path.write_text(html, encoding='utf-8')
print(f'  Credentials document: {out_path}')
print('  Open in Chrome -> Ctrl+P -> Save as PDF -> "Unit_Test_Credentials.pdf"')
print('\nAll done!')
