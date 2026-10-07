"""Find all tables missing AuditModel columns."""
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

# All investigation tables
inv_tables = [
    'investigations_device',
    'investigations_devicedowntime',
    'investigations_investigationtype',
    'investigations_investigationorder',
    'investigations_acquisitionrecord',
    'investigations_investigationresult',
    'investigations_investigationresultamendment',
    'investigations_biometryrecord',
    'investigations_imagingstudy',
    'investigations_investigationfile',
    'investigations_visitinvestigationplan',
    'investigations_visitinvestigationstep',
    'investigations_contrastreactionlog',
]

# All lab tables that might have issues
lab_tables = [
    'laboratory_cumulativeantibiogram',
    'laboratory_laborder',
    'laboratory_laborderitem',
    'laboratory_labresult',
    'laboratory_specimen',
    'laboratory_qcmaterial',
    'laboratory_qcresult',
    'laboratory_sendouttest',
    'laboratory_microbioculture',
    'laboratory_cultureorganism',
    'laboratory_organismsensitivity',
    'laboratory_histopathspecimen',
    'laboratory_criticalvaluenotification',
    'laboratory_deltacheck',
    'laboratory_labtesttype',
]

audit_cols = ['is_deleted', 'deleted_at', 'created_by_id', 'updated_by_id']

print("Checking for missing AuditModel columns...")
print()

for table in inv_tables + lab_tables:
    cursor.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name='{table}'")
    cols = {row[0] for row in cursor.fetchall()}
    if not cols:
        print(f"  MISSING TABLE: {table}")
        continue
    missing = [c for c in audit_cols if c not in cols]
    if missing:
        print(f"  {table}: MISSING {missing}")
    else:
        print(f"  {table}: OK")
'''

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS)
sftp = ssh.open_sftp()
with sftp.open('/opt/ehr-africa/_audit4.py', 'w') as f:
    f.write(REMOTE_SCRIPT)
sftp.close()
stdin, stdout, stderr = ssh.exec_command(
    'cd /opt/ehr-africa && /opt/ehr-africa/venv/bin/python _audit4.py 2>&1'
)
print(stdout.read().decode())
ssh.exec_command('rm /opt/ehr-africa/_audit4.py')
ssh.close()
