"""Verify server state — migrations, services, key features."""
import paramiko, sys

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS)

checks = {
    'Gunicorn running':       'pgrep -fa gunicorn | grep -v grep | head -3',
    'Daphne running':         'pgrep -fa daphne | grep -v grep | head -3',
    'Celery running':         'pgrep -fa celery | grep -v grep | head -3',
    'Nginx running':          'pgrep -fa nginx | grep -v grep | head -3',
    'Redis running':          'pgrep -fa redis | grep -v grep | head -3',
    'Unapplied migrations':   'cd /opt/ehr-africa && /opt/ehr-africa/venv/bin/python manage.py showmigrations --list 2>/dev/null | grep "\\[ \\]" | head -20',
    'Signature field in DB':  'cd /opt/ehr-africa && /opt/ehr-africa/venv/bin/python -c "import django,os;os.environ[\'DJANGO_SETTINGS_MODULE\']=\'ehr_project.settings.production\';django.setup();from apps.accounts.models import User;print(\'signature field:\', hasattr(User(),"signature\"))"',
    'Accounts migration 036': 'cd /opt/ehr-africa && /opt/ehr-africa/venv/bin/python manage.py showmigrations accounts 2>/dev/null | tail -10',
    'Static files present':   'ls /opt/ehr-africa/staticfiles/js/ | head -5',
    'Media dir writable':     'ls /opt/ehr-africa/media/ 2>/dev/null | head -5 || echo "NO MEDIA DIR"',
    'Disk space':             'df -h /opt/ehr-africa | tail -1',
    'DB connection':          'cd /opt/ehr-africa && /opt/ehr-africa/venv/bin/python -c "import django,os;os.environ[\'DJANGO_SETTINGS_MODULE\']=\'ehr_project.settings.production\';django.setup();from django.db import connection;connection.ensure_connection();print(\'DB OK\')"',
}

print('='*60)
print('EHR AFRICA — SYSTEM STATE CHECK')
print('='*60)
for label, cmd in checks.items():
    _, stdout, stderr = ssh.exec_command(cmd)
    stdout.channel.recv_exit_status()
    out = stdout.read().decode('utf-8', errors='replace').strip()
    err = stderr.read().decode('utf-8', errors='replace').strip()
    result = out or err or '(no output)'
    print(f'\n[{label}]')
    print(result)

print('\n' + '='*60)
ssh.close()
