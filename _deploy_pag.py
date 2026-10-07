import paramiko, zipfile, time

with zipfile.ZipFile('/tmp/deploy_pagination.zip', 'w', zipfile.ZIP_DEFLATED) as zf:
    zf.write('templates/components/pagination.html', 'templates/components/pagination.html')
    zf.write('templates/patients/list.html', 'templates/patients/list.html')
    zf.write('templates/pharmacy/drug_list.html', 'templates/pharmacy/drug_list.html')
    zf.write('templates/billing/shift_list.html', 'templates/billing/shift_list.html')
    zf.write('templates/billing/invoice_list.html', 'templates/billing/invoice_list.html')
    zf.write('templates/billing/expenses.html', 'templates/billing/expenses.html')
    zf.write('templates/billing/proforma_list.html', 'templates/billing/proforma_list.html')
    zf.write('templates/investigations/imaging_list.html', 'templates/investigations/imaging_list.html')
    zf.write('templates/layouts/base_authenticated.html', 'templates/layouts/base_authenticated.html')
    zf.write('apps/core/middleware.py', 'apps/core/middleware.py')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.30.169', username='grudd420', password='123456')

sftp = ssh.open_sftp()
sftp.put('/tmp/deploy_pagination.zip', '/tmp/deploy_pagination.zip')
sftp.close()

cmds = [
    'echo 123456 | sudo -S unzip -o /tmp/deploy_pagination.zip -d /opt/ehr-africa',
    'echo 123456 | sudo -S systemctl restart ehr-gunicorn',
]
for cmd in cmds:
    stdin, stdout, stderr = ssh.exec_command(cmd)
    stdout.read()

time.sleep(3)

# Verify
verify = """import os; os.environ['DJANGO_SETTINGS_MODULE']='ehr_project.settings.base'
import django; django.setup()
from django.test import Client
import re
c = Client()
c.login(username='admin', password='Admin2026')
r = c.get('/patients/')
html = r.content.decode()
links = re.findall(r'href="([^"]*page=[^"]*)"', html)
print('Pagination links:', links[:5])
print('Has hx-disable:', 'hx-disable' in html)
print('Has hx-boost=true:', 'hx-boost="true"' in html)
"""

sftp2 = ssh.open_sftp()
with sftp2.open('/tmp/_vp.py', 'w') as f:
    f.write(verify)
sftp2.close()
ssh.exec_command('echo 123456 | sudo -S cp /tmp/_vp.py /opt/ehr-africa/_vp.py')
time.sleep(1)

stdin, stdout, stderr = ssh.exec_command('cd /opt/ehr-africa && /opt/ehr-africa/venv/bin/python manage.py shell < _vp.py 2>&1')
out = stdout.read().decode('utf-8', errors='replace')
for line in out.split('\n'):
    if any(k in line for k in ['Pagination', 'hx-disable', 'hx-boost']):
        print(line)

stdin2, stdout2, stderr2 = ssh.exec_command('curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/accounts/login/')
print('HTTP:', stdout2.read().decode().strip())

ssh.close()
print('Done')
