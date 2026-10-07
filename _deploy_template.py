import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.30.169', username='grudd420', password='123456', timeout=10)

# Upload updated base.html
sftp = ssh.open_sftp()
sftp.put('templates/base.html', '/opt/ehr-africa/templates/base.html')
sftp.close()
print("base.html uploaded")

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=15)
    return stdout.read().decode(errors='replace').strip()

# Warm up
run('curl -s -o /dev/null http://127.0.0.1:8000/accounts/login/')
run('curl -s -o /dev/null http://127.0.0.1:8000/accounts/login/')

# Test response times (warm)
print("\n=== RESPONSE TIMES (warm, through Nginx) ===")
for i in range(5):
    result = run('curl -s -o /dev/null -w "%{http_code} %{time_total}s %{size_download}B" http://192.168.30.169/accounts/login/')
    print(f"  Request {i+1}: {result}")

# Test static file serving
print("\n=== STATIC FILE TIMES ===")
for path in ['/static/vendor/bootstrap/css/bootstrap.min.css', '/static/css/custom.css', '/static/js/vendor/chart.umd.min.js', '/static/vendor/htmx.min.js']:
    result = run(f'curl -s -o /dev/null -w "%{{http_code}} %{{time_total}}s %{{size_download}}B" http://192.168.30.169{path}')
    print(f"  {path}: {result}")

# Test gzip on HTML
print("\n=== GZIP COMPRESSION ===")
result_no_gz = run('curl -s -o /dev/null -w "%{size_download}" http://192.168.30.169/accounts/login/')
result_gz = run('curl -s -H "Accept-Encoding: gzip" -o /dev/null -w "%{size_download}" http://192.168.30.169/accounts/login/')
print(f"  HTML uncompressed: {result_no_gz} bytes")
print(f"  HTML gzipped: {result_gz} bytes")

# Test keepalive (multiple requests on same connection)
print("\n=== KEEPALIVE TEST (3 requests, 1 connection) ===")
result = run('curl -s -o /dev/null -o /dev/null -o /dev/null -w "total: %{time_total}s" http://192.168.30.169/accounts/login/ http://192.168.30.169/accounts/login/ http://192.168.30.169/accounts/login/')
print(f"  {result}")

ssh.close()
