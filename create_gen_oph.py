"""Add 2 General Ophthalmologists per tier (6 accounts)."""
import paramiko, sys

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'
PASSWORD = 'DemoRun2@2026'

NEW = [
    dict(username='dr2_dr_vip_gen1', first='VIP',      last='Gen. Ophthalmologist 1', role='ophthalmologist', patient_tier='VIP',      consultation_unit='VIP_CONSULT', email='dr2.dr.vip.gen1@demorun2.ehr'),
    dict(username='dr2_dr_vip_gen2', first='VIP',      last='Gen. Ophthalmologist 2', role='ophthalmologist', patient_tier='VIP',      consultation_unit='VIP_CONSULT', email='dr2.dr.vip.gen2@demorun2.ehr'),
    dict(username='dr2_dr_std_gen1', first='Standard', last='Gen. Ophthalmologist 1', role='ophthalmologist', patient_tier='STANDARD', consultation_unit='GENERAL',     email='dr2.dr.std.gen1@demorun2.ehr'),
    dict(username='dr2_dr_std_gen2', first='Standard', last='Gen. Ophthalmologist 2', role='ophthalmologist', patient_tier='STANDARD', consultation_unit='GENERAL',     email='dr2.dr.std.gen2@demorun2.ehr'),
    dict(username='dr2_dr_exp_gen1', first='Express',  last='Gen. Ophthalmologist 1', role='ophthalmologist', patient_tier='EXPRESS',  consultation_unit='EXP_CONSULT', email='dr2.dr.exp.gen1@demorun2.ehr'),
    dict(username='dr2_dr_exp_gen2', first='Express',  last='Gen. Ophthalmologist 2', role='ophthalmologist', patient_tier='EXPRESS',  consultation_unit='EXP_CONSULT', email='dr2.dr.exp.gen2@demorun2.ehr'),
]

lines = [
    "import django, os, sys",
    "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.production')",
    "sys.path.insert(0, '/opt/ehr-africa')",
    "django.setup()",
    "from apps.accounts.models import User",
    "created, skipped = [], []",
]
for a in NEW:
    lines.append(
        f"if not User.objects.filter(username='{a['username']}').exists():\n"
        f"    User.objects.create_user(username='{a['username']}',password='{PASSWORD}',"
        f"email='{a['email']}',first_name='{a['first']}',last_name='{a['last']}',"
        f"role='{a['role']}',patient_tier='{a['patient_tier']}',"
        f"cashier_station='ALL',consultation_unit='{a['consultation_unit']}')\n"
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
with sftp.open('/tmp/create_gen_oph.py', 'w') as f:
    f.write('\n'.join(lines))
sftp.close()

_, stdout, stderr = ssh.exec_command(
    'cd /opt/ehr-africa && /opt/ehr-africa/venv/bin/python /tmp/create_gen_oph.py'
)
stdout.channel.recv_exit_status()
out = stdout.read().decode('utf-8', errors='replace')
err = stderr.read().decode('utf-8', errors='replace')
sys.stdout.buffer.write(out.encode('utf-8', errors='replace'))
if err:
    sys.stdout.buffer.write(('ERRORS: ' + err + '\n').encode('utf-8', errors='replace'))
ssh.close()
print('Done.')
