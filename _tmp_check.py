
import sys
sys.path.insert(0, '/opt/ehr-africa')
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.production')
django.setup()

from apps.accounts.models import User
from apps.qms.models import ServiceCounter

roles = ['optometrist', 'pediatric_refractionist']
for u in User.objects.filter(role__in=roles, is_active=True).select_related('department'):
    dc = u.department.code if u.department else 'NO_DEPT'
    tier = getattr(u, 'patient_tier', '') or ''
    cs = ServiceCounter.objects.filter(staff_assigned=u, is_active=True)
    cn = '; '.join(c.name + '[' + c.service_type + '] in=' + str(c.is_checked_in_today) for c in cs) or 'NO_COUNTER'
    print(u.username + ' | ' + u.role + ' | dept=' + dc + ' | tier=' + tier + ' | ' + cn)
