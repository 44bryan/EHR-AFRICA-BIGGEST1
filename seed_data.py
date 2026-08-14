"""
EHR Africa — Comprehensive Demo Seed Data Script
Generates 12 months of realistic hospital data so all dashboards & charts populate.

Run with:
  python manage.py shell < seed_data.py
"""
import random
from datetime import date, datetime, timedelta, time
from decimal import Decimal
from django.utils import timezone

random.seed(42)

def rand_date_in_month(year, month):
    """Return a random date within the given month."""
    import calendar
    _, days_in_month = calendar.monthrange(year, month)
    return date(year, month, random.randint(1, days_in_month))

def months_back(n):
    """Return (year, month) for n months ago."""
    today = date.today()
    m = today.month - n
    y = today.year
    while m <= 0:
        m += 12
        y -= 1
    return y, m

# ── 1. DEPARTMENTS ────────────────────────────────────────────────────────────
print("Creating departments...")
from apps.departments.models import Department, DepartmentCode, create_default_departments
create_default_departments()

dept_gen   = Department.objects.get(code=DepartmentCode.GENERAL_OPHTHALMOLOGY)
dept_ret   = Department.objects.get(code=DepartmentCode.RETINA)
dept_glauc = Department.objects.get(code=DepartmentCode.GLAUCOMA)
dept_ped   = Department.objects.get(code=DepartmentCode.PEDIATRIC)
dept_ref   = Department.objects.get(code=DepartmentCode.REFRACTION)
dept_cat   = Department.objects.get(code=DepartmentCode.CATARACT)
dept_lab   = Department.objects.get(code=DepartmentCode.LABORATORY)
dept_inv   = Department.objects.get(code=DepartmentCode.INVESTIGATION)
dept_corn      = Department.objects.filter(code=DepartmentCode.CORNEA).first() or dept_gen
dept_neuro     = Department.objects.filter(code=DepartmentCode.NEURO_OPH).first() or dept_gen
dept_uveitis   = Department.objects.filter(code=DepartmentCode.UVEITIS).first() or dept_gen
dept_oculoplasty = Department.objects.filter(code=DepartmentCode.OCULOPLASTICS).first() or dept_gen
dept_lv        = Department.objects.filter(code=DepartmentCode.LOW_VISION).first() or dept_gen

print(f"  {Department.objects.count()} departments ready.")

# ── 2. STAFF ACCOUNTS ─────────────────────────────────────────────────────────
print("Creating staff accounts...")
from apps.accounts.models import User, UserRole

def make_user(email, first, last, role, dept, emp_id, password='EHR@2024'):
    u, created = User.objects.get_or_create(email=email, defaults={
        'username': email.split('@')[0],
        'first_name': first,
        'last_name': last,
        'role': role,
        'department': dept,
        'employee_id': emp_id,
        'must_change_password': False,
        'is_active': True,
    })
    if created:
        u.set_password(password)
        u.save()
    return u

# Fix super admin
try:
    admin = User.objects.get(email='admin@ehr.com')
    admin.first_name = 'Bryan'
    admin.last_name = 'Admin'
    admin.role = UserRole.SUPER_ADMIN
    admin.must_change_password = False
    admin.save()
except User.DoesNotExist:
    pass

med_dir     = make_user('dr.james@ehr.com',      'James',    'Atanga',      UserRole.MEDICAL_DIRECTOR,           dept_gen,   'EMP001')
ceo_user    = make_user('ceo@ehr.com',            'Emmanuel', 'Mbarga',      UserRole.CEO,                        dept_gen,   'EMP000')
retina_dr   = make_user('dr.sarah@ehr.com',       'Sarah',    'Mbeki',       UserRole.RETINA_SPECIALIST,          dept_ret,   'EMP002')
glauc_dr    = make_user('dr.paul@ehr.com',        'Paul',     'Nkemdirim',   UserRole.GLAUCOMA_SPECIALIST,        dept_glauc, 'EMP003')
ped_dr      = make_user('dr.alice@ehr.com',       'Alice',    'Tchamba',     UserRole.PEDIATRIC_OPHTHALMOLOGIST,  dept_ped,   'EMP004')
optom       = make_user('optom.john@ehr.com',     'John',     'Fokou',       UserRole.OPTOMETRIST,                dept_ref,   'EMP005')
cataract_dr = make_user('dr.felix@ehr.com',       'Felix',    'Ngwa',        UserRole.CATARACT_SURGEON,           dept_cat,   'EMP006')
corn_dr      = make_user('dr.ruth@ehr.com',        'Ruth',     'Abanda',      UserRole.CORNEA_SPECIALIST,           dept_corn,      'EMP015')
neuro_dr     = make_user('dr.simon@ehr.com',       'Simon',    'Ebong',       UserRole.NEURO_OPHTHALMOLOGIST,      dept_neuro,     'EMP016')
uveitis_dr   = make_user('dr.olivia@ehr.com',      'Olivia',   'Ndikum',      UserRole.UVEITIS_SPECIALIST,         dept_uveitis,   'EMP017')
oculoplasty_dr = make_user('dr.joseph@ehr.com',    'Joseph',   'Mbiya',       UserRole.OCULOPLASTICS_SURGEON,      dept_oculoplasty,'EMP018')
lv_spec      = make_user('lv.amara@ehr.com',       'Amara',    'Essien',      UserRole.OPTOMETRIST,                dept_lv,        'EMP019')
nurse1      = make_user('nurse.grace@ehr.com',    'Grace',    'Biya',        UserRole.NURSE,                      dept_gen,   'EMP007')
nurse2      = make_user('nurse.peter@ehr.com',    'Peter',    'Ndongo',      UserRole.NURSE,                      dept_gen,   'EMP008')
recept1     = make_user('recept.mary@ehr.com',    'Mary',     'Enow',        UserRole.RECEPTIONIST,               dept_gen,   'EMP009')
recept2     = make_user('recept.linda@ehr.com',   'Linda',    'Tabi',        UserRole.RECEPTIONIST,               dept_gen,   'EMP010')
billing_off = make_user('billing.tom@ehr.com',    'Tom',      'Musa',        UserRole.BILLING_OFFICER,            dept_gen,   'EMP011')
lab_tech    = make_user('labtech.ann@ehr.com',    'Ann',      'Obi',         UserRole.LAB_TECHNICIAN,             dept_lab,   'EMP012')
inv_tech    = make_user('invtech.ray@ehr.com',    'Raymond',  'Nkeng',       UserRole.INVESTIGATION_TECHNICIAN,   dept_inv,   'EMP013')
pharmacist  = make_user('pharma.ada@ehr.com',     'Ada',      'Ekwueme',     UserRole.PHARMACIST,                 dept_gen,   'EMP014')

print(f"  {User.objects.count()} staff accounts ready.")

# ── 3. DIAGNOSES ──────────────────────────────────────────────────────────────
print("Creating diagnoses catalogue...")
from apps.consultations.models import Diagnosis

diagnoses_data = [
    ('H40.1', 'Open-angle glaucoma'),
    ('H40.2', 'Angle-closure glaucoma'),
    ('H26.9', 'Unspecified cataract'),
    ('H26.0', 'Infantile and juvenile cataract'),
    ('H35.3', 'Degeneration of macula and posterior pole'),
    ('H35.6', 'Retinal haemorrhage'),
    ('H52.1', 'Myopia'),
    ('H52.0', 'Hypermetropia'),
    ('H52.2', 'Astigmatism'),
    ('H10.1', 'Acute atopic conjunctivitis'),
    ('H10.4', 'Chronic conjunctivitis'),
    ('H16.0', 'Corneal ulcer'),
    ('H16.1', 'Other superficial keratitis'),
    ('H33.0', 'Retinal detachment with retinal break'),
    ('H36.0', 'Diabetic retinopathy'),
    ('H57.1', 'Ocular pain'),
    ('H04.2', 'Epiphora'),
    ('H02.0', 'Entropion and trichiasis of eyelid'),
    ('H50.0', 'Convergent concomitant strabismus'),
    ('H53.1', 'Subjective visual disturbances'),
    ('H18.0', 'Corneal pigmentations and deposits'),
    ('H20.0', 'Acute and subacute iridocyclitis'),
    ('H25.1', 'Age-related nuclear cataract'),
    ('H34.2', 'Other retinal artery occlusions'),
    ('H35.0', 'Background retinopathy and retinal vascular changes'),
    ('B73',   'Onchocerciasis with eye disease'),
    ('H53.0', 'Amblyopia ex anopsia'),
    ('H49.0', 'Third nerve palsy'),
    ('H44.0', 'Purulent endophthalmitis'),
    ('H30.1', 'Disseminated chorioretinal inflammation'),
]
diag_objects = []
for code, desc in diagnoses_data:
    d, _ = Diagnosis.objects.get_or_create(icd10_code=code, defaults={
        'description': desc, 'is_ophthalmic': True,
    })
    diag_objects.append(d)
print(f"  {len(diag_objects)} diagnoses ready.")

# ── 4. PATIENTS (40 patients) ─────────────────────────────────────────────────
print("Creating patients...")
from apps.patients.models import Patient, Visit, VisitStatus, VisitType, BillingType, Gender, BloodGroup, MedicalHistory

patients_raw = [
    ('EHR-0001', 'Emeka',       'Okafor',     '1975-03-12', 'M', 'O+',  '678123456', 'Yaounde',   'Centre',    'SELF_PAY'),
    ('EHR-0002', 'Fatima',      'Hassan',     '1990-07-22', 'F', 'A+',  '677234567', 'Douala',    'Littoral',  'INSURANCE'),
    ('EHR-0003', 'Jean',        'Mbarga',     '1968-11-05', 'M', 'B+',  '699345678', 'Bafoussam', 'West',      'SELF_PAY'),
    ('EHR-0004', 'Ngo',         'Nkengasong', '1983-02-18', 'F', 'AB+', '655456789', 'Yaounde',   'Centre',    'NHIS'),
    ('EHR-0005', 'Samuel',      'Eto',        '1955-09-30', 'M', 'O-',  '676567890', 'Buea',      'South West','SELF_PAY'),
    ('EHR-0006', 'Christelle',  'Fon',        '2005-04-14', 'F', 'A-',  '671678901', 'Bamenda',   'North West','SELF_PAY'),
    ('EHR-0007', 'Ibrahim',     'Yusuf',      '1945-12-01', 'M', 'B-',  '650789012', 'Garoua',    'North',     'INSURANCE'),
    ('EHR-0008', 'Patience',    'Akomo',      '1998-06-25', 'F', 'O+',  '678890123', 'Yaounde',   'Centre',    'SELF_PAY'),
    ('EHR-0009', 'Chukwudi',    'Eze',        '1972-08-08', 'M', 'A+',  '677901234', 'Limbe',     'South West','SELF_PAY'),
    ('EHR-0010', 'Amina',       'Bello',      '1988-01-17', 'F', 'AB-', '699012345', 'Yaounde',   'Centre',    'NHIS'),
    ('EHR-0011', 'Etienne',     'Ndoumbe',    '1960-05-20', 'M', 'O+',  '655123456', 'Kribi',     'South',     'SELF_PAY'),
    ('EHR-0012', 'Marie',       'Tientcheu',  '1935-10-10', 'F', 'B+',  '676234567', 'Yaounde',   'Centre',    'SELF_PAY'),
    ('EHR-0013', 'David',       'Wainaina',   '1980-03-03', 'M', 'O+',  '671345678', 'Douala',    'Littoral',  'INSURANCE'),
    ('EHR-0014', 'Blessing',    'Obi',        '2010-09-15', 'F', 'A+',  '650456789', 'Yaounde',   'Centre',    'SELF_PAY'),
    ('EHR-0015', 'Alain',       'Fotso',      '1965-07-07', 'M', 'AB+', '678567890', 'Bangangte', 'West',      'SELF_PAY'),
    ('EHR-0016', 'Rose',        'Manga',      '1978-12-25', 'F', 'O+',  '677678901', 'Ebolowa',   'South',     'INSURANCE'),
    ('EHR-0017', 'Patrice',     'Essomba',    '1952-04-04', 'M', 'A-',  '699789012', 'Yaounde',   'Centre',    'SELF_PAY'),
    ('EHR-0018', 'Celestine',   'Abena',      '1995-08-19', 'F', 'B+',  '655890123', 'Douala',    'Littoral',  'NHIS'),
    ('EHR-0019', 'Thomas',      'Ngono',      '1963-06-11', 'M', 'O+',  '676901234', 'Mbalmayo',  'Centre',    'SELF_PAY'),
    ('EHR-0020', 'Adjoa',       'Asante',     '1987-11-30', 'F', 'AB+', '671012345', 'Yaounde',   'Centre',    'SELF_PAY'),
    ('EHR-0021', 'Rodrigue',    'Onana',      '1970-02-14', 'M', 'A+',  '650123456', 'Yagoua',    'Far North', 'SELF_PAY'),
    ('EHR-0022', 'Veronique',   'Ngo Balla',  '1982-07-08', 'F', 'O-',  '678234567', 'Sangmelima','South',     'INSURANCE'),
    ('EHR-0023', 'Moussa',      'Adamou',     '1958-03-22', 'M', 'B+',  '677345678', 'Maroua',    'Far North', 'SELF_PAY'),
    ('EHR-0024', 'Solange',     'Bilong',     '2003-01-09', 'F', 'A+',  '699456789', 'Yaounde',   'Centre',    'NHIS'),
    ('EHR-0025', 'Appolinaire', 'Zoa',        '1948-09-17', 'M', 'O+',  '655567890', 'Nkongsamba','Littoral',  'SELF_PAY'),
    ('EHR-0026', 'Henriette',   'Samba',      '1991-05-03', 'F', 'B-',  '676678901', 'Douala',    'Littoral',  'SELF_PAY'),
    ('EHR-0027', 'Aristide',    'Nkolo',      '1974-10-27', 'M', 'AB+', '671789012', 'Bertoua',   'East',      'INSURANCE'),
    ('EHR-0028', 'Nadege',      'Beyala',     '2008-06-16', 'F', 'O+',  '650890123', 'Yaounde',   'Centre',    'SELF_PAY'),
    ('EHR-0029', 'Gustave',     'Mendo',      '1966-12-05', 'M', 'A+',  '678901234', 'Edea',      'Littoral',  'SELF_PAY'),
    ('EHR-0030', 'Yvonne',      'Kotto',      '1956-08-21', 'F', 'B+',  '677012345', 'Bafia',     'Centre',    'NHIS'),
    ('EHR-0031', 'Claude',      'Owona',      '1984-04-13', 'M', 'O+',  '699123456', 'Yaounde',   'Centre',    'SELF_PAY'),
    ('EHR-0032', 'Francoise',   'Ndi',        '1943-11-28', 'F', 'A-',  '655234567', 'Obala',     'Centre',    'SELF_PAY'),
    ('EHR-0033', 'Vincent',     'Kouam',      '1977-07-19', 'M', 'AB-', '676345678', 'Bafoussam', 'West',      'INSURANCE'),
    ('EHR-0034', 'Laurette',    'Bogne',      '2000-02-28', 'F', 'O+',  '671456789', 'Dschang',   'West',      'SELF_PAY'),
    ('EHR-0035', 'Protais',     'Moto',       '1961-09-07', 'M', 'B+',  '650567890', 'Yaunde',    'Centre',    'SELF_PAY'),
    ('EHR-0036', 'Marguerite',  'Engama',     '1993-03-15', 'F', 'A+',  '678678901', 'Douala',    'Littoral',  'NHIS'),
    ('EHR-0037', 'Gervais',     'Biyong',     '1969-01-24', 'M', 'O+',  '677789012', 'Yaounde',   'Centre',    'SELF_PAY'),
    ('EHR-0038', 'Monique',     'Tsafack',    '1986-06-30', 'F', 'B+',  '699890123', 'Bafang',    'West',      'INSURANCE'),
    ('EHR-0039', 'Blaise',      'Kamga',      '1953-10-12', 'M', 'AB+', '655901234', 'Mbouda',    'West',      'SELF_PAY'),
    ('EHR-0040', 'Clotilde',    'Ngassam',    '1979-07-04', 'F', 'O-',  '676012345', 'Yaounde',   'Centre',    'SELF_PAY'),
]

allergies_list = ['', '', '', '', 'Penicillin', '', '', 'Sulphonamides', '', 'Aspirin', '']
conditions_list = [
    'Hypertension, Diabetes mellitus type 2',
    'Hypertension',
    'Diabetes mellitus type 2',
    'Sickle cell disease',
    '',
    '',
    'Hypertension, Cardiac disease',
    '',
    'Diabetes mellitus type 2',
    '',
]

created_patients = []
today = date.today()

for i, row in enumerate(patients_raw):
    pid, fn, ln, dob, sex, bg, phone, town, region, btype = row
    gender = Gender.MALE if sex == 'M' else Gender.FEMALE
    # Spread registration dates over 12 months
    reg_month_offset = i % 12
    reg_year, reg_month = months_back(11 - reg_month_offset)
    reg_date = rand_date_in_month(reg_year, reg_month)

    p, created = Patient.objects.get_or_create(patient_id=pid, defaults={
        'first_name': fn,
        'last_name': ln,
        'date_of_birth': date.fromisoformat(dob),
        'gender': gender,
        'blood_group': bg,
        'phone_number': phone,
        'village_town': town,
        'region': region,
        'country': 'Cameroon',
        'nationality': 'Cameroonian',
        'registered_by': recept1,
    })
    # Store btype for use when creating visits
    p._btype = btype
    if created:
        # Backdate registration
        Patient.objects.filter(pk=p.pk).update(created_at=datetime.combine(reg_date, time(8, 0)))
        p.refresh_from_db()

    MedicalHistory.objects.get_or_create(patient=p, defaults={
        'chronic_conditions': conditions_list[i % len(conditions_list)],
        'known_allergies': allergies_list[i % len(allergies_list)],
        'spectacle_history': 'Wearing glasses for 5 years' if i % 3 == 0 else '',
        'family_ocular_history': random.choice(['Glaucoma in parent', 'Cataract in sibling', 'None known', '']),
    })
    created_patients.append(p)

print(f"  {Patient.objects.count()} patients ready.")

# ── 5. VISITS & CONSULTATIONS (spread across 12 months) ──────────────────────
# Clear previous seed data so re-running gives clean, correct data
print("Clearing old visits and consultations...")
from apps.consultations.models import Consultation, ConsultationStatus, ConsultationDiagnosis
ConsultationDiagnosis.objects.all().delete()
Consultation.objects.all().delete()
Visit.objects.all().delete()
print("Creating visits and consultations (12 months of data)...")

doctors_depts = [
    (med_dir,     dept_gen),
    (retina_dr,   dept_ret),
    (glauc_dr,    dept_glauc),
    (ped_dr,      dept_ped),
    (optom,       dept_ref),
    (cataract_dr, dept_cat),
    (corn_dr,          dept_corn),
    (neuro_dr,         dept_neuro),
    (uveitis_dr,       dept_uveitis),
    (oculoplasty_dr,   dept_oculoplasty),
    (lv_spec,          dept_lv),
]

complaints = [
    "Blurred vision for 3 months",
    "Eye pain and headache",
    "Floaters and flashes of light",
    "Difficulty seeing at night",
    "Red eye and discharge",
    "Gradual loss of central vision",
    "Double vision",
    "Foreign body sensation",
    "Watering eyes",
    "Decreased vision after trauma",
    "Itching and burning sensation",
    "Swollen eyelid",
    "Difficulty reading small print",
    "Halos around lights",
    "Loss of side vision",
    "Child not seeing well at school",
    "Eye deviation noticed by family",
    "Sudden loss of vision in one eye",
    "Eye injury from tree branch",
    "Routine annual check (diabetic)",
]

plans = [
    "Start Timolol 0.5% BD + Latanoprost nocte. Review in 4 weeks with IOP check.",
    "Phacoemulsification surgery planned for right eye. Pre-op biometry ordered.",
    "Anti-VEGF injection (Bevacizumab) 1.25mg intravitreal. Review in 6 weeks.",
    "Prescribe spectacles: RE -2.50/-0.75x180, LE -2.00/-0.50x175. Review in 1 year.",
    "Topical Tobramycin 0.3% QID for 7 days. Lubricating drops TDS. Review in 1 week.",
    "Continue current therapy. Humphrey VF and OCT nerve fibre analysis arranged.",
    "Patching therapy 2 hours daily for amblyopia. Review in 6 weeks.",
    "Urgent retinal laser planned. Avoid heavy lifting. Review post-laser in 2 weeks.",
    "Systemic acetazolamide 250mg QDS. Urgent gonioscopy. Review in 24 hours.",
    "Corneal scraping for culture. Natamycin 5% hourly. Admit for close monitoring.",
    "Refer to retina for further assessment. Continue lubricating drops.",
    "Reassure. Dry eye confirmed. Preservative-free artificial tears QID.",
]

hist_templates = [
    "Patient reports {} for approximately {}. No prior eye surgery. On antihypertensives.",
    "Presenting with {} since {}. Family history of glaucoma. No known allergies.",
    "Gradual onset of {} over {}. Diabetic for 10 years, poorly controlled.",
    "Acute onset of {} {}. No prior eye problems. Referred from primary health centre.",
    "Recurrent {} over {}. On spectacles since childhood. No systemic illness.",
]

ocular_histories = [
    "No previous eye surgery. Spectacle wearer since age 12.",
    "Previous trabeculectomy right eye 2019. Cataract surgery left eye 2021.",
    "No significant ocular history. First presentation.",
    "History of recurrent iritis. Last episode 2022.",
    "Previous LASIK surgery bilateral 2015. No complications reported.",
    "Penetrating ocular trauma right eye in childhood. No light perception RE since.",
    "Regular follow-up for diabetic retinopathy since 2018.",
    "Previous intravitreal injections x3 right eye for AMD.",
    "Childhood squint — operated age 6. Residual amblyopia right eye.",
    "No prior ocular treatment. Glasses prescribed at age 30.",
]

systemic_histories = [
    "Hypertension — on Amlodipine 5mg OD. Diabetes mellitus type 2 — on Metformin 500mg BD.",
    "No known systemic illness. No regular medications.",
    "Hypertension — on Lisinopril 10mg OD. Hypercholesterolaemia — on statin.",
    "Sickle cell disease (HbSS). On folic acid and hydroxyurea.",
    "Diabetes mellitus type 2 poorly controlled (HbA1c 9.8%). On insulin.",
    "No systemic illness. Non-smoker, no alcohol.",
    "HIV positive — on ARV therapy (TDF/3TC/DTG). CD4 count 450.",
    "Thyroid disease — on levothyroxine 100mcg. Cardiac arrhythmia.",
    "Rheumatoid arthritis — on Methotrexate and Hydroxychloroquine.",
    "Hypertension and CKD stage 3 — on Amlodipine and Furosemide.",
]

drug_histories = [
    "Timolol 0.5% eye drops BD bilaterally. Latanoprost 0.005% nocte bilateral.",
    "No current eye medications. On systemic antihypertensives.",
    "Tobramycin 0.3% QID, started 5 days ago. Artificial tears TDS.",
    "Prednisolone 1% hourly (tapering). Atropine 1% BD right eye.",
    "No current medications. NKDA.",
    "Bevacizumab intravitreal injections — last received 6 weeks ago.",
    "Acetazolamide 250mg QID — started 3 days ago for IOP control.",
    "Cyclosporin 0.1% eye drops BD for dry eye. Artificial tears PRN.",
    "Hydroxychloroquine 400mg OD for RA — screening for maculopathy.",
    "Brimonidine 0.2% BD + Dorzolamide 2% TDS + Latanoprost nocte.",
]

family_histories = [
    "Father: glaucoma (bilateral). Maternal uncle: cataract surgery.",
    "No known family ocular history.",
    "Mother: age-related macular degeneration. No glaucoma history.",
    "Sibling with retinitis pigmentosa. Father: diabetes with retinopathy.",
    "No significant family history.",
    "Maternal grandmother: bilateral blindness (unknown cause).",
    "Father: high myopia. No other ocular family history.",
    "Strabismus in two siblings. Father: amblyopia.",
    "Strong family history of glaucoma — father and two paternal uncles affected.",
    "No family history of eye disease. No consanguinity.",
]


def make_exam_findings():
    """Return a correctly structured examination_findings dict matching get_default_examination_template()."""
    return {
        'visual_acuity': {
            'right_unaided':       random.choice(['6/6', '6/9', '6/12', '6/18', '6/24', '6/36', '6/60']),
            'left_unaided':        random.choice(['6/6', '6/9', '6/12', '6/18', '6/24', '6/36']),
            'right_pinhole':       random.choice(['6/6', '6/9', '6/12']),
            'left_pinhole':        random.choice(['6/6', '6/9', '6/12']),
            'right_best_corrected': random.choice(['6/6', '6/9', '6/12']),
            'left_best_corrected':  random.choice(['6/6', '6/9', '6/12']),
        },
        'intraocular_pressure': {
            'right':  random.randint(10, 30),
            'left':   random.randint(10, 30),
            'method': random.choice(['Non-Contact Tonometry', 'Goldmann Applanation', 'iCare Rebound']),
        },
        'anterior_segment': {
            'right': random.choice([
                'Clear cornea, deep AC, round reactive pupil, clear lens',
                'Nuclear sclerosis grade II, cornea clear, AC deep and quiet',
                'Corneal haze inferior quadrant, AC cells 1+, pupil reactive',
                'Clear cornea, AC quiet, mild cortical lens changes',
                'Pseudophakic — IOL centred, posterior capsule clear',
            ]),
            'left': random.choice([
                'Normal cornea, AC quiet, round pupil, clear lens',
                'Nuclear sclerosis grade I, otherwise normal anterior segment',
                'Peaked pupil, AC flare 2+, KPs on endothelium',
                'Clear cornea, shallow AC, angle appositionally closed',
                'Dense posterior sub-capsular cataract, reduced fundal view',
            ]),
        },
        'posterior_segment': {
            'right': random.choice([
                'Healthy disc C:D 0.3, macula flat, vessels normal calibre, no peripheral pathology',
                'Disc cupping 0.8, nasal RNFL thinning, macula normal, inferior arcuate defect',
                'Dot-blot haemorrhages, hard exudates within macular area, NVD grade 1',
                'Macular drusen medium-large, pigmentary changes, no choroidal neovascularisation',
                'Peripheral lattice degeneration 3 clock hours inferiorly, one small round break — flat',
            ]),
            'left': random.choice([
                'Healthy disc, macula flat, no peripheral pathology',
                'Disc pallor temporal, attenuated vessels, bone-spicule pigmentation periphery',
                'NVD grade 2, fibrovascular proliferation, vitreous haze 1+',
                'Subretinal fluid temporal to fovea, elevated pigment epithelial detachment',
                'Normal fundus appearance — no pathology detected',
            ]),
        },
        'pupils': random.choice([
            'Equal, round, reactive to light, no RAPD',
            'RAPD present right eye (Marcus Gunn — swinging torch test)',
            'Equal and reactive, mildly sluggish bilaterally',
            'Dilated right eye — pharmacological mydriasis (tropicamide)',
        ]),
        'ocular_motility': random.choice([
            'Full and conjugate in all directions of gaze',
            'Restricted elevation right eye — superior rectus palsy suspected',
            'Esotropia 30PD primary position, full ductions bilaterally',
            'Gaze-evoked horizontal nystagmus bilaterally',
        ]),
        'cover_test': random.choice([
            'Orthophoric at distance and near',
            'Exophoria 8PD at distance, ortho at near',
            'Esotropia 25PD distance, 20PD near',
            'Microtropia with identity',
        ]),
        'color_vision': random.choice([
            'Normal (Ishihara 17/17 bilaterally)',
            'Red-green deficiency OD (8/17 Ishihara)',
            'Normal bilaterally — full Ishihara',
            'Reduced OD (10/17 Ishihara) — optic nerve pathology',
        ]),
        'confrontation_fields': random.choice([
            'Full to confrontation bilaterally — no defect detected',
            'Superior arcuate defect right eye on confrontation',
            'Inferior nasal step left eye — confirmed on Humphrey VF',
            'Bitemporal hemianopia — chiasmal lesion suspected',
        ]),
        'slit_lamp': {
            'lids_lashes':     random.choice(['Normal lids and lashes bilaterally', 'Mild blepharitis posterior lid margin', 'Entropion right lower lid, trichiasis']),
            'conjunctiva':     random.choice(['Clear bilaterally', 'Mild conjunctival injection, no discharge', 'Follicular reaction inferior fornix', 'Chemosis present, hyperaemia 2+']),
            'cornea':          random.choice(['Clear bilaterally', 'Corneal scar central OD', 'Superficial punctate keratitis inferiorly', 'Dense central leucoma RE']),
            'anterior_chamber': random.choice(['Deep and quiet bilaterally', 'Cells 1+ flare 1+ OD', 'Deep, cells 2+, fibrin strand present', 'Shallow, no cells or flare']),
            'iris':            random.choice(['Normal architecture bilaterally', 'Posterior synechiae 3 and 9 o\'clock OD', 'Rubeosis iridis — NVI at pupil margin', 'Normal']),
            'lens':            random.choice(['Clear bilaterally', 'Nuclear sclerosis grade II OD, grade I OS', 'Posterior sub-capsular opacity OD', 'Pseudophakic IOL in place, posterior capsule clear']),
        },
    }


def make_dept_specific_data(dept):
    """Return realistic department_specific_data matching exact keys used in clinical display templates."""

    if dept == dept_gen:
        return {
            # VA table
            'va_re_unaided': random.choice(['6/6', '6/9', '6/12', '6/18', '6/24']),
            'va_le_unaided': random.choice(['6/6', '6/9', '6/12', '6/18', '6/24']),
            'va_re_ph':      random.choice(['6/6', '6/9', '6/12']),
            'va_le_ph':      random.choice(['6/6', '6/9', '6/12']),
            'va_re_bcva':    random.choice(['6/6', '6/9', '6/12']),
            'va_le_bcva':    random.choice(['6/6', '6/9', '6/12']),
            'va_re_near':    random.choice(['N6', 'N8', 'N10', 'N12']),
            'va_le_near':    random.choice(['N6', 'N8', 'N10']),
            'va_method':     'Snellen Chart at 6m',
            'va_remarks':    'Patient cooperative. Results reliable.',
            # Refraction
            'rx_re_sphere':  round(random.uniform(-5.0, 3.0), 2),
            'rx_re_cyl':     round(random.uniform(-2.5, 0), 2),
            'rx_re_axis':    random.randint(1, 180),
            'rx_re_add':     random.choice(['', '+1.50', '+2.00', '+2.50']),
            'rx_re_va':      random.choice(['6/6', '6/9', '6/12']),
            'rx_le_sphere':  round(random.uniform(-5.0, 3.0), 2),
            'rx_le_cyl':     round(random.uniform(-2.5, 0), 2),
            'rx_le_axis':    random.randint(1, 180),
            'rx_le_add':     random.choice(['', '+1.50', '+2.00', '+2.50']),
            'rx_le_va':      random.choice(['6/6', '6/9', '6/12']),
            'rx_type':       random.choice(['Distance', 'Reading', 'Bifocal', 'Progressive']),
            'rx_lens_type':  random.choice(['Single Vision', 'Bifocal', 'Progressive addition lens']),
            # Cover test & motility
            'cover_test':    random.choice(['Orthophoric', 'Exophoria 8PD distance', 'Microtropia with identity']),
            'motility':      'Full in all directions of gaze',
            'rapd':          random.choice(['Absent', 'Absent', 'Present right eye']),
            'color_vision':  random.choice(['Normal (Ishihara 17/17)', 'Reduced OD (12/17)']),
            # Adnexa
            'adnexa_re':     random.choice(['Normal lids, no ptosis, no lag', 'Mild blepharitis, no entropion', 'Normal']),
            'adnexa_le':     'Normal',
            # Slit lamp
            'sl_conjunctiva_re':       'Clear, no injection',
            'sl_conjunctiva_le':       'Clear, no injection',
            'sl_cornea_re':            random.choice(['Clear cornea, no staining', 'SPK inferiorly 1+', 'Old scar inferior paracentral — stable']),
            'sl_cornea_le':            'Clear cornea, no staining',
            'sl_anterior_chamber_re':  'Deep and quiet',
            'sl_anterior_chamber_le':  'Deep and quiet',
            'sl_iris_re':              'Normal architecture, no NVI',
            'sl_iris_le':              'Normal architecture',
            'sl_pupil_re':             f'{random.randint(3,5)}mm, round, reactive to light',
            'sl_pupil_le':             f'{random.randint(3,5)}mm, round, reactive to light',
            'sl_lens_re':              random.choice(['Clear', 'Nuclear sclerosis grade I', 'Nuclear sclerosis grade II', 'Posterior sub-capsular opacity']),
            'sl_lens_le':              random.choice(['Clear', 'Nuclear sclerosis grade I', 'Cortical spokes']),
            # IOP
            'iop_re':     random.randint(10, 24),
            'iop_le':     random.randint(10, 24),
            'iop_method': 'Non-Contact Tonometry',
            'iop_time':   '10:00 AM',
            # Posterior segment
            'fundus_method':  'Direct ophthalmoscopy',
            'fundus_dilated': 'Dilated (Tropicamide 1%)',
            'disc_re':        random.choice(['Pink, healthy disc, C:D 0.4, sharp margins', 'Disc C:D 0.6, inferior notching', 'Pale disc, temporal pallor']),
            'disc_le':        random.choice(['Pink, healthy disc, C:D 0.3', 'Normal disc', 'C:D 0.5, healthy neuroretinal rim']),
            'macula_re':      random.choice(['Flat, foveal reflex present', 'Drusen medium, foveal reflex dull', 'CSME — hard exudates within 500 microns']),
            'macula_le':      random.choice(['Flat, foveal reflex present', 'Normal macular appearance']),
            'periphery_re':   random.choice(['No peripheral pathology', 'Lattice degeneration 2 clock hours']),
            'periphery_le':   'No peripheral pathology',
            'vitreous_re':    random.choice(['Clear', 'Posterior vitreous detachment', 'Mild syneresis']),
            'vitreous_le':    'Clear',
            # Summary diagnosis
            'diagnosis_re':      '',
            'diagnosis_le':      '',
            'diagnosis_summary': '',
        }

    elif dept == dept_ret:
        return {
            'va_od_un':    random.choice(['6/9', '6/12', '6/18', '6/24', '6/36', 'CF 2m']),
            'va_os_un':    random.choice(['6/9', '6/12', '6/18', '6/24', '6/36']),
            'bcva_od':     random.choice(['6/6', '6/9', '6/12', '6/18']),
            'bcva_os':     random.choice(['6/6', '6/9', '6/12']),
            'iop_od':      random.randint(12, 22),
            'iop_os':      random.randint(12, 22),
            'macula_od':   random.choice([
                'Flat and dry, foveal reflex present, no exudates',
                'Clinically significant macular oedema — hard exudates within 500um of fovea',
                'Subretinal fluid temporal to fovea, no haemorrhage',
                'Geographic atrophy, outer retinal atrophy, dry AMD changes',
                'Drusen medium-large, pigmentary changes, RPE disturbance',
            ]),
            'macula_os':   random.choice([
                'Flat and dry, foveal reflex present',
                'CMO confirmed on OCT — CRT 380um',
                'Choroidal neovascular membrane — active leakage on FFA',
                'Epiretinal membrane, mild macular puckering — no CMO',
            ]),
            'vitreous_od': random.choice(['Clear', 'Vitreous haemorrhage moderate', 'Mild vitreous haze 1+', 'Posterior vitreous detachment — ring visible']),
            'vitreous_os': random.choice(['Clear', 'Mild floaters, no significant haemorrhage', 'Asteroid hyalosis — visual acuity not affected']),
            'peripheral_od': random.choice([
                'Lattice degeneration 3 clock hours inferotemporally',
                'Retinal break superior 11 o\'clock — flat surrounding retina',
                'No peripheral pathology',
                'Pigmentary degeneration, bone-spicule pattern peripherally',
            ]),
            'peripheral_os': random.choice(['No peripheral pathology', 'Peripheral atrophy inferiorly', 'Lattice degeneration x2 areas']),
            'dr_grade_od': random.choice(['None', 'Mild NPDR', 'Moderate NPDR', 'Severe NPDR', 'PDR']),
            'dr_grade_os': random.choice(['None', 'Mild NPDR', 'Moderate NPDR']),
            'dme_od':      random.choice(['Absent', 'CSME present', 'Non-CSME oedema', 'Centre-involving DMO']),
            'dme_os':      random.choice(['Absent', 'Non-CSME oedema', 'CSME present']),
            'oct_findings': random.choice([
                'OCT macula OD: CRT 320um, no subretinal fluid, ELM intact. OS: CRT 285um, normal foveal contour.',
                'OCT: Intraretinal cysts OD (CRT 415um). Subretinal fluid OS (CRT 380um). ELM disrupted OD.',
                'OCT: Normal foveal contour bilaterally. No retinal thickening. RNFL intact at disc.',
                'OCT: Epiretinal membrane OD with macular pucker. CRT 350um. No full thickness macular hole.',
                'OCT: Geographic atrophy OD — outer nuclear layer loss. OS mild drusenoid PED, no fluid.',
            ]),
            'ffa_findings': random.choice([
                'FFA: Microaneurysms and dot-blot haemorrhages. Focal capillary non-perfusion. No NVD or NVE.',
                'FFA: Leakage from NVD. Fibrovascular proliferation. Extensive peripheral non-perfusion.',
                'FFA: Hyperfluorescence classic CNV. Late leakage pattern. Active choroidal neovascularisation.',
                'FFA: Blocked fluorescence from haemorrhage. No neovascularisation identified.',
                'Not performed this visit — deferred to next appointment.',
            ]),
            'treatment_given': random.choice([
                'Intravitreal Bevacizumab 1.25mg OD administered under sterile conditions. Next injection 4 weeks.',
                'Pan-retinal photocoagulation (PRP) nasal retina OD — 500 burns applied, 200um spot size.',
                'Observation only. Patient to maintain HbA1c <7.0% and BP <130/80. Review 3 months.',
                'Referred for vitreoretinal surgery — tractional retinal detachment, macula threatened.',
                'Focal laser grid therapy applied to macular oedema OS — 200um spot, 0.1s, 50mW.',
            ]),
        }

    elif dept == dept_glauc:
        return {
            'bcva_od':     random.choice(['6/6', '6/9', '6/12', '6/18']),
            'bcva_os':     random.choice(['6/6', '6/9', '6/12']),
            'near_va':     'N8 bilaterally',
            'cd_ratio_od': random.choice(['0.5', '0.6', '0.7', '0.8', '0.9', '1.0']),
            'cd_ratio_os': random.choice(['0.5', '0.6', '0.7', '0.8', '0.9']),
            'disc_od':     random.choice([
                'Vertical C:D elongation, notching inferior pole, RNFL wedge defect inferotemporal',
                'Large cup C:D 0.8, temporal rim pallor, cup-disc asymmetry >0.2',
                'Physiological cup C:D 0.4, healthy neuroretinal rim, no RNFL defect',
                'Disc haemorrhage 7 o\'clock, C:D 0.8, thin inferior rim — Drance haemorrhage',
            ]),
            'disc_os':     random.choice([
                'Healthy rim, no notching, RNFL intact on OCT',
                'Inferior notching, C:D 0.7, RNFL thinning inferotemporally',
                'End-stage glaucoma — total cupping, minimal rim tissue remaining',
                'Normal disc appearance — no suspicious features',
            ]),
            'iop_od':      random.randint(14, 38),
            'iop_os':      random.randint(14, 38),
            'cct_od':      random.randint(490, 580),
            'cct_os':      random.randint(490, 580),
            'gonio_od':    random.choice(['Open angle grade 4 Shaffer, no PAS', 'Narrow angle grade 2, PAS 90 degrees', 'Open angle grade 3, trabecular meshwork visible', 'Closed angle, goniosynechiae 180 degrees']),
            'gonio_os':    random.choice(['Open angle grade 4 Shaffer', 'Open angle grade 3', 'Grade 2, heavy trabecular pigment']),
            'vf_md_od':    round(random.uniform(-18.0, -1.0), 1),
            'vf_md_os':    round(random.uniform(-12.0, -1.0), 1),
            'vf_psd_od':   round(random.uniform(1.5, 8.0), 1),
            'vf_psd_os':   round(random.uniform(1.5, 6.0), 1),
            'vf_ght_od':   random.choice(['Outside Normal Limits', 'Within Normal Limits', 'Borderline', 'General Reduction of Sensitivity']),
            'vf_ght_os':   random.choice(['Outside Normal Limits', 'Within Normal Limits', 'Borderline']),
            'vf_type':     'Humphrey 24-2 SITA Standard',
            'vf_progression': random.choice(['Stable', 'Slowly Progressing', 'Progressing — treatment intensified', 'New — no prior baseline available']),
            'rnfl_avg_od': random.randint(55, 95),
            'rnfl_avg_os': random.randint(60, 100),
            'rnfl_inf_od': random.randint(60, 110),
            'rnfl_inf_os': random.randint(65, 115),
            'rnfl_interp': random.choice([
                'Significant inferior and superior RNFL thinning consistent with glaucomatous damage',
                'Borderline RNFL thickness inferotemporally. Correlation with VF pattern recommended.',
                'RNFL within normal limits bilaterally — no atrophy detected.',
                'Severe diffuse RNFL loss bilaterally consistent with end-stage glaucoma.',
            ]),
            'rim_area_od': round(random.uniform(0.6, 1.8), 2),
            'rim_area_os': round(random.uniform(0.6, 1.8), 2),
            'target_iop':  random.choice([12, 14, 16, 18]),
            'glaucoma_meds': random.choice([
                'Timolol 0.5% BD + Latanoprost 0.005% nocte bilateral',
                'Latanoprost 0.005% nocte + Brimonidine 0.2% BD + Dorzolamide 2% TDS',
                'Monotherapy — Bimatoprost 0.01% nocte bilateral',
                'Post-trabeculectomy — Prednisolone 1% QID (week 4 taper)',
                'Fixed combination Timolol/Dorzolamide BD bilateral',
            ]),
            'compliance': random.choice(['Good — patient using drops consistently', 'Poor — admits to missing drops frequently', 'Moderate — irregular use admitted', 'Excellent — no missed doses']),
            'staging':    random.choice(['Early Glaucoma', 'Moderate Glaucoma', 'Advanced Glaucoma', 'End-Stage Glaucoma', 'Glaucoma Suspect / OHT']),
        }

    elif dept == dept_ref:
        return {
            'auto_sph_od':     round(random.uniform(-6.0, 3.0), 2),
            'auto_cyl_od':     round(random.uniform(-3.0, -0.25), 2),
            'auto_axis_od':    random.randint(1, 180),
            'va_unaided_od':   random.choice(['6/9', '6/12', '6/18', '6/24', '6/36', '6/60']),
            'va_corrected_od': random.choice(['6/6', '6/9', '6/12']),
            'auto_sph_os':     round(random.uniform(-6.0, 3.0), 2),
            'auto_cyl_os':     round(random.uniform(-3.0, -0.25), 2),
            'auto_axis_os':    random.randint(1, 180),
            'va_unaided_os':   random.choice(['6/9', '6/12', '6/18', '6/24', '6/36']),
            'va_corrected_os': random.choice(['6/6', '6/9', '6/12']),
            'final_sph_od':    round(random.uniform(-5.75, 3.0), 2),
            'final_cyl_od':    round(random.uniform(-2.75, -0.25), 2),
            'final_axis_od':   random.randint(1, 180),
            'add_od':          random.choice(['', '+1.50', '+2.00', '+2.50']),
            'bcva_od':         random.choice(['6/6', '6/9', '6/12']),
            'final_sph_os':    round(random.uniform(-5.75, 3.0), 2),
            'final_cyl_os':    round(random.uniform(-2.75, -0.25), 2),
            'final_axis_os':   random.randint(1, 180),
            'add_os':          random.choice(['', '+1.50', '+2.00', '+2.50']),
            'bcva_os':         random.choice(['6/6', '6/9', '6/12']),
            'near_vision':     random.choice(['N6 bilaterally', 'N8 bilaterally', 'N10 with addition OS']),
            'lens_type':       random.choice(['Single Vision', 'Bifocal', 'Progressive addition lens', 'Office lens']),
            'refraction_type': random.choice(['Dry refraction', 'Cycloplegic refraction (Cyclopentolate 1%)', 'Wet refraction post-cycloplegia']),
        }

    elif dept == dept_cat:
        return {
            'lens_od':      random.choice(['Nuclear sclerosis grade 3', 'Posterior sub-capsular cataract grade 2', 'Nuclear + cortical grade 2', 'Mature cataract — white, no red reflex', 'Pseudophakic — IOL centred, posterior capsule clear']),
            'lens_os':      random.choice(['Nuclear sclerosis grade 2', 'Cortical cataract grade 1', 'Nuclear sclerosis grade 3', 'Clear lens', 'Pseudophakic — IOL centred']),
            'locs_od':      random.choice(['LOCS III: NO3 NC3 C0 P1', 'LOCS III: NO4 NC4 C2 P2', 'LOCS III: NO2 NC2 C0 P0', 'LOCS III: NO5 NC5 (mature)']),
            'locs_os':      random.choice(['LOCS III: NO2 NC2 C1 P0', 'LOCS III: NO3 NC3 C0 P1', 'LOCS III: NO1 NC1 C0 P0']),
            'al_od':        round(random.uniform(22.0, 26.5), 2),
            'al_os':        round(random.uniform(22.0, 26.5), 2),
            'biom_k_od':    f'{round(random.uniform(41.0, 45.0), 2)} / {round(random.uniform(42.0, 46.0), 2)} @ {random.randint(85, 95)} deg',
            'biom_k_os':    f'{round(random.uniform(41.0, 45.0), 2)} / {round(random.uniform(42.0, 46.0), 2)} @ {random.randint(85, 95)} deg',
            'target_rx':    random.choice(['Plano (emmetropia)', '-0.50D (slight myopia for reading)', '+0.25D']),
            'iol_power_od': round(random.uniform(18.0, 24.0), 1),
            'iol_power_os': round(random.uniform(18.0, 24.0), 1),
            'iol_model':    random.choice(['Alcon SN60WF', 'AMO Tecnis ZCB00', 'Bausch & Lomb enVista MX60', 'Hoya AF-1 UV']),
            'surgery_date': str(today - timedelta(days=random.randint(7, 180))),
            'surgeon':      random.choice(['Dr. Felix Ngwa', 'Dr. James Atanga']),
            'anaesthesia':  random.choice(['Topical (proxymetacaine 0.5%)', 'Peribulbar block', 'Sub-Tenon\'s block']),
            'op_notes':     random.choice([
                'Phacoemulsification with foldable IOL implantation in-bag. Capsulorhexis 5.5mm. Hydrodissection complete. No complications.',
                'MSICS technique. Posterior chamber IOL implanted. Wound sutured 10-0 nylon 3 interrupted sutures.',
                'Uneventful phacoemulsification. 2-incision technique. BSS polish posterior capsule. OVD removed.',
                'Posterior capsule rupture — converted to ECCE. IOL placed in sulcus. No vitreous loss. Extra suture placed.',
            ]),
            'postop':       random.choice([
                'Post-op day 1: VA 6/9. Wound intact. IOL centred. IOP 14mmHg. Prednisolone 1% QID + Tobramycin BD x 4 weeks.',
                'Post-op week 1: VA 6/6. IOP 12mmHg. AC quiet. IOL centred. Good recovery.',
                'Awaiting surgery — on elective waiting list. Pre-op assessment complete.',
                'Post-op month 1: VA 6/6. Posterior capsule clear. YAG not yet needed. Discharged to optom.',
            ]),
        }

    elif dept == dept_ped:
        return {
            'va_od':         random.choice(['6/9', '6/12', '6/18', '6/24', '6/60', 'CF', 'Kay pictures: 6/9', 'LogMAR 0.3', 'Cardiff cards: 6/12']),
            'va_os':         random.choice(['6/9', '6/12', '6/18', '6/24', 'Kay pictures: 6/12']),
            'va_method':     random.choice(['Kay pictures', 'Snellen E chart', 'LogMAR chart', 'Cardiff acuity cards', 'ETDRS at 4m']),
            'fixation_od':   random.choice(['Central, steady, maintained (CSM)', 'Eccentric fixation noted', 'Unsteady, not maintained', 'Central and steady']),
            'fixation_os':   random.choice(['Central, steady, maintained', 'Central and steady', 'Eccentric fixation — amblyopia']),
            'cyclo_od':      f'{round(random.uniform(-4.0, 4.0), 2)}/{round(random.uniform(-2.0, -0.25), 2)}x{random.randint(1, 180)}',
            'cyclo_os':      f'{round(random.uniform(-4.0, 4.0), 2)}/{round(random.uniform(-2.0, -0.25), 2)}x{random.randint(1, 180)}',
            'cyclo_agent':   random.choice(['Cyclopentolate 1%', 'Atropine 1% (3-day regimen)', 'Tropicamide 1%']),
            'cover_test_dist':  random.choice(['Orthophoric', 'Esotropia 30PD', 'Exotropia 20PD', 'Left hypertropia 8PD', 'Microesotropia']),
            'cover_test_near':  random.choice(['Orthophoric', 'Esotropia 25PD', 'Exophoria 10PD', 'Same as distance']),
            'hirschberg':       random.choice(['+0 (Orthophoric)', '+15PD esotropia RE', '+20PD exotropia', 'Asymmetric corneal reflexes — RE deviated']),
            'prism_cover':      random.choice(['30PD ET, AC/A 6:1', '20PD XT intermittent', 'Orthophoric', '8PD RHT']),
            'deviation_pd':     random.choice(['30PD ET', '20PD XT', 'Orthophoric', '35PD ET with DVD']),
            'strabismus_type':  random.choice(['Infantile esotropia', 'Accommodative esotropia — fully accommodative', 'Intermittent exotropia', 'Sensory exotropia', 'None', 'DVD (Dissociated Vertical Deviation)']),
            'amblyopia':        random.choice(['Right amblyopia — moderate (2 lines difference on logMAR)', 'Left amblyopia — mild (1 line)', 'None identified', 'Bilateral amblyopia secondary to high refractive error', 'Anisometropic amblyopia right eye']),
            'bsv':              random.choice(['Present — Lang stereotest +ve (200 arcsec)', 'Absent', 'Reduced — Randot gross stereopsis only', 'Normal — Titmus 40 arcsec']),
            'patching':         random.choice(['2 hours daily — right eye patched to treat left amblyopia', '4 hours daily — right eye patched', 'Not required at present', '6 hours daily — left eye patched for right amblyopia', 'Atropine penalisation 1% left eye OD — alternative to patching']),
            'glasses':          random.choice(['+2.50/-0.75x90 OD, +2.00/-0.50x85 OS — spectacles prescribed', 'No new glasses needed — current Rx adequate', 'Bifocal +2.50 add prescribed for accommodative ET', 'Single vision -1.50/-0.75x180 OD prescribed']),
            'surgery_plan':     random.choice(['Strabismus surgery planned — bilateral medial rectus recession 4.5mm', 'No surgery at present — patching response first', 'Resection left LR + recession left MR for exotropia', 'Review in 3 months to assess patching response before surgery decision']),
        }

    elif dept == dept_corn:
        return {
            'kerato_od':      f'{round(random.uniform(40.0, 48.0), 2)} @ {random.randint(0,90)} deg / {round(random.uniform(41.0, 49.0), 2)} @ {random.randint(90,180)} deg',
            'kerato_os':      f'{round(random.uniform(40.0, 48.0), 2)} @ {random.randint(0,90)} deg / {round(random.uniform(41.0, 49.0), 2)} @ {random.randint(90,180)} deg',
            'pachymetry_od':  random.randint(440, 580),
            'pachymetry_os':  random.randint(440, 580),
            'ecc':            f'{random.randint(1800, 2800)} cells/mm2',
            'topography_od':  random.choice([
                'Inferior steepening on Placido — cone suspect. Progression from baseline +2.5D.',
                'Normal bow-tie pattern, no ectasia, indices within normal limits.',
                'Superior flattening consistent with pterygium involvement. No cone.',
                'Keratoconus stage 2 (Amsler-Krumeich). Apical cone inferiorly. Sim K 52.5D.',
            ]),
            'topography_os':  random.choice([
                'Normal topography. No suspicious indices. Sim K symmetric.',
                'Mild inferior steepening — monitor closely. No crosslinking criteria yet.',
                'Post-LASIK topography — central flattening as expected. No ectasia.',
            ]),
            'fluor_od':       random.choice([
                'Positive — central punctate staining 2+ (SPK) consistent with dry eye',
                'Negative — no epithelial defect on fluorescein',
                'Positive — geographic corneal ulcer 5x4mm central. Hypopyon 1mm.',
                'Negative — epithelium fully intact, no staining',
            ]),
            'fluor_os':       random.choice(['Negative', 'SPK 1+ inferonasal — mild dry eye', 'Negative — intact epithelium']),
            'rose_bengal':    random.choice(['Negative bilaterally', 'Positive nasal conjunctiva OU — consistent with dry eye disease', 'Not performed this visit']),
            'tbut':           f'{random.randint(3, 12)} seconds (OU)',
            'schirmer':       f'{random.randint(3, 20)}mm/5min without anaesthesia',
            'corneal_diagnosis': random.choice([
                'Keratoconus Stage 2 OD / Stage 1 OS — crosslinking candidate both eyes',
                'Bacterial corneal ulcer OD — corneal scraping sent for culture and sensitivity',
                'Dry eye disease moderate severity — MGD grade 3, reduced TBUT, SPK',
                'Fuchs endothelial dystrophy — ECC < 1500 cells/mm2, guttata on specular',
                'Recurrent corneal erosion syndrome OD — anterior basement membrane dystrophy',
                'Band keratopathy RE secondary to chronic uveitis — chelation therapy planned',
            ]),
            'corneal_plan':   random.choice([
                'Corneal crosslinking (CXL) right eye scheduled in 2 weeks. Avoid contact lenses. UV protection.',
                'Intensive Tobramycin 0.3% Q1H + Natamycin 5% Q1H. Admit for close monitoring. Culture awaited.',
                'Preservative-free artificial tears 4x/day. Warm compresses BD. Omega-3 2g supplementation.',
                'Penetrating keratoplasty (PK) right eye — on donor cornea waiting list. Expected 6-9 months.',
                'Bandage contact lens fitted right eye. Sodium hyaluronate 0.4% QID. Review in 1 week.',
            ]),
        }

    elif dept == dept_neuro:
        return {
            'va_od_un':       random.choice(['6/9', '6/12', '6/18', '6/24', '6/60', 'CF 1m', 'HM', 'PL']),
            'va_os_un':       random.choice(['6/9', '6/12', '6/18', '6/24', '6/36']),
            'neuro_bcva_od':  random.choice(['6/6', '6/9', '6/12', '6/18', '6/24']),
            'neuro_bcva_os':  random.choice(['6/6', '6/9', '6/12', '6/18']),
            'iop_od':         random.randint(10, 22),
            'iop_os':         random.randint(10, 22),
            'pupil_od':       random.choice(['Round, reactive to light and accommodation', 'Dilated, fixed — CN III palsy', 'Sluggish response', 'Mid-dilated, oval']),
            'pupil_os':       random.choice(['Round, reactive to light and accommodation', 'Round, reactive', 'Sluggish']),
            'pupil_size_od':  random.randint(2, 7),
            'pupil_size_os':  random.randint(2, 6),
            'rapd':           random.choice(['None', 'Right RAPD present — relative afferent pupillary defect', 'Left RAPD present', 'Not assessable bilaterally']),
            'cv_test':        'Ishihara 38-plate',
            'colour_od':      f'{random.randint(8, 17)}/17',
            'colour_os':      f'{random.randint(8, 17)}/17',
            'cv_defect':      random.choice(['', 'Red-green dyschromatopsia OD', 'Bilateral colour loss', 'Acquired colour deficiency']),
            'vf_pattern':     random.choice(['Normal', 'Bitemporal hemianopia', 'Right homonymous hemianopia', 'Inferior altitudinal defect', 'Arcuate scotoma', 'Central scotoma OD']),
            'vf_od':          random.choice([
                'Full fields to confrontation — no defect detected',
                'Superior temporal defect — chiasmal compression suspected',
                'Dense central scotoma — optic nerve pathology',
                'Inferior altitudinal defect — NAION pattern',
            ]),
            'vf_os':          random.choice(['Full to confrontation', 'Superior temporal defect matching OD — chiasmal pattern', 'Normal']),
            'conf_vf_od':     'Confrontation (finger counting)',
            'conf_vf_os':     'Confrontation (finger counting)',
            'hvf_md_od':      round(random.uniform(-15.0, -1.0), 1),
            'hvf_md_os':      round(random.uniform(-10.0, -1.0), 1),
            'hvf_psd_od':     round(random.uniform(1.5, 7.0), 1),
            'hvf_psd_os':     round(random.uniform(1.5, 5.0), 1),
            'disc_appearance_od': random.choice(['Normal', 'Pallor', 'Swollen', 'Hyperaemic']),
            'disc_appearance_os': random.choice(['Normal', 'Pallor', 'Normal']),
            'disc_neuro_od':  random.choice([
                'Pale disc, temporal pallor pronounced — optic atrophy',
                'Swollen, blurred margins, peripapillary splinter haemorrhage',
                'Normal pink disc, sharp margins, C:D 0.4',
                'Disc swelling with peripapillary exudates — AION pattern',
            ]),
            'disc_neuro_os':  random.choice(['Normal disc, no swelling', 'Mild temporal pallor', 'Hyperaemic disc, margins blurred']),
            'papilloedema_od': random.choice(['0 (Normal)', '1 (Mild)', '2 (Moderate)', '3 (Marked)']),
            'papilloedema_os': random.choice(['0 (Normal)', '1 (Mild)', '2 (Moderate)']),
            'rnfl_avg_od':    random.randint(55, 100),
            'rnfl_avg_os':    random.randint(55, 100),
            'rnfl_inf_od':    random.randint(60, 115),
            'rnfl_inf_os':    random.randint(60, 115),
            'oct_rnfl':       random.choice([
                'Significant temporal RNFL thinning OD consistent with optic neuropathy — correlates with central scotoma',
                'Diffuse RNFL loss bilaterally — compressive neuropathy pattern',
                'RNFL within normal limits — no atrophy on OCT',
                'Superior RNFL thinning OD — correlates with inferior altitudinal defect on HVF',
            ]),
            'cn2':  'Optic nerve — see findings above',
            'cn3':  random.choice(['Normal', 'Complete right CN III palsy — ptosis, mydriasis, exotropia', 'Partial CN III — incomplete ptosis']),
            'cn4':  random.choice(['Normal', 'Right CN IV palsy — right hypertropia worse looking down and left', 'Normal']),
            'cn5':  'Normal corneal sensation bilaterally — V1 V2 V3 intact',
            'cn6':  random.choice(['Normal', 'Right CN VI palsy — esotropia worse right gaze', 'Left CN VI palsy — left gaze restriction', 'Normal']),
            'cn7':  'Normal facial movement and tone bilaterally',
            'other_cn': random.choice(['', 'CN VIII — reduced hearing right, referred ENT', 'No other cranial nerve deficit detected']),
            'motility':   random.choice(['Full conjugate in all directions', 'Restricted elevation OD — superior rectus palsy', 'INO bilateral — MLF lesion suspected', 'Esotropia in primary position — CN VI']),
            'nystagmus':  random.choice(['None', 'Horizontal gaze-evoked bilaterally', 'Pendular nystagmus — congenital type', 'Downbeat nystagmus — cerebellar pathology']),
            'diplopia':   random.choice(['None', 'Binocular horizontal diplopia — worse right gaze', 'Vertical diplopia — worse looking down and right', 'None reported']),
            'neuro_diagnosis': random.choice([
                'Non-arteritic anterior ischaemic optic neuropathy (NAION) right eye',
                'Compressive optic neuropathy — intracranial mass on imaging',
                'Optic neuritis right eye — probable demyelinating disease (MS)',
                'Pituitary macroadenoma — bitemporal hemianopia',
                'CN III palsy — posterior communicating artery aneurysm excluded on CTA',
                'Optic disc drusen bilateral — pseudo-papilloedema',
            ]),
            'imaging_ordered': random.choice(['MRI Brain & Orbits with gadolinium contrast', 'CT Head urgent (non-contrast)', 'MRI Pituitary protocol with dynamic contrast', 'CT Angiography cerebral vessels', 'None ordered this visit']),
            'imaging_result':  random.choice(['Awaiting result', 'Normal MRI brain and orbits', 'Pituitary macroadenoma 18x15mm — neurosurgery referral made', 'Periventricular demyelinating plaques — MS neurology board notified', 'CT angiography — no aneurysm identified']),
            'neuro_referral':  random.choice(['Neurology — urgent same-week', 'Neurosurgery — urgent', 'None required', 'Neuro-radiology MDT', 'General neurology OPD — routine']),
            'neuro_impression': random.choice([
                'NAION right eye. No proven treatment to reverse visual loss. High-dose aspirin 300mg started. CV risk factors addressed — BP target <130/80, statin therapy commenced. Fellow eye risk counselled.',
                'Optic neuritis right eye — probable first MS episode. High-dose IV methylprednisolone 1g x3 days started. Neurology referral urgent. MRI requested.',
                'Bitemporal hemianopia confirmed — pituitary macroadenoma on MRI. Urgent neurosurgical referral. Endocrinology review arranged. Visual field documentation complete.',
                'Right CN III palsy. Aneurysm excluded on CTA. Diabetic microvascular aetiology most likely given HbA1c 9.2%. Expectant management — monitor monthly. Prism glasses for diplopia.',
            ]),
        }

    elif dept == dept_uveitis:
        return {
            'uveitis_type':     random.choice(['Anterior', 'Intermediate', 'Posterior', 'Panuveitis']),
            'uveitis_laterality': random.choice(['Unilateral RE', 'Unilateral LE', 'Bilateral']),
            'uveitis_onset':    random.choice(['Acute', 'Chronic', 'Recurrent']),
            'uveitis_course':   random.choice(['Acute', 'Chronic', 'Remitting']),
            'uveitis_aetiology': random.choice(['Toxoplasmosis', 'HLA-B27 Associated', 'Sarcoidosis', 'Tuberculosis', 'Idiopathic', 'Herpetic (HSV/VZV)']),
            'uveitis_aetiology_notes': random.choice(['HLA-B27 positive on testing', 'PCR confirmed toxoplasmosis', 'Elevated ACE — sarcoidosis probable', 'IGRA positive — TB uveitis', '']),
            'aq_cells_re':  random.choice(['0', '0.5+', '1+', '2+', '3+']),
            'aq_cells_le':  random.choice(['0', '0.5+', '1+', '2+']),
            'aq_flare_re':  random.choice(['0', '1+', '2+', '3+']),
            'aq_flare_le':  random.choice(['0', '1+', '2+']),
            'kp_re':        random.choice(['None', 'Fine (non-granulomatous)', 'Mutton-fat (granulomatous)']),
            'kp_le':        random.choice(['None', 'Fine (non-granulomatous)']),
            'ps_re':        random.choice(['None', 'Focal', 'Sectoral']),
            'ps_le':        'None',
            'iris_nodules_re': random.choice(['None', 'Koeppe (pupil margin)', 'Busacca (iris stroma)']),
            'iris_nodules_le': 'None',
            'hypopyon_re':  random.choice(['Absent', 'Absent', 'Present']),
            'hypopyon_le':  'Absent',
            'rubeosis_re':  random.choice(['Absent', 'Absent', 'Present']),
            'rubeosis_le':  'Absent',
            'anterior_notes': random.choice(['Mild flare in AC, no active cells this visit — improving', 'Band keratopathy noted inferonasal', 'AC quiet on steroids']),
            'iop_re':       random.randint(10, 28),
            'iop_le':       random.randint(10, 28),
            'vit_haze_re':  random.choice(['0', '0.5+', '1+', '2+']),
            'vit_haze_le':  random.choice(['0', '0.5+', '1+']),
            'ret_vasculitis_re': random.choice(['Absent', 'Periphlebitis', 'Arteritis']),
            'ret_vasculitis_le': random.choice(['Absent', 'Absent']),
            'cme_re':       random.choice(['Absent', 'Present', 'Absent']),
            'cme_le':       random.choice(['Absent', 'Absent']),
            'disc_oedema_re': random.choice(['Absent', 'Absent', 'Present']),
            'disc_oedema_le': 'Absent',
            'choroiditis_re': random.choice(['None', 'Inactive (atrophic scar)', 'Active (yellow-white)']),
            'choroiditis_le': 'None',
            'snowball_re':  random.choice(['Absent', 'Snowballs (vitreous)']),
            'snowball_le':  'Absent',
            'posterior_notes': random.choice(['Toxoplasma scar temporal to disc OD — inactive this visit', 'No posterior segment involvement', 'Active retinitis lesion superior to fovea — satellite lesion']),
            'hla_b27':      random.choice(['Positive', 'Negative', '']),
            'vdrl':         random.choice(['Non-reactive', '']),
            'tb_test':      random.choice(['Negative', 'Positive', '']),
            'toxo_serology': random.choice(['IgG positive, IgM negative', 'IgG positive, IgM positive', '']),
            'comp_cataract': random.choice(['None', 'Posterior subcapsular']),
            'comp_band_kp': random.choice(['Absent', 'Present']),
            'comp_glaucoma': random.choice(['No', 'Ocular hypertension']),
            'tx_topical_steroid': random.choice(['Prednisolone 1% Q2H tapering', 'Dexamethasone 0.1% QID', 'Prednisolone 1% QID']),
            'tx_cycloplegic': random.choice(['Atropine 1% BD', 'Cyclopentolate 1% TDS', 'Homatropine 2% BD']),
            'tx_iop':       random.choice(['Timolol 0.5% BD', 'Dorzolamide 2% TDS', '']),
            'tx_systemic_steroid': random.choice(['Prednisolone 60mg OD tapering by 10mg weekly', '']),
            'tx_antimicrobial': random.choice(['TMP-SMX DS 960mg BD x 6 weeks', 'Acyclovir 400mg 5x/day', '']),
            'management_plan': random.choice([
                'Toxoplasma chorioretinitis — TMP-SMX DS BD x 6 weeks. Prednisolone 40mg OD started 48h after antibiotics. Pred Forte tapering QH→TDS over 4 weeks. Review 2 weeks.',
                'HLA-B27+ acute anterior uveitis. Pred Forte 1% Q1H for 1 week then taper. Atropine 1% BD x 1 week. IOP monitored — currently safe. Systemic workup for spondyloarthropathy.',
                'Idiopathic panuveitis. Systemics started. Methotrexate 15mg weekly under rheumatology co-management. LFTs to be checked in 4 weeks.',
            ]),
            'review_in':    random.choice(['2 weeks', '1 month', '3 months']),
        }

    elif dept == dept_oculoplasty:
        return {
            'mrd1_od':      round(random.uniform(1.5, 4.5), 1),
            'mrd1_os':      round(random.uniform(1.5, 4.5), 1),
            'mrd2_od':      round(random.uniform(4.5, 6.0), 1),
            'mrd2_os':      round(random.uniform(4.5, 6.0), 1),
            'lagoph_od':    random.choice(['0', '1', '2', '0']),
            'lagoph_os':    '0',
            'ptosis_type_od': random.choice(['None', 'Aponeurotic', 'Congenital', 'Myogenic', 'Mechanical']),
            'ptosis_type_os': random.choice(['None', 'None', 'None']),
            'levator_od':   round(random.uniform(4.0, 15.0), 1),
            'levator_os':   round(random.uniform(10.0, 15.0), 1),
            'fissure_od':   round(random.uniform(6.0, 11.0), 1),
            'fissure_os':   round(random.uniform(7.0, 11.0), 1),
            'bells':        random.choice(['Positive OD & OS', 'Positive OD only', 'Negative']),
            'lid_condition': random.choice([
                'OD: Aponeurotic ptosis, moderate. OS: Normal lid position and contour.',
                'OD: Upper lid lesion — papilloma, pedunculated, 4mm. OS: Normal.',
                'OU: Dermatochalasis, moderate. No functional visual obstruction.',
                'OD: Involutional ectropion lower lid, moderate — exposed conjunctiva, no corneal involvement.',
            ]),
            'lacrimal':     random.choice(['Patent bilaterally on syringing', 'Blocked right lacrimal duct — regurgitation on syringing', 'Partially patent left — mild resistance']),
            'dcr_status':   random.choice(['Pre-operative — awaiting DCR', 'Post-DCR — tube removed, patient well', 'No DCR — conservative management']),
            'hertel_od':    round(random.uniform(14.0, 20.0), 1),
            'hertel_os':    round(random.uniform(14.0, 20.0), 1),
            'orbital':      random.choice(['No mass, no bruit, no enophthalmos', 'Soft tissue mass superomedial OD — biopsy planned', 'Post-trauma — orbital floor fracture repaired']),
            'cas_score':    random.choice(['', '1', '2', '3', '4']),
            'ted_phase':    random.choice(['Active (inflammatory)', 'Inactive (stable)', 'Not applicable']),
            'exposure_risk': random.choice(['Low', 'Moderate', 'High — lubrication needed']),
            'surgical_plan': random.choice([
                'Ptosis correction — levator advancement OD. Target MRD1 3.5mm. Planned in 3 weeks.',
                'Excision papilloma OD under local anaesthetic. Send for histopathology.',
                'DCR right side — endoscopic approach. Listed on waiting list.',
                'Medial conjunctivoplasty for involutional ectropion OD.',
                'Conservative — lubricating drops QID, eye protection at night. Review 3 months.',
            ]),
        }

    elif dept == dept_lv:
        return {
            'dist_va_re_sc': random.choice(['6/60', '6/36', '3/60', 'CF 3m', 'CF 1m', 'HM', 'PL']),
            'dist_va_le_sc': random.choice(['6/60', '6/36', '3/60', 'CF 3m', 'CF 2m', 'HM']),
            'dist_va_re_cc': random.choice(['6/24', '6/18', '6/36', 'CF 3m']),
            'dist_va_le_cc': random.choice(['6/24', '6/36', 'CF 4m']),
            'near_va_re':    random.choice(['N18', 'N24', 'N36', 'N12', 'Cannot read N36']),
            'near_va_le':    random.choice(['N18', 'N24', 'N48']),
            'who_category':  random.choice(['2 (Moderate VI: <6/18 to ≥6/60)', '3 (Severe VI: <6/60 to ≥3/60)', '4 (Profound VI: <3/60 to ≥1/60)', '5 (Blindness: <1/60 to PL)']),
            'contrast_sensitivity': random.choice(['Reduced — Pelli-Robson 1.2 logCS', 'Severely reduced — 0.6 logCS', 'Moderately reduced — 0.9 logCS']),
            'lva_distance':  random.choice(['4× monocular telescope OD — VA improves to 6/18', 'Spectacle-mounted 2× telescope OU — improved mobility', 'Not indicated for distance']),
            'lva_near':      random.choice(['10D stand magnifier — N8 achievable', '4× Eschenbach hand magnifier — N12 read', 'CCTV / electronic magnifier — best option given field loss']),
            'lva_training':  random.choice(['Patient counselled on magnifier use. Eccentric viewing training started.', 'Rehabilitation plan commenced — 4 sessions needed.', 'Orientation & mobility referral made.']),
            'functional_goals': random.choice([
                'Patient wants to read newspaper and manage medications — achievable with 10D stand mag.',
                'Goals: recognise family members at 2m, read large print Bible — eccentric viewing strategy applied.',
                'Employment-related visual demands — computer use. ZoomText software recommended.',
            ]),
            'lv_impression': random.choice([
                'Moderate low vision secondary to advanced dry AMD — magnification aids prescribed. Review 6 months.',
                'Severe low vision secondary to end-stage glaucoma — eccentric viewing training commenced. CCTV recommended.',
                'Profound vision loss secondary to optic atrophy — social services referral made for registration as severely sight impaired.',
                'Low vision secondary to diabetic maculopathy — anti-VEGF already underway. LVA as bridge. Review after treatment.',
            ]),
        }

    return {}  # fallback for unrecognised departments


created_visits = []
created_consultations = []

# Generate ~10 visits per month for 12 months = ~120 visits
for month_offset in range(11, -1, -1):
    yr, mo = months_back(month_offset)
    visits_this_month = random.randint(8, 14)

    for _ in range(visits_this_month):
        patient = random.choice(created_patients)
        doctor, dept = random.choice(doctors_depts)
        complaint = random.choice(complaints)
        vdate = rand_date_in_month(yr, mo)
        vtype = random.choice([VisitType.NEW, VisitType.NEW, VisitType.FOLLOW_UP])
        btype = getattr(patient, '_btype', BillingType.SELF_PAY)

        v = Visit.objects.create(
            patient=patient,
            visit_type=vtype,
            department=dept,
            attending_doctor=doctor,
            chief_complaint=complaint,
            status=VisitStatus.COMPLETED,
            billing_type=btype,
            created_by=recept1,
        )
        Visit.objects.filter(pk=v.pk).update(
            visit_date=datetime.combine(vdate, time(random.randint(8, 16), random.randint(0, 59)))
        )
        v.refresh_from_db()
        created_visits.append(v)

        duration_str = random.choice(['2 weeks', '1 month', '3 months', '6 months', 'a few days'])
        hpc = random.choice(hist_templates).format(complaint.lower(), duration_str)

        c = Consultation.objects.create(
            visit=v,
            patient=patient,
            department=dept,
            consulting_doctor=doctor,
            status=ConsultationStatus.COMPLETED,
            presenting_complaint=complaint,
            history_of_presenting_complaint=hpc,
            ocular_history=random.choice(ocular_histories),
            systemic_history=random.choice(systemic_histories),
            drug_history=random.choice(drug_histories),
            family_history=random.choice(family_histories),
            management_plan=random.choice(plans),
            follow_up_date=vdate + timedelta(days=random.choice([14, 30, 42, 60, 90])),
            examination_findings=make_exam_findings(),
            department_specific_data=make_dept_specific_data(dept),
            created_by=doctor,
        )
        Consultation.objects.filter(pk=c.pk).update(
            consultation_date=datetime.combine(vdate, time(random.randint(9, 17), 0))
        )
        c.refresh_from_db()

        num_dx = random.randint(1, 2)
        dx_choices = random.sample(diag_objects[:20], num_dx)
        for j, dx in enumerate(dx_choices):
            ConsultationDiagnosis.objects.get_or_create(
                consultation=c, diagnosis=dx,
                defaults={
                    'is_primary': (j == 0),
                    'laterality': random.choice(['RE', 'LE', 'BE', 'BE', 'BE']),
                }
            )

        created_consultations.append(c)

# ── 5b. TODAY'S RICH DEMO CONSULTATIONS (for live CEO demo) ──────────────────
print("Creating today's rich demo consultations...")

demo_cases = [
    # (patient_idx, doctor, dept, complaint, plan, dx_idx, dx_laterality)
    (15, med_dir,     dept_gen,   'Sudden painless loss of vision right eye', 'Urgent FFA and OCT ordered. CRVO suspected — intravitreal anti-VEGF planned. Haematology referral for thrombophilia screen.',    13, 'RE'),
    (16, glauc_dr,    dept_glauc, 'Acute angle closure — severe pain and vomiting', 'IV acetazolamide 500mg stat. Topical Timolol + Pilocarpine. Urgent YAG PI planned tonight. Contralateral prophylactic PI booked.', 1,  'RE'),
    (17, retina_dr,   dept_ret,   'Floaters and flashes — worsening 3 days', 'Urgent vitreoretinal surgery referral — retinal detachment with macula-off. NPO from midnight. Surgical consent obtained.',             0,  'RE'),
    (18, optom,       dept_ref,   'Blurred distance vision — difficulty driving at night', 'Final Rx: RE -3.25/-0.75x175, LE -2.75/-0.50x10. Progressive addition lenses recommended. Anti-reflection coating advised.',    6,  'BE'),
    (19, cataract_dr, dept_cat,   'Post-operative day 1 review — right eye cataract surgery yesterday', 'VA 6/9 OD improving. IOP 14mmHg. Wound secure. Prednisolone 1% QID + Ciprofloxacin 0.3% QID x4 weeks. Review in 1 week.',  2,  'RE'),
]

for pidx, doctor, dept, complaint, plan, dx_idx, laterality in demo_cases:
    patient = created_patients[pidx]
    btype = getattr(patient, '_btype', BillingType.SELF_PAY)

    v = Visit.objects.create(
        patient=patient,
        visit_type=VisitType.NEW,
        department=dept,
        attending_doctor=doctor,
        chief_complaint=complaint,
        status=VisitStatus.COMPLETED,
        billing_type=btype,
        created_by=recept1,
    )
    Visit.objects.filter(pk=v.pk).update(
        visit_date=datetime.combine(today, time(8, 30))
    )
    v.refresh_from_db()
    created_visits.append(v)

    c = Consultation.objects.create(
        visit=v,
        patient=patient,
        department=dept,
        consulting_doctor=doctor,
        status=ConsultationStatus.COMPLETED,
        presenting_complaint=complaint,
        history_of_presenting_complaint=f'Patient presents today with {complaint.lower()}. Onset was sudden / gradual over the past week. No prior similar episode. Referred from A&E / self-referred.',
        ocular_history=random.choice(ocular_histories),
        systemic_history=random.choice(systemic_histories),
        drug_history=random.choice(drug_histories),
        family_history=random.choice(family_histories),
        management_plan=plan,
        follow_up_date=today + timedelta(days=7),
        examination_findings=make_exam_findings(),
        department_specific_data=make_dept_specific_data(dept),
        created_by=doctor,
    )
    Consultation.objects.filter(pk=c.pk).update(
        consultation_date=datetime.combine(today, time(9, 0))
    )
    c.refresh_from_db()

    ConsultationDiagnosis.objects.get_or_create(
        consultation=c, diagnosis=diag_objects[dx_idx],
        defaults={'is_primary': True, 'laterality': laterality}
    )
    created_consultations.append(c)

print(f"  {Visit.objects.count()} visits ready.")
print(f"  {Consultation.objects.count()} consultations ready.")

# ── 6. BILLING (spread across 12 months) ─────────────────────────────────────
print("Creating billing records...")
from apps.billing.models import Invoice, InvoiceItem, Payment, InvoiceStatus, ServiceCategory, PaymentMethod

services = [
    ('Consultation Fee (New Patient)',    ServiceCategory.CONSULTATION,  Decimal('15000')),
    ('Consultation Fee (Follow-up)',      ServiceCategory.CONSULTATION,  Decimal('10000')),
    ('Visual Acuity Test',               ServiceCategory.INVESTIGATION, Decimal('5000')),
    ('IOP Measurement (Tonometry)',       ServiceCategory.INVESTIGATION, Decimal('3000')),
    ('Fundus Photography',               ServiceCategory.INVESTIGATION, Decimal('20000')),
    ('OCT Scan',                         ServiceCategory.INVESTIGATION, Decimal('35000')),
    ('Humphrey Visual Field',            ServiceCategory.INVESTIGATION, Decimal('25000')),
    ('Biometry (A-Scan)',                ServiceCategory.INVESTIGATION, Decimal('18000')),
    ('Intravitreal Injection (Anti-VEGF)',ServiceCategory.SURGICAL,      Decimal('80000')),
    ('Cataract Surgery (Phacoemulsification)',ServiceCategory.SURGICAL,  Decimal('350000')),
    ('YAG Laser Capsulotomy',            ServiceCategory.SURGICAL,      Decimal('45000')),
    ('Drug: Timolol 0.5% Eye Drops',     ServiceCategory.PHARMACY,      Decimal('8000')),
    ('Drug: Latanoprost 0.005%',         ServiceCategory.PHARMACY,      Decimal('12000')),
    ('Drug: Artificial Tears',           ServiceCategory.PHARMACY,      Decimal('4000')),
    ('Drug: Tobramycin 0.3%',            ServiceCategory.PHARMACY,      Decimal('7500')),
    ('Registration Fee',                 ServiceCategory.REGISTRATION,  Decimal('2000')),
]

payment_methods = [
    PaymentMethod.CASH, PaymentMethod.CASH, PaymentMethod.CASH,
    PaymentMethod.MOBILE_MONEY, PaymentMethod.MOBILE_MONEY,
    PaymentMethod.TRANSFER, PaymentMethod.INSURANCE,
]

inv_counter = Invoice.objects.count()
for i, v in enumerate(created_visits):
    inv_counter += 1
    inv_num = f"INV-{today.year}-{inv_counter:04d}"
    if Invoice.objects.filter(invoice_number=inv_num).exists():
        continue

    consult = Consultation.objects.filter(visit=v).first()
    vdate = v.visit_date.date() if hasattr(v.visit_date, 'date') else today

    inv = Invoice.objects.create(
        invoice_number=inv_num,
        patient=v.patient,
        consultation=consult,
        status=InvoiceStatus.DRAFT,
        issue_date=vdate,
        created_by=billing_off,
    )

    # 2-4 line items
    chosen = random.sample(services, random.randint(2, 4))
    for name, cat, price in chosen:
        InvoiceItem.objects.create(
            invoice=inv, category=cat, description=name,
            quantity=1, unit_price=price,
        )

    inv.refresh_from_db()
    try:
        inv.recalculate()
    except Exception:
        pass

    # 80% of invoices paid
    if random.random() < 0.80:
        inv.refresh_from_db()
        total = getattr(inv, 'total_amount', None) or getattr(inv, 'total', 0)
        method = random.choice(payment_methods)
        pay = Payment.objects.create(
            invoice=inv,
            payment_method=method,
            amount=total,
            reference=f"REF{2000+i}",
            received_by=billing_off,
        )
        # Backdate payment to match visit
        Payment.objects.filter(pk=pay.pk).update(
            payment_date=datetime.combine(vdate, time(random.randint(9, 17), 0))
        )
        try:
            inv.refresh_from_db()
            inv.recalculate()
        except Exception:
            pass

print(f"  {Invoice.objects.count()} invoices ready.")

# ── 7. PHARMACY DRUGS ─────────────────────────────────────────────────────────
print("Creating pharmacy stock...")
from apps.pharmacy.models import Drug, DrugCategory, DrugForm, DrugStock
from datetime import date as _date

drugs_data = [
    ('Timolol 0.5% Eye Drops',        'Timolol maleate',         DrugCategory.GLAUCOMA,   DrugForm.EYE_DROP,     '0.5%',     Decimal('8000'),   50),
    ('Latanoprost 0.005% Drops',      'Latanoprost',             DrugCategory.GLAUCOMA,   DrugForm.EYE_DROP,     '0.005%',   Decimal('12000'),  30),
    ('Tobramycin 0.3% Eye Drops',     'Tobramycin',              DrugCategory.ANTIBIOTIC, DrugForm.EYE_DROP,     '0.3%',     Decimal('7500'),   40),
    ('Dexamethasone 0.1% Eye Drops',  'Dexamethasone',           DrugCategory.STEROID,    DrugForm.EYE_DROP,     '0.1%',     Decimal('6500'),   35),
    ('Artificial Tears (10ml)',       'Carboxymethylcellulose',  DrugCategory.LUBRICANT,  DrugForm.EYE_DROP,     '0.5%',     Decimal('4000'),   80),
    ('Atropine 1% Eye Drops',         'Atropine sulphate',       DrugCategory.MYDRIATIC,  DrugForm.EYE_DROP,     '1%',       Decimal('5000'),   25),
    ('Tropicamide 1% Eye Drops',      'Tropicamide',             DrugCategory.MYDRIATIC,  DrugForm.EYE_DROP,     '1%',       Decimal('4500'),   45),
    ('Acetazolamide 250mg Tablets',   'Acetazolamide',           DrugCategory.GLAUCOMA,   DrugForm.TABLET,       '250mg',    Decimal('3500'),   60),
    ('Vitamin A 200,000 IU Capsules', 'Retinol palmitate',       DrugCategory.VITAMIN,    DrugForm.CAPSULE,      '200000IU', Decimal('2500'),  100),
    ('Chloramphenicol 1% Ointment',   'Chloramphenicol',         DrugCategory.ANTIBIOTIC, DrugForm.EYE_OINTMENT, '1%',       Decimal('3000'),   55),
    ('Pilocarpine 2% Eye Drops',      'Pilocarpine HCl',         DrugCategory.GLAUCOMA,   DrugForm.EYE_DROP,     '2%',       Decimal('5500'),   20),
    ('Betaxolol 0.5% Eye Drops',      'Betaxolol',               DrugCategory.GLAUCOMA,   DrugForm.EYE_DROP,     '0.5%',     Decimal('9500'),   15),
    ('Natamycin 5% Eye Drops',        'Natamycin',               DrugCategory.ANTIFUNGAL, DrugForm.EYE_DROP,     '5%',       Decimal('18000'),   8),
    ('Prednisolone Acetate 1%',       'Prednisolone acetate',    DrugCategory.STEROID,    DrugForm.EYE_DROP,     '1%',       Decimal('7000'),   30),
    ('Ciprofloxacin 0.3% Drops',      'Ciprofloxacin HCl',       DrugCategory.ANTIBIOTIC, DrugForm.EYE_DROP,     '0.3%',     Decimal('6000'),   45),
    ('Bevacizumab (Avastin) 1.25mg',  'Bevacizumab',             DrugCategory.ANTIFUNGAL, DrugForm.INJECTION,    '1.25mg',   Decimal('65000'),   5),
    ('Brimonidine 0.2% Eye Drops',    'Brimonidine tartrate',    DrugCategory.GLAUCOMA,   DrugForm.EYE_DROP,     '0.2%',     Decimal('11000'),  20),
    ('Fluorometholone 0.1% Drops',    'Fluorometholone',         DrugCategory.STEROID,    DrugForm.EYE_DROP,     '0.1%',     Decimal('8500'),   25),
    ('Ofloxacin 0.3% Eye Drops',      'Ofloxacin',               DrugCategory.ANTIBIOTIC, DrugForm.EYE_DROP,     '0.3%',     Decimal('5500'),   40),
    ('Cyclopentolate 1% Eye Drops',   'Cyclopentolate HCl',      DrugCategory.MYDRIATIC,  DrugForm.EYE_DROP,     '1%',       Decimal('4000'),   30),
]

expiry_2027 = _date(2027, 6, 30)
for name, generic, cat, form, strength, price, stock in drugs_data:
    drug, created = Drug.objects.get_or_create(name=name, defaults={
        'generic_name':  generic,
        'category':      cat,
        'form':          form,
        'strength':      strength,
        'selling_price': price,
        'cost_price':    price * Decimal('0.65'),
        'reorder_level': 10,
        'is_active':     True,
        'created_by':    pharmacist,
    })
    if created:
        DrugStock.objects.create(
            drug=drug,
            batch_number=f'BATCH-{str(drug.pk)[:8].upper()}',
            expiry_date=expiry_2027,
            quantity_received=stock,
            quantity_remaining=stock,
            purchase_price=price * Decimal('0.65'),
            created_by=pharmacist,
        )

print(f"  {Drug.objects.count()} drugs in pharmacy.")

# ── 8. APPOINTMENTS ───────────────────────────────────────────────────────────
print("Creating appointments...")
from apps.appointments.models import Appointment

appt_data = [
    (created_patients[0],  med_dir,     dept_gen,   today + timedelta(days=7),  time(9, 0),  'Follow-up: IOP check and pressure monitoring',     'CONFIRMED'),
    (created_patients[1],  retina_dr,   dept_ret,   today + timedelta(days=3),  time(10, 30),'Anti-VEGF injection review',                        'CONFIRMED'),
    (created_patients[2],  glauc_dr,    dept_glauc, today + timedelta(days=5),  time(11, 0), 'VF test and nerve fibre analysis',                  'CONFIRMED'),
    (created_patients[3],  optom,       dept_ref,   today + timedelta(days=1),  time(8, 30), 'Spectacle prescription update',                     'CONFIRMED'),
    (created_patients[4],  cataract_dr, dept_cat,   today + timedelta(days=14), time(14, 0), 'Pre-op biometry and assessment',                    'SCHEDULED'),
    (created_patients[5],  ped_dr,      dept_ped,   today + timedelta(days=2),  time(9, 30), 'Amblyopia patch therapy review',                    'CONFIRMED'),
    (created_patients[6],  med_dir,     dept_gen,   today + timedelta(days=10), time(15, 0), 'Annual diabetic eye examination',                   'CONFIRMED'),
    (created_patients[7],  retina_dr,   dept_ret,   today + timedelta(days=4),  time(11, 30),'Post-injection monitoring visit',                   'CONFIRMED'),
    (created_patients[8],  glauc_dr,    dept_glauc, today + timedelta(days=6),  time(10, 0), 'Glaucoma medication review',                        'SCHEDULED'),
    (created_patients[9],  optom,       dept_ref,   today + timedelta(days=8),  time(14, 30),'Contact lens fitting session',                      'CONFIRMED'),
    (created_patients[10], corn_dr,     dept_corn,  today + timedelta(days=3),  time(9, 0),  'Corneal ulcer follow-up — culture results review',  'CONFIRMED'),
    (created_patients[11], cataract_dr, dept_cat,   today + timedelta(days=21), time(13, 0), 'Cataract surgery counselling',                      'SCHEDULED'),
    (created_patients[12], retina_dr,   dept_ret,   today - timedelta(days=1),  time(10, 0), 'OCT and fluorescein angiography',                   'COMPLETED'),
    (created_patients[13], ped_dr,      dept_ped,   today - timedelta(days=2),  time(8, 0),  'Squint assessment for surgery',                     'COMPLETED'),
    (created_patients[14], neuro_dr,    dept_neuro, today + timedelta(days=12), time(11, 0), 'Optic neuropathy investigation',                    'CONFIRMED'),
    (created_patients[15], med_dir,     dept_gen,   today,                      time(9, 0),  'Emergency — sudden vision loss',                    'CONFIRMED'),
    (created_patients[16], glauc_dr,    dept_glauc, today,                      time(10, 0), 'Acute angle closure — urgent',                      'CONFIRMED'),
    (created_patients[17], retina_dr,   dept_ret,   today,                      time(11, 0), 'Retinal detachment — urgent review',                'CONFIRMED'),
    (created_patients[18], optom,       dept_ref,   today,                      time(14, 0), 'New spectacle prescription',                        'CONFIRMED'),
    (created_patients[19], cataract_dr, dept_cat,   today,                      time(15, 0), 'Post-op day 1 cataract check',                      'CONFIRMED'),
]

for pat, doc, dept, appt_date, appt_time, reason, status in appt_data:
    Appointment.objects.get_or_create(
        patient=pat, appointment_date=appt_date,
        defaults={
            'doctor':           doc,
            'department':       dept,
            'appointment_time': appt_time,
            'reason':           reason,
            'status':           status,
            'booked_by':        recept1,
            'created_by':       recept1,
        }
    )

print(f"  {Appointment.objects.count()} appointments ready.")

# ── 9. QMS TOKENS (today's queue) ─────────────────────────────────────────────
print("Creating today's queue tokens...")
from apps.qms.models import (
    QueueToken, ServiceType, ServiceTier, TokenStatus,
    IssuancePoint, DailyTokenSequence, TIER_PRIORITY
)

queue_today = [
    (created_patients[15], ServiceType.GENERAL,  ServiceTier.STANDARD,   TokenStatus.WAITING),
    (created_patients[16], ServiceType.GLAUCOMA, ServiceTier.EXPRESS,    TokenStatus.SERVING),
    (created_patients[17], ServiceType.RETINA,   ServiceTier.VIP,        TokenStatus.CALLED),
    (created_patients[18], ServiceType.REFRACTION,ServiceTier.STANDARD,  TokenStatus.WAITING),
    (created_patients[19], ServiceType.CATARACT, ServiceTier.FAST_TRACK, TokenStatus.WAITING),
    (created_patients[20], ServiceType.GENERAL,  ServiceTier.STANDARD,   TokenStatus.COMPLETED),
    (created_patients[21], ServiceType.PHARMACY, ServiceTier.STANDARD,   TokenStatus.WAITING),
    (created_patients[22], ServiceType.GENERAL,  ServiceTier.EXPRESS,    TokenStatus.COMPLETED),
]

for pat, svc, tier, status in queue_today:
    token_num = DailyTokenSequence.next_entry_token(tier)
    QueueToken.objects.get_or_create(
        patient=pat,
        token_date=today,
        service_type=svc,
        defaults={
            'token_number': token_num,
            'service_tier': tier,
            'issuance_point': IssuancePoint.GATE,
            'status': status,
            'priority': TIER_PRIORITY.get(tier, 0),
            'issued_by': recept1,
        }
    )

print(f"  {QueueToken.objects.filter(token_date=today).count()} tokens in today's queue.")

# ── 10. FEEDBACK / NPS ────────────────────────────────────────────────────────
print("Creating patient feedback...")
try:
    from apps.feedback.models import PatientFeedback
    feedback_data = [
        (created_patients[0],  5, 5, 5, 'Excellent service, very professional doctors.'),
        (created_patients[1],  4, 5, 4, 'Good experience overall. Wait time was a bit long.'),
        (created_patients[2],  5, 5, 5, 'Dr. Paul explained everything clearly. Very happy.'),
        (created_patients[3],  3, 4, 3, 'Waited over 2 hours. Need more staff at reception.'),
        (created_patients[4],  5, 5, 5, 'Best eye hospital I have visited. Highly recommend.'),
        (created_patients[5],  4, 4, 5, 'Child was treated very kindly. Good paediatric unit.'),
        (created_patients[6],  2, 3, 2, 'Pharmacy was out of my medication. Very inconvenient.'),
        (created_patients[7],  5, 5, 5, 'Injection done with no pain. Excellent technique.'),
        (created_patients[8],  4, 4, 4, 'Good service. Parking could be improved.'),
        (created_patients[9],  5, 5, 5, 'Very modern equipment. Staff are very helpful.'),
    ]
    for pat, overall, staff, cleanliness, comment in feedback_data:
        PatientFeedback.objects.get_or_create(
            patient=pat,
            feedback_type='SATISFACTION',
            defaults={
                'overall_rating': overall,
                'staff_courtesy_rating': staff,
                'cleanliness_rating': cleanliness,
                'message': comment,
            }
        )
    print(f"  {PatientFeedback.objects.count()} feedback records ready.")
except Exception as e:
    print(f"  Feedback skipped: {e}")

# ── SUMMARY ───────────────────────────────────────────────────────────────────
from apps.billing.models import Payment as _Pay
from apps.qms.models import QueueToken as _QT

print("\n" + "="*55)
print("  SEED DATA COMPLETE — EHR AFRICA DEMO")
print("="*55)
print(f"  Departments      : {Department.objects.count()}")
print(f"  Staff accounts   : {User.objects.count()}")
print(f"  Patients         : {Patient.objects.count()}")
print(f"  Visits           : {Visit.objects.count()}")
print(f"  Consultations    : {Consultation.objects.count()}")
print(f"  Diagnoses (ICD)  : {Diagnosis.objects.count()}")
print(f"  Invoices         : {Invoice.objects.count()}")
print(f"  Payments         : {_Pay.objects.count()}")
print(f"  Drugs (pharmacy) : {Drug.objects.count()}")
print(f"  Appointments     : {Appointment.objects.count()}")
print(f"  Queue tokens     : {_QT.objects.count()}")
print("="*55)
print()
print("  SUPER ADMIN LOGIN")
print("  Email   : admin@ehr.com")
print("  Password: admin1234")
print()
print("  CEO LOGIN")
print("  Email   : ceo@ehr.com")
print("  Password: EHR@2024")
print()
print("  DOCTOR LOGIN (Medical Director)")
print("  Email   : dr.james@ehr.com")
print("  Password: EHR@2024")
print()
print("  RETINA SPECIALIST")
print("  Email   : dr.sarah@ehr.com")
print("  Password: EHR@2024")
print("="*55)
