"""Check server logs for billing errors."""
import paramiko, sys

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS)

checks = {
    'Last 50 gunicorn errors':      'tail -80 /opt/ehr-africa/logs/gunicorn-error.log | grep -i "error\|exception\|traceback\|billing\|cashier\|invoice" | tail -50',
    'Last traceback in error log':  'tail -200 /opt/ehr-africa/logs/gunicorn-error.log | grep -A 20 "Traceback" | tail -60',
    'Billing day open status':      'cd /opt/ehr-africa && /opt/ehr-africa/venv/bin/python -c "import django,os;os.environ[\'DJANGO_SETTINGS_MODULE\']=\'ehr_project.settings.production\';django.setup();from apps.billing.models import *;d=BillingDay.objects.order_by(\'-date\').first();print(\'Latest BillingDay:\',d.date if d else None,\'| open:\',d.is_open if d else None)"',
    'Cashier station check':        'cd /opt/ehr-africa && /opt/ehr-africa/venv/bin/python -c "import django,os;os.environ[\'DJANGO_SETTINGS_MODULE\']=\'ehr_project.settings.production\';django.setup();from apps.accounts.models import User;[print(u.username,\'|\',u.role,\'|\',u.cashier_station,\'|\',u.patient_tier) for u in User.objects.filter(username__startswith=\'dr2_cash\')]"',
    'Recent access log (billing)':  'tail -100 /opt/ehr-africa/logs/gunicorn-access.log | grep -i "billing\|invoice\|cashier\|collect\|pay" | tail -30',
    'Daphne still running':         'pgrep -fa daphne | grep -v grep',
    'Gunicorn still running':       'pgrep -fa gunicorn | grep -v grep | head -2',
}

print('='*65)
print('EHR AFRICA — BILLING / CASHIER ERROR CHECK')
print('='*65)
for label, cmd in checks.items():
    _, stdout, stderr = ssh.exec_command(cmd)
    stdout.channel.recv_exit_status()
    out = stdout.read().decode('utf-8', errors='replace').strip()
    err = stderr.read().decode('utf-8', errors='replace').strip()
    result = out or err or '(no output / no errors found)'
    print(f'\n[{label}]')
    print(result)

print('\n' + '='*65)
ssh.close()
