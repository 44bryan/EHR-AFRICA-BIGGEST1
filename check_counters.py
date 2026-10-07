import paramiko, sys

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'

script = """
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.production')
import sys; sys.path.insert(0, '/opt/ehr-africa')
django.setup()
from apps.qms.models import ServiceCounter

counters = ServiceCounter.objects.select_related('staff_assigned','zone').order_by('service_type','name')
print(f'Total counters: {counters.count()}')
print()
for c in counters:
    staff = c.staff_assigned.username if c.staff_assigned else 'unassigned'
    zone = c.zone.name if c.zone else 'no zone'
    print(f'  [{c.code}] {c.name} | type:{c.station_type} | service:{c.service_type} | tiers:{c.serves_tiers or "ALL"} | staff:{staff} | active:{c.is_active}')
"""

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS)
sftp = ssh.open_sftp()
with sftp.open('/tmp/check_counters.py', 'w') as f:
    f.write(script)
sftp.close()
_, stdout, stderr = ssh.exec_command('cd /opt/ehr-africa && /opt/ehr-africa/venv/bin/python /tmp/check_counters.py')
stdout.channel.recv_exit_status()
out = stdout.read().decode('utf-8', errors='replace')
err = stderr.read().decode('utf-8', errors='replace')
sys.stdout.buffer.write(out.encode('utf-8', errors='replace'))
if err:
    sys.stdout.buffer.write(('ERR: ' + err + '\n').encode('utf-8', errors='replace'))
ssh.close()
