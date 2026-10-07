"""
Deploy: can_do_refraction feature + counter delete fix
- apps/accounts/models.py (can_do_refraction field)
- apps/accounts/migrations/0037_user_can_do_refraction.py
- apps/consultations/views.py (workstation includes REFRACTION for VIP+flag)
- templates/consultations/clinical/_gen_oph_form.html (editable refraction zone)
- templates/qms/counter_manage.html (delete button always visible)
- apps/qms/views.py (clear current_serving before delete)
Then sets can_do_refraction=True on all VIP doctor accounts.
"""
import paramiko, zipfile, io, os, sys

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'
APP_DIR = '/opt/ehr-africa'

BASE = r'c:\Users\GROD\Desktop\EHR AFRICA BACKUP'

FILES = [
    'apps/accounts/models.py',
    'apps/accounts/migrations/0037_user_can_do_refraction.py',
    'apps/consultations/views.py',
    'apps/qms/views.py',
    'templates/consultations/clinical/_gen_oph_form.html',
    'templates/qms/counter_manage.html',
]

print('Building zip...')
buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
    for rel in FILES:
        local = os.path.join(BASE, rel.replace('/', os.sep))
        if not os.path.exists(local):
            print(f'  MISSING: {local}')
            sys.exit(1)
        zf.write(local, rel)
        print(f'  + {rel}')
buf.seek(0)

print('\nUploading...')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS)

sftp = ssh.open_sftp()
with sftp.open('/tmp/deploy_refrac_counter.zip', 'wb') as f:
    f.write(buf.read())
sftp.close()

def run(cmd, label=''):
    _, out, err = ssh.exec_command(cmd)
    exit_code = out.channel.recv_exit_status()
    o = out.read().decode('utf-8', errors='replace').strip()
    e = err.read().decode('utf-8', errors='replace').strip()
    if label:
        print(f'\n--- {label} ---')
    if o:
        print(o)
    if e and exit_code != 0:
        print(f'ERR: {e}')
    return exit_code

run(f'cd {APP_DIR} && unzip -o /tmp/deploy_refrac_counter.zip', 'Unzip')

run(
    f'cd {APP_DIR} && {APP_DIR}/venv/bin/python manage.py migrate --settings=ehr_project.settings.production 2>&1',
    'Migrate'
)

set_flag_script = """
import django, os, sys
os.environ['DJANGO_SETTINGS_MODULE'] = 'ehr_project.settings.production'
sys.path.insert(0, '/opt/ehr-africa')
django.setup()
from apps.accounts.models import User
vip_users = User.objects.filter(username__in=[
    'dr2_dr_vip_gen1', 'dr2_dr_vip_gen2',
    'dr2_dr_vip_ret',  'dr2_dr_vip_gla',
])
updated = vip_users.update(can_do_refraction=True)
print(f'Set can_do_refraction=True on {updated} VIP doctor(s):')
for u in vip_users:
    u.refresh_from_db()
    print(f'  {u.username}: can_do_refraction={u.can_do_refraction}')
"""

sftp = ssh.open_sftp()
with sftp.open('/tmp/set_vip_refrac.py', 'w') as f:
    f.write(set_flag_script)
sftp.close()

run(
    f'cd {APP_DIR} && {APP_DIR}/venv/bin/python /tmp/set_vip_refrac.py',
    'Set VIP refraction flag'
)

run('pkill -f gunicorn || true', 'Restart gunicorn')

import time; time.sleep(3)
run('pgrep -a gunicorn | head -5', 'Gunicorn PIDs')

ssh.close()
print('\nDeploy complete.')
