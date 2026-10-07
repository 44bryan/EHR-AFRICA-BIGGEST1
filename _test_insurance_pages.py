"""Quick test: verify all insurance + billing pages return HTTP 200 on production."""
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.30.169', username='grudd420', password='123456')

# Login to get session cookie
login_cmd = (
    "TOKEN=$(curl -s -c /tmp/c.txt http://127.0.0.1:8000/accounts/login/ "
    "| grep -oP '(?<=value=\")[a-zA-Z0-9]+' | head -1) && "
    "curl -s -c /tmp/c.txt -b /tmp/c.txt -L "
    "-d \"username=admin&password=Admin2026&csrfmiddlewaretoken=$TOKEN\" "
    "-H \"Referer: http://127.0.0.1:8000/accounts/login/\" "
    "-o /dev/null -w '%{http_code}' "
    "http://127.0.0.1:8000/accounts/login/"
)
stdin, stdout, stderr = ssh.exec_command(login_cmd)
print("Login:", stdout.read().decode().strip())

# Test pages
pages = [
    "/hmo/",
    "/hmo/schemes/",
    "/hmo/members/",
    "/hmo/pre-auth/",
    "/hmo/batches/",
    "/hmo/claims/",
    "/hmo/ledger/",
    "/hmo/aging/",
    "/billing/patient-financial-history/",
]

ok = 0
fail = 0
for page in pages:
    cmd = "curl -s -b /tmp/c.txt -o /dev/null -w '%{http_code}' http://127.0.0.1:8000" + page
    stdin, stdout, stderr = ssh.exec_command(cmd)
    code = stdout.read().decode().strip()
    if code == "200":
        print(f"  OK   {page}")
        ok += 1
    else:
        print(f"  FAIL {page} -> {code}")
        fail += 1

print(f"\n{ok}/{ok+fail} pages OK")

# Check GL accounts seeded
check_cmd = (
    "cd /opt/ehr-africa && /opt/ehr-africa/venv/bin/python manage.py shell -c "
    "\"from apps.billing.models import GLAccount; "
    "codes=['411000','412000','413000','658200']; "
    "[print(f'{c}: EXISTS' if GLAccount.objects.filter(code=c).exists() else f'{c}: MISSING') for c in codes]\""
)
stdin, stdout, stderr = ssh.exec_command(check_cmd)
out = stdout.read().decode().strip()
err = stderr.read().decode().strip()
if out:
    print("\nGL Accounts:")
    print(out)

ssh.close()
