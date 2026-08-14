"""Just restart gunicorn on production — migration already applied."""
import paramiko, time

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS, timeout=30)
print('Connected.')

def run_sudo(cmd):
    """Run a sudo command by sending password via stdin."""
    chan = ssh.get_transport().open_session()
    chan.get_pty()
    chan.exec_command(f'echo "{PASS}" | sudo -S {cmd}')
    out = b''
    deadline = time.time() + 30
    while time.time() < deadline:
        if chan.recv_ready():
            chunk = chan.recv(4096)
            out += chunk
        if chan.exit_status_ready():
            break
        time.sleep(0.3)
    rc = chan.recv_exit_status()
    print(out.decode(errors='replace'))
    return rc

print('Restarting ehr-gunicorn...')
rc = run_sudo('systemctl restart ehr-gunicorn')
time.sleep(3)
print('Status:')
run_sudo('systemctl status ehr-gunicorn --no-pager -n 8')
print('Done.' if rc == 0 else f'WARNING: exit code {rc}')
ssh.close()
