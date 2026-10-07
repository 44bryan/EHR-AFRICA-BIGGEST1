import paramiko, time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.30.169', username='grudd420', password='123456', timeout=10)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=15)
    return stdout.read().decode().strip()

# Nginx config
print("=== NGINX ===")
print(run("ls /etc/nginx/sites-enabled/"))
print(run("cat /etc/nginx/sites-enabled/ehr 2>/dev/null || cat /etc/nginx/sites-enabled/ehr-africa 2>/dev/null || cat /etc/nginx/conf.d/ehr.conf 2>/dev/null || echo 'checking default...' && head -60 /etc/nginx/sites-enabled/default 2>/dev/null"))

# Django .env
print("\n=== .ENV ===")
print(run("cat /opt/ehr-africa/.env"))

# Django DATABASES setting
print("\n=== DB CONFIG ===")
print(run("grep -A5 'CONN_MAX_AGE\|DATABASES\|persistent' /opt/ehr-africa/ehr_project/settings/base.py 2>/dev/null | head -20"))
print(run("grep -A5 'CONN_MAX_AGE\|DATABASES' /opt/ehr-africa/ehr_project/settings/production.py 2>/dev/null | head -20"))

# Middleware
print("\n=== MIDDLEWARE ===")
print(run("grep -A20 'MIDDLEWARE' /opt/ehr-africa/ehr_project/settings/base.py | head -25"))

# Caching
print("\n=== CACHES ===")
print(run("grep -A10 'CACHES' /opt/ehr-africa/ehr_project/settings/base.py | head -15"))

# Response time
print("\n=== RESPONSE TIMES ===")
for url in ['/accounts/login/', '/billing/']:
    result = run(f'curl -s -o /dev/null -w "%{{http_code}} %{{time_total}}s" http://127.0.0.1:8000{url}')
    print(f"  {url} -> {result}")

ssh.close()
