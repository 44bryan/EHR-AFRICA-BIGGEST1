"""Quick deploy — upload zip, unzip, restart (no migrate needed)."""
import paramiko, time

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'
APP  = '/opt/ehr-africa'
ZIP  = r'c:\Users\GROD\Desktop\deploy_tier_billing.zip'

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS, timeout=30)
print('Connected.')

sftp = ssh.open_sftp()
sftp.put(ZIP, '/tmp/deploy_tier_billing.zip')
sftp.close()
print('Uploaded.')

def run(cmd, timeout=60):
    _, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode(errors='replace')
    err = stderr.read().decode(errors='replace')
    if out: print(out)
    if err: print('ERR:', err)

def run_sudo(cmd):
    chan = ssh.get_transport().open_session()
    chan.get_pty()
    chan.exec_command(f'echo "{PASS}" | sudo -S {cmd}')
    out = b''
    deadline = time.time() + 30
    while time.time() < deadline:
        if chan.recv_ready():
            out += chan.recv(4096)
        if chan.exit_status_ready():
            break
        time.sleep(0.2)
    print(out.decode(errors='replace'))

run(f'cd {APP} && unzip -o /tmp/deploy_tier_billing.zip -d . > /tmp/unzip.log 2>&1 && echo "Unzip OK"')
print('Unzipped.')

run_sudo('systemctl restart ehr-gunicorn')
time.sleep(3)
run('systemctl is-active ehr-gunicorn')

# Quick HTTP check
run('curl -s -o /dev/null -w "HTTP %{http_code}" http://localhost:8000/accounts/login/')

print('Done.')
ssh.close()
