"""Deploy: WebSocket live discount approval notification"""
import paramiko, zipfile, os, io, time

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'
APP  = '/opt/ehr-africa'

FILES = [
    'apps/billing/views.py',
    'templates/billing/cashier_pos.html',
]
BASE = r'c:\Users\GROD\Desktop\EHR AFRICA BACKUP'

buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
    for f in FILES:
        zf.write(os.path.join(BASE, f), f)
        print(f'  + {f}')
buf.seek(0)

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS)

sftp = ssh.open_sftp()
sftp.putfo(buf, '/tmp/deploy_ws_discount.zip')
sftp.close()

def run(cmd):
    _, out, err = ssh.exec_command(cmd)
    o = out.read().decode().strip()
    e = err.read().decode().strip()
    if o: print(o)
    if e: print('[ERR]', e)

run(f'cd {APP} && unzip -o /tmp/deploy_ws_discount.zip')
run(f'cd {APP} && source venv/bin/activate && python manage.py check 2>&1 | tail -3')

run('pkill -f gunicorn || true')
time.sleep(2)
run(f'cd {APP} && source venv/bin/activate && nohup gunicorn ehr_project.wsgi:application --bind 127.0.0.1:8000 --workers 4 --worker-class gevent --timeout 120 --daemon 2>/dev/null')
time.sleep(3)
run('pgrep -f gunicorn')
print('Done.')
