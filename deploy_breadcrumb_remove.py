import paramiko, sys

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'
APP_DIR = '/opt/ehr-africa'

LOCAL = r'c:\Users\GROD\Desktop\EHR AFRICA BACKUP\templates\layouts\base_authenticated.html'
REMOTE = f'{APP_DIR}/templates/layouts/base_authenticated.html'

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS)

sftp = ssh.open_sftp()
sftp.put(LOCAL, REMOTE)
sftp.close()
print('Uploaded base_authenticated.html')

_, stdout, stderr = ssh.exec_command('pkill -f gunicorn; sleep 2; cd /opt/ehr-africa && /opt/ehr-africa/venv/bin/gunicorn ehr_project.wsgi:application --workers 3 --worker-class gevent --bind 127.0.0.1:8000 --daemon --pid /tmp/gunicorn.pid')
stdout.channel.recv_exit_status()
err = stderr.read().decode('utf-8', errors='replace')
if err: sys.stdout.buffer.write(('STDERR: ' + err + '\n').encode('utf-8', errors='replace'))
print('Gunicorn restarted.')

import time; time.sleep(3)
_, stdout2, _ = ssh.exec_command('pgrep -f gunicorn | head -5')
pids = stdout2.read().decode().strip()
print('PIDs:', pids if pids else 'NONE')
ssh.close()
print('Done.')
