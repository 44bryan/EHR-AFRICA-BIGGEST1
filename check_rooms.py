import paramiko, sys

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'

script = """
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.production')
import sys; sys.path.insert(0, '/opt/ehr-africa')
django.setup()
from apps.departments.models import Department, ConsultationRoom

print('=== DEPARTMENTS ===')
for d in Department.objects.filter(is_active=True).order_by('name'):
    rooms = ConsultationRoom.objects.filter(department=d)
    print(f'  [{d.code}] {d.name} — {rooms.count()} room(s)')

print()
print('=== EXISTING ROOMS ===')
rooms = ConsultationRoom.objects.select_related('department','assigned_doctor').order_by('department__name','room_number')
if rooms.exists():
    for r in rooms:
        doc = f'Dr. {r.assigned_doctor.last_name}' if r.assigned_doctor else 'unassigned'
        print(f'  {r.department.name} | Room {r.room_number} | {r.label or ""} | Tier:{r.room_tier} | {doc} | active:{r.is_active}')
else:
    print('  No rooms configured yet.')
"""

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS)
sftp = ssh.open_sftp()
with sftp.open('/tmp/check_rooms.py', 'w') as f:
    f.write(script)
sftp.close()
_, stdout, stderr = ssh.exec_command('cd /opt/ehr-africa && /opt/ehr-africa/venv/bin/python /tmp/check_rooms.py')
stdout.channel.recv_exit_status()
out = stdout.read().decode('utf-8', errors='replace')
err = stderr.read().decode('utf-8', errors='replace')
sys.stdout.buffer.write(out.encode('utf-8', errors='replace'))
if err:
    sys.stdout.buffer.write(('ERR: ' + err + '\n').encode('utf-8', errors='replace'))
ssh.close()
