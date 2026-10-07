import paramiko, zipfile, io, os

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'
APP_DIR = '/opt/ehr-africa'

files_to_deploy = [
    'templates/billing/service_prices.html',
]

buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
    for f in files_to_deploy:
        if os.path.exists(f):
            zf.write(f, f.replace('\\', '/'))
            print(f'  Added: {f}')

buf.seek(0)
print(f'Zip size: {buf.getbuffer().nbytes} bytes')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS, timeout=30)

sftp = ssh.open_sftp()
sftp.putfo(buf, '/tmp/deploy_sp_fix.zip')
sftp.close()
print('Uploaded.')

for cmd in [
    f'cd {APP_DIR} && unzip -o /tmp/deploy_sp_fix.zip 2>&1',
    'pkill -f gunicorn || true',
    'sleep 3 && systemctl start ehr-gunicorn',
    'sleep 4 && pgrep -c gunicorn',
]:
    _, stdout, stderr = ssh.exec_command(cmd, timeout=30)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if out: print(out[:300])
    if err and 'warning' not in err.lower(): print('ERR:', err[:200])

ssh.close()
print('Done.')
