"""Check controlled drug register table."""
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.base')
import django
django.setup()

from django.db import connection
cur = connection.cursor()
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'pharmacy_controlleddrugentry' ORDER BY ordinal_position")
cols = [r[0] for r in cur.fetchall()]
if cols:
    print('Table exists with columns:', cols)
else:
    print('TABLE MISSING: pharmacy_controlleddrugentry')

from apps.pharmacy.models import ControlledDrugEntry
try:
    print('Entry count:', ControlledDrugEntry.objects.count())
except Exception as e:
    print('Query error:', e)
