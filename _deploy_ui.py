"""Deploy UI standards update to production server."""
import paramiko, zipfile, os, io, time

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'
APP_DIR = '/opt/ehr-africa'
ZIP_NAME = 'ehr_deploy.zip'

EXCLUDE_DIRS  = {'.git', '__pycache__', 'node_modules', 'staticfiles', 'mediafiles', 'media', 'venv'}
EXCLUDE_FILES = {'.env', 'ehr_africa_dump.dump'}

def should_exclude(path):
    parts = path.replace(os.sep, '/').split('/')
    for part in parts:
        if part in EXCLUDE_DIRS:
            return True
    fname = os.path.basename(path)
    if fname in EXCLUDE_FILES or fname.endswith('.pyc'):
        return True
    return False

print('Zipping project...')
buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk('.'):
        dirs[:] = [d for d in dirs if not should_exclude(os.path.join(root, d))]
        for file in files:
            fpath = os.path.join(root, file)
            if not should_exclude(fpath):
                zf.write(fpath)
buf.seek(0)
size_mb = len(buf.getvalue()) / 1024 / 1024
print(f'Zip: {size_mb:.1f} MB')

print('Connecting SSH...')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS, timeout=30)

sftp = ssh.open_sftp()
print('Uploading...')
sftp.putfo(buf, f'/tmp/{ZIP_NAME}')
sftp.close()
print('Upload done.')

def run(cmd, timeout=120):
    chan = ssh.get_transport().open_session()
    chan.get_pty()
    chan.exec_command(cmd)
    out = ''
    deadline = time.time() + timeout
    while time.time() < deadline:
        if chan.recv_ready():
            out += chan.recv(4096).decode('utf-8', errors='replace')
        if chan.exit_status_ready():
            while chan.recv_ready():
                out += chan.recv(4096).decode('utf-8', errors='replace')
            break
        time.sleep(0.2)
    return out, chan.recv_exit_status()

print('Extracting...')
out, rc = run(f'cd {APP_DIR} && unzip -o /tmp/{ZIP_NAME} -d . > /dev/null 2>&1 && echo EXTRACTED')
print(f'  rc={rc} {out.strip()[:80]}')

print('Collecting static...')
out, rc = run(f'cd {APP_DIR} && source venv/bin/activate && python manage.py collectstatic --noinput --settings=ehr_project.settings.base 2>&1 | tail -3')
print(f'  {out.strip()[:200]}')

print('Migrating...')
out, rc = run(f'cd {APP_DIR} && source venv/bin/activate && python manage.py migrate --settings=ehr_project.settings.base 2>&1 | tail -5')
print(f'  {out.strip()[:300]}')

print('Restarting gunicorn...')
run('pkill -f gunicorn 2>/dev/null; sleep 2; sudo systemctl start ehr-gunicorn 2>&1 || true')
time.sleep(3)
out2, _ = run('pgrep -f gunicorn | head -3')
print(f'  Gunicorn PIDs: {out2.strip()}')

ssh.close()
print('Deploy complete.')
