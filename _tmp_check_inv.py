
import os, sys, django
sys.path.insert(0, '/opt/ehr-africa')
os.environ['DJANGO_SETTINGS_MODULE'] = 'ehr_project.settings.base'
django.setup()
from apps.billing.models import ServiceWorkOrder
from apps.investigations.models import InvestigationOrder
print('=== ServiceWorkOrders (INVESTIGATION) ===')
wos = ServiceWorkOrder.objects.filter(category='INVESTIGATION', is_deleted=False).order_by('-created_at')[:10]
for wo in wos:
    cid = str(wo.consultation_id)[:8] if wo.consultation_id else 'None'
    print(f'  {str(wo.pk)[:8]} | {wo.patient.patient_id} | status={wo.status} | consult={cid}')
    print(f'    desc: {wo.description[:80]}')

print()
print('=== Recent InvestigationOrders ===')
orders = InvestigationOrder.objects.filter(is_deleted=False).order_by('-created_at')[:5]
for o in orders:
    print(f'  {str(o.pk)[:8]} | {o.patient.patient_id} | {o.investigation_type.name}')
    print(f'    status={o.status} pay={o.payment_status} acq={o.acquisition_status} assigned={o.assigned_to}')
