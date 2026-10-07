
import sys; sys.path.insert(0, '/opt/ehr-africa')
import os; os.environ['DJANGO_SETTINGS_MODULE']='ehr_project.settings.base'
import django; django.setup()
from apps.billing.models import ServiceWorkOrder
from apps.investigations.models import InvestigationOrder

# ALL invest WOs for patient EHR-2026-039192
print('=== ALL WOs for patient EHR-2026-039192 ===')
wos = ServiceWorkOrder.objects.filter(patient__patient_id='EHR-2026-039192', is_deleted=False).order_by('-created_at')
for wo in wos:
    print(f'  cat={wo.category} | status={wo.status} | completed_at={wo.completed_at} | completed_by={wo.completed_by}')
    print(f'  desc: {wo.description[:80]}')
    print(f'  consult: {wo.consultation_id}')
    print()

# Check the investigation order
print('=== Investigation Order for that patient ===')
for o in InvestigationOrder.objects.filter(patient__patient_id='EHR-2026-039192', is_deleted=False):
    print(f'  type={o.investigation_type.name} | status={o.status} | pay={o.payment_status} | acq={o.acquisition_status}')
    print(f'  payment_authorized_by={o.payment_authorized_by} | payment_authorized_at={o.payment_authorized_at}')
