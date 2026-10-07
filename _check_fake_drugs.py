"""Check and remove fake/test drugs from DB."""
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.30.169', username='grudd420', password='123456')

script = (
    "import os; os.environ['DJANGO_SETTINGS_MODULE']='ehr_project.settings.base'; "
    "import django; django.setup(); "
    "from apps.pharmacy.models import Drug, DrugStock; "
    "real = Drug.objects.filter(is_deleted=False, barcode__startswith='PH0'); "
    "fake = Drug.objects.filter(is_deleted=False).exclude(barcode__startswith='PH0'); "
    "print(f'Total: {Drug.objects.filter(is_deleted=False).count()}'); "
    "print(f'Real (PH0): {real.count()}'); "
    "print(f'Fake: {fake.count()}'); "
    "[print(f'  {d.name} | bc={d.barcode} | stk={d.stock_items.filter(is_deleted=False).count()}') for d in fake.order_by('name')]"
)

cmd = f'/opt/ehr-africa/venv/bin/python -c "{script}"'
stdin, stdout, stderr = ssh.exec_command(cmd, get_pty=True)
out = stdout.read().decode()
err = stderr.read().decode()
print(out)
if 'Traceback' in err:
    print('ERR:', err[-500:])
ssh.close()
