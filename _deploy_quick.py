"""Quick deploy — only migrations + restart, no zip/upload needed for small fixes."""
import paramiko, time

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'
APP_DIR = '/opt/ehr-africa'

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS, timeout=30)

def run(cmd, show=True):
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if show and out: print(out)
    if show and err: print('ERR:', err)
    return out, err

def sudo_cmd(cmd):
    transport = ssh.get_transport()
    chan = transport.open_session()
    chan.get_pty()
    chan.exec_command('sudo -S bash -c "' + cmd + '"')
    chan.send(PASS + '\n')
    time.sleep(4)
    out = b''
    while chan.recv_ready():
        out += chan.recv(65535)
    chan.close()
    return out.decode().strip()

import zipfile, os
ZIP_NAME = 'ehr_deploy.zip'
LOCAL_ZIP = 'C:/Users/GROD/Desktop/' + ZIP_NAME
REMOTE_ZIP = '/tmp/' + ZIP_NAME

EXCLUDE_DIRS = {'.git', '__pycache__', 'node_modules', 'staticfiles', 'media', 'venv', 'env'}
EXCLUDE_FILES = {'ehr_deploy.zip', '.env.local'}

def should_exclude(path):
    parts = path.split(os.sep)
    for part in parts:
        if part in EXCLUDE_DIRS:
            return True
    fname = parts[-1]
    if fname in EXCLUDE_FILES or fname.endswith('.pyc') or fname.endswith('.dump') or fname.endswith('.sqlite3'):
        return True
    return False

print('Zipping project...')
count = 0
with zipfile.ZipFile(LOCAL_ZIP, 'w', zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk('.'):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for f in files:
            fpath = os.path.join(root, f)
            if not should_exclude(fpath):
                zf.write(fpath)
                count += 1
print('Zipped %d files (%d KB)' % (count, os.path.getsize(LOCAL_ZIP)//1024))

print('Uploading...')
sftp = ssh.open_sftp()
sftp.put(LOCAL_ZIP, REMOTE_ZIP)
sftp.close()
print('Upload done.')

print('Extracting...')
run('cd /opt && unzip -o ' + REMOTE_ZIP + ' -d ehr-africa > /dev/null 2>&1 && echo EXTRACTED')

print('Running migrations...')
run('cd ' + APP_DIR + ' && source venv/bin/activate && python manage.py migrate --no-input 2>&1')

print('Collecting static...')
run('cd ' + APP_DIR + ' && source venv/bin/activate && DJANGO_SETTINGS_MODULE=ehr_project.settings.production python manage.py collectstatic --no-input -v 0 2>&1')

print('Restarting gunicorn...')
sudo_cmd('systemctl restart ehr-gunicorn && sleep 2 && pgrep -f gunicorn')
time.sleep(3)
out, _ = run('pgrep -f gunicorn', show=False)
print('Gunicorn PIDs: ' + out.replace('\n', ' '))

run('rm ' + REMOTE_ZIP, show=False)
ssh.close()
print('DEPLOY COMPLETE.')
