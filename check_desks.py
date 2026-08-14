import os, sys
sys.path.insert(0, '/opt/ehr-africa')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.production')
import django; django.setup()

from apps.patients.models import Patient, Visit, PatientConsent
from apps.qms.models import QueueToken
from apps.billing.models import Invoice, InvoiceItem, Payment

SEEDED = [
    ("Alphonse",   "Nkemdirim"),
    ("Celestine",  "Onana-Mengue"),
    ("Emmanuel",   "Nguele-Abomo"),
    ("Fatima",     "Oumarou"),
    ("Rodrigue",   "Tchamba"),
    ("Nadege",     "Essomba"),
    ("Paul-Eric",  "Talla-Nkembe"),
    ("Brigitte",   "Essama-Fouda"),
]

print("\n=== SOFT-DELETING ALL SEEDED PATIENTS FROM SYSTEM ===\n")

for fn, ln in SEEDED:
    for pat in Patient.objects.filter(first_name=fn, last_name=ln):
        name = pat.full_name
        pid  = pat.patient_id

        # Soft-delete all related data
        q = QueueToken.objects.filter(patient=pat, is_deleted=False).update(is_deleted=True)
        v = Visit.objects.filter(patient=pat, is_deleted=False).update(is_deleted=True)
        c = PatientConsent.objects.filter(patient=pat, is_deleted=False).update(is_deleted=True)

        # Soft-delete invoices and their items/payments
        inv_ids = Invoice.objects.filter(patient=pat, is_deleted=False).values_list('id', flat=True)
        InvoiceItem.objects.filter(invoice_id__in=inv_ids, is_deleted=False).update(is_deleted=True)
        Payment.objects.filter(invoice_id__in=inv_ids, is_deleted=False).update(is_deleted=True)
        inv = Invoice.objects.filter(patient=pat, is_deleted=False).update(is_deleted=True)

        # Finally soft-delete the patient
        pat.is_deleted = True
        pat.save(update_fields=['is_deleted'])

        print(f"  REMOVED {name} ({pid})")
        print(f"    tokens={q}  visits={v}  consents={c}  invoices={inv}")

print("\n=== DONE — All seeded patients invisible system-wide ===\n")
