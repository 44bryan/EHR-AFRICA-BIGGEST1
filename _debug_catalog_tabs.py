"""Debug: check why catalog tabs are empty on cashier POS"""
import paramiko

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'
APP  = '/opt/ehr-africa'

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS)

sftp = ssh.open_sftp()
sftp.put(r'c:\Users\GROD\Desktop\EHR AFRICA BACKUP\_dbg_tabs_remote.py', '/tmp/_dbg_tabs.py')
sftp.close()

def run(cmd):
    _, out, err = ssh.exec_command(cmd)
    o = out.read().decode().strip()
    e = err.read().decode().strip()
    if o: print(o)
    if e: print('[ERR]', e)
    return o

print('--- Catalog tab debug ---')
run('cd /opt/ehr-africa && source venv/bin/activate && python /tmp/_dbg_tabs.py')

ssh.close()
