import os, django
os.environ["DJANGO_SETTINGS_MODULE"] = "ehr_project.settings.base"
django.setup()
from apps.consultations.models import Consultation

# Show all consultations that have LE but not RE
missing_re = Consultation.objects.filter(
    is_deleted=False, diagnosis_re=''
).exclude(diagnosis_le='').values_list(
    'patient__patient_id', 'diagnosis_re', 'diagnosis_le', 'diagnosis_summary'
)[:10]
print("=== Have LE but MISSING RE ===")
for pid, re, le, s in missing_re:
    print(f"  {pid}: RE='{re}' | LE='{le}' | summary='{s}'")

# Show recent consultations with diagnosis data
recent = Consultation.objects.filter(is_deleted=False).exclude(
    diagnosis_re='', diagnosis_le=''
).order_by('-consultation_date').values_list(
    'patient__patient_id', 'diagnosis_re', 'diagnosis_le', 'diagnosis_summary'
)[:15]
print("\n=== Recent with RE or LE ===")
for pid, re, le, s in recent:
    print(f"  {pid}: RE='{re}' | LE='{le}'")

# Stats
both = Consultation.objects.filter(is_deleted=False).exclude(diagnosis_re='').exclude(diagnosis_le='').count()
only_re = Consultation.objects.filter(is_deleted=False, diagnosis_le='').exclude(diagnosis_re='').count()
only_le = Consultation.objects.filter(is_deleted=False, diagnosis_re='').exclude(diagnosis_le='').count()
print(f"\nBoth RE+LE: {both}, Only RE: {only_re}, Only LE: {only_le}")
