"""Audit all investigation + lab views on production server."""
import paramiko

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'

REMOTE_SCRIPT = r'''
import django, os, sys, traceback
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
        if status >= 400 and status != 403:
            body = resp.content.decode('utf-8', errors='replace')[:200]
            print(f"      {body}")
    except Exception as e:
        tb = traceback.format_exc()
        # Get last line of traceback
        last = tb.strip().split('\n')[-1]
        print(f"  ERR {label}: {last[:200]}")

print("=== INVESTIGATION VIEWS ===")
test_view('apps.investigations.views', 'investigation_workstation_view', 'workstation')
test_view('apps.investigations.views', 'investigation_list_view', 'list')
test_view('apps.investigations.views', 'device_list_view', 'device_list')
test_view('apps.investigations.views', 'imaging_study_list', 'imaging_list')
test_view('apps.investigations.views', 'investigation_stats_view', 'stats')
test_view('apps.investigations.views', 'machine_revenue_view', 'machine_revenue')
test_view('apps.investigations.views', 'staff_throughput_view', 'staff_throughput')
test_view('apps.investigations.views', 'unacknowledged_results_view', 'unacknowledged')

print()
print("=== LABORATORY VIEWS ===")
test_view('apps.laboratory.views', 'lab_dashboard_view', 'dashboard')
test_view('apps.laboratory.views', 'lab_order_list_view', 'order_list')
test_view('apps.laboratory.views', 'qc_dashboard_view', 'qc_dashboard')
test_view('apps.laboratory.views', 'sendout_list_view', 'sendout_list')
test_view('apps.laboratory.views', 'culture_list_view', 'culture_list')
test_view('apps.laboratory.views', 'histopath_list_view', 'histopath_list')
test_view('apps.laboratory.views', 'tat_report_view', 'tat_report')
test_view('apps.laboratory.views', 'antibiogram_view', 'antibiogram')
test_view('apps.laboratory.views', 'unacknowledged_results_view', 'unacknowledged')
test_view('apps.laboratory.views', 'lab_stats_view', 'stats')
test_view('apps.laboratory.views', 'staff_throughput_view', 'staff_throughput')

print()
print("DONE")
'''

# Upload and run
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS)

sftp = ssh.open_sftp()
with sftp.open('/opt/ehr-africa/_audit.py', 'w') as f:
    f.write(REMOTE_SCRIPT)
sftp.close()

stdin, stdout, stderr = ssh.exec_command(
    'cd /opt/ehr-africa && /opt/ehr-africa/venv/bin/python _audit.py 2>&1'
)
print(stdout.read().decode())
err = stderr.read().decode()
if err:
    print("STDERR:", err[-500:])

# Cleanup
ssh.exec_command('rm /opt/ehr-africa/_audit.py')
ssh.close()
