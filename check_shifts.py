import paramiko, sys

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'

script = """
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.production')
import sys; sys.path.insert(0, '/opt/ehr-africa')
django.setup()
from django.utils import timezone
from apps.billing.models import CashierShift, ShiftStatus
from apps.accounts.models import User

today = timezone.localdate()
print('Today:', today)
print()

cashiers = User.objects.filter(role__in=['cashier','chief_cashier'], is_active=True)
print(f'Cashier accounts: {cashiers.count()}')

for c in cashiers:
    shift = CashierShift.objects.filter(cashier=c, shift_date=today, is_deleted=False).first()
    if shift:
        print(f'  {c.username:25} -> shift STATUS: {shift.status} | opened: {shift.opened_at}')
    else:
        print(f'  {c.username:25} -> *** NO SHIFT OPEN TODAY ***')

print()
total_today = CashierShift.objects.filter(shift_date=today, is_deleted=False).count()
open_today  = CashierShift.objects.filter(shift_date=today, status=ShiftStatus.OPEN, is_deleted=False).count()
print(f'Shifts today: {total_today} total, {open_today} open')

# Also check if there are any invoices today
from apps.billing.models import Invoice
inv_today = Invoice.objects.filter(created_at__date=today, is_deleted=False).count()
print(f'Invoices created today: {inv_today}')

# Check recent payments
from apps.billing.models import Payment
pay_today = Payment.objects.filter(created_at__date=today, is_deleted=False).count()
print(f'Payments recorded today: {pay_today}')
"""

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS)

sftp = ssh.open_sftp()
with sftp.open('/tmp/check_shifts2.py', 'w') as f:
    f.write(script)
sftp.close()

_, stdout, stderr = ssh.exec_command('cd /opt/ehr-africa && /opt/ehr-africa/venv/bin/python /tmp/check_shifts2.py')
stdout.channel.recv_exit_status()
out = stdout.read().decode('utf-8', errors='replace')
err = stderr.read().decode('utf-8', errors='replace')
sys.stdout.buffer.write(out.encode('utf-8', errors='replace'))
if err:
    sys.stdout.buffer.write(('ERR: ' + err + '\n').encode('utf-8', errors='replace'))
ssh.close()
