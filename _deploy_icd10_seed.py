"""Deploy ICD-10 seed + updated diagnosis search UI."""
import paramiko, zipfile, os, io, sys

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'
REMOTE_DIR = '/opt/ehr-africa'
PROJECT = r'c:\Users\GROD\Desktop\EHR AFRICA BACKUP'

FILES = [
    'seed_icd10_full.py',
    'templates/consultations/detail.html',
    'apps/consultations/views.py',
]

buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
    for f in FILES:
        full = os.path.join(PROJECT, f)
        if os.path.exists(full):
            zf.write(full, f)
            print(f'  + {f}')
buf.seek(0)

print(f'\nConnecting to {HOST}...')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS, timeout=15)

sftp = ssh.open_sftp()
rz = f'{REMOTE_DIR}/_tmp_deploy.zip'
with sftp.file(rz, 'w') as rf:
    rf.write(buf.read())

cmds = [
    f'cd {REMOTE_DIR} && echo {PASS} | sudo -S unzip -o _tmp_deploy.zip && echo {PASS} | sudo -S rm _tmp_deploy.zip',
    f'cd {REMOTE_DIR} && {REMOTE_DIR}/venv/bin/python seed_icd10_full.py',
    f'echo {PASS} | sudo -S kill -9 $(pgrep -f "gunicorn.*ehr_project" | head -1); sleep 2; echo {PASS} | sudo -S systemctl start ehr-gunicorn',
    'sleep 2 && pgrep -a gunicorn | head -2',
]

for cmd in cmds:
    print(f'\n$ {cmd[:80]}...')
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=120)
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    if out.strip():
        sys.stdout.buffer.write(out.encode('utf-8'))
        print()
    if err.strip() and 'password' not in err.lower():
        # Filter noisy lines
        for line in err.splitlines():
            if 'warning' in line.lower() or 'info' in line.lower():
                continue
            sys.stdout.buffer.write((line + '\n').encode('utf-8'))

sftp.close()
ssh.close()
print('\nDeploy complete!')
