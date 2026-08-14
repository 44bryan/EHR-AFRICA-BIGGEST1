import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.production')
sys.path.insert(0, '/opt/ehr-africa')
django.setup()

from apps.accounts.models import HospitalConfig
cfg = HospitalConfig.get()
print("module_qms:", cfg.module_qms)

# Check if _qms_active works
from apps.core.context_processors import qms_active
print("qms_active():", qms_active())

# Check cashier sessions open today
from django.utils import timezone
from apps.billing.models import CashierSession, SessionStatus
today = timezone.localdate()
sessions = CashierSession.objects.filter(status=SessionStatus.OPEN, opened_at__date=today, is_deleted=False).select_related('cash_desk', 'cashier')
print("Open cashier sessions today:", sessions.count())
for s in sessions:
    print(f"  {s.cashier.username} -> {s.cash_desk.name} | desk_type={s.cash_desk.desk_type} | tier={s.cash_desk.tier}")
