#!/usr/bin/env python
"""Deploy the investigation workstation fix to production."""
import paramiko, os, zipfile, sys, io, time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PROJECT_DIR = r'c:\Users\GROD\Desktop\EHR AFRICA BACKUP'
REMOTE_DIR = '/opt/ehr-africa'
ZIP_NAME = 'deploy_cashier_first_flow.zip'

# Files to deploy
files = [
    'apps/investigations/views.py',
    'apps/billing/views.py',
    'apps/core/patient_flow.py',
    'apps/consultations/views.py',
    'templates/consultations/detail.html',
    'templates/consultations/create.html',
]

# Create zip
zip_path = os.path.join(PROJECT_DIR, ZIP_NAME)
with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
    for f in files:
        full = os.path.join(PROJECT_DIR, f)
        zf.write(full, f)
        print(f'  + {f}')

print(f'\nZip created: {ZIP_NAME}')

# Upload & deploy
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.30.169', username='grudd420', password='123456')

sftp = ssh.open_sftp()
sftp.put(zip_path, f'/tmp/{ZIP_NAME}')
sftp.close()
print('Uploaded to server.')

# Unzip
stdin, stdout, stderr = ssh.exec_command(f'cd {REMOTE_DIR} && unzip -o /tmp/{ZIP_NAME} && rm /tmp/{ZIP_NAME}')
print(stdout.read().decode('utf-8', errors='replace').strip())

# Collect static
stdin, stdout, stderr = ssh.exec_command(f'cd {REMOTE_DIR} && source venv/bin/activate && python manage.py collectstatic --no-input 2>&1 | tail -3')
print(stdout.read().decode('utf-8', errors='replace').strip())

# Restart gunicorn
stdin, stdout, stderr = ssh.exec_command('pgrep -f gunicorn')
old_pids = stdout.read().decode().strip()
print(f'Old PIDs: {old_pids}')

stdin, stdout, stderr = ssh.exec_command('sudo -S pkill -f gunicorn 2>&1')
stdin.write('123456\n')
stdin.flush()
stdout.read()
time.sleep(4)

stdin, stdout, stderr = ssh.exec_command('pgrep -f gunicorn')
new_pids = stdout.read().decode().strip()
print(f'New PIDs: {new_pids}')

if new_pids and new_pids != old_pids:
    print('RESTART SUCCESS')
else:
    print('WARNING - restart may have failed')

# Health check
stdin, stdout, stderr = ssh.exec_command('curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/accounts/login/')
print(f'Login page HTTP: {stdout.read().decode().strip()}')

ssh.close()
print('Done.')
