import paramiko, zipfile, io, os, sys

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'
APP_DIR = '/opt/ehr-africa'

dirs_to_sync = [
    'apps/billing',
    'apps/patients',
    'apps/inventory',
    'apps/opticals',
    'apps/accounts',
    'apps/consultations',
    'apps/reception',
    'apps/departments',
    'apps/investigations',
    'apps/laboratory',
    'apps/pharmacy',
    'apps/appointments',
    'apps/hmo',
    'apps/notifications',
    'apps/infection_control',
    'apps/dietary',
    'apps/mortuary',
    'apps/blood_bank',
    'apps/ipd',
    'apps/core',
    'apps/qms',
    'apps/hrms',
    'apps/outreach',
    'templates',
    'ehr_project',
]

buf = io.BytesIO()
total = 0
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
    for d in dirs_to_sync:
        if not os.path.exists(d):
            continue
        for root, dirs, files in os.walk(d):
            dirs[:] = [x for x in dirs if x not in ('__pycache__', '.git', 'node_modules')]
            for f in files:
                if f.endswith(('.py', '.html', '.css', '.js', '.json')) and not f.endswith('.pyc'):
                    fpath = os.path.join(root, f)
                    arc_path = fpath.replace('\\', '/')
                    zf.write(fpath, arc_path)
                    total += 1

buf.seek(0)
size_mb = buf.getbuffer().nbytes / 1024 / 1024
print(f'Zip ready: {total} files, {size_mb:.1f} MB')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS, timeout=60)

sftp = ssh.open_sftp()
sftp.putfo(buf, '/tmp/deploy_everything.zip')
sftp.close()
print('Uploaded to server')

for cmd in [
    f'cd {APP_DIR} && unzip -o /tmp/deploy_everything.zip 2>&1 | tail -5',
    f'cd {APP_DIR} && source venv/bin/activate && python manage.py migrate --no-input 2>&1 | tail -10',
    'pkill -f gunicorn || true',
]:
    _, stdout, stderr = ssh.exec_command(cmd, timeout=120)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if out:
        print(out[:500])
    if err and 'warning' not in err.lower() and 'info' not in err.lower():
        print('ERR:', err[:300])

import time
time.sleep(5)
_, stdout, _ = ssh.exec_command('systemctl start ehr-gunicorn')
time.sleep(6)
_, stdout, _ = ssh.exec_command('pgrep -c gunicorn && curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/')
print('Status:', stdout.read().decode().strip())
ssh.close()
print('FULL DEPLOY COMPLETE.')
