import os, django, traceback
os.environ['DJANGO_SETTINGS_MODULE'] = 'ehr_project.settings.production'
django.setup()
from apps.pharmacy.views import quick_reorder
from django.test import RequestFactory
from apps.accounts.models import User
u = User.objects.filter(role='SUPER_ADMIN').first()
rf = RequestFactory()
req = rf.get('/pharmacy/quick-reorder/')
req.user = u
req.session = {}
try:
    resp = quick_reorder(req)
    print('STATUS:', resp.status_code)
except Exception as e:
    traceback.print_exc()
