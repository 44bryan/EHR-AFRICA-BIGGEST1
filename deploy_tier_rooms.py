"""
Deploy tier-filtered room picker + tablet sidebar GPU fix.
Files: templates/patients/triage.html, apps/qms/views.py, static/css/custom.css
"""
import paramiko, zipfile, io, time

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'
APP_DIR = '/opt/ehr-africa'
VENV = '/opt/ehr-africa/venv'

FILES = [
    (r'c:\Users\GROD\Desktop\EHR AFRICA BACKUP\templates\patients\triage.html',
     'templates/patients/triage.html'),
    (r'c:\Users\GROD\Desktop\EHR AFRICA BACKUP\apps\qms\views.py',
     'apps/qms/views.py'),
    (r'c:\Users\GROD\Desktop\EHR AFRICA BACKUP\static\css\custom.css',
     'static/css/custom.css'),
]

buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
    for local, arc in FILES:
        zf.write(local, arc)
buf.seek(0)
print(f'Zip: {buf.getbuffer().nbytes:,} bytes')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS, timeout=15)
print('SSH connected')

sftp = ssh.open_sftp()
sftp.putfo(buf, f'{APP_DIR}/deploy_tier_rooms.zip')
sftp.close()
print('Uploaded')

def run(cmd, timeout=90):
    _, out, err = ssh.exec_command(cmd, timeout=timeout)
    o = out.read().decode('utf-8', errors='replace')
    e = err.read().decode('utf-8', errors='replace')
    if o.strip(): print(o.strip())
    if e.strip(): print('[ERR]', e.strip())

run(f'cd {APP_DIR} && unzip -o deploy_tier_rooms.zip')
print('--- collectstatic ---')
run(f'cd {APP_DIR} && {VENV}/bin/python manage.py collectstatic --noinput --settings=ehr_project.settings.production 2>&1', timeout=120)
print('--- restart ---')
run(f'echo {PASS} | sudo -S systemctl restart ehr-gunicorn', timeout=30)
time.sleep(3)
_, o, _ = ssh.exec_command('systemctl is-active ehr-gunicorn')
print('gunicorn:', o.read().decode().strip())
run(f'rm {APP_DIR}/deploy_tier_rooms.zip')
ssh.close()
print('=== Done ===')
