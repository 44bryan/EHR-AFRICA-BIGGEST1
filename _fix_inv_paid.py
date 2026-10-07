
import sys; sys.path.insert(0, '/opt/ehr-africa')
import os; os.environ['DJANGO_SETTINGS_MODULE']='ehr_project.settings.base'
import django; django.setup()
from apps.investigations.models import InvestigationOrder, PaymentStatus
from django.utils import timezone

# Mark all today's UNPAID investigation orders as PAID
today = timezone.localdate()
unpaid = InvestigationOrder.objects.filter(
    payment_status=PaymentStatus.UNPAID,
    is_deleted=False,
    created_at__date=today,
)
count = unpaid.count()
unpaid.update(payment_status=PaymentStatus.PAID, payment_authorized_at=timezone.now())
print(f'Fixed {count} UNPAID investigation orders -> PAID')

# Also mark their ServiceWorkOrders as DONE
from apps.billing.models import ServiceWorkOrder, WorkOrderStatus
wo_count = ServiceWorkOrder.objects.filter(
    category='INVEST',
    status__in=['PENDING', 'PENDING_PAYMENT'],
    is_deleted=False,
    created_at__date=today,
).update(status='DONE', completed_at=timezone.now())
print(f'Fixed {wo_count} investigation WOs -> DONE')

# Verify
still_unpaid = InvestigationOrder.objects.filter(
    payment_status=PaymentStatus.UNPAID, is_deleted=False, created_at__date=today
).count()
print(f'Still UNPAID today: {still_unpaid}')
paid_today = InvestigationOrder.objects.filter(
    payment_status=PaymentStatus.PAID, is_deleted=False, created_at__date=today
).count()
print(f'PAID today: {paid_today}')
