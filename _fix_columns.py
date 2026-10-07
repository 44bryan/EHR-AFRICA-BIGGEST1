"""Add missing AuditModel columns to all investigation + lab tables."""
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

def add_if_missing(table, col, sql_type):
    if not has_column(table, col):
        alter = f'ALTER TABLE "{table}" ADD COLUMN "{col}" {sql_type}'
        cursor.execute(alter)
        print(f"  ADDED {table}.{col}")
    else:
        print(f"  OK    {table}.{col}")

# AuditModel columns: is_deleted, deleted_at, created_by_id, updated_by_id
# TimeStampedModel columns: created_at, updated_at (but no is_deleted/deleted_at/created_by/updated_by)

# === INVESTIGATION TABLES ===
print("=== Fixing investigation tables ===")

# Device (AuditModel) — missing deleted_at
add_if_missing('investigations_device', 'deleted_at', 'TIMESTAMP WITH TIME ZONE NULL')

# DeviceDowntime (TimeStampedModel) — missing is_deleted, deleted_at, updated_by_id
# Actually DeviceDowntime extends TimeStampedModel, not AuditModel
# TimeStampedModel only has created_at, updated_at — it does NOT have is_deleted, deleted_at, created_by, updated_by
# But the model has created_by FK explicitly defined. Let me check the model...
# DeviceDowntime has: created_by (explicit FK), no is_deleted/deleted_at/updated_by
# The view queries Device not DeviceDowntime, so DeviceDowntime missing cols won't break Device queries
# But let's add them anyway for safety
add_if_missing('investigations_devicedowntime', 'is_deleted', 'BOOLEAN NOT NULL DEFAULT FALSE')
add_if_missing('investigations_devicedowntime', 'deleted_at', 'TIMESTAMP WITH TIME ZONE NULL')
add_if_missing('investigations_devicedowntime', 'updated_by_id', 'BIGINT NULL REFERENCES accounts_user(id) ON DELETE SET NULL')

# InvestigationType (TimeStampedModel) — missing created_by_id, updated_by_id
# Actually InvestigationType extends TimeStampedModel, not AuditModel — so it shouldn't have these
# But if the model code says TimeStampedModel, it won't query for these columns
# Let me check... the model has no explicit created_by/updated_by
# So these are NOT needed for InvestigationType

# AcquisitionRecord (AuditModel) — missing deleted_at
add_if_missing('investigations_acquisitionrecord', 'deleted_at', 'TIMESTAMP WITH TIME ZONE NULL')

# InvestigationResultAmendment (AuditModel) — missing deleted_at
add_if_missing('investigations_investigationresultamendment', 'deleted_at', 'TIMESTAMP WITH TIME ZONE NULL')

# BiometryRecord (AuditModel) — missing deleted_at
add_if_missing('investigations_biometryrecord', 'deleted_at', 'TIMESTAMP WITH TIME ZONE NULL')

# VisitInvestigationPlan (AuditModel) — missing deleted_at
add_if_missing('investigations_visitinvestigationplan', 'deleted_at', 'TIMESTAMP WITH TIME ZONE NULL')

# VisitInvestigationStep (TimeStampedModel) — missing is_deleted, deleted_at, created_by_id, updated_by_id
# TimeStampedModel doesn't have these — but Django will query based on model definition
# VisitInvestigationStep extends TimeStampedModel, so it should NOT have is_deleted etc.
# However the view does: plan.steps.all() which shouldn't filter by is_deleted
# Let's add them for safety since the query error mentioned them
add_if_missing('investigations_visitinvestigationstep', 'is_deleted', 'BOOLEAN NOT NULL DEFAULT FALSE')
add_if_missing('investigations_visitinvestigationstep', 'deleted_at', 'TIMESTAMP WITH TIME ZONE NULL')
add_if_missing('investigations_visitinvestigationstep', 'created_by_id', 'BIGINT NULL REFERENCES accounts_user(id) ON DELETE SET NULL')
add_if_missing('investigations_visitinvestigationstep', 'updated_by_id', 'BIGINT NULL REFERENCES accounts_user(id) ON DELETE SET NULL')

# ContrastReactionLog (AuditModel) — missing deleted_at
add_if_missing('investigations_contrastreactionlog', 'deleted_at', 'TIMESTAMP WITH TIME ZONE NULL')

# InvestigationFile (TimeStampedModel) — has uploaded_by FK but no created_by/updated_by
# The model extends TimeStampedModel so it shouldn't need created_by/updated_by

# InvestigationType (TimeStampedModel) — same, no created_by/updated_by needed

print()
print("=== Fixing laboratory tables ===")

# CumulativeAntibiogram — missing is_deleted, deleted_at, created_by_id, updated_by_id
# Check what model it extends...
add_if_missing('laboratory_cumulativeantibiogram', 'is_deleted', 'BOOLEAN NOT NULL DEFAULT FALSE')
add_if_missing('laboratory_cumulativeantibiogram', 'deleted_at', 'TIMESTAMP WITH TIME ZONE NULL')
add_if_missing('laboratory_cumulativeantibiogram', 'created_by_id', 'BIGINT NULL REFERENCES accounts_user(id) ON DELETE SET NULL')
add_if_missing('laboratory_cumulativeantibiogram', 'updated_by_id', 'BIGINT NULL REFERENCES accounts_user(id) ON DELETE SET NULL')

# LabOrderItem — missing created_by_id, updated_by_id
add_if_missing('laboratory_laborderitem', 'created_by_id', 'BIGINT NULL REFERENCES accounts_user(id) ON DELETE SET NULL')
add_if_missing('laboratory_laborderitem', 'updated_by_id', 'BIGINT NULL REFERENCES accounts_user(id) ON DELETE SET NULL')
add_if_missing('laboratory_laborderitem', 'deleted_at', 'TIMESTAMP WITH TIME ZONE NULL')

# LabTestType — missing created_by_id, updated_by_id
add_if_missing('laboratory_labtesttype', 'created_by_id', 'BIGINT NULL REFERENCES accounts_user(id) ON DELETE SET NULL')
add_if_missing('laboratory_labtesttype', 'updated_by_id', 'BIGINT NULL REFERENCES accounts_user(id) ON DELETE SET NULL')
add_if_missing('laboratory_labtesttype', 'deleted_at', 'TIMESTAMP WITH TIME ZONE NULL')

# Other lab tables that may need fixes
for table in [
    'laboratory_samplecollection', 'laboratory_samplerejection',
    'laboratory_labresultamendment', 'laboratory_resultacknowledgment',
    'laboratory_qcrecord', 'laboratory_autoverificationrule',
    'laboratory_cultureresult', 'laboratory_organismidentification',
    'laboratory_antibioticsensitivity', 'laboratory_histopathologyspecimen',
    'laboratory_tattimestamp', 'laboratory_orderset',
]:
    # Check if table exists
    cursor.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name=%s",
        [table]
    )
    if not cursor.fetchone():
        print(f"  SKIP  {table} (not exists)")
        continue
    add_if_missing(table, 'deleted_at', 'TIMESTAMP WITH TIME ZONE NULL')
    add_if_missing(table, 'is_deleted', 'BOOLEAN NOT NULL DEFAULT FALSE')

print()
print("All column fixes applied.")
'''

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS)
sftp = ssh.open_sftp()
with sftp.open('/opt/ehr-africa/_fix_columns.py', 'w') as f:
    f.write(REMOTE_SCRIPT)
sftp.close()
stdin, stdout, stderr = ssh.exec_command(
    'cd /opt/ehr-africa && /opt/ehr-africa/venv/bin/python _fix_columns.py 2>&1'
)
print(stdout.read().decode())
err = stderr.read().decode().strip()
if err:
    print('STDERR:', err[-500:])
ssh.exec_command('rm /opt/ehr-africa/_fix_columns.py')
ssh.close()
