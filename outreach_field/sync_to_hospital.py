"""
sync_to_hospital.py
───────────────────
Run this script when the field laptop is back on the hospital LAN.
It reads all local SQLite records and pushes them to the hospital server.

Usage:
    python outreach_field/sync_to_hospital.py
    python outreach_field/sync_to_hospital.py --server http://192.168.30.169
    python outreach_field/sync_to_hospital.py --dry-run
"""
import os, sys, json, argparse, uuid
from datetime import date
from pathlib import Path

# ── Setup Django with field settings ─────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'outreach_field.settings_field')

import django
django.setup()

from django.conf import settings
from apps.outreach.models import (
    OutreachActivity, OutreachPatient, OutreachExamination,
    OutreachReferral, OutreachRecord,
)

# ── Args ──────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description='Sync field outreach data to hospital server')
parser.add_argument('--server', default=getattr(settings, 'HOSPITAL_SERVER_URL',
                    'http://192.168.30.169'), help='Hospital server URL')
parser.add_argument('--token', default=getattr(settings, 'OUTREACH_SYNC_TOKEN', ''),
                    help='Sync bearer token')
parser.add_argument('--dry-run', action='store_true',
                    help='Show what would be synced without sending')
args = parser.parse_args()

DEVICE_ID    = getattr(settings, 'FIELD_DEVICE_ID', 'UNKNOWN-DEVICE')
DEVICE_LABEL = getattr(settings, 'FIELD_DEVICE_LABEL', 'Field Laptop')
SYNC_URL     = f"{args.server.rstrip('/')}/outreach/api/sync/"

print(f"\n{'='*60}")
print(f"  EHR Africa — Outreach Field Sync")
print(f"  Device  : {DEVICE_ID} ({DEVICE_LABEL})")
print(f"  Server  : {SYNC_URL}")
print(f"{'='*60}\n")

# ── Collect data ──────────────────────────────────────────────────────────────

def _str(v):
    return str(v) if v is not None else None

def _date(v):
    return str(v) if v else None

# Activities
activities_data = []
for a in OutreachActivity.objects.all():
    activities_data.append({
        'id': str(a.id),
        'title': a.title,
        'activity_type': a.activity_type,
        'status': a.status,
        'location_name': a.location_name,
        'region': a.region,
        'town': a.town,
        'gps_coordinates': a.gps_coordinates,
        'activity_date': _date(a.activity_date),
        'end_date': _date(a.end_date),
        'partner_org': a.partner_org,
        'sponsor': a.sponsor,
        'sponsor_amount': float(a.sponsor_amount),
        'budget_fcfa': float(a.budget_fcfa),
        'target_screened': a.target_screened,
        'objectives': a.objectives,
        'notes': a.notes,
    })

# Patients (unsynchronised)
patients_data = []
for pt in OutreachPatient.objects.filter(is_synced=False):
    patients_data.append({
        'id': str(pt.id),
        'activity_id': str(pt.activity_id),
        'outreach_patient_id': pt.outreach_patient_id,
        'first_name': pt.first_name,
        'last_name': pt.last_name,
        'date_of_birth': _date(pt.date_of_birth),
        'age_years': pt.age_years,
        'sex': pt.sex,
        'village': pt.village,
        'district': pt.district,
        'phone': pt.phone,
        'next_of_kin': pt.next_of_kin,
        'chief_complaint': pt.chief_complaint,
        'known_diabetic': pt.known_diabetic,
        'known_hypertensive': pt.known_hypertensive,
        'previous_eye_surgery': pt.previous_eye_surgery,
    })

# Examinations
exams_data = []
for ex in OutreachExamination.objects.filter(patient__is_synced=False):
    exams_data.append({
        'id': str(ex.id),
        'patient_id': str(ex.patient_id),
        'exam_date': _date(ex.exam_date),
        'va_re_distance': ex.va_re_distance,
        'va_le_distance': ex.va_le_distance,
        'va_re_distance_ph': ex.va_re_distance_ph,
        'va_le_distance_ph': ex.va_le_distance_ph,
        'va_re_distance_corrected': ex.va_re_distance_corrected,
        'va_le_distance_corrected': ex.va_le_distance_corrected,
        'va_re_near': ex.va_re_near,
        'va_le_near': ex.va_le_near,
        're_sphere': float(ex.re_sphere) if ex.re_sphere is not None else None,
        're_cylinder': float(ex.re_cylinder) if ex.re_cylinder is not None else None,
        're_axis': ex.re_axis,
        'le_sphere': float(ex.le_sphere) if ex.le_sphere is not None else None,
        'le_cylinder': float(ex.le_cylinder) if ex.le_cylinder is not None else None,
        'le_axis': ex.le_axis,
        'add_power': float(ex.add_power) if ex.add_power is not None else None,
        'glasses_dispensed': ex.glasses_dispensed,
        'iop_re': float(ex.iop_re) if ex.iop_re is not None else None,
        'iop_le': float(ex.iop_le) if ex.iop_le is not None else None,
        'iop_method': ex.iop_method,
        'ant_segment_re': ex.ant_segment_re,
        'ant_segment_le': ex.ant_segment_le,
        'post_segment_re': ex.post_segment_re,
        'post_segment_le': ex.post_segment_le,
        'diagnoses_re': ex.diagnoses_re,
        'diagnoses_le': ex.diagnoses_le,
        'medications_given': ex.medications_given,
        'surgery_performed': ex.surgery_performed,
        'surgery_type': ex.surgery_type,
        'needs_referral': ex.needs_referral,
        'referral_urgency': ex.referral_urgency,
        'referral_reason': ex.referral_reason,
        'clinical_notes': ex.clinical_notes,
    })

# Referrals
referrals_data = []
for ref in OutreachReferral.objects.filter(is_synced=False):
    referrals_data.append({
        'id': str(ref.id),
        'patient_id': str(ref.patient_id),
        'referral_code': ref.referral_code,
        'urgency': ref.urgency,
        'diagnosis': ref.diagnosis,
        'reason': ref.reason,
        'recommendations': ref.recommendations,
    })

# Daily aggregate records
records_data = []
for rec in OutreachRecord.objects.all():
    records_data.append({
        'activity_id': str(rec.activity_id),
        'record_date': _date(rec.record_date),
        'total_screened': rec.total_screened,
        'male_screened': rec.male_screened,
        'female_screened': rec.female_screened,
        'cataract': rec.cataract,
        'refractive_errors': rec.refractive_errors,
        'glaucoma_suspects': rec.glaucoma_suspects,
        'glasses_dispensed': rec.glasses_dispensed,
        'total_referred': rec.total_referred,
        'drugs_cost': float(rec.drugs_cost),
        'transport_cost': float(rec.transport_cost),
        'other_cost': float(rec.other_cost),
    })

# ── Summary ───────────────────────────────────────────────────────────────────
print(f"  Records to sync:")
print(f"    Activities  : {len(activities_data)}")
print(f"    Patients    : {len(patients_data)}")
print(f"    Examinations: {len(exams_data)}")
print(f"    Referrals   : {len(referrals_data)}")
print(f"    Daily records: {len(records_data)}")
print()

if len(patients_data) == 0 and len(exams_data) == 0:
    print("  Nothing new to sync. All records already synced.")
    sys.exit(0)

if args.dry_run:
    print("  [DRY RUN] No data sent to server.")
    sys.exit(0)

# ── Send ──────────────────────────────────────────────────────────────────────
payload = {
    'device_id': DEVICE_ID,
    'device_label': DEVICE_LABEL,
    'activities': activities_data,
    'patients': patients_data,
    'examinations': exams_data,
    'referrals': referrals_data,
    'records': records_data,
}

try:
    import urllib.request
    data    = json.dumps(payload).encode('utf-8')
    headers = {'Content-Type': 'application/json'}
    if args.token:
        headers['Authorization'] = f'Bearer {args.token}'

    req = urllib.request.Request(SYNC_URL, data=data, headers=headers, method='POST')
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode())
        print(f"  Server response: {result['status'].upper()}")
        print(f"  Sync ID: {result.get('sync_id', '—')}")
        c = result.get('created', {})
        print(f"  Created — Activities: {c.get('activities',0)}, Patients: {c.get('patients',0)}, "
              f"Exams: {c.get('examinations',0)}, Referrals: {c.get('referrals',0)}")
        if result.get('errors'):
            print(f"\n  Warnings:")
            for e in result['errors'][:10]:
                print(f"    - {e}")

        # Mark synced patients locally
        if result['status'] in ('ok', 'partial'):
            OutreachPatient.objects.filter(is_synced=False).update(is_synced=True)
            OutreachReferral.objects.filter(is_synced=False).update(is_synced=True)
            print(f"\n  Local records marked as synced.")

except Exception as e:
    print(f"\n  ERROR: Could not connect to {SYNC_URL}")
    print(f"  {e}")
    print(f"\n  Make sure the hospital server is reachable on the LAN.")
    sys.exit(1)

print(f"\n{'='*60}")
print(f"  Sync complete.")
print(f"{'='*60}\n")
