import os, django, re
os.environ["DJANGO_SETTINGS_MODULE"] = "ehr_project.settings.base"
django.setup()
from django.test import Client
from apps.accounts.models import User
from apps.consultations.models import Consultation

# Check backfill results
sample = Consultation.objects.filter(is_deleted=False).exclude(diagnosis_re='', diagnosis_le='', diagnosis_general='').values_list(
    'patient__patient_id', 'diagnosis_re', 'diagnosis_le', 'diagnosis_general'
)[:8]
print("=== BACKFILL RESULTS ===")
for pid, re_dx, le_dx, gen_dx in sample:
    print(f"  {pid}: RE={re_dx} | LE={le_dx} | Gen={gen_dx}")

# Check patient with RE/LE data
has_re_le = Consultation.objects.filter(is_deleted=False).exclude(diagnosis_re='').exclude(diagnosis_le='').first()
if has_re_le:
    test_pid = has_re_le.patient.patient_id
    print(f"\nTesting patient with both RE+LE: {test_pid}")
else:
    test_pid = 'EHR-2026-041473'
    print(f"\nNo patient with both RE+LE. Testing: {test_pid}")

c = Client()
c.force_login(User.objects.get(username='admin'))

# Patient detail
resp = c.get(f'/patients/{test_pid}/')
html = resp.content.decode()

print("\n=== PATIENT BANNER ===")
for label in ['RE:', 'LE:', 'Gen:']:
    idx = html.find(f'<strong style="color:#93c5fd;">{label}</strong>')
    if idx < 0:
        idx = html.find(f'<strong class="text-primary">{label}</strong>')  # RE uses class
    print(f"  {label} {'FOUND' if idx >= 0 else 'NOT FOUND'}")
    if idx >= 0:
        print(f"    {html[idx:idx+120]}")

print("\n=== QUICK VIEW CARD (should be REMOVED) ===")
idx = html.find('Latest Dx:')
print(f"  {'STILL EXISTS (bad)' if idx >= 0 else 'REMOVED (good)'}")

print("\n=== TIMELINE ===")
re_count = len(re.findall(r'<strong class="text-primary">RE:</strong>', html))
le_count = len(re.findall(r'<strong style="color:#dc2626;">LE:</strong>', html))
print(f"  RE labels: {re_count}, LE labels: {le_count}")

# Consultation create
resp2 = c.get(f'/consultations/new/{test_pid}/')
html2 = resp2.content.decode()
print("\n=== CONSULTATION CREATE FORM ===")
print(f"  diagnosis_re field: {'FOUND' if 'diagnosis_re' in html2 else 'NOT FOUND'}")
print(f"  diagnosis_le field: {'FOUND' if 'diagnosis_le' in html2 else 'NOT FOUND'}")
print(f"  diagnosis_general field: {'FOUND' if 'diagnosis_general' in html2 else 'NOT FOUND'}")
print(f"  Old vitals Dx removed: {'GOOD' if 'Dx:</strong>' not in html2 else 'STILL THERE'}")
print(f"  Right Eye label: {'FOUND' if 'Right Eye (RE)' in html2 else 'NOT FOUND'}")
