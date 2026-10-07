import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.30.169', username='grudd420', password='123456')
cmd = "cd /opt/ehr-africa && /opt/ehr-africa/venv/bin/python -c \"import django,os;os.environ['DJANGO_SETTINGS_MODULE']='ehr_project.settings.base';django.setup();from django.db import connection;c=connection.cursor();c.execute(\\\"SELECT column_name FROM information_schema.columns WHERE table_name='opticals_opticalrepair' ORDER BY ordinal_position\\\");[print(r[0]) for r in c.fetchall()]\""
stdin, stdout, stderr = ssh.exec_command(cmd)
print(stdout.read().decode())
err = stderr.read().decode()
if err:
    print("ERR:", err[-500:])
ssh.close()
