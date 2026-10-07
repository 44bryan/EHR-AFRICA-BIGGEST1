"""
Re-backfill: move diagnosis_general data into RE/LE fields.
- If text contains "LE" prefix → LE only
- If text contains "RE" prefix → RE only
- If text contains "Bil" or "bilateral" → both RE and LE
- Otherwise → both RE and LE (assume bilateral for ophthalmology)
Also parse old diagnosis_summary that had "RE:" and "LE:" patterns.
"""
import os, re, django
os.environ["DJANGO_SETTINGS_MODULE"] = "ehr_project.settings.base"
django.setup()

from apps.consultations.models import Consultation

# First: move diagnosis_general → RE/LE
qs_gen = Consultation.objects.filter(is_deleted=False).exclude(diagnosis_general='')
moved = 0
for c in qs_gen.iterator():
    gen = c.diagnosis_general.strip()
    if not gen:
        continue

    # Check if it starts with "LE " or "LE:" → left eye only
    if re.match(r'^LE\b', gen, re.IGNORECASE):
        clean = re.sub(r'^LE[\s:]+', '', gen, flags=re.IGNORECASE).strip()
        if not c.diagnosis_le:
            c.diagnosis_le = clean
    # Check if starts with "RE " or "RE:" → right eye only
    elif re.match(r'^RE\b', gen, re.IGNORECASE):
        clean = re.sub(r'^RE[\s:]+', '', gen, flags=re.IGNORECASE).strip()
        if not c.diagnosis_re:
            c.diagnosis_re = clean
    # Bilateral or no prefix → put in both
    else:
        if not c.diagnosis_re:
            c.diagnosis_re = gen
        if not c.diagnosis_le:
            c.diagnosis_le = gen

    c.diagnosis_general = ''
    # Rebuild summary
    parts = []
    if c.diagnosis_re:
        parts.append('RE: ' + c.diagnosis_re)
    if c.diagnosis_le:
        parts.append('LE: ' + c.diagnosis_le)
    c.diagnosis_summary = ' | '.join(parts)
    c.save(update_fields=['diagnosis_re', 'diagnosis_le', 'diagnosis_general', 'diagnosis_summary'])
    moved += 1

# Second: for records with only diagnosis_summary (no RE/LE fields), parse them
qs_legacy = Consultation.objects.filter(
    is_deleted=False, diagnosis_re='', diagnosis_le=''
).exclude(diagnosis_summary='')
parsed = 0
for c in qs_legacy.iterator():
    raw = c.diagnosis_summary.strip()
    if not raw:
        continue

    has_re = bool(re.search(r'\bRE:', raw, re.IGNORECASE))
    has_le = bool(re.search(r'\bLE:', raw, re.IGNORECASE))

    if has_re or has_le:
        parts = re.split(r'\s*\|\s*', raw)
        for part in parts:
            part = part.strip()
            if re.match(r'^RE:\s*', part, re.IGNORECASE):
                c.diagnosis_re = re.sub(r'^RE:\s*', '', part, flags=re.IGNORECASE).strip().rstrip(',')
            elif re.match(r'^LE:\s*', part, re.IGNORECASE):
                c.diagnosis_le = re.sub(r'^LE:\s*', '', part, flags=re.IGNORECASE).strip().rstrip(',')
    else:
        # No RE/LE markers — put in both eyes
        clean = raw.rstrip(',').strip()
        c.diagnosis_re = clean
        c.diagnosis_le = clean

    # Rebuild summary
    parts = []
    if c.diagnosis_re:
        parts.append('RE: ' + c.diagnosis_re)
    if c.diagnosis_le:
        parts.append('LE: ' + c.diagnosis_le)
    c.diagnosis_summary = ' | '.join(parts)
    c.save(update_fields=['diagnosis_re', 'diagnosis_le', 'diagnosis_general', 'diagnosis_summary'])
    parsed += 1

print(f"Moved from general: {moved}")
print(f"Parsed from legacy summary: {parsed}")

# Verify
total_re = Consultation.objects.filter(is_deleted=False).exclude(diagnosis_re='').count()
total_le = Consultation.objects.filter(is_deleted=False).exclude(diagnosis_le='').count()
still_gen = Consultation.objects.filter(is_deleted=False).exclude(diagnosis_general='').count()
print(f"Final: {total_re} with RE, {total_le} with LE, {still_gen} still in General")
