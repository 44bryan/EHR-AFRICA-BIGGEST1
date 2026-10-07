import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.30.169', username='grudd420', password='123456', timeout=10)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=15)
    out = stdout.read().decode(errors='replace').strip()
    err = stderr.read().decode(errors='replace').strip()
    return out, err

# Check actual Django DEBUG value
out, err = run("cd /opt/ehr-africa && source venv/bin/activate && DJANGO_SETTINGS_MODULE=ehr_project.settings.production python -c \"from django.conf import settings; print('DEBUG:', settings.DEBUG); print('CACHES:', list(settings.CACHES.keys())); print('SESSION_ENGINE:', settings.SESSION_ENGINE); print('CONN_MAX_AGE:', settings.DATABASES['default'].get('CONN_MAX_AGE')); print('TEMPLATES cached:', 'cached' in str(settings.TEMPLATES))\"")
print("=== DJANGO RUNTIME CONFIG ===")
print(out)
if err:
    print("ERR:", err[:300])

# Check response times from localhost
print("\n=== RESPONSE TIMES (from server) ===")
for url in ['/accounts/login/', '/billing/', '/dashboard/']:
    out, _ = run('curl -s -o /dev/null -w "%{http_code} %{time_total}s" http://127.0.0.1:8000' + url)
    print(f"  {url} -> {out}")

# Check Nginx response times (through proxy)
print("\n=== NGINX PROXY TIMES ===")
for url in ['/accounts/login/', '/static/css/main.css']:
    out, _ = run('curl -s -o /dev/null -w "%{http_code} %{time_total}s" http://192.168.30.169' + url)
    print(f"  {url} -> {out}")

# Check if WhiteNoise middleware is in the chain
out, _ = run("cd /opt/ehr-africa && source venv/bin/activate && DJANGO_SETTINGS_MODULE=ehr_project.settings.production python -c \"from django.conf import settings; [print(m) for m in settings.MIDDLEWARE]\"")
print("\n=== MIDDLEWARE ===")
print(out)

ssh.close()
