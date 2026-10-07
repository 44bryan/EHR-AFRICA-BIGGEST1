"""Deploy EVIP tier changes + real data seed to server."""
import paramiko, zipfile, io, os, sys, time

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'
APP_DIR = '/opt/ehr-africa'

# Files changed for EVIP tier support
evip_files = [
    'apps/billing/models.py',
    'apps/appointments/models.py',
    'apps/billing/views.py',
    'apps/patients/views.py',
    'templates/billing/service_prices.html',
    'templates/patients/prereg.html',
    'templates/patients/register.html',
    'templates/accounts/staff_hub.html',
]

print('='*60)
print('Step 1: Deploying EVIP tier code changes...')
print('='*60)

buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
    for f in evip_files:
        if os.path.exists(f):
            arc = f.replace('\\', '/')
            zf.write(f, arc)
            print(f'  Added: {f}')
        else:
            print(f'  SKIP (not found): {f}')
buf.seek(0)

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS, timeout=20)

sftp = ssh.open_sftp()
sftp.putfo(buf, '/tmp/deploy_evip.zip')
print('Uploaded EVIP zip.')

_, out, err = ssh.exec_command(f'cd {APP_DIR} && unzip -o /tmp/deploy_evip.zip 2>&1', timeout=30)
time.sleep(3)
o = out.read().decode('utf-8', errors='replace')
e = err.read().decode('utf-8', errors='replace')
if o: print(o)
if e: print('STDERR:', e)

print('\n' + '='*60)
print('Step 2: Uploading real data seed script...')
print('='*60)

sftp.put('_seed_real_data.py', '/tmp/_seed_real_data.py')
print('Uploaded _seed_real_data.py (667KB)')

print('\n' + '='*60)
print('Step 3: Running seed import on server...')
print('='*60)

_, out, err = ssh.exec_command(
    f'cd {APP_DIR} && source venv/bin/activate && python /tmp/_seed_real_data.py 2>&1',
    timeout=300
)
# Seed can take up to 5 minutes for 2872 inventory items
start = time.time()
while not out.channel.exit_status_ready():
    if time.time() - start > 290:
        print('WARNING: seed taking too long, reading partial output...')
        break
    time.sleep(5)

o = out.read().decode('utf-8', errors='replace')
e = err.read().decode('utf-8', errors='replace')
if o: print(o)
if e: print('STDERR:', e)

print('\n' + '='*60)
print('Step 4: Restarting gunicorn...')
print('='*60)

_, out, err = ssh.exec_command('pkill -f gunicorn; sleep 3; pgrep -f gunicorn | head -5', timeout=15)
time.sleep(6)
o = out.read().decode('utf-8', errors='replace')
print('New gunicorn PIDs:', o.strip() or '(systemd will restart shortly)')

sftp.close()
ssh.close()
print('\nDone.')
