"""
Deploy: doctor room check-in system
- New /qms/room-checkin/ and /qms/room-board/ URLs
- doctor_queue uses checked_in_counter context
- Triage dispatch sets token.counter via ServiceCounter UUID
- New template: qms/doctor_checkin.html
- Sidebar: Room Check-In link for all doctor roles
"""
import os, sys, zipfile, io, time
import paramiko

SERVER   = '192.168.30.169'
PORT     = 22
USER     = 'grudd420'
PASSWD   = '123456'
APP_DIR  = '/opt/ehr-africa'
VENV     = '/opt/ehr-africa/venv'

BASE = r'c:\Users\GROD\Desktop\EHR AFRICA BACKUP'

INCLUDE = [
    'apps/qms/views.py',
    'apps/qms/urls.py',
    'apps/patients/views.py',
    'templates/patients/triage.html',
    'templates/qms/doctor_checkin.html',
    'templates/components/sidebar.html',
]

print('Building zip...')
buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
    for rel in INCLUDE:
        full = os.path.join(BASE, rel.replace('/', os.sep))
        if os.path.exists(full):
            zf.write(full, rel)
            print(f'  + {rel}')
        else:
            print(f'  MISSING: {rel}')
buf.seek(0)

print('\nConnecting to server...')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(SERVER, port=PORT, username=USER, password=PASSWD, timeout=15)

sftp = ssh.open_sftp()
remote_zip = '/tmp/deploy_room_checkin.zip'
print(f'Uploading zip to {remote_zip}...')
sftp.putfo(buf, remote_zip)
sftp.close()

def run(cmd, label=''):
    label = label or cmd[:60]
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=120)
    out = stdout.read().decode()
    err = stderr.read().decode()
    rc  = stdout.channel.recv_exit_status()
    if out.strip(): print(f'  [{label}] {out.strip()[:300]}')
    if err.strip() and rc != 0: print(f'  [ERR] {err.strip()[:300]}')
    return rc == 0

print('\nDeploying files...')
run(f'cd {APP_DIR} && unzip -o {remote_zip}', 'unzip')

print('Running migrations...')
run(f'{VENV}/bin/python {APP_DIR}/manage.py migrate --no-input 2>&1', 'migrate')

print('Collecting static...')
run(f'{VENV}/bin/python {APP_DIR}/manage.py collectstatic --no-input -v0 2>&1', 'collectstatic')

print('Restarting gunicorn...')
run('sudo systemctl restart ehr-gunicorn', 'restart')
time.sleep(3)

print('Checking service...')
run('systemctl is-active ehr-gunicorn', 'status')

ssh.close()
print('\nDeploy complete.')
