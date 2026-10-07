"""Check DB columns for failing tables."""
import paramiko

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'

REMOTE_SCRIPT = '''
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.base')
django.setup()
from django.db import connection
cursor = connection.cursor()

print('=== investigations_device columns ===')
cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='investigations_device' ORDER BY ordinal_position")
for row in cursor.fetchall():
    print(f'  {row[0]}')

print()
print('=== investigations_acquisitionrecord columns ===')
cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='investigations_acquisitionrecord' ORDER BY ordinal_position")
rows = cursor.fetchall()
if rows:
    for row in rows:
        print(f'  {row[0]}')
else:
    print('  TABLE DOES NOT EXIST')

print()
print('=== laboratory_cumulativeantibiogram columns ===')
cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='laboratory_cumulativeantibiogram' ORDER BY ordinal_position")
rows = cursor.fetchall()
if rows:
    for row in rows:
        print(f'  {row[0]}')
else:
    print('  TABLE DOES NOT EXIST')

print()
print('=== AuditModel fields ===')
from apps.core.models import AuditModel
for f in AuditModel._meta.get_fields():
    print(f'  {f.name}')
'''

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS)
sftp = ssh.open_sftp()
with sftp.open('/opt/ehr-africa/_audit3.py', 'w') as f:
    f.write(REMOTE_SCRIPT)
sftp.close()
stdin, stdout, stderr = ssh.exec_command(
    'cd /opt/ehr-africa && /opt/ehr-africa/venv/bin/python _audit3.py 2>&1'
)
print(stdout.read().decode())
ssh.exec_command('rm /opt/ehr-africa/_audit3.py')
ssh.close()
