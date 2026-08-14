import paramiko, time

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS, timeout=30)

# Get logs from last 2 minutes only
_, stdout, _ = ssh.exec_command('journalctl -u ehr-gunicorn --since "2 minutes ago" --no-pager -o short')
out = stdout.read().decode(errors='replace')
print(out if out.strip() else 'No log entries in last 2 minutes (no errors)')

# Also check migration state
_, stdout, _ = ssh.exec_command('cd /opt/ehr-africa && source venv/bin/activate && python manage.py showmigrations billing 2>&1 | tail -8')
print('\nMigrations:')
print(stdout.read().decode(errors='replace'))

ssh.close()
