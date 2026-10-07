"""Check Boyomo Brandon payment status for low vision exam."""
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.base')
import sys; sys.path.insert(0, os.path.dirname(__file__))
django.setup()

from apps.patients.models import Patient
from apps.billing.models import Invoice, InvoiceItem, InvoiceStatus
from apps.investigations.models import InvestigationOrder
from django.utils import timezone

ps = Patient.objects.filter(first_name__icontains='boyomo') | Patient.objects.filter(last_name__icontains='boyomo')
if not ps.exists():
    ps = Patient.objects.filter(first_name__icontains='brandon') | Patient.objects.filter(last_name__icontains='brandon')

today = timezone.localdate()
for p in ps:
    print(f'Patient: {p.full_name} (ID: {p.patient_id})')
    invs = Invoice.objects.filter(patient=p, issue_date=today, is_deleted=False)
    for inv in invs:
        print(f'  Invoice {inv.id} status={inv.status}')
        for it in InvoiceItem.objects.filter(invoice=inv, is_deleted=False):
            print(f'    {it.description} | cat={it.category} | {it.unit_price} FCFA')

    paid_descs = set()
    for pi in Invoice.objects.filter(patient=p, issue_date=today, status='PAID', is_deleted=False):
        for it in InvoiceItem.objects.filter(invoice=pi, is_deleted=False):
            paid_descs.add(f'{it.description} [cat={it.category}]')
    print(f'  ALL paid items today: {paid_descs or "NONE"}')

    has_lv = any('low vision' in d.lower() for d in paid_descs)
    has_refrac = any('refraction' in d.lower() or 'optometry' in d.lower() for d in paid_descs)
    print(f'  Has "low vision" in paid: {has_lv}')
    print(f'  Has "refraction/optometry" fee in paid: {has_refrac}')

    orders = InvestigationOrder.objects.filter(patient=p, created_at__date=today)
    for o in orders:
        print(f'  Order: {o.investigation_type.name} (cat={o.investigation_type.category}) | status={o.status} | payment={o.payment_status}')
    print()
