"""Deploy type-to-filter for ehr-combo fields."""
import paramiko, zipfile, os, io, sys

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'
REMOTE_DIR = '/opt/ehr-africa'
PROJECT = r'c:\Users\GROD\Desktop\EHR AFRICA BACKUP'

FILES = ['static/js/main.js']

buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
    for f in FILES:
        zf.write(os.path.join(PROJECT, f), f)
        print(f'  + {f}')
buf.seek(0)

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS, timeout=15)
sftp = ssh.open_sftp()
rz = f'{REMOTE_DIR}/_tmp_deploy.zip'
with sftp.file(rz, 'w') as rf:
    rf.write(buf.read())

cmds = [
    f'cd {REMOTE_DIR} && echo {PASS} | sudo -S unzip -o _tmp_deploy.zip && echo {PASS} | sudo -S rm _tmp_deploy.zip',
    # Copy to staticfiles too so nginx serves it
    f'echo {PASS} | sudo -S cp {REMOTE_DIR}/static/js/main.js {REMOTE_DIR}/staticfiles/js/main.js 2>/dev/null; echo ok',
    f'echo {PASS} | sudo -S kill -9 $(pgrep -f "gunicorn.*ehr_project" | head -1); sleep 2; echo {PASS} | sudo -S systemctl start ehr-gunicorn',
    'sleep 2 && pgrep -f gunicorn | head -2',
]
for cmd in cmds:
    print(f'\n$ {cmd[:80]}...')
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=30)
    out = stdout.read().decode('utf-8', errors='replace')
    if out.strip(): print(out.strip())

sftp.close()
ssh.close()
print('\nDone!')
