"""Check actual lab table names."""
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

cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name LIKE 'laboratory_%' ORDER BY table_name")
print("=== All laboratory tables ===")
for row in cursor.fetchall():
    print(f"  {row[0]}")

cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name LIKE 'investigations_%' ORDER BY table_name")
print()
print("=== All investigations tables ===")
for row in cursor.fetchall():
    print(f"  {row[0]}")

# Also check the model Meta for db_table overrides
print()
print("=== Lab model db_table ===")
from django.apps import apps
for model in apps.get_app_config('laboratory').get_models():
    print(f"  {model.__name__}: {model._meta.db_table}")

print()
print("=== Investigation model db_table ===")
for model in apps.get_app_config('investigations').get_models():
    print(f"  {model.__name__}: {model._meta.db_table}")
'''

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS)
sftp = ssh.open_sftp()
with sftp.open('/opt/ehr-africa/_audit5.py', 'w') as f:
    f.write(REMOTE_SCRIPT)
sftp.close()
stdin, stdout, stderr = ssh.exec_command(
    'cd /opt/ehr-africa && /opt/ehr-africa/venv/bin/python _audit5.py 2>&1'
)
print(stdout.read().decode())
ssh.exec_command('rm /opt/ehr-africa/_audit5.py')
ssh.close()
