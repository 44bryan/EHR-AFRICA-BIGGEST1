import os, django
os.environ["DJANGO_SETTINGS_MODULE"] = "ehr_project.settings.base"
django.setup()
from apps.consultations.models import Consultation

total = Consultation.objects.filter(is_deleted=False).count()
with_dx = Consultation.objects.filter(is_deleted=False).exclude(diagnosis_summary="").count()
print(f"Total consultations: {total}")
print(f"With diagnosis_summary: {with_dx}")

patients_with = Consultation.objects.filter(is_deleted=False).exclude(diagnosis_summary="").values("patient_id").distinct().count()
total_patients = Consultation.objects.filter(is_deleted=False).values("patient_id").distinct().count()
print(f"Patients with dx_summary: {patients_with} / {total_patients}")

pids = list(Consultation.objects.filter(is_deleted=False).exclude(diagnosis_summary="").values_list("patient__patient_id", "diagnosis_summary").distinct()[:15])
print("\nPatients WITH diagnosis_summary:")
for pid, dx in pids:
    print(f"  {pid}: {dx}")

recent_empty = list(Consultation.objects.filter(is_deleted=False, diagnosis_summary="").order_by("-consultation_date").values_list("patient__patient_id", "status", "consultation_date")[:10])
print(f"\nRecent consultations WITHOUT dx_summary:")
for pid, status, dt in recent_empty:
    print(f"  {pid} - {status} - {dt}")
