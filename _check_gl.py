import django, os, sys
sys.path.insert(0, '/opt/ehr-africa')
os.environ['DJANGO_SETTINGS_MODULE'] = 'ehr_project.settings.base'
django.setup()

from apps.billing.models import GLAccount, ServicePrice
from django.db import connection

cursor = connection.cursor()
cursor.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name='billing_serviceprice'
    AND column_name IN ('purchase_gl_account_id','stock_gl_account_id','stock_variation_gl_account_id')
""")
cols = [r[0] for r in cursor.fetchall()]

# Sample GL accounts
gl_sample = list(GLAccount.objects.filter(is_active=True).values('code','name')[:5])

print(f"GL Accounts in DB: {GLAccount.objects.filter(is_active=True).count()}")
print(f"Service Prices in DB: {ServicePrice.objects.filter(is_deleted=False).count()}")
print(f"ERP GL columns present: {cols}")
print(f"Sample GL accounts: {gl_sample}")

# Check if any service has purchase_gl linked
linked = ServicePrice.objects.filter(is_deleted=False, purchase_gl_account__isnull=False).count()
print(f"Services with Purchase GL linked: {linked}")
