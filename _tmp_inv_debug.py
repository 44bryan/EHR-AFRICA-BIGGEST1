
import sys; sys.path.insert(0, '/opt/ehr-africa')
import os; os.environ['DJANGO_SETTINGS_MODULE']='ehr_project.settings.base'
import django; django.setup()
from apps.billing.models import ServiceWorkOrder
from apps.investigations.models import InvestigationOrder
from django.utils import timezone
today = timezone.localdate()

# Investigation WOs today
print('=== Investigation ServiceWorkOrders (today) ===')
wos = ServiceWorkOrder.objects.filter(category='INVEST', created_at__date=today, is_deleted=False).order_by('-created_at')
print(f'Count: {wos.count()}')
for wo in wos[:10]:
    print(f'  {wo.patient.patient_id} | status={wo.status} | desc={wo.description[:70]}')

# Now check ALL invest WOs
print()
total_invest = ServiceWorkOrder.objects.filter(category='INVEST', is_deleted=False).count()
print(f'Total INVEST WOs all time: {total_invest}')
done_invest = ServiceWorkOrder.objects.filter(category='INVEST', is_deleted=False, status='DONE').count()
print(f'DONE INVEST WOs: {done_invest}')

# Recent investigation orders with payment info
print()
print('=== Recent Investigation Orders ===')
for o in InvestigationOrder.objects.filter(is_deleted=False, created_at__date=today).order_by('-created_at')[:8]:
    print(f'  {o.patient.patient_id} | {o.investigation_type.name} | pay={o.payment_status} | acq={o.acquisition_status} | assigned={o.assigned_to}')
