import paramiko, time

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS, timeout=30)

# Check if gunicorn is already running (systemd may have auto-restarted after pkill)
_, stdout, _ = ssh.exec_command('pgrep -c gunicorn')
count = stdout.read().decode().strip()
print(f'Gunicorn processes: {count}')

if count == '0':
    # Force start via sudo with password pipe
    cmd = 'echo "123456" | sudo -S systemctl start ehr-gunicorn 2>&1'
    _, stdout, stderr = ssh.exec_command(cmd, timeout=20)
    print(stdout.read().decode().strip()[:300])
    time.sleep(5)
    _, stdout, _ = ssh.exec_command('pgrep -c gunicorn')
    count = stdout.read().decode().strip()
    print(f'After restart: {count} gunicorn processes')

# Quick health check
_, stdout, _ = ssh.exec_command('curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/')
print(f'HTTP status: {stdout.read().decode().strip()}')

ssh.close()
