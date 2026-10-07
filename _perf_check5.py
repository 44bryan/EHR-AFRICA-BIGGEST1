import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.30.169', username='grudd420', password='123456', timeout=10)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=20)
    return stdout.read().decode(errors='replace').strip()

# Page sizes (HTML only)
print("=== HTML PAGE SIZES ===")
for url in ['/accounts/login/', '/billing/', '/billing/invoices/']:
    result = run(f'curl -s -o /tmp/page.html http://127.0.0.1:8000{url} && wc -c /tmp/page.html && wc -l /tmp/page.html')
    print(f"  {url}: {result}")

# Check what external resources the base template loads
print("\n=== BASE TEMPLATE RESOURCES ===")
print(run("grep -E 'href=.*cdn|src=.*cdn|googleapis|jsdelivr|cloudflare|fonts.google' /opt/ehr-africa/templates/layouts/base_authenticated.html 2>/dev/null | head -20"))

# Check main.js size
print("\n=== JS/CSS SIZES ===")
print(run("ls -lh /opt/ehr-africa/staticfiles/js/ 2>/dev/null"))
print(run("ls -lh /opt/ehr-africa/staticfiles/css/ 2>/dev/null"))
print(run("ls -lh /opt/ehr-africa/staticfiles/vendor/ 2>/dev/null"))
print(run("ls -lh /opt/ehr-africa/static/js/main.js 2>/dev/null"))
print(run("ls -lh /opt/ehr-africa/static/css/ 2>/dev/null"))

# Nginx gzip check on dynamic content
print("\n=== GZIP ON DYNAMIC PAGES ===")
result = run('curl -s -H "Accept-Encoding: gzip" -o /dev/null -w "size_download: %{size_download}, content_type: %{content_type}" http://127.0.0.1:8000/accounts/login/')
print(f"  Without Nginx: {result}")
result = run('curl -s -H "Accept-Encoding: gzip" -o /dev/null -w "size_download: %{size_download}, content_type: %{content_type}" http://192.168.30.169/accounts/login/')
print(f"  Through Nginx: {result}")

# Check if there's a main.js and what it loads
print("\n=== MAIN.JS ===")
print(run("wc -c /opt/ehr-africa/static/js/main.js 2>/dev/null"))
print(run("head -5 /opt/ehr-africa/static/js/main.js 2>/dev/null"))

ssh.close()
