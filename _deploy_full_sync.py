import paramiko, time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.30.169', username='grudd420', password='123456', timeout=10)

# Upload zip
print('Uploading...')
sftp = ssh.open_sftp()
sftp.put('deploy_full_sync.zip', '/tmp/deploy_full_sync.zip')
sftp.close()
print('Upload done.')

def run(cmd, sudo=False, timeout=60):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    if sudo:
        stdin.write('123456\n')
        stdin.flush()
    out = stdout.read().decode(errors='replace').strip()
    err = stderr.read().decode(errors='replace').strip()
    return out, err

# Unzip over existing
print('Extracting...')
out, err = run('cd /opt/ehr-africa && unzip -o /tmp/deploy_full_sync.zip 2>&1 | tail -5')
print(out)

# Run migrations
print('\nMigrating...')
out, err = run('cd /opt/ehr-africa && source venv/bin/activate && python manage.py migrate --no-input 2>&1', timeout=120)
print(out[-500:] if len(out) > 500 else out)
if err and 'warning' not in err.lower():
    print('Migration ERR:', err[:300])

# Collect static
print('\nCollecting static...')
out, err = run('cd /opt/ehr-africa && source venv/bin/activate && python manage.py collectstatic --no-input 2>&1 | tail -3')
print(out)

# Restart gunicorn
print('\nRestarting gunicorn...')
stdin_k, stdout_k, stderr_k = ssh.exec_command('pgrep -f gunicorn', timeout=10)
old_pids = stdout_k.read().decode().strip()

out, err = run('sudo -S pkill -f gunicorn 2>&1', sudo=True)
time.sleep(5)

stdin_k, stdout_k, stderr_k = ssh.exec_command('pgrep -f gunicorn', timeout=10)
new_pids = stdout_k.read().decode().strip()

old_first = old_pids.split('\n')[0] if old_pids else 'none'
new_first = new_pids.split('\n')[0] if new_pids else 'none'
print(f'Old PIDs: {old_first}...  New PIDs: {new_first}...')

if new_pids and new_pids != old_pids:
    print('RESTART SUCCESS')
else:
    print('Waiting a bit more...')
    time.sleep(5)
    stdin_k, stdout_k, stderr_k = ssh.exec_command('pgrep -f gunicorn', timeout=10)
    pids = stdout_k.read().decode().strip()
    print('PIDs:', pids.split('\n')[0] if pids else 'NONE')

# Health checks
print('\nHealth checks...')
for url in ['/accounts/login/', '/billing/', '/billing/bank-accounts/', '/billing/advances/',
            '/billing/cheque-register/', '/billing/safe-balance/', '/billing/reports/liquidity/',
            '/billing/reports/surgery-revenue/', '/billing/reports/dsf/']:
    out, _ = run(f'curl -s -o /dev/null -w "%{{http_code}}" http://127.0.0.1:8000{url}')
    print(f'  {url} -> HTTP {out}')

# Django system check
print('\nDjango check...')
out, err = run('cd /opt/ehr-africa && source venv/bin/activate && python manage.py check --no-color 2>&1 | tail -3')
print(out)

ssh.close()
print('\nDEPLOY COMPLETE.')
