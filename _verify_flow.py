#!/usr/bin/env python
"""Quick verify: prices set, bridge working."""
import paramiko, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.30.169', username='grudd420', password='123456')

remote_script = r"""
import os, sys, django
os.environ['DJANGO_SETTINGS_MODULE'] = 'ehr_project.settings.base'
sys.path.insert(0, '/opt/ehr-africa')
sys.stdout.reconfigure(encoding='utf-8')
django.setup()

from apps.investigations.models import InvestigationType

# Check: any investigation types still at 0 price?
zero = InvestigationType.objects.filter(is_deleted=False, unit_price=0)
if zero.exists():
    print(f'WARNING: {zero.count()} investigation types still at 0 FCFA:')
    for t in zero:
        print(f'  - {t.name} ({t.category})')
else:
    print('OK: All investigation types have prices > 0')

print()

# Check: any recent ServiceWorkOrders with 0 amount?
from apps.billing.models import ServiceWorkOrder, ServiceCategory
from django.utils import timezone
from datetime import timedelta
recent = timezone.now() - timedelta(days=7)
zero_wos = ServiceWorkOrder.objects.filter(
    category=ServiceCategory.INVESTIGATION,
    created_at__gte=recent,
    is_deleted=False,
).order_by('-created_at')[:10]

print(f'Recent Investigation Work Orders (last 7 days):')
for wo in zero_wos:
    print(f'  {wo.created_at.strftime("%Y-%m-%d %H:%M")} | {wo.description[:50]:<50} | {wo.amount} FCFA | status={wo.status}')

if not zero_wos:
    print('  (none found)')

print()

# Check bridge: any InvestigationOrders with UNPAID that have a matching DONE work order?
from apps.investigations.models import InvestigationOrder, PaymentStatus
unpaid = InvestigationOrder.objects.filter(
    payment_status=PaymentStatus.UNPAID,
    is_deleted=False,
    created_at__gte=recent,
)
print(f'Unpaid investigation orders (last 7 days): {unpaid.count()}')
paid = InvestigationOrder.objects.filter(
    payment_status=PaymentStatus.PAID,
    is_deleted=False,
    created_at__gte=recent,
)
print(f'Paid investigation orders (last 7 days): {paid.count()}')

# Sample a couple investigation types with their prices
print()
print('Sample investigation prices:')
samples = ['Subjective Refraction', 'OCT Macula', 'Fundus Photography', 'Visual Field 24-2', 'Auto-Refraction']
for name in samples:
    try:
        t = InvestigationType.objects.get(name=name, is_deleted=False)
        print(f'  {t.name:<35} {t.unit_price:>10,} FCFA')
    except InvestigationType.DoesNotExist:
        print(f'  {name:<35} NOT FOUND')
"""

sftp = ssh.open_sftp()
with sftp.open('/tmp/_verify.py', 'w') as f:
    f.write(remote_script)
sftp.close()

stdin, stdout, stderr = ssh.exec_command('cd /opt/ehr-africa && source venv/bin/activate && python3 /tmp/_verify.py')
print(stdout.read().decode('utf-8', errors='replace'))
err = stderr.read().decode('utf-8', errors='replace')
if err:
    for line in err.splitlines():
        if 'INFO' not in line and 'WARNING' not in line:
            print('ERR:', line)
ssh.close()
