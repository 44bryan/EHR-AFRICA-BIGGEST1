import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.30.169', username='grudd420', password='123456', timeout=10)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=20)
    return stdout.read().decode(errors='replace').strip()

# Warm up the server first
run('curl -s -o /dev/null http://127.0.0.1:8000/accounts/login/')

# Now test warmed-up response times
print("=== WARMED-UP RESPONSE TIMES ===")
for url in ['/accounts/login/', '/accounts/login/', '/accounts/login/']:
    result = run('curl -s -o /dev/null -w "%{http_code} %{time_total}s" http://127.0.0.1:8000' + url)
    print(f"  {url} -> {result}")

# Login and test authenticated pages
print("\n=== AUTHENTICATED PAGE TIMES ===")
# Login first to get a session cookie
login_cmd = """curl -s -c /tmp/ehr_cookies.txt -b /tmp/ehr_cookies.txt \
  http://127.0.0.1:8000/accounts/login/ \
  -o /dev/null -w "%{http_code} %{time_total}s" """
print("  Login GET:", run(login_cmd))

# Get CSRF token and login
login_cmd2 = """CSRF=$(curl -s -c /tmp/ehr_cookies.txt -b /tmp/ehr_cookies.txt http://127.0.0.1:8000/accounts/login/ | grep csrfmiddlewaretoken | head -1 | sed "s/.*value='//" | sed "s/'.*//") && \
curl -s -c /tmp/ehr_cookies.txt -b /tmp/ehr_cookies.txt \
  -X POST http://127.0.0.1:8000/accounts/login/ \
  -d "csrfmiddlewaretoken=$CSRF&username=admin&password=Admin2026" \
  -H "Referer: http://127.0.0.1:8000/accounts/login/" \
  -o /dev/null -w "%{http_code} %{time_total}s" -L"""
print("  Login POST:", run(login_cmd2))

# Test authenticated pages
for url in ['/dashboard/', '/billing/', '/billing/invoices/', '/billing/reports/ap-aging/', '/billing/dashboard/finance-director/']:
    result = run(f'curl -s -b /tmp/ehr_cookies.txt -o /dev/null -w "%{{http_code}} %{{time_total}}s" -L http://127.0.0.1:8000{url}')
    print(f"  {url} -> {result}")

# Check static files
print("\n=== STATIC FILES ===")
print("  Staticfiles dir:", run("ls /opt/ehr-africa/staticfiles/ | head -10"))
print("  CSS files:", run("ls /opt/ehr-africa/staticfiles/css/ 2>/dev/null | head -5"))
print("  Total static:", run("find /opt/ehr-africa/staticfiles -type f | wc -l"))

# Check custom middleware source
print("\n=== CUSTOM MIDDLEWARE SIZE ===")
print("  middleware.py:", run("wc -l /opt/ehr-africa/apps/core/middleware.py"))
print("  multi_session:", run("wc -l /opt/ehr-africa/apps/core/multi_session_middleware.py"))

ssh.close()
