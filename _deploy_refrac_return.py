"""Deploy Return-to-Referring-Doctor feature + optic disc optgroups."""
import paramiko, os, time

HOST, PORT, USER, PASS = '192.168.30.169', 22, 'grudd420', '123456'
APP = '/opt/ehr-africa'

LOCAL = r'c:\Users\GROD\Desktop\EHR AFRICA BACKUP'

FILES = [
    ('apps/patients/models.py',                                  f'{APP}/apps/patients/models.py'),
    ('apps/patients/migrations/0034_visit_referring_doctor.py',  f'{APP}/apps/patients/migrations/0034_visit_referring_doctor.py'),
    ('apps/qms/views.py',                                        f'{APP}/apps/qms/views.py'),
    ('apps/consultations/views.py',                              f'{APP}/apps/consultations/views.py'),
    ('apps/consultations/urls.py',                               f'{APP}/apps/consultations/urls.py'),
    ('templates/consultations/workstation.html',                 f'{APP}/templates/consultations/workstation.html'),
    ('templates/consultations/clinical/_gen_oph_form.html',      f'{APP}/templates/consultations/clinical/_gen_oph_form.html'),
    ('templates/consultations/clinical/_gen_oph.html',           f'{APP}/templates/consultations/clinical/_gen_oph.html'),
    ('templates/consultations/clinical/_record_summary.html',    f'{APP}/templates/consultations/clinical/_record_summary.html'),
]

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, PORT, USER, PASS)
sftp = ssh.open_sftp()

print('Uploading files...')
for local_rel, remote in FILES:
    local_abs = os.path.join(LOCAL, local_rel.replace('/', os.sep))
    print(f'  {local_rel}')
    sftp.put(local_abs, remote)

sftp.close()
print('All files uploaded.')

def run(cmd):
    _, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if out: print(out)
    if err: print('[stderr]', err)

print('\nRunning migration...')
run(f'cd {APP} && source venv/bin/activate && python manage.py migrate patients 0034_visit_referring_doctor --settings=ehr_project.settings.production')

print('\nRestarting gunicorn...')
run('pkill -f gunicorn')
time.sleep(3)
run(f'pgrep -f gunicorn | head -5')

ssh.close()
print('\nDone.')
