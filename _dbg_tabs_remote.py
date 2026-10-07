import sys, os
sys.path.insert(0, '/opt/ehr-africa')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.base')
import django; django.setup()

# Check what queue_url is set to in the two POS views
import subprocess
result = subprocess.run(
    ['grep', '-n', 'queue_url\|QUEUE_URL\|billing:dashboard\|dashboard:home', '/opt/ehr-africa/apps/billing/views.py'],
    capture_output=True, text=True
)
for line in result.stdout.splitlines():
    if 'queue_url' in line.lower() or 'billing:dashboard' in line.lower() or 'dashboard:home' in line.lower():
        print(line)
