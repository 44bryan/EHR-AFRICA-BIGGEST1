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

# Upload
print('Uploading fixes...')
sftp = ssh.open_sftp()
sftp.put('deploy_fixes.zip', '/tmp/deploy_fixes.zip')
sftp.close()

# Extract
out, _ = run('cd /opt/ehr-africa && unzip -o /tmp/deploy_fixes.zip 2>&1 | tail -5')
print(out)

# Restart gunicorn
print('\nRestarting gunicorn...')
run('sudo -S pkill -f gunicorn 2>&1', sudo=True)
time.sleep(5)
pids, _ = run('pgrep -f gunicorn')
print(f'New PIDs: {pids.split(chr(10))[0]}...' if pids else 'WAITING...')
if not pids:
    time.sleep(3)
    pids, _ = run('pgrep -f gunicorn')
    print(f'PIDs: {pids.split(chr(10))[0]}...' if pids else 'STILL NONE')

# Login and test all previously broken pages
print('\nLogging in...')
run('curl -s -c /tmp/ehr.jar http://127.0.0.1:8000/accounts/login/ -o /tmp/login.html')
csrf, _ = run("""grep csrfmiddlewaretoken /tmp/login.html | head -1 | sed 's/.*value="//' | sed 's/".*//' """)
run(
    f'curl -s -c /tmp/ehr.jar -b /tmp/ehr.jar '
    f'-d "csrfmiddlewaretoken={csrf}&username=admin&password=Admin2026" '
    f'-H "Referer: http://127.0.0.1:8000/accounts/login/" '
    f'-o /dev/null http://127.0.0.1:8000/accounts/login/'
)

broken_pages = {
    "Advances":          "/billing/advances/",
    "Cash Transfers":    "/billing/cash/transfers/",
    "Safe Balance":      "/billing/cash/safe/",
    "Variance Register": "/billing/reports/variance-register/",
    "Asset Disposals":   "/billing/assets/disposals/",
    "Surgery Revenue":   "/billing/reports/surgery-revenue/",
    "Revenue by Dept":   "/billing/reports/revenue-by-department/",
    "Donor Report":      "/billing/reports/donor/",
    "DSF Report":        "/billing/reports/dsf/",
    "Monthly Summary":   "/billing/reports/monthly-summary/",
    "Sr Accountant":     "/billing/dashboard/senior-accountant/",
}

print(f'\nTesting {len(broken_pages)} previously broken pages:\n')
fixed = 0
still_broken = []
for name, url in broken_pages.items():
    code, _ = run(f'curl -s -b /tmp/ehr.jar -o /dev/null -w "%{{http_code}}" http://127.0.0.1:8000{url}')
    if code == "200":
        fixed += 1
        print(f'  [OK]  {name:25s} {url}')
    else:
        still_broken.append((name, url, code))
        print(f'  [!!]  {name:25s} {url} -> {code}')

print(f'\n{"="*60}')
print(f'Fixed: {fixed}/{len(broken_pages)}')
if still_broken:
    print(f'Still broken: {len(still_broken)}')
    for name, url, code in still_broken:
        print(f'  {name}: {url} -> HTTP {code}')
else:
    print('ALL PAGES WORKING!')

ssh.close()
