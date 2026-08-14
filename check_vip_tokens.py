import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.production')
sys.path.insert(0, '/opt/ehr-africa')
django.setup()

from django.utils import timezone
from apps.qms.models import QueueToken, TokenStatus, ServiceType

today = timezone.localdate()
print("Today:", today)

tokens = QueueToken.objects.filter(service_type=ServiceType.CASHIER, token_date=today, is_deleted=False)
print("Total cashier tokens today:", tokens.count())
for t in tokens:
    print(f"  #{t.token_number} | {t.patient.full_name} | status={t.status} | tier={t.service_tier} | is_deleted={t.is_deleted}")

waiting = tokens.filter(status=TokenStatus.WAITING)
print("Waiting:", waiting.count())
print("WAITING value:", repr(TokenStatus.WAITING))
print("ServiceType.CASHIER:", repr(ServiceType.CASHIER))
