"""Add missing columns — User PK is UUID."""
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

def has_column(table, col):
    cursor.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_name=%s AND column_name=%s",
        [table, col]
    )
    return cursor.fetchone() is not None

def table_exists(table):
    cursor.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name=%s",
        [table]
    )
    return cursor.fetchone() is not None

USER_FK = 'UUID NULL REFERENCES accounts_user(id) ON DELETE SET NULL'

def add_if_missing(table, col, sql_type):
    if not has_column(table, col):
        alter = f'ALTER TABLE "{table}" ADD COLUMN "{col}" {sql_type}'
        try:
            cursor.execute(alter)
            print(f"  ADDED {table}.{col}")
        except Exception as e:
            connection.cursor()  # reset after error
            print(f"  FAIL  {table}.{col}: {e}")
    else:
        print(f"  OK    {table}.{col}")

def fix_audit_table(table):
    """Add missing AuditModel columns."""
    if not table_exists(table):
        print(f"  SKIP  {table} (not exists)")
        return
    add_if_missing(table, 'deleted_at', 'TIMESTAMP WITH TIME ZONE NULL')
    add_if_missing(table, 'is_deleted', 'BOOLEAN NOT NULL DEFAULT FALSE')
    add_if_missing(table, 'created_by_id', USER_FK)
    add_if_missing(table, 'updated_by_id', USER_FK)

print("=== Fixing investigation tables ===")

# AuditModel tables — need deleted_at (and maybe other cols)
for t in [
    'investigations_device',
    'investigations_acquisitionrecord',
    'investigations_investigationresultamendment',
    'investigations_biometryrecord',
    'investigations_visitinvestigationplan',
    'investigations_contrastreactionlog',
]:
    add_if_missing(t, 'deleted_at', 'TIMESTAMP WITH TIME ZONE NULL')

# DeviceDowntime (TimeStampedModel + explicit created_by)
add_if_missing('investigations_devicedowntime', 'updated_by_id', USER_FK)

# VisitInvestigationStep (TimeStampedModel but code might reference AuditModel cols)
for col, sql in [
    ('is_deleted', 'BOOLEAN NOT NULL DEFAULT FALSE'),
    ('deleted_at', 'TIMESTAMP WITH TIME ZONE NULL'),
    ('created_by_id', USER_FK),
    ('updated_by_id', USER_FK),
]:
    add_if_missing('investigations_visitinvestigationstep', col, sql)

print()
print("=== Fixing laboratory tables ===")

# CumulativeAntibiogram
fix_audit_table('laboratory_cumulativeantibiogram')

# LabOrderItem
for col, sql in [
    ('deleted_at', 'TIMESTAMP WITH TIME ZONE NULL'),
    ('created_by_id', USER_FK),
    ('updated_by_id', USER_FK),
]:
    add_if_missing('laboratory_laborderitem', col, sql)

# LabTestType
for col, sql in [
    ('deleted_at', 'TIMESTAMP WITH TIME ZONE NULL'),
    ('created_by_id', USER_FK),
    ('updated_by_id', USER_FK),
]:
    add_if_missing('laboratory_labtesttype', col, sql)

# Fix deleted_at + is_deleted on remaining lab tables
for t in [
    'laboratory_samplecollection', 'laboratory_samplerejection',
    'laboratory_labresultamendment', 'laboratory_resultacknowledgment',
    'laboratory_qcrecord', 'laboratory_autoverificationrule',
    'laboratory_cultureresult', 'laboratory_organismidentification',
    'laboratory_antibioticsensitivity', 'laboratory_histopathologyspecimen',
    'laboratory_tattimestamp', 'laboratory_orderset',
]:
    if table_exists(t):
        add_if_missing(t, 'deleted_at', 'TIMESTAMP WITH TIME ZONE NULL')
        add_if_missing(t, 'is_deleted', 'BOOLEAN NOT NULL DEFAULT FALSE')
    else:
        print(f"  SKIP  {t} (not exists)")

print()
print("All fixes applied.")
'''

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS)
sftp = ssh.open_sftp()
with sftp.open('/opt/ehr-africa/_fix_columns2.py', 'w') as f:
    f.write(REMOTE_SCRIPT)
sftp.close()
stdin, stdout, stderr = ssh.exec_command(
    'cd /opt/ehr-africa && /opt/ehr-africa/venv/bin/python _fix_columns2.py 2>&1'
)
print(stdout.read().decode())
err = stderr.read().decode().strip()
if err:
    print('STDERR:', err[-300:])
ssh.exec_command('rm /opt/ehr-africa/_fix_columns2.py')
ssh.close()
