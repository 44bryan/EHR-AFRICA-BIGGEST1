"""Deploy VA display on workstation + optical order detail + optical dashboard."""
import paramiko, zipfile, os, io

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'
REMOTE_DIR = '/opt/ehr-africa'
PROJECT = r'c:\Users\GROD\Desktop\EHR AFRICA BACKUP'

FILES = [
    'templates/consultations/workstation.html',
    'templates/opticals/order_detail.html',
    'templates/opticals/dashboard.html',
]

buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
    for f in FILES:
        full = os.path.join(PROJECT, f)
        if os.path.exists(full):
            zf.write(full, f)
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
