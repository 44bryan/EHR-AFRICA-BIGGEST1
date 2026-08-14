"""
EHR Africa — Visit Tier & Billing Type Seed
============================================
Seeds realistic visits for the CURRENT month covering all service tiers
(Standard, Express, Fast Track, VIP) and billing types (Self Pay, Insurance,
HMO, Free), with consultations and diagnoses attached.

Designed to populate Monthly Statistics with meaningful numbers.

Run with:
    python manage.py shell < seed_visits_tiers.py
"""
import random
from decimal import Decimal
from datetime import date, timedelta
from django.utils import timezone
from django.db import transaction

random.seed(99)
TODAY = timezone.localdate()
MONTH_START = TODAY.replace(day=1)


def _random_complaint(dx_desc):
    templates = [
        "Blurred vision",
        "Eye pain and redness",
        "Gradual loss of vision",
        "Sudden visual disturbance",
        "Foreign body sensation",
        "Watering eyes",
        "Routine eye check",
        f"Known case of {dx_desc.lower()}",
        "Difficulty reading",
        "Flashes and floaters",
        "Double vision",
        "Eye discharge",
        "Headache with visual symptoms",
        "Follow-up after treatment",
        "Review of glasses prescription",
    ]
    return random.choice(templates)


print("=" * 65)
print("EHR AFRICA — Visit Tier & Billing Type Seed")
print(f"Seeding visits for {MONTH_START.strftime('%B %Y')}")
print("=" * 65)

# ─────────────────────────────────────────────────────────────────────────────
# IMPORTS
# ─────────────────────────────────────────────────────────────────────────────
from apps.accounts.models import User, UserRole
from apps.departments.models import Department
from apps.patients.models import Patient, Visit, ServiceTier, BillingType, VisitType, VisitStatus
from apps.consultations.models import (
    Consultation, ConsultationDiagnosis, ConsultationStatus, Diagnosis
)

# ─────────────────────────────────────────────────────────────────────────────
# LOAD RESOURCES
# ─────────────────────────────────────────────────────────────────────────────
print("\n[1/4] Loading existing resources...")

doctors = list(User.objects.filter(
    role__in=[
        UserRole.OPHTHALMOLOGIST, UserRole.RETINA_SPECIALIST, UserRole.GLAUCOMA_SPECIALIST,
        UserRole.CATARACT_SURGEON, UserRole.CORNEA_SPECIALIST, UserRole.PEDIATRIC_OPHTHALMOLOGIST,
        UserRole.OCULOPLASTICS_SURGEON, UserRole.NEURO_OPHTHALMOLOGIST, UserRole.UVEITIS_SPECIALIST,
        UserRole.OPTOMETRIST, UserRole.MEDICAL_DIRECTOR,
    ],
    is_active=True
))
if not doctors:
    doctors = list(User.objects.filter(is_superuser=True))
if not doctors:
    print("  ✗ No doctors found — cannot seed consultations. Create staff first.")
    raise SystemExit(1)

departments = list(Department.objects.filter(is_active=True))
if not departments:
    print("  ✗ No departments found — create departments first.")
    raise SystemExit(1)

patients = list(Patient.objects.filter(is_deleted=False, is_active=True))
if len(patients) < 10:
    print(f"  ✗ Only {len(patients)} patients found. Run seed_demo_300.py first.")
    raise SystemExit(1)

diagnoses = list(Diagnosis.objects.filter(is_active=True))
if not diagnoses:
    print("  ✗ No diagnoses found. Run seed_demo_300.py first to seed ICD-10 codes.")
    raise SystemExit(1)

print(f"  ✓ {len(doctors)} doctors, {len(departments)} departments")
print(f"  ✓ {len(patients)} patients, {len(diagnoses)} diagnoses")

# ─────────────────────────────────────────────────────────────────────────────
# DISTRIBUTION PLAN
# ─────────────────────────────────────────────────────────────────────────────
# Realistic eye hospital distribution for a month:
#   Standard:   55%  — regular OPD
#   Express:    20%  — paid premium queue
#   Fast Track: 15%  — priority (staff, elderly, referral)
#   VIP:        10%  — executive suite

# Billing type distribution:
#   Self Pay:  60%
#   Insurance: 20%
#   HMO:       12%
#   Free:       8%

# Visit type distribution:
#   New:        40%
#   Follow-up:  35%
#   Review:     12%
#   Procedure:   8%
#   Emergency:   5%

TIER_PLAN = [
    (ServiceTier.STANDARD,   55),
    (ServiceTier.EXPRESS,    20),
    (ServiceTier.FAST_TRACK, 15),
    (ServiceTier.VIP,        10),
]

BILLING_PLAN = [
    (BillingType.SELF_PAY,  60),
    (BillingType.INSURANCE, 20),
    (BillingType.HMO,       12),
    (BillingType.FREE,       8),
]

VISIT_TYPE_PLAN = [
    (VisitType.NEW,       40),
    (VisitType.FOLLOW_UP, 35),
    (VisitType.REVIEW,    12),
    (VisitType.PROCEDURE,  8),
    (VisitType.EMERGENCY,  5),
]

INSURANCE_COMPANIES = [
    "Saar Insurance", "Activa Assurances", "Chanas Assurances",
    "NSIA Cameroun", "Allianz Cameroun", "AXA Assurance",
    "Prudential Beneficial Life", "Beneficial Life Cameroon",
]
HMO_COMPANIES = [
    "CNPS (National Social Insurance Fund)", "BEAC Health Plan",
    "Total Energies Health Plan", "MTN Employee Health", "Orange Employee Health",
    "Civil Service Health Scheme", "Military Health Plan",
]

def weighted_choice(plan):
    items  = [p[0] for p in plan]
    weights = [p[1] for p in plan]
    return random.choices(items, weights=weights, k=1)[0]

# Number of days to seed (days elapsed in current month)
days_elapsed = (TODAY - MONTH_START).days + 1
# Target: ~12–18 visits per day = 150–200 for a partial month
TARGET_VISITS = min(200, days_elapsed * 14)

print(f"\n[2/4] Planning {TARGET_VISITS} visits over {days_elapsed} days of {MONTH_START.strftime('%B')}...")

# ─────────────────────────────────────────────────────────────────────────────
# SEED VISITS + CONSULTATIONS
# ─────────────────────────────────────────────────────────────────────────────
print("\n[3/4] Creating visits and consultations...")

visits_created = 0
consults_created = 0
skipped = 0
used_patients = set()

# Spread visits across all days of the month so far
all_days = [MONTH_START + timedelta(days=i) for i in range(days_elapsed)]

# Group visits per day (some days busier than others - realistic)
visits_per_day = {}
for d in all_days:
    # Mon-Fri busier, Sat lighter, Sun minimal
    weekday = d.weekday()
    if weekday < 5:    # Mon–Fri
        count = random.randint(10, 18)
    elif weekday == 5: # Saturday
        count = random.randint(4, 9)
    else:              # Sunday
        count = random.randint(0, 3)
    visits_per_day[d] = count

total_planned = sum(visits_per_day.values())
print(f"  Planned {total_planned} visits across {days_elapsed} days")

with transaction.atomic():
    for visit_date, daily_count in visits_per_day.items():
        for _ in range(daily_count):
            patient = random.choice(patients)
            doctor  = random.choice(doctors)
            dept    = random.choice(departments)

            tier         = weighted_choice(TIER_PLAN)
            billing_type = weighted_choice(BILLING_PLAN)
            visit_type   = weighted_choice(VISIT_TYPE_PLAN)

            # Insurance / HMO specific fields
            insurance_company = ""
            insurance_ref     = ""
            if billing_type == BillingType.INSURANCE:
                insurance_company = random.choice(INSURANCE_COMPANIES)
                insurance_ref     = f"POL-{random.randint(10000, 99999)}"
            elif billing_type == BillingType.HMO:
                insurance_company = random.choice(HMO_COMPANIES)
                insurance_ref     = f"HMO-{random.randint(1000, 9999)}"

            # Determine visit status (most completed, some in-progress for today)
            if visit_date < TODAY:
                status = VisitStatus.COMPLETED
            else:
                status = random.choice([VisitStatus.WAITING, VisitStatus.IN_CONSULTATION, VisitStatus.COMPLETED])

            # Visit datetime — random time during clinic hours
            hour   = random.randint(8, 17)
            minute = random.randint(0, 59)
            visit_dt = timezone.make_aware(
                timezone.datetime(visit_date.year, visit_date.month, visit_date.day, hour, minute)
            )

            try:
                dx_preview = random.choice(diagnoses)
                visit = Visit(
                    patient=patient,
                    visit_type=visit_type,
                    department=dept,
                    attending_doctor=doctor,
                    service_tier=tier,
                    billing_type=billing_type,
                    status=status,
                    chief_complaint=_random_complaint(dx_preview.description),
                    insurance_company=insurance_company,
                    insurance_policy_ref=insurance_ref,
                )
                # Override auto_now_add visit_date
                visit.save()
                Visit.objects.filter(pk=visit.pk).update(visit_date=visit_dt)
                visits_created += 1

                # Attach a consultation for completed visits
                if status == VisitStatus.COMPLETED and random.random() < 0.85:
                    dx = dx_preview
                    consult_status = ConsultationStatus.COMPLETED

                    consult = Consultation(
                        patient=patient,
                        visit=visit,
                        consulting_doctor=doctor,
                        department=dept,
                        status=consult_status,
                        chief_complaint=_random_complaint(dx.description),
                        clinical_notes=f"Patient presents with {dx.description.lower()}. Assessment and plan documented.",
                        is_deleted=False,
                    )
                    consult.save()
                    # Set created_at to match visit date
                    Consultation.objects.filter(pk=consult.pk).update(created_at=visit_dt)

                    ConsultationDiagnosis.objects.get_or_create(
                        consultation=consult,
                        diagnosis=dx,
                        defaults={'is_primary': True, 'laterality': random.choice(['RE', 'LE', 'BE', 'NA'])}
                    )
                    consults_created += 1

            except Exception as e:
                skipped += 1
                if skipped <= 5:
                    print(f"  ⚠ Skipped one visit: {e}")

print(f"  ✓ {visits_created} visits created, {consults_created} consultations")
if skipped:
    print(f"  ⚠ {skipped} visits skipped (see errors above)")

# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
print("\n[4/4] Verification counts...")

from django.db.models import Count

month_visits = Visit.objects.filter(
    visit_date__date__gte=MONTH_START,
    visit_date__date__lte=TODAY,
    is_deleted=False,
)

print(f"\n  Total visits this month : {month_visits.count()}")
print()
print("  By Service Tier:")
for row in month_visits.values('service_tier').annotate(n=Count('id')).order_by('-n'):
    print(f"    {row['service_tier']:12s} : {row['n']}")

print()
print("  By Billing Type:")
for row in month_visits.values('billing_type').annotate(n=Count('id')).order_by('-n'):
    print(f"    {row['billing_type']:12s} : {row['n']}")

print()
print("  By Visit Type:")
for row in month_visits.values('visit_type').annotate(n=Count('id')).order_by('-n'):
    print(f"    {row['visit_type']:12s} : {row['n']}")

print()
print("=" * 65)
print("Done! Open Monthly Statistics to see the populated report.")
print("=" * 65)
