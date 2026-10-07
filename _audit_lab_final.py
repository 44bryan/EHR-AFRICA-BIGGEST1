"""Final lab audit with correct view names."""
import paramiko

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'

REMOTE_SCRIPT = '''
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
        if status >= 500:
            print(f"      {resp.content.decode('utf-8', errors='replace')[:200]}")
    except Exception as e:
        tb = traceback.format_exc()
        lines = tb.strip().split("\\n")
        print(f"  ERR {label}: {lines[-1][:200]}")

print("=== ALL LAB VIEWS (correct names) ===")
# From the url patterns:
# dashboard -> lab_list_view? Let me check what the / URL maps to
import apps.laboratory.urls as lu
for p in lu.urlpatterns:
    if not hasattr(p, 'callback'):
        continue
    print(f"  URL: {p.name} -> {p.callback.__name__}")

print()
print("=== Testing lab views by URL name ===")

# Get all lab URL names and their view functions
from apps.laboratory import urls as lab_urls
for pattern in lab_urls.urlpatterns:
    name = pattern.name
    view_fn = pattern.callback
    fn_name = view_fn.__name__

    # Skip views that need URL params (pk, consultation_pk, etc)
    route = str(pattern.pattern)
    if '<' in route:
        print(f"  SKIP {name} ({fn_name}) — needs URL param: {route}")
        continue

    try:
        request = factory.get('/test/')
        request.user = admin
        request.session = SessionStore()
        resp = view_fn(request)
        print(f"  {resp.status_code} {name} ({fn_name})")
        if resp.status_code >= 500:
            body = resp.content.decode('utf-8', errors='replace')[:200]
            print(f"      {body}")
    except Exception as e:
        tb = traceback.format_exc()
        lines = tb.strip().split("\\n")
        print(f"  ERR {name} ({fn_name}): {lines[-1][:200]}")

print()
print("=== Testing investigation views by URL name ===")
from apps.investigations import urls as inv_urls
for pattern in inv_urls.urlpatterns:
    name = pattern.name
    view_fn = pattern.callback
    fn_name = view_fn.__name__
    route = str(pattern.pattern)
    if '<' in route:
        print(f"  SKIP {name} ({fn_name}) — needs param: {route}")
        continue
    try:
        request = factory.get('/test/')
        request.user = admin
        request.session = SessionStore()
        resp = view_fn(request)
        print(f"  {resp.status_code} {name} ({fn_name})")
        if resp.status_code >= 500:
            body = resp.content.decode('utf-8', errors='replace')[:200]
            print(f"      {body}")
    except Exception as e:
        tb = traceback.format_exc()
        lines = tb.strip().split("\\n")
        print(f"  ERR {name} ({fn_name}): {lines[-1][:200]}")
'''

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS)
sftp = ssh.open_sftp()
with sftp.open('/opt/ehr-africa/_audit_lab_final.py', 'w') as f:
    f.write(REMOTE_SCRIPT)
sftp.close()
stdin, stdout, stderr = ssh.exec_command(
    'cd /opt/ehr-africa && /opt/ehr-africa/venv/bin/python _audit_lab_final.py 2>&1'
)
print(stdout.read().decode())
ssh.exec_command('rm /opt/ehr-africa/_audit_lab_final.py')
ssh.close()
