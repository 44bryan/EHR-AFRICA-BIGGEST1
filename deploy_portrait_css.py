"""
Deploy portrait tablet CSS fix to server.
Only uploads static/css/custom.css then runs collectstatic + restart.
"""
import paramiko, zipfile, io, time, os

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'
APP_DIR = '/opt/ehr-africa'
VENV = '/opt/ehr-africa/venv'

LOCAL_CSS = r'c:\Users\GROD\Desktop\EHR AFRICA BACKUP\static\css\custom.css'

print('=== Deploying portrait tablet CSS fix ===')

# --- Build zip in memory ---
buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
    zf.write(LOCAL_CSS, 'static/css/custom.css')
buf.seek(0)
print(f'Zip built: {buf.getbuffer().nbytes:,} bytes')

# --- SSH connect ---
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS, timeout=15)
print('SSH connected')

# --- Upload ---
sftp = ssh.open_sftp()
sftp.putfo(buf, f'{APP_DIR}/deploy_portrait_css.zip')
sftp.close()
print('Zip uploaded')

def run(cmd, timeout=60):
    _, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    if out.strip(): print(out.strip())
    if err.strip(): print('[STDERR]', err.strip())
    return out

# --- Unzip ---
run(f'cd {APP_DIR} && unzip -o deploy_portrait_css.zip')

# --- collectstatic ---
print('\n--- collectstatic ---')
run(f'cd {APP_DIR} && {VENV}/bin/python manage.py collectstatic --noinput --settings=ehr_project.settings.production 2>&1', timeout=120)

# --- restart gunicorn ---
print('\n--- restarting ehr-gunicorn ---')
run('sudo systemctl restart ehr-gunicorn', timeout=30)
time.sleep(3)
run('sudo systemctl is-active ehr-gunicorn')

# --- cleanup ---
run(f'rm {APP_DIR}/deploy_portrait_css.zip')

ssh.close()
print('\n=== Done — portrait CSS live on server ===')
