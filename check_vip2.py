import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.production')
sys.path.insert(0, '/opt/ehr-africa')
django.setup()

from django.utils import timezone
from apps.qms.models import QueueToken, TokenStatus, ServiceType

today = timezone.localdate()

# Check enum values
print("ServiceType.CASHIER value:", ServiceType.CASHIER.value if hasattr(ServiceType.CASHIER, 'value') else repr(ServiceType.CASHIER))
print("TokenStatus.WAITING value:", TokenStatus.WAITING.value if hasattr(TokenStatus.WAITING, 'value') else repr(TokenStatus.WAITING))

# Raw DB check
from django.db import connection
with connection.cursor() as c:
    c.execute("SELECT token_number, service_type, service_tier, status, token_date FROM qms_queuetoken WHERE status='WAITING'")
    rows = c.fetchall()
    print("Raw DB rows (status=WAITING):", len(rows))
    for r in rows:
        print(" ", r)

# Try the exact dashboard filter
qs = QueueToken.objects.filter(
    service_type='CASHIER',
    status=TokenStatus.WAITING,
    token_date=today,
    is_deleted=False,
)
print("Dashboard filter count:", qs.count())

# Try with enum
qs2 = QueueToken.objects.filter(
    service_type=ServiceType.CASHIER,
    status=TokenStatus.WAITING,
    token_date=today,
    is_deleted=False,
)
print("Dashboard filter with enum count:", qs2.count())

# Check token_date type
t = QueueToken.objects.filter(status=TokenStatus.WAITING).first()
if t:
    print("token_date type:", type(t.token_date), "value:", t.token_date, "today:", today, "match:", t.token_date == today)
