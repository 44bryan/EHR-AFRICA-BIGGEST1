import paramiko, time

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS, timeout=30)

def run(cmd):
    _, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode(errors='replace')
    err = stderr.read().decode(errors='replace')
    return out + err

# Check gunicorn status
status = run('systemctl is-active ehr-gunicorn')
print('ehr-gunicorn:', status.strip())

# Check migration applied
result = run('cd /opt/ehr-africa && source venv/bin/activate && python manage.py showmigrations billing | tail -10')
print('\nBilling migrations:')
print(result)

# Quick HTTP check
http = run('curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/accounts/login/')
print('HTTP status on /login:', http.strip())

ssh.close()
