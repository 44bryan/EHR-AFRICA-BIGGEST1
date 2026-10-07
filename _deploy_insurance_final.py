"""Deploy all insurance + English + dropdown changes to production."""
import paramiko, os, zipfile, io, time

files = [
    'apps/billing/gl_service.py',
    'apps/billing/views.py',
    'apps/billing/migrations/0030_seed_insurance_gl_accounts.py',
    'apps/hmo/views.py',
    'apps/hmo/urls.py',
    'templates/hmo/insurance_ledger.html',
    'templates/hmo/insurance_aging.html',
    'templates/billing/patient_accounts.html',
    'templates/billing/reports/dsf.html',
    'templates/billing/journal_entry_form.html',
    'templates/billing/cashier_pos.html',
    'templates/billing/budget_annual_create.html',
    'templates/billing/proforma_create.html',
    'templates/inventory/stock_ledger.html',
    'templates/inventory/po_create.html',
    'templates/inventory/supplier_invoice_form.html',
    'templates/inventory/item_form.html',
    'templates/inventory/quotation_form.html',
    'templates/inventory/three_way_match_form.html',
    'templates/inventory/grn_form.html',
    'templates/inventory/store_location_form.html',
    'templates/inventory/store_location_list.html',
    'templates/opticals/create_order.html',
    'templates/patients/triage.html',
    'templates/components/sidebar.html',
    'templates/components/tom_select.html',
    'apps/inventory/models.py',
    'apps/inventory/views.py',
    'apps/inventory/gl_service.py',
    'templates/consultations/clinical/_gen_oph_form.html',
]

buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
    for f in files:
        if os.path.exists(f):
            zf.write(f)
        else:
            print(f"  SKIP: {f}")
buf.seek(0)
print(f"Zip: {buf.getbuffer().nbytes:,} bytes")

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.30.169', username='grudd420', password='123456')

sftp = ssh.open_sftp()
with sftp.file('/tmp/deploy_all.zip', 'wb') as remote:
    remote.write(buf.read())
sftp.close()
print("Uploaded")

cmds = [
    'cd /opt/ehr-africa && unzip -o /tmp/deploy_all.zip',
    'rm /tmp/deploy_all.zip',
    'echo 123456 | sudo -S systemctl restart ehr-gunicorn 2>&1',
]
for cmd in cmds:
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode().strip()
    if out and '[sudo]' not in out:
        print(out)

time.sleep(3)
stdin, stdout, stderr = ssh.exec_command('pgrep -c gunicorn')
count = stdout.read().decode().strip()
print(f"Gunicorn workers: {count}")

# Login
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
print(f"Login: {stdout.read().decode().strip()}")

pages = [
    '/hmo/', '/hmo/ledger/', '/hmo/aging/', '/hmo/schemes/', '/hmo/claims/',
    '/billing/patient-accounts/', '/billing/reports/dsf/',
    '/inventory/items/', '/inventory/items/create/',
    '/inventory/store-locations/',
]
ok = fail = 0
for page in pages:
    cmd = f"curl -s -b /tmp/c.txt -o /dev/null -w '%{{http_code}}' http://127.0.0.1:8000{page}"
    stdin, stdout, stderr = ssh.exec_command(cmd)
    code = stdout.read().decode().strip()
    if code == '200':
        print(f"  OK   {page}")
        ok += 1
    else:
        print(f"  FAIL {page} -> {code}")
        fail += 1

print(f"\n{ok}/{ok+fail} pages OK")
ssh.close()
print("DEPLOY COMPLETE")
