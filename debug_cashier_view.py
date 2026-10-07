import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.production')
sys.path.insert(0, '/opt/ehr-africa')
django.setup()

from django.utils import timezone
from apps.core.context_processors import qms_active as _qms_active
from apps.billing.models import CashierShift, CashierSession, SessionStatus
from apps.accounts.models import User

today = timezone.localdate()
print("Today:", today)
print("QMS active:", _qms_active())

# Simulate as cashier01
try:
    user = User.objects.get(username='cashier01')
except User.DoesNotExist:
    cashiers = User.objects.filter(role='cashier')
    print("cashier01 not found, cashiers:", list(cashiers.values_list('username', flat=True)))
    user = cashiers.first()

if not user:
    print("No cashier found!")
    exit()

print("User:", user.username, "role:", user.role)

my_session = CashierSession.objects.filter(
    cashier=user, status=SessionStatus.OPEN,
    opened_at__date=today, is_deleted=False,
).select_related('cash_desk').first()

print("my_session:", my_session)
if my_session:
    print("  desk:", my_session.cash_desk.name)
    print("  desk_type:", my_session.cash_desk.desk_type)
    print("  desk.tier:", my_session.cash_desk.tier)

_desk_tier = None
if my_session and my_session.cash_desk.desk_type == 'TIER' and my_session.cash_desk.tier:
    _desk_tier = my_session.cash_desk.tier

print("_desk_tier:", _desk_tier)

if _qms_active():
    from apps.qms.models import QueueToken, TokenStatus
    _cq = QueueToken.objects.select_related('patient').filter(
        service_type='CASHIER',
        status=TokenStatus.WAITING,
        token_date=today,
        is_deleted=False,
    )
    print("Before tier filter:", _cq.count())
    if _desk_tier:
        _cq = _cq.filter(service_tier=_desk_tier)
    print("After tier filter:", _cq.count())
    cashier_queue = list(_cq.order_by('-priority', 'issued_at')[:20])
    print("cashier_queue length:", len(cashier_queue))
    for tok in cashier_queue:
        print(f"  Token #{tok.token_number} | {tok.patient.full_name if tok.patient else 'N/A'} | tier={tok.service_tier}")
else:
    print("QMS NOT ACTIVE — cashier_queue = []")
