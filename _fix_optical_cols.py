import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.30.169', username='grudd420', password='123456')

# Direct SQL to add missing columns
sql_cmds = [
    "ALTER TABLE opticals_opticalrepair ADD COLUMN deleted_at timestamp with time zone NULL",
    "ALTER TABLE opticals_opticalwarranty ADD COLUMN deleted_at timestamp with time zone NULL",
]

for sql in sql_cmds:
    cmd = f'cd /opt/ehr-africa && /opt/ehr-africa/venv/bin/python manage.py dbshell <<< "{sql};" 2>&1'
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    print(f'SQL: {sql[:60]}...')
    if out: print(f'  OUT: {out}')
    if err and 'already exists' in err:
        print(f'  Already exists.')
    elif err:
        print(f'  ERR: {err[-200:]}')

ssh.close()
print('Done.')
