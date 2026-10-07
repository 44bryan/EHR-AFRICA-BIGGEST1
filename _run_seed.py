"""Upload and run the pharmacy seed script on the server."""
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.30.169', username='grudd420', password='123456')

# Run the seed script using manage.py shell
cmd = (
    'cd /opt/ehr-africa && '
    '/opt/ehr-africa/venv/bin/python manage.py shell '
    '< seed_pharmacy_stock.py 2>&1'
)
stdin, stdout, stderr = ssh.exec_command(cmd)
out = stdout.read().decode()
err = stderr.read().decode()
print("OUT:", out)
if err.strip():
    print("ERR:", err[-500:])

# If no output, try checking drug count directly
if not out.strip():
    print("\n--- Checking DB directly ---")
    check_cmd = (
        "cd /opt/ehr-africa && /opt/ehr-africa/venv/bin/python -c \""
        "import os; os.environ['DJANGO_SETTINGS_MODULE']='ehr_project.settings.base'; "
        "import django; django.setup(); "
        "from apps.pharmacy.models import Drug, DrugStock, PharmacyLocation; "
        "print(f'Drugs: {Drug.objects.filter(is_deleted=False).count()}'); "
        "print(f'Stock batches: {DrugStock.objects.filter(is_deleted=False).count()}'); "
        "print(f'Locations: {list(PharmacyLocation.objects.values_list(chr(110)+chr(97)+chr(109)+chr(101), flat=True))}'); "
        "\""
    )
    stdin2, stdout2, stderr2 = ssh.exec_command(check_cmd)
    out2 = stdout2.read().decode()
    err2 = stderr2.read().decode()
    print(out2)
    if 'Traceback' in err2:
        print("ERR:", err2[-500:])

ssh.close()
print("DONE")
