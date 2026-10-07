import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.30.169', username='grudd420', password='123456', timeout=15)

script = (
    "import django,os;"
    "os.environ['DJANGO_SETTINGS_MODULE']='ehr_project.settings.base';"
    "django.setup();"
    "from apps.consultations.models import Diagnosis;"
    "print('Total:', Diagnosis.objects.count());"
    "print('Ophthalmic:', Diagnosis.objects.filter(is_ophthalmic=True).count());"
    "print('Non-oph:', Diagnosis.objects.filter(is_ophthalmic=False).count());"
    "[print(d.icd10_code, '-', d.description) for d in Diagnosis.objects.all()[:20]]"
)
cmd = f'cd /opt/ehr-africa && /opt/ehr-africa/venv/bin/python -c "{script}"'
stdin, stdout, stderr = ssh.exec_command(cmd, timeout=20)
out = stdout.read().decode('utf-8', errors='replace')
err = stderr.read().decode('utf-8', errors='replace')
if out.strip():
    print(out)
if err.strip():
    for line in err.splitlines():
        if 'warning' not in line.lower() and 'info' not in line.lower():
            print('ERR:', line)
ssh.close()
