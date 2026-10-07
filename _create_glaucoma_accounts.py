import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.30.169', username='grudd420', password='123456', timeout=10)

# Upload the creation script
sftp = ssh.open_sftp()
with sftp.open('/tmp/create_glaucoma.py', 'w') as f:
    f.write("""
import django, os
os.environ['DJANGO_SETTINGS_MODULE'] = 'ehr_project.settings.production'
django.setup()
from apps.accounts.models import User, UserRole, ConsultationUnit

accounts = [
    ('dr.glaucoma1', 'Glaucoma', 'Doctor 1', 'glaucoma1@ehrafrica.com'),
    ('dr.glaucoma2', 'Glaucoma', 'Doctor 2', 'glaucoma2@ehrafrica.com'),
]

for username, first, last, email in accounts:
    u, created = User.objects.get_or_create(username=username, defaults={
        'first_name': first,
        'last_name': last,
        'email': email,
        'role': UserRole.GLAUCOMA_SPECIALIST,
        'consultation_unit': ConsultationUnit.GENERAL,
        'is_active': True,
    })
    if created:
        u.set_password('Glaucoma2026')
        u.save()
        print(f'CREATED: {u.username} | {u.first_name} {u.last_name} | Role: {u.role}')
    else:
        print(f'EXISTS:  {u.username} | {u.first_name} {u.last_name} | Role: {u.role}')

print('Done.')
""")
sftp.close()

stdin, stdout, stderr = ssh.exec_command(
    'cd /opt/ehr-africa && source venv/bin/activate && python /tmp/create_glaucoma.py',
    timeout=20
)
print(stdout.read().decode(errors='replace').strip())
err = stderr.read().decode(errors='replace').strip()
if err:
    print('ERR:', err[:500])

ssh.close()
