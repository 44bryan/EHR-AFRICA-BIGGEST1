"""
Deploy: GL fix + discount workflow + catalog sub-category grouping
Files: models.py, views.py, migrations 0037+0038, cashier_pos.html, discount_approval_list.html
"""
import paramiko
import zipfile
import os
import io

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'
APP  = '/opt/ehr-africa'

FILES = [
    'apps/billing/models.py',
    'apps/billing/views.py',
    'apps/billing/gl_service.py',
    'apps/billing/migrations/0037_seed_cash_payment_gl_accounts.py',
    'apps/billing/migrations/0038_discountapproval_type_and_pct.py',
    'templates/billing/cashier_pos.html',
    'templates/billing/discount_approval_list.html',
]

BASE = r'c:\Users\GROD\Desktop\EHR AFRICA BACKUP'

# Build zip
buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
    for f in FILES:
        full = os.path.join(BASE, f)
        if os.path.exists(full):
            zf.write(full, f)
            print(f'  + {f}')
        else:
            print(f'  MISSING: {f}')
buf.seek(0)

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS)

# Upload zip
sftp = ssh.open_sftp()
remote_zip = '/tmp/deploy_gl_discount.zip'
sftp.putfo(buf, remote_zip)
sftp.close()
print('Uploaded zip')

def run(cmd):
    _, out, err = ssh.exec_command(cmd)
    o = out.read().decode().strip()
    e = err.read().decode().strip()
    if o: print(o)
    if e: print('[ERR]', e)
    return o

# Unzip
run(f'cd {APP} && unzip -o {remote_zip}')
print('Unzipped')

# Migrate
print('\n--- Migrations ---')
run(f'cd {APP} && source venv/bin/activate && python manage.py migrate billing --no-input 2>&1')

# Check
print('\n--- System check ---')
run(f'cd {APP} && source venv/bin/activate && python manage.py check --deploy 2>&1 | tail -5')

# Restart gunicorn
print('\n--- Restarting gunicorn ---')
run('pkill -f gunicorn || true')
import time; time.sleep(3)
run(f'cd {APP} && source venv/bin/activate && nohup gunicorn ehr_project.wsgi:application --bind 127.0.0.1:8000 --workers 4 --worker-class gevent --timeout 120 --daemon 2>/dev/null')
time.sleep(3)
pids = run('pgrep -f gunicorn')
print('Gunicorn PIDs:', pids)

# Quick GL verification
print('\n--- GL Account check ---')
check = run(f'''cd {APP} && source venv/bin/activate && python manage.py shell -c "
from apps.billing.models import GLAccount
codes = ['572000','521000','411000','412000','521100']
for c in codes:
    try:
        a = GLAccount.objects.get(code=c, is_active=True)
        print(f'  OK  {c}  {a.name}')
    except GLAccount.DoesNotExist:
        print(f'  MISSING  {c}')
"''')

# Recent payment GL check
print('\n--- Recent payment GL entries ---')
run(f'''cd {APP} && source venv/bin/activate && python manage.py shell -c "
from apps.billing.models import Payment, JournalEntry
from django.utils import timezone
payments = Payment.objects.filter(is_deleted=False).order_by('-created_at')[:5]
for p in payments:
    je = JournalEntry.objects.filter(source_type='payment', source_id=str(p.pk)).first()
    status = 'GL_OK' if je else 'NO_GL'
    print(f'  {p.payment_method:12} {int(p.amount):>10,} FCFA  {status}')
"''')

ssh.close()
print('\nDone.')
