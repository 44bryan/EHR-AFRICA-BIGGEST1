"""Deploy store keeper UI fixes to server."""
import paramiko, zipfile, io, os, sys, time

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'
APP_DIR = '/opt/ehr-africa'

files = [
    'templates/inventory/stats.html',
    'templates/inventory/alerts.html',
    'templates/inventory/dashboard.html',
    'templates/inventory/item_list.html',
    'templates/inventory/stock_entry_form.html',
    'templates/inventory/transfer_form.html',
    'templates/inventory/stock_count_form.html',
    'templates/inventory/store_location_list.html',
    'templates/inventory/stock_ledger.html',
    'apps/inventory/views.py',
]

buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
    for f in files:
        if os.path.exists(f):
            zf.write(f, f.replace('\\', '/'))
            print(f'  Added: {f}')
buf.seek(0)

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS, timeout=20)

sftp = ssh.open_sftp()
sftp.putfo(buf, '/tmp/deploy_store_fixes.zip')
sftp.close()

_, out, err = ssh.exec_command(f'cd {APP_DIR} && unzip -o /tmp/deploy_store_fixes.zip 2>&1', timeout=30)
time.sleep(4)
print(out.read().decode('utf-8', errors='replace'))

# Quick Django check
_, out, _ = ssh.exec_command(f'cd {APP_DIR} && source venv/bin/activate && python manage.py check --settings=ehr_project.settings.production 2>&1 | tail -3', timeout=20)
time.sleep(8)
print('Django check:', out.read().decode().strip())

# Restart gunicorn
_, out, _ = ssh.exec_command('pkill -f gunicorn; sleep 2; pgrep -f gunicorn | wc -l', timeout=15)
time.sleep(6)
print('Gunicorn workers:', out.read().decode().strip())

ssh.close()
print('Done.')
