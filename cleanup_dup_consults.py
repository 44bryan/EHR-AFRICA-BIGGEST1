"""
Find and soft-delete duplicate IN_PROGRESS consultations where a COMPLETED
consultation already exists for the same visit+doctor.
Run on server: python cleanup_dup_consults.py
"""
import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.production')
sys.path.insert(0, '/opt/ehr-africa')
django.setup()

from apps.consultations.models import Consultation, ConsultationStatus
from django.db.models import Count

# Find visits that have both IN_PROGRESS and COMPLETED consultations
from django.db.models import Q

visits_with_dupes = (
    Consultation.objects
    .filter(is_deleted=False)
    .values('visit', 'consulting_doctor')
    .annotate(n=Count('id'))
    .filter(n__gt=1)
)

print(f'Visit+doctor combos with multiple consultations: {visits_with_dupes.count()}')

deleted = 0
for row in visits_with_dupes:
    visit_id = row['visit']
    doctor_id = row['consulting_doctor']

    all_c = list(
        Consultation.objects.filter(
            visit_id=visit_id,
            consulting_doctor_id=doctor_id,
            is_deleted=False,
        ).order_by('created_at')
    )

    if len(all_c) <= 1:
        continue

    # Keep the COMPLETED/REFERRED one; if none, keep the latest
    completed = [c for c in all_c if c.status in (
        ConsultationStatus.COMPLETED, ConsultationStatus.REFERRED
    )]
    in_progress = [c for c in all_c if c.status == ConsultationStatus.IN_PROGRESS]

    if completed and in_progress:
        for dup in in_progress:
            print(f'  Soft-deleting IN_PROGRESS {dup.pk} (patient: {dup.patient}, kept COMPLETED {completed[0].pk})')
            dup.is_deleted = True
            dup.save(update_fields=['is_deleted'])
            deleted += 1
    elif len(all_c) > 1:
        # No COMPLETED — keep the newest, soft-delete the rest
        keep = all_c[-1]
        for dup in all_c[:-1]:
            print(f'  Soft-deleting older duplicate {dup.pk} (status={dup.status}, keeping {keep.pk})')
            dup.is_deleted = True
            dup.save(update_fields=['is_deleted'])
            deleted += 1

print(f'\nDone — {deleted} duplicate consultations soft-deleted.')
