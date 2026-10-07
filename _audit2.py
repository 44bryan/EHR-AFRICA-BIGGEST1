"""Get full error details for failing views."""
import paramiko

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'

REMOTE_SCRIPT = r'''
import django, os, traceback
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.base')
django.setup()

from django.test import RequestFactory
from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore

User = get_user_model()
admin = User.objects.get(username='admin')
factory = RequestFactory()

def test_view(mod_path, fn_name, label, **kwargs):
    try:
        module = __import__(mod_path, fromlist=[fn_name])
        view_fn = getattr(module, fn_name)
        request = factory.get('/test/')
        request.user = admin
        request.session = SessionStore()
        resp = view_fn(request, **kwargs)
        status = resp.status_code
        print(f"  {status} {label}")
    except Exception as e:
        tb = traceback.format_exc()
        print(f"  ERR {label}:")
        # Print last 5 lines of traceback
        lines = tb.strip().split('\n')
        for line in lines[-5:]:
            print(f"      {line}")
        print()

# Investigation failing views
print("=== INVESTIGATION FAILING VIEWS (full errors) ===")
test_view('apps.investigations.views', 'investigation_workstation_view', 'workstation')
test_view('apps.investigations.views', 'investigation_list_view', 'list')
test_view('apps.investigations.views', 'device_list_view', 'device_list')

# Lab - find correct view names first
print()
print("=== LAB VIEW NAMES ===")
import apps.laboratory.views as lv
all_views = [x for x in dir(lv) if 'view' in x.lower() and not x.startswith('_')]
for v in sorted(all_views):
    print(f"  {v}")

# Lab failing views
print()
print("=== LAB FAILING VIEWS (full errors) ===")
# Find correct names
test_view('apps.laboratory.views', 'antibiogram_view', 'antibiogram')

# Also check the lab URLs
print()
print("=== LAB URL PATTERNS ===")
from apps.laboratory import urls as lab_urls
for pattern in lab_urls.urlpatterns:
    print(f"  {pattern.name}: {pattern.pattern}")

# Also check investigation URL patterns
print()
print("=== INVESTIGATION URL PATTERNS ===")
from apps.investigations import urls as inv_urls
for pattern in inv_urls.urlpatterns:
    print(f"  {pattern.name}: {pattern.pattern}")
'''

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS)
sftp = ssh.open_sftp()
with sftp.open('/opt/ehr-africa/_audit2.py', 'w') as f:
    f.write(REMOTE_SCRIPT)
sftp.close()
stdin, stdout, stderr = ssh.exec_command(
    'cd /opt/ehr-africa && /opt/ehr-africa/venv/bin/python _audit2.py 2>&1'
)
print(stdout.read().decode())
ssh.exec_command('rm /opt/ehr-africa/_audit2.py')
ssh.close()
