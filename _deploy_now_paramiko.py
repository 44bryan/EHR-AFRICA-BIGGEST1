import paramiko
import os
import time

# Connection details
HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'
REMOTE_BASE = '/opt/ehr-africa'

# Files to upload
files = [
    'apps/accounts/models.py',
    'apps/accounts/migrations/0040_add_procurement_officer_role.py',
    'apps/inventory/views.py',
    'apps/inventory/urls.py',
    'apps/inventory/gl_service.py',
    'apps/dashboard/views.py',
    'templates/components/sidebar.html',
    'templates/inventory/procurement_dashboard.html',
]

# Connect
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS)
sftp = ssh.open_sftp()


def ensure_remote_dir(sftp_client, remote_dir):
    """Ensure remote directory exists, creating parents as needed."""
    dirs_to_create = []
    current = remote_dir
    while current and current != '/':
        try:
            sftp_client.stat(current)
            break
        except FileNotFoundError:
            dirs_to_create.append(current)
            current = os.path.dirname(current)
    for d in reversed(dirs_to_create):
        print(f'  Creating directory: {d}')
        sftp_client.mkdir(d)


# Upload files
print('=== Uploading files ===')
for f in files:
    local_path = f
    remote_path = REMOTE_BASE + '/' + f
    remote_dir = os.path.dirname(remote_path)
    ensure_remote_dir(sftp, remote_dir)
    print(f'  {f} -> {remote_path}')
    sftp.put(local_path, remote_path)

sftp.close()
print('\n=== All files uploaded successfully ===')

# Run migrate
print('\n=== Running migrations ===')
cmd = 'cd /opt/ehr-africa && source venv/bin/activate && python manage.py migrate --settings=ehr_project.settings.production 2>&1'
stdin, stdout, stderr = ssh.exec_command(cmd)
output = stdout.read().decode()
print(output)
err = stderr.read().decode()
if err:
    print('STDERR:', err)

# Restart gunicorn
print('\n=== Restarting gunicorn ===')
stdin, stdout, stderr = ssh.exec_command('echo "123456" | sudo -S systemctl restart ehr-gunicorn 2>&1')
output = stdout.read().decode()
print(output if output else '(restart command sent)')
err = stderr.read().decode()
if err and 'password' not in err.lower():
    print('STDERR:', err)

# Verify new PIDs
time.sleep(3)
print('\n=== Verifying gunicorn PIDs ===')
stdin, stdout, stderr = ssh.exec_command('pgrep -f gunicorn')
output = stdout.read().decode()
print(f'Gunicorn PIDs:\n{output}')

ssh.close()
print('=== Deployment complete ===')
