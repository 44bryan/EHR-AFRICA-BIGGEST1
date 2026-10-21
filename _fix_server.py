import paramiko, time

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'
APP_DIR = '/opt/ehr-africa'

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS, timeout=30)

def run(cmd, show=True):
    stdin, stdout, stderr = ssh.exec_command('bash -c \'' + cmd + '\'')
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if show and out: print(out)
    if show and err: print('ERR:', err)
    return out, err

def sudo_run(cmd, show=True):
    transport = ssh.get_transport()
    chan = transport.open_session()
    chan.get_pty()
    chan.exec_command('sudo -S ' + cmd)
    chan.send(PASS + '\n')
    time.sleep(2)
    out = chan.recv(65535).decode().strip()
    if show and out: print(out)
    return out

# Check gunicorn status
print('=== Checking gunicorn ===')
out, _ = run('pgrep -f gunicorn', show=False)
print('Current gunicorn PIDs:', out or 'NONE (down!)')

# Try to start via systemd with sudo
print('\n=== Starting ehr-gunicorn service ===')
sudo_run('systemctl start ehr-gunicorn')
time.sleep(4)

out, _ = run('pgrep -f gunicorn', show=False)
print('Gunicorn PIDs after start:', out or 'NONE')

if not out:
    # Try direct start from service file
    print('Trying direct gunicorn start...')
    run('cat /etc/systemd/system/ehr-gunicorn.service | grep ExecStart')

# Also fix collectstatic by retrying with --ignore flag workaround
print('\n=== Re-running collectstatic with MANIFEST_STRICT=False ===')
env_cmd = 'cd ' + APP_DIR + ' && source venv/bin/activate && PYTHONPATH=' + APP_DIR
run('cd ' + APP_DIR + ' && source venv/bin/activate && python -c "import os; os.environ[\'DJANGO_SETTINGS_MODULE\']=\'ehr_project.settings.production\'; from django.conf import settings; print(settings.STATICFILES_STORAGE)"')

ssh.close()
print('\nDone.')
