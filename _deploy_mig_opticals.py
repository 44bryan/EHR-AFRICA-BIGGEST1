import paramiko, zipfile, io, os, sys, time

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'
APP_DIR = '/opt/ehr-africa'

files = ['apps/opticals/migrations/0013_add_updated_by_audit_fields.py']

buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
    for f in files:
        arc = f.replace('\\', '/')
        zf.write(f, arc)
        print('  Added:', f)
buf.seek(0)

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS, timeout=20)

sftp = ssh.open_sftp()
sftp.putfo(buf, '/tmp/deploy_mig.zip')
sftp.close()
print('Uploaded.')

cmds = [
    'cd /opt/ehr-africa && unzip -o /tmp/deploy_mig.zip 2>&1',
    'cd /opt/ehr-africa && source venv/bin/activate && python manage.py migrate opticals 2>&1',
]
for cmd in cmds:
    _, out, err = ssh.exec_command(cmd, timeout=30)
    time.sleep(6)
    o = out.read()
    e = err.read()
    if o: sys.stdout.buffer.write(o)
    if e: sys.stdout.buffer.write(e)

ssh.close()
print('Done.')
