import paramiko, time

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS, timeout=30)

_, stdout, _ = ssh.exec_command('journalctl -u ehr-gunicorn -n 50 --no-pager -o short')
print(stdout.read().decode(errors='replace'))
ssh.close()
