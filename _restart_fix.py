import paramiko, time

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'
APP_DIR = '/opt/ehr-africa'

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS, timeout=30)

def sudo_cmd(cmd):
    transport = ssh.get_transport()
    chan = transport.open_session()
    chan.get_pty()
    chan.exec_command('sudo -S bash -c "' + cmd + '"')
    chan.send(PASS + '\n')
    time.sleep(3)
    out = b''
    while chan.recv_ready():
        out += chan.recv(65535)
    chan.close()
    return out.decode().strip()

def run(cmd, show=True):
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if show and out: print(out)
    if show and err: print('ERR:', err)
    return out, err

print('=== Restarting ehr-gunicorn via sudo systemctl ===')
result = sudo_cmd('systemctl restart ehr-gunicorn && sleep 2 && pgrep -f gunicorn')
print(result)

time.sleep(3)
out, _ = run('pgrep -f gunicorn', show=False)
print('New gunicorn PIDs:', out)

# Fix whitenoise map issue - run collectstatic with WHITENOISE_MANIFEST_STRICT=False
print('\n=== Fix: collectstatic ignoring missing .map source files ===')
collect_cmd = (
    'cd ' + APP_DIR + ' && '
    'source venv/bin/activate && '
    'WHITENOISE_MANIFEST_STRICT=False python manage.py collectstatic --no-input -v 0 2>&1 | tail -5'
)
out, err = run(collect_cmd)

# Verify site is up
print('\n=== Verifying site ===')
run('curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/')

ssh.close()
print('\nDone.')
