"""Deploy consultation resume fix — doctor resumes same consultation after refraction."""
import paramiko, os, time

HOST, PORT, USER, PASS = '192.168.30.169', 22, 'grudd420', '123456'
APP = '/opt/ehr-africa'
LOCAL = r'c:\Users\GROD\Desktop\EHR AFRICA BACKUP'

FILES = [
    ('apps/qms/views.py',                           f'{APP}/apps/qms/views.py'),
    ('apps/consultations/views.py',                 f'{APP}/apps/consultations/views.py'),
    ('templates/consultations/workstation.html',    f'{APP}/templates/consultations/workstation.html'),
]

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, PORT, USER, PASS)
sftp = ssh.open_sftp()

print('Uploading files...')
for local_rel, remote in FILES:
    local_abs = os.path.join(LOCAL, local_rel.replace('/', os.sep))
    print(f'  {local_rel}')
    sftp.put(local_abs, remote)
sftp.close()
print('All files uploaded.')

def run(cmd):
    _, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if out: print(out)
    if err: print('[stderr]', err)

print('\nRestarting gunicorn...')
run('pkill -f gunicorn')
time.sleep(3)
run('pgrep -f gunicorn | head -3')

ssh.close()
print('Done.')
