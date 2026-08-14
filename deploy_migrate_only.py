"""Upload migration file, run migrate, restart gunicorn."""
import paramiko, time

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'
APP  = '/opt/ehr-africa'

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS, timeout=30)
print('Connected.')

sftp = ssh.open_sftp()
sftp.put(
    r'c:\Users\GROD\Desktop\EHR AFRICA BACKUP\apps\billing\migrations\0019_fix_audit_deleted_at.py',
    f'{APP}/apps/billing/migrations/0019_fix_audit_deleted_at.py'
)
sftp.close()
print('Migration uploaded.')

def run(cmd):
    _, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode(errors='replace')
    err = stderr.read().decode(errors='replace')
    if out: print(out)
    if err and 'WARNING' not in err: print('ERR:', err)

def run_sudo(cmd):
    chan = ssh.get_transport().open_session()
    chan.get_pty()
    chan.exec_command(f'echo "{PASS}" | sudo -S {cmd}')
    out = b''
    for _ in range(40):
        if chan.recv_ready():
            out += chan.recv(4096)
        if chan.exit_status_ready():
            break
        time.sleep(0.3)
    print(out.decode(errors='replace'))

run(f'cd {APP} && source venv/bin/activate && python manage.py migrate billing --noinput')
print('Migrated. Restarting...')
run_sudo('systemctl restart ehr-gunicorn')
time.sleep(3)
run('curl -s -o /dev/null -w "HTTP %{http_code}" http://localhost:8000/accounts/login/')
print('\nDone.')
ssh.close()
