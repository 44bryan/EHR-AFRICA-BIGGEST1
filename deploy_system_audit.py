"""Deploy system audit fixes: lab notifications, polling, tablet fonts, perf settings."""
import zipfile, pathlib, paramiko, time, io

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'
APP  = '/opt/ehr-africa'
ZIP_NAME = 'deploy_system_audit'
ZIP_PATH = f'c:\\Users\\GROD\\Desktop\\{ZIP_NAME}.zip'

# Only the changed files from the system audit session
CHANGED = [
    'apps/laboratory/views.py',
    'apps/notifications/views.py',
    'apps/billing/views.py',
    'ehr_project/settings/base.py',
    'static/css/custom.css',
    'static/js/main.js',
    'templates/base.html',
    'templates/patients/detail.html',
    'templates/billing/cashier_pos.html',
]

root = pathlib.Path(r'c:\Users\GROD\Desktop\EHR AFRICA BACKUP')
out  = pathlib.Path(ZIP_PATH)

count = 0
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as zf:
    for rel in CHANGED:
        p = root / rel
        if p.exists():
            zf.write(p, rel)
            count += 1
            print(f'  + {rel}')
        else:
            print(f'  MISSING: {rel}')

print(f'\nZipped {count} files -> {out}  ({out.stat().st_size/1024:.0f} KB)')

# --- SSH deploy ---
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS, timeout=30)
print('Connected to server.')

sftp = ssh.open_sftp()
sftp.put(ZIP_PATH, f'/tmp/{ZIP_NAME}.zip')
sftp.close()
print('Uploaded.')

def run(cmd, timeout=90):
    _, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode(errors='replace').strip()
    err = stderr.read().decode(errors='replace').strip()
    if out: print('OUT:', out)
    if err: print('ERR:', err)
    return out

def run_sudo(cmd, timeout=30):
    chan = ssh.get_transport().open_session()
    chan.get_pty()
    chan.exec_command(f'echo "{PASS}" | sudo -S {cmd}')
    out = b''
    deadline = time.time() + timeout
    while time.time() < deadline:
        if chan.recv_ready():
            out += chan.recv(4096)
        if chan.exit_status_ready():
            break
        time.sleep(0.2)
    result = out.decode(errors='replace').strip()
    if result:
        print(result)
    return result

# Unzip
print('\n-- Unzipping --')
run(f'cd {APP} && unzip -o /tmp/{ZIP_NAME}.zip -d . > /tmp/unzip.log 2>&1 && cat /tmp/unzip.log | tail -5')

# Collect static (css/js changed)
print('\n-- Collecting static files --')
run_sudo(f'bash -c "cd {APP} && source venv/bin/activate && python manage.py collectstatic --noinput -v 0 2>&1 | tail -5"')

# Restart gunicorn
print('\n-- Restarting ehr-gunicorn --')
run_sudo('systemctl restart ehr-gunicorn')
time.sleep(3)
status = run('systemctl is-active ehr-gunicorn')
print(f'gunicorn status: {status}')

# HTTP check
print('\n-- HTTP check --')
run('curl -s -o /dev/null -w "HTTP %{http_code}" http://localhost:8000/accounts/login/')

print('\nDone.')
ssh.close()
