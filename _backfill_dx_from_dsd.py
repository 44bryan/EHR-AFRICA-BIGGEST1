"""
Re-backfill diagnosis_re and diagnosis_le from department_specific_data.
The Gen Oph form stores the REAL per-eye diagnosis in:
  department_specific_data.diagnosis_re
  department_specific_data.diagnosis_le
"""
import os, django
os.environ["DJANGO_SETTINGS_MODULE"] = "ehr_project.settings.base"
django.setup()

from apps.consultations.models import Consultation

updated = 0
for c in Consultation.objects.filter(is_deleted=False).iterator():
    dsd = c.department_specific_data or {}
    dsd_re = dsd.get('diagnosis_re', '').strip().rstrip(',')
    dsd_le = dsd.get('diagnosis_le', '').strip().rstrip(',')

    changed = False
    if dsd_re and c.diagnosis_re != dsd_re:
        c.diagnosis_re = dsd_re[:255]
        changed = True
    if dsd_le and c.diagnosis_le != dsd_le:
        c.diagnosis_le = dsd_le[:255]
        changed = True

    if changed:
        # Rebuild summary
        parts = []
        if c.diagnosis_re:
            parts.append('RE: ' + c.diagnosis_re)
        if c.diagnosis_le:
            parts.append('LE: ' + c.diagnosis_le)
        c.diagnosis_summary = ' | '.join(parts)
        c.save(update_fields=['diagnosis_re', 'diagnosis_le', 'diagnosis_summary'])
        updated += 1

print(f"Updated {updated} consultations from department_specific_data")

# Show sample
sample = Consultation.objects.filter(is_deleted=False).exclude(
    diagnosis_re='', diagnosis_le=''
).order_by('-consultation_date').values_list(
    'patient__patient_id', 'diagnosis_re', 'diagnosis_le'
)[:10]
for pid, re, le in sample:
    print(f"  {pid}: RE={re} | LE={le}")
