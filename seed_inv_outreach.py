"""
Seed investigation + outreach stats data — 50 patients per tier.
Run on server: cd /opt/ehr-africa && python seed_inv_outreach.py
"""
import os, sys, django, random
from datetime import date, timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.production')
sys.path.insert(0, '/opt/ehr-africa')
django.setup()

from django.utils import timezone
from django.db import transaction

from apps.patients.models import Patient, Visit, BillingType, VisitStatus
from apps.accounts.models import User, UserRole
from apps.consultations.models import Consultation
from apps.investigations.models import (
    InvestigationOrder, InvestigationType, InvestigationResult
)
from apps.outreach.models import (
    OutreachActivity, OutreachRecord, OutreachPatient, OutreachExamination,
    OutreachType, OutreachStatus
)

# ── fake name pools ───────────────────────────────────────────────────────────
FIRST_M = ['Kwame','Jean','Paul','Alain','Bernard','Christophe','Didier','Eric',
           'François','Georges','Henri','Ibrahim','Jacques','Kevin','Luc','Martin',
           'Nicolas','Olivier','Patrick','Richard']
FIRST_F = ['Aïcha','Brigitte','Carine','Diane','Estelle','Fatima','Grace',
           'Hortense','Ines','Josephine','Karine','Laura','Marie','Nadia',
           'Olivia','Patricia','Rose','Sophie','Therese','Valerie']
LAST    = ['Nkomo','Biya','Tchoupo','Mbarga','Fouda','Ekotto','Abega','Djoum',
           'Ngono','Onana','Ateba','Essomba','Mba','Ndongo','Kamga','Tabi',
           'Njoya','Sanga','Beyala','Kom','Mbock','Ngah','Oyono','Tchinda',
           'Awono','Bello','Dina','Effa','Foning','Garga']
REGIONS = ['Centre','Littoral','West','North West','South West','South','East','Adamawa']

def rand_dob(min_age=5, max_age=80):
    days = random.randint(min_age * 365, max_age * 365)
    return date.today() - timedelta(days=days)

def rand_phone():
    return f'+2376{random.randint(50000000, 99999999)}'

def unique_patient_id():
    import string
    for _ in range(100):
        pid = 'S-' + ''.join(random.choices(string.digits, k=6))
        if not Patient.objects.filter(patient_id=pid).exists():
            return pid
    return 'S-' + ''.join(random.choices(string.digits, k=8))

# ── get staff users ───────────────────────────────────────────────────────────
def get_doctor():
    for role in [UserRole.OPHTHALMOLOGIST, UserRole.MEDICAL_DIRECTOR, UserRole.SUPER_ADMIN]:
        u = User.objects.filter(role=role, is_active=True).first()
        if u:
            return u
    return User.objects.filter(is_active=True, is_staff=True).first()

def get_inv_tech():
    u = User.objects.filter(role=UserRole.INVESTIGATION_TECHNICIAN, is_active=True).first()
    return u or get_doctor()

doctor   = get_doctor()
inv_tech = get_inv_tech()

if not doctor:
    print("ERROR: No active doctor/staff user found.")
    sys.exit(1)

print(f"Doctor  : {doctor.get_full_name()} ({doctor.role})")
print(f"Inv Tech: {inv_tech.get_full_name()} ({inv_tech.role})")

# ── investigation types ───────────────────────────────────────────────────────
INV_TYPES = list(InvestigationType.objects.all())
if not INV_TYPES:
    print("ERROR: No InvestigationType records found.")
    sys.exit(1)
print(f"Investigation types: {len(INV_TYPES)} found")

TIERS     = ['STANDARD', 'EXPRESS', 'VIP']
GENDERS   = ['M', 'F']
STATUSES  = ['COMPLETED','COMPLETED','COMPLETED','ORDERED','IN_PROGRESS','CANCELLED']
URGENCIES = ['ROUTINE','ROUTINE','ROUTINE','URGENT','EMERGENCY']
EYES      = ['RE','LE','BE','NA']
IS_NORMAL = [True,True,True,False,False]   # ~40% abnormal

TODAY = timezone.now()

# ═════════════════════════════════════════════════════════════════════════════
# PART 1 — INVESTIGATIONS (50 patients × 3 tiers)
# ═════════════════════════════════════════════════════════════════════════════
print("\n=== Seeding Investigation Data (50 per tier) ===")

with transaction.atomic():
    for tier in TIERS:
        print(f"  [{tier}] creating 50 patients + orders …", end=' ', flush=True)
        for _ in range(50):
            gender = random.choice(GENDERS)
            fname  = random.choice(FIRST_M if gender == 'M' else FIRST_F)
            lname  = random.choice(LAST)
            dob    = rand_dob()

            patient = Patient.objects.create(
                patient_id    = unique_patient_id(),
                first_name    = fname,
                last_name     = lname,
                gender        = gender,
                date_of_birth = dob,
                phone_number  = rand_phone(),
            )

            days_ago = random.randint(0, 28)
            visit_dt = TODAY - timedelta(days=days_ago)

            visit = Visit.objects.create(
                patient      = patient,
                service_tier = tier,
                billing_type = BillingType.SELF_PAY,
                status       = VisitStatus.COMPLETED,
            )
            # update created_at
            Visit.objects.filter(pk=visit.pk).update(created_at=visit_dt)

            consult = Consultation.objects.create(
                visit                = visit,
                patient              = patient,
                consulting_doctor    = doctor,
                presenting_complaint = 'Seed routine eye check',
            )
            Consultation.objects.filter(pk=consult.pk).update(created_at=visit_dt)

            # 1–3 investigation orders per patient
            for _ in range(random.randint(1, 3)):
                inv_type = random.choice(INV_TYPES)
                status   = random.choice(STATUSES)
                urgency  = random.choice(URGENCIES)

                order = InvestigationOrder.objects.create(
                    consultation       = consult,
                    patient            = patient,
                    ordered_by         = doctor,
                    investigation_type = inv_type,
                    urgency            = urgency,
                    clinical_indication= 'Seed data — routine',
                    eye                = random.choice(EYES),
                    status             = status,
                )
                InvestigationOrder.objects.filter(pk=order.pk).update(created_at=visit_dt)

                if status == 'COMPLETED':
                    is_norm = random.choice(IS_NORMAL)
                    InvestigationResult.objects.get_or_create(
                        order = order,
                        defaults=dict(
                            performed_by   = inv_tech,
                            interpretation = 'Normal — seed data' if is_norm else 'Abnormal finding noted — seed data',
                            is_normal      = is_norm,
                            result_data    = {'seed': True, 'abnormal': not is_norm},
                        )
                    )

        print("done")

print("Investigation seed complete.")

# ═════════════════════════════════════════════════════════════════════════════
# PART 2 — OUTREACH (4 activities × 50 patients each)
# ═════════════════════════════════════════════════════════════════════════════
print("\n=== Seeding Outreach Data (4 activities × 50 patients) ===")

VA_LIST = ['6/6','6/9','6/12','6/18','6/24','6/36','6/60','3/60','1/60','CF','HM','PL']

# VA → WHO grade mapping (simplified)
def va_grade(va):
    if va in ('6/6','6/9','6/12'):        return 0   # normal
    if va in ('6/18','6/24'):             return 1   # mild
    if va in ('6/36','6/60'):             return 2   # moderate
    if va in ('3/60','1/60'):             return 3   # severe
    return 4                                          # blind (CF/HM/PL)

ACT_TYPES_LIST = [
    OutreachType.EYE_CAMP, OutreachType.SCHOOL_SCREENING,
    OutreachType.MOBILE_CLINIC, OutreachType.VILLAGE_VISIT,
]
COND_POOL    = ['normal','refractive','cataract','glaucoma','dr','pterygium','trachoma','corneal']
COND_WEIGHTS = [40, 25, 15, 5, 4, 4, 4, 3]

with transaction.atomic():
    for month_offset in range(4):
        act_date = (TODAY - timedelta(days=month_offset * 70)).date()
        act_type = ACT_TYPES_LIST[month_offset % len(ACT_TYPES_LIST)]
        region   = REGIONS[month_offset % len(REGIONS)]

        activity = OutreachActivity.objects.create(
            title         = f"Eye Camp — {region} {act_date.strftime('%b %Y')}",
            activity_type = act_type,
            status        = OutreachStatus.COMPLETED,
            location_name = f"{region} District",
            region        = region,
            activity_date = act_date,
        )

        # aggregate counters
        total_m = total_f = total_child = total_elderly = 0
        total_treated = total_referred = total_surgery = total_glasses = 0
        ref_cat = ref_glauc = ref_ret = ref_other = 0

        patients_created = []
        for _ in range(50):
            gender = random.choice(['M', 'F'])
            dob    = rand_dob(5, 85)
            age    = (date.today() - dob).days // 365

            # retry on duplicate outreach_patient_id collision
            op = None
            for attempt in range(10):
                try:
                    import string as _str
                    from django.db import IntegrityError
                    op = OutreachPatient.objects.create(
                        activity        = activity,
                        outreach_patient_id = 'OP-' + str(activity.pk) + '-' + ''.join(random.choices(_str.digits, k=5)),
                        first_name      = random.choice(FIRST_M if gender == 'M' else FIRST_F),
                        last_name       = random.choice(LAST),
                        sex             = gender,
                        date_of_birth   = dob,
                        phone           = rand_phone(),
                        chief_complaint = 'Poor vision seed data',
                    )
                    break
                except Exception:
                    continue
            if not op:
                continue
            patients_created.append((op, gender, age))

            # demographic counters
            if gender == 'M': total_m += 1
            else:             total_f += 1
            if age < 18:    total_child   += 1
            elif age >= 60: total_elderly += 1

            # pick condition
            cond = random.choices(COND_POOL, weights=COND_WEIGHTS, k=1)[0]
            is_normal_v = (cond == 'normal')

            va_re = random.choice(VA_LIST)
            va_le = random.choice(VA_LIST)

            # worse eye grade
            grade = max(va_grade(va_re), va_grade(va_le))
            glasses_given  = (cond == 'refractive' and random.random() < 0.65)
            surgery_done   = (cond == 'cataract'   and random.random() < 0.25)
            referred       = not is_normal_v and random.random() < 0.30
            treated_here   = not is_normal_v and not referred

            # referral type
            if referred:
                rt = random.choice(['cataract','glaucoma','retina','other'])
                if rt == 'cataract': ref_cat   += 1
                elif rt == 'glaucoma': ref_glauc += 1
                elif rt == 'retina': ref_ret   += 1
                else: ref_other += 1

            if treated_here: total_treated += 1
            if referred:     total_referred += 1
            if surgery_done: total_surgery += 1
            if glasses_given: total_glasses += 1

            # build diagnosis codes
            diag_map = {
                'normal':    'H52',
                'refractive':'H52',
                'cataract':  'H26',
                'glaucoma':  'H40',
                'dr':        'H36',
                'pterygium': 'H11',
                'trachoma':  'A71',
                'corneal':   'H17',
            }
            diag_code = diag_map.get(cond, '')

            OutreachExamination.objects.create(
                patient           = op,
                examiner          = doctor,
                exam_date         = act_date,
                va_re_distance    = va_re,
                va_le_distance    = va_le,
                diagnoses_re      = diag_code,
                diagnoses_le      = diag_code,
                glasses_dispensed = glasses_given,
                surgery_performed = surgery_done,
                surgery_type      = 'Cataract extraction (SICS)' if surgery_done else '',
                needs_referral    = referred,
                referral_urgency  = 'ROUTINE' if referred else '',
                referral_reason   = cond if referred else '',
                informed_consent  = True,
            )

        # create one OutreachRecord per activity with aggregated counts
        OutreachRecord.objects.create(
            activity          = activity,
            record_date       = act_date,
            total_screened    = 50,
            male_screened     = total_m,
            female_screened   = total_f,
            children_screened = total_child,
            elderly_screened  = total_elderly,
            total_treated     = total_treated,
            total_referred    = total_referred,
            surgeries_performed = total_surgery,
            glasses_dispensed = total_glasses,
            referred_cataract = ref_cat,
            referred_glaucoma = ref_glauc,
            referred_retina   = ref_ret,
            referred_other    = ref_other,
        )

        print(f"  Activity '{activity.title}': 50 patients, "
              f"treated={total_treated}, referred={total_referred}, "
              f"surgery={total_surgery}, glasses={total_glasses}")

print("\nOutreach seed complete.")
print("\nAll done! Clear cache if needed, then refresh stats pages.")
