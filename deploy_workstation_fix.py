"""Deploy workstation.html event-delegation fix to production server."""
import paramiko, os, sys

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'
APP_DIR = '/opt/ehr-africa'

LOCAL = r'c:\Users\GROD\Desktop\EHR AFRICA BACKUP\templates\consultations\workstation.html'
REMOTE = f'{APP_DIR}/templates/consultations/workstation.html'

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS)

sftp = ssh.open_sftp()
sftp.put(LOCAL, REMOTE)
sftp.close()
print('Uploaded workstation.html')

# Restart gunicorn — pkill lets systemd restart it with the correct unit config
_, stdout, stderr = ssh.exec_command('pkill -f gunicorn || true')
stdout.channel.recv_exit_status()
out = stdout.read().decode('utf-8', errors='replace')
err = stderr.read().decode('utf-8', errors='replace')
if out: sys.stdout.buffer.write(('STDOUT: ' + out + '\n').encode('utf-8', errors='replace'))
if err: sys.stdout.buffer.write(('STDERR: ' + err + '\n').encode('utf-8', errors='replace'))
print('Gunicorn restarted.')

import time; time.sleep(3)
_, stdout2, _ = ssh.exec_command('pgrep -f gunicorn | head -5')
pids = stdout2.read().decode().strip()
print('Gunicorn PIDs:', pids if pids else 'NONE — check manually')

ssh.close()
print('Done.')
