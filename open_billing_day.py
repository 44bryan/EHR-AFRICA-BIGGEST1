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
from decimal import Decimal
from apps.billing.models import CashierShift, ShiftStatus, CashierSession, SessionStatus
from apps.accounts.models import User, UserRole

today = timezone.localdate()
print('Opening billing day for:', today)

# Get chief cashier to act as created_by
chief = User.objects.filter(role='chief_cashier', is_active=True).first()
if not chief:
    chief = User.objects.filter(is_superuser=True).first()
print(f'Acting as: {chief.username}')

# Auto-close any stale shifts from previous days
stale = CashierShift.objects.filter(shift_date__lt=today, status=ShiftStatus.OPEN, is_deleted=False)
stale_count = stale.count()
if stale_count:
    stale.update(status=ShiftStatus.CLOSED, closed_at=timezone.now(),
                 notes='Auto-closed when new day was opened.')
    print(f'  Closed {stale_count} stale shift(s) from previous days.')

# Auto-close stale desk sessions
stale_sessions = CashierSession.objects.filter(
    status=SessionStatus.OPEN, is_deleted=False
).exclude(opened_at__date=today)
ss_count = stale_sessions.count()
if ss_count:
    stale_sessions.update(status=SessionStatus.CLOSED, closed_at=timezone.now(),
                          notes='Auto-closed by day open.')
    print(f'  Closed {ss_count} stale session(s).')

# Get all active cashiers
cashiers = User.objects.filter(
    role__in=['cashier', 'billing_officer', 'optical_dispenser', 'pharmacist', 'chief_cashier'],
    is_active=True
).order_by('username')

existing_ids = set(
    CashierShift.objects.filter(shift_date=today, is_deleted=False).values_list('cashier_id', flat=True)
)

created = 0
skipped = 0
for c in cashiers:
    if c.id in existing_ids:
        print(f'  SKIP {c.username} (shift already exists)')
        skipped += 1
        continue
    CashierShift.objects.create(
        cashier=c,
        shift_date=today,
        opening_cash=Decimal('0'),
        status=ShiftStatus.OPEN,
        created_by=chief,
    )
    print(f'  OPENED shift for {c.username}')
    created += 1

print()
print(f'Done. Created: {created}, Skipped: {skipped}')
print(f'All cashiers can now process payments for {today}.')
"""

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS)

sftp = ssh.open_sftp()
with sftp.open('/tmp/open_billing_day.py', 'w') as f:
    f.write(script)
sftp.close()

_, stdout, stderr = ssh.exec_command('cd /opt/ehr-africa && /opt/ehr-africa/venv/bin/python /tmp/open_billing_day.py')
stdout.channel.recv_exit_status()
out = stdout.read().decode('utf-8', errors='replace')
err = stderr.read().decode('utf-8', errors='replace')
sys.stdout.buffer.write(out.encode('utf-8', errors='replace'))
if err:
    sys.stdout.buffer.write(('ERR: ' + err + '\n').encode('utf-8', errors='replace'))
ssh.close()
