"""
Deploy enterprise modules + bug fixes to production server.
Includes: dietary, mortuary, blood_bank, hmo, infection_control + Chart.js fix + MD 500 fix
Migrations: accounts/0033, blood_bank/0001, dietary/0001, hmo/0001,
            infection_control/0001, mortuary/0001, notifications/0003,
            opticals/0002, pharmacy/0005, ipd/0007
"""
import zipfile, pathlib, os, time, paramiko

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'
APP  = '/opt/ehr-africa'
ZIP_LOCAL  = r'c:\Users\GROD\Desktop\deploy_enterprise_modules.zip'
ZIP_REMOTE = '/tmp/deploy_enterprise_modules.zip'

EXCLUDES = {'.git', '__pycache__', '.cache', 'node_modules',
            'staticfiles', 'media', 'backups', 'venv', '.env'}
EXT_SKIP  = {'.zip', '.pdf', '.docx', '.xlsx', '.png', '.jpg',
             '.jpeg', '.gif', '.svg', '.pyc', '.br', '.gz',
             '.sqlite3'}

# ── 1. Build zip ─────────────────────────────────────────────────────────────
print('Building zip...')
root = pathlib.Path(r'c:\Users\GROD\Desktop\EHR AFRICA BACKUP')
count = 0
with zipfile.ZipFile(ZIP_LOCAL, 'w', zipfile.ZIP_DEFLATED) as zf:
    for p in root.rglob('*'):
        if p.is_dir():
            continue
        skip = False
        for part in p.parts:
            if part in EXCLUDES:
                skip = True
                break
        if skip:
            continue
        if p.suffix.lower() in EXT_SKIP:
            continue
        # Skip loose helper/seed/deploy scripts at root level
        rel = p.relative_to(root)
        parts = rel.parts
        if len(parts) == 1 and parts[0].endswith('.py') and parts[0] not in (
            'manage.py',
        ):
            continue
        zf.write(p, str(rel))
        count += 1

size = pathlib.Path(ZIP_LOCAL).stat().st_size
print(f'Zipped {count} files -> {size / 1024 / 1024:.1f} MB')

# ── 2. Connect ───────────────────────────────────────────────────────────────
print('Connecting...')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS, timeout=30)
print('Connected.')

def run(cmd, timeout=120):
    _, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    stdout.channel.set_combine_stderr(False)
    out = stdout.read().decode(errors='replace').strip()
    err = stderr.read().decode(errors='replace').strip()
    if out:
        print(out)
    if err:
        print('STDERR:', err[:500])
    return out

def run_venv(cmd, timeout=120):
    return run(f'cd {APP} && source venv/bin/activate && {cmd}', timeout=timeout)

# ── 3. Upload ────────────────────────────────────────────────────────────────
print('Uploading...')
sftp = ssh.open_sftp()
sftp.put(ZIP_LOCAL, ZIP_REMOTE)
sftp.close()
print('Uploaded.')

# ── 4. Unzip ─────────────────────────────────────────────────────────────────
print('Unzipping...')
run(f'unzip -o {ZIP_REMOTE} -d {APP} > /tmp/unzip.log 2>&1 && echo "Unzip OK"')

# ── 5. Migrate (all apps with new migrations) ────────────────────────────────
print('Running migrations...')
for app in ['accounts', 'ipd', 'notifications', 'opticals', 'pharmacy',
            'blood_bank', 'dietary', 'hmo', 'infection_control', 'mortuary']:
    print(f'  migrate {app}...')
    out = run_venv(f'python manage.py migrate {app} --no-input 2>&1', timeout=60)
    if 'Error' in out or 'error' in out.lower():
        print(f'  !! {app} migration had errors')

# Run any remaining unapplied
print('  migrate (all remaining)...')
run_venv('python manage.py migrate --no-input 2>&1', timeout=90)

# ── 6. Collect static ────────────────────────────────────────────────────────
print('Collecting static files...')
run_venv('python manage.py collectstatic --no-input -v 0 2>&1', timeout=120)

# ── 7. Restart gunicorn ──────────────────────────────────────────────────────
print('Restarting gunicorn...')
before_pids = run('pgrep -f gunicorn || echo "none"')
print(f'  PIDs before: {before_pids}')

run('pkill -f gunicorn || true')
time.sleep(4)

# systemd should auto-restart; give it a moment
time.sleep(4)
after_pids = run('pgrep -f gunicorn || echo "none"')
print(f'  PIDs after:  {after_pids}')

if after_pids == 'none':
    print('  Gunicorn did not restart automatically — starting manually via systemd...')
    chan = ssh.get_transport().open_session()
    chan.get_pty()
    chan.exec_command(f'echo "{PASS}" | sudo -S systemctl start ehr-gunicorn')
    time.sleep(5)
    after_pids = run('pgrep -f gunicorn || echo "none"')
    print(f'  PIDs after manual start: {after_pids}')

# ── 8. Health check ──────────────────────────────────────────────────────────
time.sleep(2)
print('Health check...')
status = run('curl -s -o /dev/null -w "HTTP %{http_code}" http://localhost:8000/accounts/login/')
print(f'  {status}')

print('\nDone.')
ssh.close()
