"""
Backfill diagnosis_re, diagnosis_le, diagnosis_general from existing diagnosis_summary.
Parses patterns like:
  "RE: Glaucoma | LE: Dry eye"
  "RE: Cataract, LE: Pterygium"
  "Mature Cataract"  (no RE/LE prefix → goes to diagnosis_general)
"""
import os, re, django
os.environ["DJANGO_SETTINGS_MODULE"] = "ehr_project.settings.base"
django.setup()

from apps.consultations.models import Consultation

qs = Consultation.objects.filter(is_deleted=False).exclude(diagnosis_summary='')
total = qs.count()
updated = 0

for c in qs.iterator():
    if c.diagnosis_re or c.diagnosis_le or c.diagnosis_general:
        continue  # already has structured data

    raw = c.diagnosis_summary.strip()
    dx_re = ''
    dx_le = ''
    dx_gen = ''

    # Try to parse "RE: ... | LE: ... | Gen: ..."
    # Split by | or common separators between eye sections
    has_re = bool(re.search(r'\bRE:', raw, re.IGNORECASE))
    has_le = bool(re.search(r'\bLE:', raw, re.IGNORECASE))

    if has_re or has_le:
        # Split into sections by RE:/LE:/Gen: markers
        parts = re.split(r'\s*\|\s*', raw)
        for part in parts:
            part = part.strip()
            if re.match(r'^RE:\s*', part, re.IGNORECASE):
                dx_re = re.sub(r'^RE:\s*', '', part, flags=re.IGNORECASE).strip().rstrip(',')
            elif re.match(r'^LE:\s*', part, re.IGNORECASE):
                dx_le = re.sub(r'^LE:\s*', '', part, flags=re.IGNORECASE).strip().rstrip(',')
            elif re.match(r'^(Gen|General):\s*', part, re.IGNORECASE):
                dx_gen = re.sub(r'^(Gen|General):\s*', '', part, flags=re.IGNORECASE).strip().rstrip(',')
            else:
                # No prefix — might be general or part of previous
                if not dx_gen:
                    dx_gen = part.rstrip(',')
    else:
        # No RE/LE markers — put everything in general
        dx_gen = raw.rstrip(',')

    c.diagnosis_re = dx_re[:255]
    c.diagnosis_le = dx_le[:255]
    c.diagnosis_general = dx_gen[:255]
    c.save(update_fields=['diagnosis_re', 'diagnosis_le', 'diagnosis_general'])
    updated += 1

print(f"Backfilled {updated} / {total} consultations")
