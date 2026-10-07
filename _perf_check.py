import paramiko, time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.30.169', username='grudd420', password='123456', timeout=10)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=30)
    return stdout.read().decode().strip()

# 1. CPU / RAM / Load
print("=== SYSTEM RESOURCES ===")
print(run("uptime"))
print(run("free -h | head -3"))
print(run("nproc"))

# 2. Gunicorn config
print("\n=== GUNICORN CONFIG ===")
print(run("cat /etc/systemd/system/ehr-gunicorn.service"))

# 3. Gunicorn worker count
print("\n=== GUNICORN WORKERS ===")
print(run("pgrep -fa gunicorn | head -15"))

# 4. Nginx config
print("\n=== NGINX CONFIG ===")
print(run("cat /etc/nginx/sites-enabled/ehr-africa 2>/dev/null || cat /etc/nginx/sites-enabled/default 2>/dev/null | head -40"))

# 5. Database connection count
print("\n=== DB CONNECTIONS ===")
print(run("sudo -S bash -c 'echo 123456 | sudo -S -u postgres psql -c \"SELECT count(*) FROM pg_stat_activity WHERE datname=\\\"ehr_africa\\\";\" 2>/dev/null'"))

# 6. Response time test
print("\n=== RESPONSE TIMES ===")
for url in ['/accounts/login/', '/billing/', '/billing/reports/ap-aging/']:
    t1 = time.time()
    result = run(f'curl -s -o /dev/null -w "%{{http_code}} %{{time_total}}" -b "sessionid=fake" http://127.0.0.1:8000{url}')
    print(f"  {url}: {result}")

# 7. PostgreSQL slow queries
print("\n=== PG SETTINGS ===")
print(run("sudo -S bash -c 'echo 123456 | sudo -S -u postgres psql -c \"SHOW shared_buffers;\" 2>/dev/null'"))
print(run("sudo -S bash -c 'echo 123456 | sudo -S -u postgres psql -c \"SHOW work_mem;\" 2>/dev/null'"))
print(run("sudo -S bash -c 'echo 123456 | sudo -S -u postgres psql -c \"SHOW effective_cache_size;\" 2>/dev/null'"))

# 8. Disk I/O
print("\n=== DISK ===")
print(run("df -h /opt/ehr-africa"))

# 9. Django settings - DEBUG, caches
print("\n=== DJANGO ENV ===")
print(run("grep -E 'DEBUG|CACHE|CONN_MAX_AGE|CONN_HEALTH' /opt/ehr-africa/.env 2>/dev/null"))
print(run("grep -E 'DEBUG|CONN_MAX_AGE' /opt/ehr-africa/ehr_project/settings/base.py 2>/dev/null | head -5"))

ssh.close()
