"""Deploy unified routing refactor to production server."""
import paramiko, zipfile, os, sys, io

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'
REMOTE_DIR = '/opt/ehr-africa'

# Files to deploy
FILES = [
    'apps/consultations/views.py',
    'apps/consultations/urls.py',
    'templates/layouts/base_authenticated.html',
    'templates/consultations/workstation.html',
]

PROJECT = r'c:\Users\GROD\Desktop\EHR AFRICA BACKUP'

# Create zip
buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
    for f in FILES:
        full = os.path.join(PROJECT, f)
        if os.path.exists(full):
            zf.write(full, f)
            print(f'  + {f}')
        else:
            print(f'  ! MISSING: {f}')
buf.seek(0)

print(f'\nConnecting to {HOST}...')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS, timeout=15)

sftp = ssh.open_sftp()
remote_zip = f'{REMOTE_DIR}/deploy_route_refactor.zip'
with sftp.file(remote_zip, 'w') as rf:
    rf.write(buf.read())
print('Zip uploaded.')

commands = [
    f'cd {REMOTE_DIR} && echo {PASS} | sudo -S unzip -o deploy_route_refactor.zip',
    f'cd {REMOTE_DIR} && echo {PASS} | sudo -S rm deploy_route_refactor.zip',
    f'cd {REMOTE_DIR} && echo {PASS} | sudo -S /opt/ehr-africa/venv/bin/python manage.py migrate --no-input 2>&1',
    f'echo {PASS} | sudo -S pkill -f gunicorn; sleep 2; echo {PASS} | sudo -S systemctl start ehr-gunicorn',
    'pgrep -a gunicorn | head -5',
]

for cmd in commands:
    print(f'\n$ {cmd[:80]}...')
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=30)
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    if out.strip():
        sys.stdout.buffer.write(out.encode('utf-8'))
        print()
    if err.strip() and 'password' not in err.lower():
        sys.stdout.buffer.write(err.encode('utf-8'))
        print()

sftp.close()
ssh.close()
print('\nDeploy complete!')
