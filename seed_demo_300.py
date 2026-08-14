"""
EHR Africa — Comprehensive 300-Patient Demo Seed
=================================================
Seeds 300 patients with diverse demographics, 2–5 visits each,
full consultations, diagnoses, vital signs, and medical records.

Run with:
    python manage.py shell < seed_demo_300.py
"""
import random
from decimal import Decimal
from datetime import date, timedelta, datetime
from django.utils import timezone
from django.db import transaction

random.seed(42)
TODAY = date(2026, 6, 15)

print("=" * 65)
print("EHR AFRICA — Comprehensive 300-Patient Demo Seed")
print("=" * 65)

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: DIAGNOSES
# ─────────────────────────────────────────────────────────────────────────────
print("\n[1/6] Seeding ophthalmic ICD-10 diagnoses...")
from apps.consultations.models import Diagnosis, Consultation, ConsultationDiagnosis, ConsultationStatus

DIAGNOSES_DATA = [
    ("H25.9",  "Age-related cataract, unspecified"),
    ("H26.0",  "Infantile and juvenile cataract"),
    ("H26.9",  "Cataract, unspecified"),
    ("H40.10", "Unspecified open-angle glaucoma"),
    ("H40.11", "Primary open-angle glaucoma"),
    ("H40.20", "Unspecified primary angle-closure glaucoma"),
    ("H40.9",  "Unspecified glaucoma"),
    ("H35.30", "Unspecified macular degeneration"),
    ("H35.31", "Nonexudative age-related macular degeneration"),
    ("H35.32", "Exudative age-related macular degeneration"),
    ("H35.00", "Unspecified background retinopathy"),
    ("H35.01", "Nonproliferative diabetic retinopathy"),
    ("H35.02", "Proliferative diabetic retinopathy"),
    ("H52.10", "Myopia, unspecified"),
    ("H52.00", "Hypermetropia, unspecified"),
    ("H52.20", "Astigmatism, unspecified"),
    ("H52.4",  "Presbyopia"),
    ("H10.30", "Unspecified acute conjunctivitis"),
    ("H10.10", "Acute atopic conjunctivitis"),
    ("H10.40", "Chronic conjunctivitis, unspecified"),
    ("H16.00", "Unspecified corneal ulcer"),
    ("H18.60", "Keratoconus, unspecified"),
    ("H57.10", "Ocular pain, unspecified"),
    ("H53.00", "Deprivation amblyopia"),
    ("H50.00", "Unspecified esotropia"),
    ("H50.10", "Unspecified exotropia"),
    ("H11.00", "Unspecified pterygium"),
    ("H33.00", "Unspecified rhegmatogenous retinal detachment"),
    ("H34.10", "Central retinal artery occlusion, unspecified"),
    ("H34.20", "Unspecified retinal vein occlusion"),
    ("H43.10", "Vitreous haemorrhage, unspecified"),
    ("H46.9",  "Unspecified optic neuritis"),
    ("H47.00", "Unspecified disorder of optic nerve"),
    ("H20.00", "Unspecified acute and subacute iridocyclitis"),
    ("H20.10", "Chronic iridocyclitis, unspecified"),
    ("H02.10", "Unspecified ectropion of eyelid"),
    ("H02.00", "Unspecified entropion and trichiasis of eyelid"),
    ("H04.30", "Unspecified dacryocystitis"),
    ("H49.00", "Third nerve palsy, unspecified"),
    ("Z01.00", "Routine eye examination, no abnormality found"),
]

dx_map = {}
dx_created = 0
for code, desc in DIAGNOSES_DATA:
    obj, created = Diagnosis.objects.get_or_create(
        icd10_code=code,
        defaults={'description': desc, 'is_ophthalmic': True, 'is_active': True}
    )
    dx_map[code] = obj
    if created:
        dx_created += 1

print(f"  ✓ {dx_created} new diagnoses  ({len(dx_map)} total in catalogue)")

# Group diagnoses by condition for realistic assignment
DX_GROUPS = {
    'cataract':    [dx_map[k] for k in ("H25.9","H26.0","H26.9") if k in dx_map],
    'glaucoma':    [dx_map[k] for k in ("H40.10","H40.11","H40.20","H40.9") if k in dx_map],
    'retina':      [dx_map[k] for k in ("H35.30","H35.31","H35.32","H35.00","H35.01","H35.02","H33.00","H34.10","H34.20","H43.10") if k in dx_map],
    'refraction':  [dx_map[k] for k in ("H52.10","H52.00","H52.20","H52.4") if k in dx_map],
    'cornea':      [dx_map[k] for k in ("H16.00","H18.60","H11.00") if k in dx_map],
    'conjunctiva': [dx_map[k] for k in ("H10.30","H10.10","H10.40") if k in dx_map],
    'strabismus':  [dx_map[k] for k in ("H50.00","H50.10","H53.00") if k in dx_map],
    'uveitis':     [dx_map[k] for k in ("H20.00","H20.10") if k in dx_map],
    'neuro':       [dx_map[k] for k in ("H46.9","H47.00","H49.00") if k in dx_map],
    'adnexa':      [dx_map[k] for k in ("H02.10","H02.00","H04.30") if k in dx_map],
    'routine':     [dx_map[k] for k in ("Z01.00","H57.10") if k in dx_map],
}

# Probability weights for diagnosis groups (eye hospital distribution)
DX_GROUP_WEIGHTS = {
    'cataract': 20, 'glaucoma': 14, 'refraction': 18, 'retina': 12,
    'cornea': 8, 'conjunctiva': 10, 'strabismus': 4, 'uveitis': 4,
    'neuro': 3, 'adnexa': 4, 'routine': 3,
}
DX_GROUP_NAMES = list(DX_GROUP_WEIGHTS.keys())
DX_GROUP_PROBS = [DX_GROUP_WEIGHTS[g] / sum(DX_GROUP_WEIGHTS.values()) for g in DX_GROUP_NAMES]


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2: GET EXISTING STAFF + DEPARTMENTS
# ─────────────────────────────────────────────────────────────────────────────
print("\n[2/6] Loading staff and departments...")
from apps.accounts.models import User, UserRole
from apps.departments.models import Department

doctor_roles = [
    UserRole.OPHTHALMOLOGIST, UserRole.RETINA_SPECIALIST, UserRole.GLAUCOMA_SPECIALIST,
    UserRole.PEDIATRIC_OPHTHALMOLOGIST, UserRole.CATARACT_SURGEON, UserRole.CORNEA_SPECIALIST,
    UserRole.OCULOPLASTICS_SURGEON, UserRole.NEURO_OPHTHALMOLOGIST, UserRole.UVEITIS_SPECIALIST,
    UserRole.OPTOMETRIST, UserRole.MEDICAL_DIRECTOR, UserRole.INTERN,
]
doctors = list(User.objects.filter(role__in=doctor_roles, is_active=True))
nurses = list(User.objects.filter(role__in=[UserRole.NURSE, UserRole.THEATRE_NURSE, UserRole.WARD_NURSE, UserRole.COUNSELING_NURSE], is_active=True))
receptionists = list(User.objects.filter(role=UserRole.RECEPTIONIST, is_active=True))

departments = list(Department.objects.filter(is_active=True))

print(f"  ✓ {len(doctors)} doctors, {len(nurses)} nurses, {len(departments)} departments")

# Fallback: use any user/superuser if no doctors seeded yet
if not doctors:
    doctors = list(User.objects.filter(is_superuser=True) or User.objects.all()[:3])

fallback_user = doctors[0] if doctors else None
fallback_dept = departments[0] if departments else None


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3: PATIENT DATA POOLS
# ─────────────────────────────────────────────────────────────────────────────

FIRST_NAMES_M = [
    "Jean-Pierre","Emmanuel","Christophe","Paul","François","André","Michel","Patrick",
    "Thierry","Nicolas","Cédric","Laurent","Bruno","Hervé","Daniel","Gilbert","Alain",
    "Serge","Roger","Sylvain","Rodrigue","Ulrich","Arsène","Brice","Cedric","Désiré",
    "Edouard","Fabrice","Gaston","Henri","Ignace","Jonas","Kevin","Landry","Marcel",
    "Narcisse","Olivier","Pierre","Quinton","René","Samuel","Théodore","Urbain",
    "Valentin","William","Xavier","Yannick","Zacharie","Bertrand","Clément",
]

FIRST_NAMES_F = [
    "Marie","Aïcha","Florence","Brigitte","Carine","Danielle","Elise","Françoise",
    "Gisèle","Honorine","Isabelle","Joëlle","Karine","Laure","Marianne","Nadège",
    "Odette","Pascale","Reine","Solange","Thérèse","Ursule","Véronique","Wanda",
    "Yvette","Zoé","Alvine","Blandine","Christelle","Dorothée","Emmanuella","Flore",
    "Gertrude","Hélène","Irène","Julie","Linda","Madeleine","Nathalie","Ophélie",
    "Pauline","Rachel","Sabine","Tina","Ulrike","Valentine","Winnie","Angèle",
    "Béatrice","Colette",
]

LAST_NAMES = [
    "MBARGA","FOUDA","NKOLO","BIYONG","TAMBA","ESSOMBA","ONDOA","ATEBA","NNOMO",
    "OWONA","MENGUE","ABENA","ELLA","NOAH","MVONDO","BALLA","NANA","ETOUNDI",
    "TSIMI","NTONGA","MESSI","BEYALA","AKONO","BIKELE","OMGBA","ZANG","SAMBA",
    "DINGANA","EYEBE","FOMEKONG","GUEDE","HAMENI","IBARA","JONGA","KONA","LELE",
    "MANGA","NGONO","OBEN","PENDA","QUENTIN","RINGO","SOLA","TOUNA","USMAN",
    "VEKOU","WAMBA","XIONG","YAMA","ZEMBA","ABODO","BELE","CISSE","DABO",
    "EBODE","FOFANA","GOMA","HAMA","ISSA","JUMA","KEBE","LAMBA","MOMA",
    "NEBA","OKOYE","PALA","RAMBE","SENGA","TABI","UMARU","VOMA","WARA",
    "YEMBA","ZAMBA","AGBOR","BESONG","CHIMA","DIBONG","EPIE","FONGE",
]

REGIONS = [
    "Centre","Littoral","West","North West","South West","South","East","Adamawa","North","Far North"
]
QUARTERS = {
    "Centre":    ["Bastos","Nlongkak","Melen","Mvog-Mbi","Ekounou","Biyem-Assi","Nkolbisson","Mimboman"],
    "Littoral":  ["Bonanjo","Akwa","Bonabéri","Deido","Bassa","Makepe","Logbaba","Ndogpassi"],
    "West":      ["Bafoussam Centre","Banengo","Tougang","Ngouache","Kamkop"],
    "North West":["Bamenda Town","Up Station","Commercial Avenue","Old Town"],
    "South West":["Buea Town","Molyko","Bonduma","Small Soppo"],
    "South":     ["Ebolowa Centre","Mvangan","Ambam","Kribi Beach"],
    "East":      ["Bertoua Centre","Belabo","Batouri"],
    "Adamawa":   ["Ngaoundéré Centre","Meiganga","Tibati"],
    "North":     ["Garoua Centre","Pitoa","Guider"],
    "Far North": ["Maroua Centre","Kousseri","Mora"],
}

OCCUPATIONS = [
    "Teacher","Civil Servant","Farmer","Trader","Nurse","Driver","Engineer",
    "Accountant","Retired","Student","Housewife","Carpenter","Mechanic","Pastor",
    "Businessperson","Doctor","Journalist","Police Officer","Military","Tailor",
    "Fisherman","Chef","Pharmacist","Lawyer","Secretary","IT Technician",
]

BLOOD_GROUPS  = ["A+","A-","B+","B-","AB+","AB-","O+","O-","Unknown"]
BLOOD_WEIGHTS = [30, 3, 10, 2, 4, 1, 38, 5, 7]
GENOTYPES     = ["AA","AS","SS","AC","Unknown"]
GENOTYPE_W    = [50, 30, 5, 5, 10]

COMPLAINTS_BY_GROUP = {
    'cataract':    ["Gradual loss of vision in both eyes","Blurred vision getting worse over months","Difficulty reading in dim light","Glare from headlights at night","Cloudy vision in right eye","Progressive visual impairment"],
    'glaucoma':    ["Eye pain and redness","Halos around lights","Peripheral vision loss","Headache and eye ache","Elevated IOP detected on routine exam","Family history of glaucoma — screening"],
    'retina':      ["Flashes of light and floaters","Sudden painless loss of vision","Distorted central vision","Dark curtain over visual field","Diabetic retina follow-up","Photopsia and metamorphopsia"],
    'refraction':  ["Difficulty reading up close","Blurred distance vision","Headache when reading","Eye strain and fatigue","Child struggling at school with vision","Need new glasses prescription"],
    'cornea':      ["Red painful eye with photophobia","Foreign body sensation","Irregular astigmatism","Progressive corneal thinning","Post-keratitis scar","Contact lens-related symptoms"],
    'conjunctiva': ["Red eye discharge","Itchy watery eyes","Mucopurulent discharge","Bilateral redness and irritation","Sandy/gritty sensation","Seasonal eye allergy"],
    'strabismus':  ["Squinting eye noticed by parent","Diplopia","Lazy eye in child","Eye turn outward","Crossed eyes","Poor binocular vision"],
    'uveitis':     ["Floaters and photophobia","Acute red painful eye","Blurred vision with floaters","Uveitis follow-up — chronic","Pain and redness with systemic disease"],
    'neuro':       ["Sudden visual loss with pain on movement","Double vision","Ptosis and diplopia","Headache with visual disturbance","Visual field defect"],
    'adnexa':      ["Watery eye (epiphora)","Lid lump / swelling","In-turning eyelashes","Swelling around eye","Drooping eyelid","Lump on eyelid"],
    'routine':     ["Routine eye check","Annual review","Pre-operative assessment","Occupation-related eye check","Diabetic eye screening","Insurance eye examination"],
}

EXAM_VA_OPTIONS     = ["6/6","6/9","6/12","6/18","6/24","6/36","6/60","CF","HM","PL"]
EXAM_IOP_OPTIONS    = [10,12,14,15,16,17,18,20,22,24,26,28,30,34,38,42]
EXAM_ANTERIOR = [
    "Clear cornea, deep AC, round reactive pupil, clear lens",
    "Cornea clear, AC deep and quiet, pupil round and reactive, lens clear",
    "Mild conjunctival injection, cornea clear, AC quiet, posterior chamber IOL",
    "Pterygium 2mm from limbus nasally, cornea otherwise clear",
    "Nuclear sclerosis grade 2, AC deep, pupil reactive",
    "Nuclear sclerosis grade 3, AC shallow centrally",
    "Posterior subcapsular cataract, cornea clear, AC quiet",
    "Pseudophakic — well centred posterior chamber IOL",
]
EXAM_POSTERIOR = [
    "Disc healthy, pink with 0.3 cup/disc ratio, vessels normal, macula flat",
    "Optic disc cupping 0.7/0.7, RNFL thinning, macula normal",
    "CSME — hard exudates at macula, background diabetic retinopathy",
    "Pale optic disc, attenuated vessels, macula spared",
    "Peripheral lattice degeneration, macula attached",
    "Dry AMD — multiple drusen at macula",
    "Vitreous clear, disc normal, macula shows BRVO changes",
    "Disc oedema, blurred margins, no haemorrhages",
    "Background diabetic retinopathy — dot and blot haemorrhages",
    "Proliferative DR — new vessels on disc",
]

MGMT_PLANS = {
    'cataract':    ["Phacoemulsification + IOL right eye scheduled. Counselling done. Informed consent obtained.",
                    "Cataract surgery counselled and booked. Pre-op biometry requested. Hypertension to be controlled before surgery.",
                    "Monitor — cataract not visually significant yet. Review in 6 months.",
                    "Extracapsular cataract extraction + PCIOL planned for left eye. Pre-op investigations requested."],
    'glaucoma':    ["Start Latanoprost 0.005% 1 drop OD nocte. Repeat IOP in 4 weeks. Visual field test requested.",
                    "Adjust pilocarpine — add Timolol 0.5% BD. Target IOP < 15mmHg. OCT RNFL ordered.",
                    "Refer for trabeculectomy. IOP uncontrolled on maximum medical therapy.",
                    "SLT (Selective Laser Trabeculoplasty) booked. Continue current drops until then."],
    'retina':      ["Urgent vitreoretinal referral for retinal detachment. Restrict activities.",
                    "Intravitreal anti-VEGF injection booked. FA/OCT reviewed.",
                    "Panretinal photocoagulation (PRP) for proliferative DR. Patient counselled.",
                    "Lucentis injection series planned for wet AMD. Monitoring protocol initiated.",
                    "Optimize glycaemic control — HbA1c target < 7%. Ophthalmology review in 3 months."],
    'refraction':  ["New prescription: OD -2.50/-0.75×180, OS -2.00/-0.50×170. Glasses advised.",
                    "Presbyopia — reading glasses +2.00 DS OU recommended.",
                    "Myopia progression noted. Atropine 0.01% therapy initiated for paediatric patient.",
                    "Multifocal glasses prescribed. Referred to optician for dispensing."],
    'cornea':      ["Topical antibiotics (Ciprofloxacin 0.3%) 2-hourly. Review in 48 hours.",
                    "Corneal cross-linking (CXL) booked for keratoconus. Discontinue contact lenses.",
                    "Topical lubricants and antifungal drops. Culture swab taken.",
                    "Pterygium excision with conjunctival autograft scheduled."],
    'conjunctiva': ["Chloramphenicol 0.5% drops QID for 5 days. Hand hygiene counselling.",
                    "Antihistamine drops (Olopatadine) BD + cold compresses. Avoid allergens.",
                    "Viral conjunctivitis — artificial tears, no antibiotics. Review if no improvement in 7 days."],
    'strabismus':  ["Prescribe full optical correction first. Review in 3 months for alignment assessment.",
                    "Occlusion therapy 2hrs/day for amblyopia. Follow-up in 6 weeks.",
                    "Surgical correction (medial rectus recession) planned. Pre-op orthoptic assessment done."],
    'uveitis':     ["Prednisolone acetate 1% drops 2-hourly. Cyclopentolate 1% TDS. Systemic work-up ordered.",
                    "Tapering steroid drops as planned. Methotrexate initiated for recurrent uveitis.",
                    "Stable uveitis — continue maintenance Mycophenolate. Review in 2 months."],
    'neuro':       ["MRI brain and orbits with gadolinium requested urgently. Neurology referral.",
                    "IV methylprednisolone 1g OD×3 days admitted. OCT RNFL baseline done.",
                    "Observe and monitor visual fields. Neuro-imaging pending."],
    'adnexa':      ["Warm compresses + topical chloramphenicol. Lid hygiene regime advised.",
                    "Dacryocystorhinostomy (DCR) planned. Pre-op nasal examination done.",
                    "Trichiasis epilation done. Lid rotation procedure planned if recurs.",
                    "Upper lid ptosis — levator resection planned. Photos taken for baseline."],
    'routine':     ["No significant pathology found. Next routine review in 12 months.",
                    "Spectacles prescription updated. No ocular disease detected.",
                    "Normal diabetic eye screening. Next screen in 12 months. Glycaemic control encouraged."],
}


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4: CREATE 300 PATIENTS
# ─────────────────────────────────────────────────────────────────────────────
print("\n[3/6] Creating 300 patients...")
from apps.patients.models import Patient, Visit, VisitStatus, VisitType, BillingType, ServiceTier

existing_count = Patient.objects.count()
patients_to_create = 300

# Phone prefixes for Cameroon
CM_PREFIXES = ["+23767","+ 23769","+ 23769","+ 23777","+ 23679","+ 23699","+ 23675"]
CM_PREFIXES = ["+23767","+23669","+23691","+23677","+23679","+23699","+23675","+23698"]

created_patients = []
skipped = 0

with transaction.atomic():
    for i in range(patients_to_create):
        gender = random.choice(["M","M","M","F","F","F","F"])
        first_name = random.choice(FIRST_NAMES_M if gender == "M" else FIRST_NAMES_F)
        last_name = random.choice(LAST_NAMES)
        region = random.choice(REGIONS)
        quarter = random.choice(QUARTERS.get(region, ["Centre Ville"]))

        # Age distribution: children 5%, young adults 20%, adults 50%, elderly 25%
        age_roll = random.random()
        if age_roll < 0.05:    age = random.randint(5, 17)
        elif age_roll < 0.25:  age = random.randint(18, 35)
        elif age_roll < 0.75:  age = random.randint(36, 60)
        else:                  age = random.randint(61, 85)

        dob = TODAY - timedelta(days=age*365 + random.randint(0, 364))

        blood_group = random.choices(BLOOD_GROUPS, weights=BLOOD_WEIGHTS)[0]
        genotype    = random.choices(GENOTYPES, weights=GENOTYPE_W)[0]

        phone_suffix = ''.join([str(random.randint(0,9)) for _ in range(7)])
        phone = random.choice(CM_PREFIXES) + phone_suffix

        marital = "Single" if age < 20 else random.choice(["Single","Married","Married","Married","Divorced","Widowed"])
        occupation = "Student" if age < 20 else random.choice(OCCUPATIONS)

        # Registration date: past 24 months, weighted toward last 12
        reg_days_ago = random.choices(
            [random.randint(1, 365), random.randint(366, 730)],
            weights=[70, 30]
        )[0]
        reg_date = TODAY - timedelta(days=reg_days_ago)

        try:
            p = Patient.objects.create(
                first_name=first_name,
                last_name=last_name,
                date_of_birth=dob,
                gender=gender,
                blood_group=blood_group,
                genotype=genotype,
                phone_number=phone,
                address=f"{quarter}, {region}",
                quarter=quarter,
                region=region,
                country="Cameroon",
                nationality="Cameroonian",
                occupation=occupation,
                marital_status=marital,
                registered_by=fallback_user,
            )
            # Backdate registration
            Patient.objects.filter(pk=p.pk).update(registration_date=reg_date)
            created_patients.append(p)
        except Exception as e:
            skipped += 1

print(f"  ✓ {len(created_patients)} patients created  ({skipped} skipped / errors)")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 5: CREATE VISITS + CONSULTATIONS
# ─────────────────────────────────────────────────────────────────────────────
print("\n[4/6] Creating visits and consultations (this may take a moment)...")

from apps.core.utils import generate_visit_number

total_visits = 0
total_consults = 0

BILLING_TYPES   = ["SELF_PAY","SELF_PAY","SELF_PAY","SELF_PAY","HMO","INSURANCE","WAIVER"]
SERVICE_TIERS   = ["STANDARD","STANDARD","STANDARD","EXPRESS","FAST_TRACK","VIP"]

with transaction.atomic():
    for patient in created_patients:
        # Each patient gets 1-4 visits
        n_visits = random.choices([1,2,3,4], weights=[30,35,25,10])[0]

        # Assign a primary condition to this patient for consistency
        dx_group_name = random.choices(DX_GROUP_NAMES, weights=[DX_GROUP_WEIGHTS[g] for g in DX_GROUP_NAMES])[0]
        primary_dx_group = DX_GROUPS[dx_group_name]

        # Get registration date for this patient (re-fetch after update)
        try:
            reg_date = Patient.objects.filter(pk=patient.pk).values_list('registration_date', flat=True).first()
        except:
            reg_date = TODAY - timedelta(days=180)

        # Generate visit dates spread from registration to today
        reg_dt = reg_date if reg_date else (TODAY - timedelta(days=180))
        days_available = (TODAY - reg_dt).days
        if days_available < 1:
            days_available = 30

        visit_offsets = sorted(random.sample(range(days_available), min(n_visits, days_available)))

        for v_idx, offset in enumerate(visit_offsets):
            is_first_visit = (v_idx == 0)
            visit_date_dt  = datetime.combine(reg_dt + timedelta(days=offset), datetime.min.time().replace(hour=random.randint(7,17), minute=random.randint(0,59)))
            visit_date_dt  = timezone.make_aware(visit_date_dt)

            billing_type = random.choice(BILLING_TYPES)
            service_tier = random.choices(SERVICE_TIERS, weights=[50,20,15,10,4,1])[0]
            visit_type   = "NEW" if is_first_visit else random.choice(["FOLLOW_UP","FOLLOW_UP","REVIEW","PROCEDURE"])

            complaint = random.choice(COMPLAINTS_BY_GROUP.get(dx_group_name, ["Eye problem"]))

            # Doctor assignment
            doctor = random.choice(doctors) if doctors else None
            nurse  = random.choice(nurses) if nurses else None
            dept   = random.choice(departments) if departments else None

            # Vital signs
            va_r = random.choice(EXAM_VA_OPTIONS)
            va_l = random.choice(EXAM_VA_OPTIONS)
            iop_r = random.choice(EXAM_IOP_OPTIONS)
            iop_l = random.choice(EXAM_IOP_OPTIONS)
            bp_sys = random.randint(110, 160)
            bp_dia = random.randint(70, 100)

            vital_signs = {
                "blood_pressure": f"{bp_sys}/{bp_dia}",
                "pulse": random.randint(60, 90),
                "temperature": round(random.uniform(36.2, 37.4), 1),
                "weight": round(random.uniform(45.0, 100.0), 1),
                "height": round(random.uniform(1.50, 1.90), 2),
                "visual_acuity_right": va_r,
                "visual_acuity_left": va_l,
                "intraocular_pressure_right": iop_r,
                "intraocular_pressure_left": iop_l,
            }

            try:
                visit = Visit.objects.create(
                    patient=patient,
                    visit_type=visit_type,
                    department=dept,
                    attending_doctor=doctor,
                    triage_nurse=nurse,
                    chief_complaint=complaint,
                    vital_signs=vital_signs,
                    status="DISCHARGED",
                    billing_type=billing_type,
                    service_tier=service_tier,
                    previously_registered=not is_first_visit,
                    has_referral_letter=random.random() < 0.08,
                    nursing_notes=f"Patient presents with {complaint.lower()}. BP {bp_sys}/{bp_dia}. Visual acuity OD: {va_r}, OS: {va_l}. IOP: {iop_r}/{iop_l}mmHg. Patient is cooperative.",
                )
                # Backdate visit
                Visit.objects.filter(pk=visit.pk).update(visit_date=visit_date_dt)
                total_visits += 1

                # ── Create consultation for this visit ──────────────────────
                mgmt_options = MGMT_PLANS.get(dx_group_name, ["Continue current management. Review as needed."])
                mgmt_plan = random.choice(mgmt_options)

                follow_up_days = random.choice([14, 30, 60, 90, 180, None])
                follow_up_date = None
                if follow_up_days:
                    fu = visit_date_dt.date() + timedelta(days=follow_up_days)
                    if fu <= TODAY:
                        follow_up_date = fu

                anterior = random.choice(EXAM_ANTERIOR)
                posterior = random.choice(EXAM_POSTERIOR)
                exam_findings = {
                    "visual_acuity": {
                        "right_unaided": va_r,
                        "left_unaided": va_l,
                        "right_pinhole": random.choice(EXAM_VA_OPTIONS[:5]),
                        "left_pinhole": random.choice(EXAM_VA_OPTIONS[:5]),
                        "right_best_corrected": random.choice(EXAM_VA_OPTIONS[:4]),
                        "left_best_corrected": random.choice(EXAM_VA_OPTIONS[:4]),
                    },
                    "intraocular_pressure": {
                        "right": str(iop_r),
                        "left": str(iop_l),
                        "method": random.choice(["Non-Contact Tonometry","Goldman Applanation","iCare"]),
                    },
                    "anterior_segment": {"right": anterior, "left": anterior},
                    "posterior_segment": {"right": posterior, "left": posterior},
                    "pupils": "Equal round and reactive to light. No RAPD.",
                    "ocular_motility": "Full and conjugate in all positions of gaze.",
                    "cover_test": random.choice(["Orthotropic","Esophoria","Exophoria","Esotropia","Exotropia"]),
                    "color_vision": random.choice(["Normal Ishihara","Defective — red-green","Not tested"]),
                    "confrontation_fields": random.choice(["Full OU","Inferior altitudinal defect OD","Temporal hemianopia","Constricted OU","Full to confrontation OU"]),
                    "slit_lamp": {
                        "lids_lashes": "Normal",
                        "conjunctiva": random.choice(["Clear","Mild hyperaemia","Papillae and follicles on palpebral conjunctiva"]),
                        "cornea": random.choice(["Clear and transparent","Scattered epithelial defects staining with fluorescein","Arcus senilis peripherally"]),
                        "anterior_chamber": random.choice(["Deep and quiet","Cells 1+ flare 1+","Shallow"]),
                        "iris": "Normal",
                        "lens": random.choice(["Clear","Nuclear sclerosis grade 2","Posterior subcapsular cataract","Pseudophakic — PCIOL well centred"]),
                    },
                }

                # Ocular and systemic history
                ocular_hx_options = [
                    "No previous eye surgery. No previous significant eye disease.",
                    "Previous cataract surgery right eye 2 years ago.",
                    "Longstanding glaucoma — on treatment for 3 years.",
                    "Childhood squint surgery. Vision never normal in left eye.",
                    "No significant ocular history.",
                    "Previous pterygium excision 5 years ago.",
                ]
                systemic_hx_options = [
                    "Hypertension — on Amlodipine. Diabetes mellitus — on Metformin.",
                    "No significant systemic illness. No known allergies.",
                    "Sickle cell disease (HbSS) — on hydroxyurea.",
                    "HIV positive — on ARV therapy.",
                    "Hypertension and dyslipidaemia.",
                    "No systemic disease.",
                    "Type 2 diabetes mellitus — poor glycaemic control.",
                ]

                consult = Consultation.objects.create(
                    visit=visit,
                    patient=patient,
                    department=dept,
                    consulting_doctor=doctor,
                    status=ConsultationStatus.COMPLETED,
                    presenting_complaint=complaint,
                    history_of_presenting_complaint=f"Patient is a {patient.age}-year-old presenting with {complaint.lower()}. Onset {random.choice(['gradual','sudden','acute','insidious'])} over {random.choice(['1 week','2 weeks','1 month','3 months','6 months','1 year'])}. Associated with {random.choice(['blurred vision','eye pain','redness','watering','photophobia','no other symptoms'])}.",
                    ocular_history=random.choice(ocular_hx_options),
                    systemic_history=random.choice(systemic_hx_options),
                    drug_history=random.choice(["None.","On lubricating drops.","Timolol 0.5% BD, Latanoprost nocte.","Metformin 500mg BD, Amlodipine 5mg OD.","No current medications."]),
                    family_history=random.choice(["No family history of glaucoma or eye disease.","Father had cataracts.","Family history of glaucoma.","Mother diabetic.","No relevant family history."]),
                    examination_findings=exam_findings,
                    management_plan=mgmt_plan,
                    follow_up_date=follow_up_date,
                    follow_up_instructions=f"Review in {follow_up_days} days." if follow_up_days else "",
                )

                # Backdate consultation
                Consultation.objects.filter(pk=consult.pk).update(consultation_date=visit_date_dt)

                # Assign 1-2 diagnoses
                primary_dx = random.choice(primary_dx_group)
                ConsultationDiagnosis.objects.create(
                    consultation=consult,
                    diagnosis=primary_dx,
                    is_primary=True,
                    laterality=random.choice(["RE","LE","BE","BE","BE","NA"]),
                )

                # 30% chance of secondary diagnosis
                if random.random() < 0.30:
                    other_groups = [g for g in DX_GROUP_NAMES if g != dx_group_name]
                    sec_group = random.choice(other_groups)
                    sec_dx = random.choice(DX_GROUPS[sec_group])
                    if sec_dx != primary_dx:
                        try:
                            ConsultationDiagnosis.objects.create(
                                consultation=consult,
                                diagnosis=sec_dx,
                                is_primary=False,
                                laterality=random.choice(["RE","LE","BE","NA"]),
                            )
                        except Exception:
                            pass

                total_consults += 1

            except Exception as e:
                pass  # Skip problematic records silently

print(f"  ✓ {total_visits} visits created")
print(f"  ✓ {total_consults} consultations created")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 6: CREATE BILLING INVOICES FOR VISITS
# ─────────────────────────────────────────────────────────────────────────────
print("\n[5/6] Creating billing invoices...")
try:
    from apps.billing.models import Invoice, InvoiceItem, ServicePrice, InvoiceStatus

    service_prices = list(ServicePrice.objects.filter(is_active=True))
    CONSULT_PRICES  = [sp for sp in service_prices if sp.category in ("CONSULT","REG")]
    INVEST_PRICES   = [sp for sp in service_prices if sp.category in ("INVEST","LAB")]
    PHARMA_PRICES   = [sp for sp in service_prices if sp.category == "PHARMACY"]

    inv_created = 0
    cashier = (
        User.objects.filter(role=UserRole.CASHIER).first()
        or User.objects.filter(role=UserRole.BILLING_OFFICER).first()
        or fallback_user
    )

    if service_prices and cashier:
        # Get consultations for the patients we created
        consults_to_bill = Consultation.objects.filter(
            patient__in=created_patients,
            status=ConsultationStatus.COMPLETED,
        ).select_related('patient', 'visit').order_by('?')[:500]

        with transaction.atomic():
            for consult in consults_to_bill:
                try:
                    if Invoice.objects.filter(consultation=consult).exists():
                        continue

                    is_paid = random.random() < 0.78  # 78% paid
                    bt = consult.visit.billing_type if consult.visit else "SELF_PAY"

                    items_data = []
                    # Consultation fee
                    if CONSULT_PRICES:
                        cp = random.choice(CONSULT_PRICES)
                        price = float(cp.nhis_price or cp.price) if bt == "HMO" else \
                                float(cp.insurance_price or cp.price) if bt == "INSURANCE" else \
                                float(cp.price)
                        items_data.append((cp.name, cp.category, price))

                    # 50% chance of investigations
                    if INVEST_PRICES and random.random() < 0.5:
                        for _ in range(random.randint(1, 3)):
                            ip = random.choice(INVEST_PRICES)
                            items_data.append((ip.name, ip.category, float(ip.price)))

                    # 30% chance of pharmacy
                    if PHARMA_PRICES and random.random() < 0.3:
                        pp = random.choice(PHARMA_PRICES)
                        items_data.append((pp.name, pp.category, float(pp.price)))

                    if not items_data:
                        continue

                    inv = Invoice.objects.create(
                        patient=consult.patient,
                        consultation=consult,
                        created_by=cashier,
                        status="PAID" if is_paid else "ISSUED",
                        notes="Auto-generated demo invoice",
                    )

                    for name, cat, price in items_data:
                        InvoiceItem.objects.create(
                            invoice=inv,
                            category=cat,
                            description=name,
                            quantity=1,
                            unit_price=Decimal(str(price)),
                        )

                    inv_created += 1
                except Exception:
                    pass

        print(f"  ✓ {inv_created} invoices created")
    else:
        print("  · No service prices or cashier found — skipping invoices (run seed_patient_journey.py first)")

except Exception as e:
    print(f"  · Billing skipped: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
print("\n[6/6] Summary")
print("-" * 65)

from apps.patients.models import Patient as P, Visit as V
from apps.consultations.models import Consultation as C

print(f"  Total patients in DB          : {P.objects.count():,}")
print(f"  Total visits in DB            : {V.objects.count():,}")
print(f"  Total consultations in DB     : {C.objects.count():,}")
print(f"  Total diagnoses in catalogue  : {Diagnosis.objects.count()}")

try:
    from apps.billing.models import Invoice
    print(f"  Total invoices in DB          : {Invoice.objects.count():,}")
except Exception:
    pass

print("")
print("  Sample patient IDs (demo):")
for p in created_patients[:8]:
    fresh = P.objects.get(pk=p.pk)
    n_v = V.objects.filter(patient=fresh).count()
    n_c = C.objects.filter(patient=fresh).count()
    print(f"    {fresh.patient_id}  {fresh.full_name:<30}  {fresh.age}y  {n_v}v {n_c}c")

print("")
print("=" * 65)
print("DONE — 300-patient demo data ready!")
print("=" * 65)
