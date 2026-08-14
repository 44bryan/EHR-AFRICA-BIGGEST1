"""
Create paid invoices for the 6 demo patients so triage button unlocks.
Run on server: python seed_pay_demo.py
"""
import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.production')
sys.path.insert(0, '/opt/ehr-africa')
django.setup()

from django.utils import timezone
from apps.patients.models import Patient
from apps.billing.models import Invoice, InvoiceItem, Payment

from apps.accounts.models import User
admin = User.objects.filter(is_superuser=True).first()
today = timezone.localdate()

phones = [
    '+237691000001', '+237691000002', '+237691000003',
    '+237691000004', '+237691000005', '+237691000006',
]

for phone in phones:
    p = Patient.objects.filter(phone_number=phone).first()
    if not p:
        print(f'Patient not found: {phone}')
        continue

    visit = p.visits.filter(visit_date__date=today, is_deleted=False).first()
    if not visit:
        print(f'No visit today for {p.full_name}')
        continue

    if Invoice.objects.filter(patient=p, issue_date=today, status='PAID', is_deleted=False).exists():
        print(f'Already paid: {p.full_name}')
        continue

    inv = Invoice(
        patient=p,
        consultation=None,
        service_tier=visit.service_tier,
        issue_date=today,
        status='DRAFT',
        created_by=admin,
    )
    inv.save()

    InvoiceItem.objects.create(
        invoice=inv,
        description='Consultation / Registration Fee',
        quantity=1,
        unit_price=5000,
        created_by=admin,
    )

    Payment.objects.create(
        invoice=inv,
        amount=5000,
        payment_method='CASH',
        received_by=admin,
    )

    inv.refresh_from_db()
    inv.update_status()
    inv.refresh_from_db()
    print(f'[{inv.status}] {inv.invoice_number} — {p.full_name} ({visit.service_tier}) — 5,000 FCFA')

print('\nDone — triage button now unlocked for all 6 patients.')
