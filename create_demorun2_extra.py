"""Add Chief Cashier, Medical Records, and Gatekeeper accounts for Demo Run 2."""
import paramiko, sys

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'
PASSWORD = 'DemoRun2@2026'

EXTRA = [
    dict(username='dr2_chief_cash',  first='Chief',   last='Cashier',         role='chief_cashier',   patient_tier='ALL', cashier_station='ALL', consultation_unit='GENERAL', email='dr2.chief.cash@demorun2.ehr'),
    dict(username='dr2_med_records', first='Medical', last='Records Officer',  role='medical_records', patient_tier='ALL', cashier_station='ALL', consultation_unit='GENERAL', email='dr2.med.records@demorun2.ehr'),
    dict(username='dr2_gatekeeper',  first='Gate',    last='Security',         role='gatekeeper',      patient_tier='ALL', cashier_station='ALL', consultation_unit='GENERAL', email='dr2.gatekeeper@demorun2.ehr'),
]

lines = [
    "import django, os, sys",
    "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.production')",
    "sys.path.insert(0, '/opt/ehr-africa')",
    "django.setup()",
    "from apps.accounts.models import User",
    "created, skipped = [], []",
]
for a in EXTRA:
    lines.append(
        f"if not User.objects.filter(username='{a['username']}').exists():\n"
        f"    u=User.objects.create_user(username='{a['username']}',password='{PASSWORD}',"
        f"email='{a['email']}',first_name='{a['first']}',last_name='{a['last']}',"
        f"role='{a['role']}',patient_tier='{a['patient_tier']}',"
        f"cashier_station='{a['cashier_station']}',consultation_unit='{a['consultation_unit']}')\n"
        f"    created.append('{a['username']}')\n"
        f"else:\n"
        f"    skipped.append('{a['username']}')"
    )
lines.append("print('CREATED:', created)")
lines.append("print('SKIPPED:', skipped)")

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS)

sftp = ssh.open_sftp()
with sftp.open('/tmp/create_dr2_extra.py', 'w') as f:
    f.write('\n'.join(lines))
sftp.close()

_, stdout, stderr = ssh.exec_command(
    'cd /opt/ehr-africa && /opt/ehr-africa/venv/bin/python /tmp/create_dr2_extra.py'
)
stdout.channel.recv_exit_status()
out = stdout.read().decode('utf-8', errors='replace')
err = stderr.read().decode('utf-8', errors='replace')
sys.stdout.buffer.write(out.encode('utf-8', errors='replace'))
if err:
    sys.stdout.buffer.write(('ERRORS: ' + err + '\n').encode('utf-8', errors='replace'))
ssh.close()
print('Done.')
