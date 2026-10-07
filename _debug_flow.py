#!/usr/bin/env python
"""Debug: check exact field values on recent investigation orders."""
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

from django.utils import timezone
from datetime import timedelta
from apps.investigations.models import InvestigationOrder, PaymentStatus, AcquisitionStatus

recent = timezone.now() - timedelta(days=3)
orders = InvestigationOrder.objects.filter(created_at__gte=recent, is_deleted=False).order_by('-created_at')[:10]

print('=== INVESTIGATION ORDER FIELD VALUES ===')
for o in orders:
    print(f'  Name: {o.investigation_type.name}')
    print(f'    status (Status):          "{o.status}"')
    print(f'    payment_status:           "{o.payment_status}"')
    print(f'    acquisition_status:       "{o.acquisition_status}"')
    print(f'    eye:                      "{o.eye}"')
    print(f'    assigned_to:              {o.assigned_to}')
    print(f'    patient:                  {o.patient}')
    print(f'    category:                 {o.investigation_type.category}')
    print(f'    created_at:               {o.created_at}')
    print()

# Now simulate the workstation query for an optometrist
print('=== SIMULATING OPTOMETRIST WORKSTATION ===')
from django.db.models import Q
_OPTOMETRY_CATS = {'REFRACTION', 'LOW_VISION'}
_paid_statuses = PaymentStatus.actionable_statuses()

base_qs = InvestigationOrder.objects.filter(is_deleted=False)
# Optometrist filter
optom_qs = base_qs.filter(
    Q(investigation_type__category__in=_OPTOMETRY_CATS)
)
print(f'All REFRACTION/LOW_VISION orders (any date): {optom_qs.count()}')

# Expected arrivals filter
expected = optom_qs.filter(
    acquisition_status=AcquisitionStatus.SCHEDULED,
    payment_status__in=_paid_statuses,
    status__in=['ORDERED', 'SCHEDULED'],
)
print(f'Expected arrivals (SCHEDULED + PAID + status ORDERED/SCHEDULED): {expected.count()}')
for o in expected:
    print(f'  {o.investigation_type.name} | status={o.status} | pay={o.payment_status} | acq={o.acquisition_status} | patient={o.patient}')

# What if we remove status filter?
expected_no_status = optom_qs.filter(
    acquisition_status=AcquisitionStatus.SCHEDULED,
    payment_status__in=_paid_statuses,
)
print(f'\nWithout status filter: {expected_no_status.count()}')
for o in expected_no_status:
    print(f'  {o.investigation_type.name} | status={o.status} | pay={o.payment_status}')

# Check the logged-in user who is the optometrist
from apps.accounts.models import User
optom_users = User.objects.filter(role__in=['optometrist', 'pediatric_refractionist'], is_active=True)
print(f'\nOptometrist users in system:')
for u in optom_users:
    print(f'  {u.get_full_name()} (role={u.role}, id={u.id})')
"""

sftp = ssh.open_sftp()
with sftp.open('/tmp/_debug2.py', 'w') as f:
    f.write(remote_script)
sftp.close()

stdin, stdout, stderr = ssh.exec_command('cd /opt/ehr-africa && source venv/bin/activate && python3 /tmp/_debug2.py')
print(stdout.read().decode('utf-8', errors='replace'))
err = stderr.read().decode('utf-8', errors='replace')
if err:
    for line in err.splitlines():
        if 'INFO' not in line and 'WARNING' not in line:
            print('ERR:', line)
ssh.close()
