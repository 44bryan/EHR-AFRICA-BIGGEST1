"""
Deploy advanced tier-scoped billing module to production.
Uploads zip, unzips, runs migrations, restarts gunicorn.
"""
import paramiko, os, time

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'
APP  = '/opt/ehr-africa'
ZIP  = r'c:\Users\GROD\Desktop\deploy_tier_billing.zip'

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS, timeout=30)
print('Connected.')

# Upload
sftp = ssh.open_sftp()
sftp.put(ZIP, '/tmp/deploy_tier_billing.zip')
sftp.close()
print('Uploaded.')

def run(cmd, timeout=120):
    chan = ssh.get_transport().open_session()
    chan.get_pty()
    chan.exec_command(cmd)
    out = b''
    while True:
        if chan.recv_ready():
            chunk = chan.recv(4096)
            out += chunk
            print(chunk.decode(errors='replace'), end='', flush=True)
        if chan.exit_status_ready():
            break
        time.sleep(0.2)
    return chan.recv_exit_status()

# Unzip
print('\n--- Unzipping ---')
run(f'cd {APP} && unzip -o /tmp/deploy_tier_billing.zip -d . > /tmp/unzip.log 2>&1 && echo "Unzip done" && tail -5 /tmp/unzip.log')

# Collect static
print('\n--- Collect static ---')
run(f'cd {APP} && source venv/bin/activate && python manage.py collectstatic --noinput')

# Migrate
print('\n--- Migrate ---')
rc = run(f'cd {APP} && source venv/bin/activate && python manage.py migrate --noinput')
if rc != 0:
    print('MIGRATION FAILED')
    ssh.close()
    exit(1)

# Restart
print('\n--- Restart gunicorn ---')
run('sudo systemctl restart ehr-gunicorn')
time.sleep(3)
run('sudo systemctl status ehr-gunicorn --no-pager -n 5')

print('\nDeploy complete.')
ssh.close()
