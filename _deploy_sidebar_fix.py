import paramiko, time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.30.169', username='grudd420', password='123456', timeout=10)

def run(cmd, sudo=False, timeout=30):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    if sudo:
        stdin.write('123456\n')
        stdin.flush()
    return stdout.read().decode(errors='replace').strip(), stderr.read().decode(errors='replace').strip()

# Upload sidebar
print('Uploading sidebar.html...')
sftp = ssh.open_sftp()
sftp.put(
    r'c:\Users\GROD\Desktop\EHR AFRICA BACKUP\templates\components\sidebar.html',
    '/opt/ehr-africa/templates/components/sidebar.html'
)
sftp.close()
print('Uploaded.')

# Restart gunicorn to clear template cache
print('Restarting gunicorn...')
run('sudo -S pkill -f gunicorn 2>&1', sudo=True)
time.sleep(5)
pids, _ = run('pgrep -f gunicorn')
if not pids:
    time.sleep(3)
    pids, _ = run('pgrep -f gunicorn')
print(f'Gunicorn PIDs: {pids.split(chr(10))[0]}...' if pids else 'WAITING...')

# Login and test a few pages as admin
print('\nLogging in as admin...')
run('curl -s -c /tmp/ehr.jar http://127.0.0.1:8000/accounts/login/ -o /tmp/login.html')
csrf, _ = run("""grep csrfmiddlewaretoken /tmp/login.html | head -1 | sed 's/.*value="//' | sed 's/".*//' """)
run(
    f'curl -s -c /tmp/ehr.jar -b /tmp/ehr.jar '
    f'-d "csrfmiddlewaretoken={csrf}&username=admin&password=Admin2026" '
    f'-H "Referer: http://127.0.0.1:8000/accounts/login/" '
    f'-o /dev/null http://127.0.0.1:8000/accounts/login/'
)
code, _ = run('curl -s -b /tmp/ehr.jar -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/patients/')
print(f'Auth: {"OK" if code == "200" else "FAILED (" + code + ")"}')

# Test key pages
test_pages = {
    "Dashboard":          "/dashboard/home/",
    "Patients":           "/patients/",
    "Billing":            "/billing/",
    "Investigations":     "/investigations/",
    "Pharmacy":           "/pharmacy/",
    "Opticals":           "/opticals/",
    "Consultations":      "/consultations/",
    "IPD":                "/ipd/",
    "Laboratory":         "/laboratory/",
    "HMO":                "/hmo/",
    "Appointments":       "/appointments/",
}

print(f'\nQuick health check ({len(test_pages)} pages):')
for name, url in test_pages.items():
    code, _ = run(f'curl -s -b /tmp/ehr.jar -o /dev/null -w "%{{http_code}}" http://127.0.0.1:8000{url}')
    status = "OK" if code == "200" else f"HTTP {code}"
    print(f'  [{status:>4s}] {name}')

print('\nDone. Sidebar deployed and cache cleared.')
ssh.close()
