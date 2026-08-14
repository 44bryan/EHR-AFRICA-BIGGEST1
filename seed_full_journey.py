"""
EHR Africa — Full Patient Journey Demo Seed
============================================
Seeds the entire clinical pipeline:
  - Investigation types, Lab test types, Drugs + stock
  - Wards, Beds, CSSD instruments + sets
  - Demo staff accounts for every clinical role
  - 20 complete patient journeys covering every module:
      Consultation → Investigations → Lab → Pharmacy → Optical Rx
      Surgical Booking → Counseling → Admission → Theatre → CSSD → Billing

Run with:
    python manage.py shell -c "exec(open('seed_full_journey.py').read())"
"""
import random
from decimal import Decimal
from datetime import date, timedelta, time as dtime, datetime
from django.utils import timezone
from django.db import transaction

random.seed(99)
TODAY = date(2026, 6, 15)

print("=" * 68)
print("EHR AFRICA — Full Patient Journey Demo Seed")
print("=" * 68)

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def past(days):
    return TODAY - timedelta(days=days)

def past_dt(days, hour=9, minute=0):
    d = TODAY - timedelta(days=days)
    return timezone.make_aware(datetime(d.year, d.month, d.day, hour, minute))

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — INVESTIGATION TYPES
# ─────────────────────────────────────────────────────────────────────────────
print("\n[1/9] Investigation types...")
from apps.investigations.models import InvestigationType, InvestigationCategory

INV_TYPES = [
    ("VA",    "Visual Acuity Assessment",          InvestigationCategory.REFRACTION,      {}),
    ("IOP",   "Intraocular Pressure (Tonometry)",  InvestigationCategory.TONOMETRY,       {}),
    ("REFR",  "Subjective Refraction",             InvestigationCategory.REFRACTION,      {}),
    ("BSCAN", "B-Scan Ultrasonography",            InvestigationCategory.IMAGING,         {}),
    ("OCT",   "OCT — Macula / Optic Nerve",        InvestigationCategory.IMAGING,         {}),
    ("FFA",   "Fundus Fluorescein Angiography",    InvestigationCategory.IMAGING,         {}),
    ("VF",    "Visual Field (Perimetry)",          InvestigationCategory.VISUAL_FIELD,    {}),
    ("ABIOM", "A-Scan Biometry (IOL Master)",      InvestigationCategory.BIOMETRY,        {}),
    ("PACH",  "Corneal Pachymetry",                InvestigationCategory.PACHYMETRY,      {}),
    ("SLE",   "Slit-Lamp Examination",             InvestigationCategory.ANTERIOR_SEGMENT,{}),
    ("FP",    "Fundus Photography",                InvestigationCategory.IMAGING,         {}),
    ("ERG",   "Electroretinography (ERG)",         InvestigationCategory.ELECTROPHYSIOLOGY,{}),
    ("HRT",   "Heidelberg Retina Tomography",      InvestigationCategory.IMAGING,         {}),
    ("CORNTO","Corneal Topography",                InvestigationCategory.ANTERIOR_SEGMENT,{}),
]

inv_type_map = {}
for code, name, cat, tmpl in INV_TYPES:
    # Try by code first, then by name, then create
    obj = InvestigationType.objects.filter(code=code).first()
    if not obj:
        obj = InvestigationType.objects.filter(name=name).first()
        if obj:
            obj.code = code  # update code to match
            obj.save(update_fields=["code"])
        else:
            obj = InvestigationType.objects.create(
                code=code, name=name, category=cat, result_template=tmpl, is_active=True
            )
    inv_type_map[code] = obj

print(f"  OK {len(inv_type_map)} investigation types ready")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — LAB TEST TYPES
# ─────────────────────────────────────────────────────────────────────────────
print("[2/9] Lab test types...")
from apps.laboratory.models import LabTestType, LabTestCategory

LAB_TYPES = [
    ("CBC",   "Full Blood Count (CBC)",            LabTestCategory.HAEMATOLOGY,   {"Hb": "g/dL", "WBC": "x109/L", "PLT": "x109/L"}),
    ("FBS",   "Fasting Blood Sugar (FBS)",         LabTestCategory.BIOCHEMISTRY,  {"range": "3.9–5.6 mmol/L"}),
    ("HBA1C", "Glycated Haemoglobin (HbA1c)",      LabTestCategory.BIOCHEMISTRY,  {"range": "<7%"}),
    ("BUN",   "Blood Urea Nitrogen",               LabTestCategory.BIOCHEMISTRY,  {}),
    ("CREAT", "Serum Creatinine",                  LabTestCategory.BIOCHEMISTRY,  {}),
    ("LFT",   "Liver Function Tests",              LabTestCategory.BIOCHEMISTRY,  {}),
    ("HIV",   "HIV Screening",                     LabTestCategory.SEROLOGY,      {}),
    ("HBsAg", "Hepatitis B Surface Antigen",       LabTestCategory.SEROLOGY,      {}),
    ("HCV",   "Hepatitis C Antibody",              LabTestCategory.SEROLOGY,      {}),
    ("GTYPE", "Blood Group & Crossmatch",          LabTestCategory.HAEMATOLOGY,   {}),
    ("COAG",  "Coagulation Screen (PT/APTT/INR)",  LabTestCategory.HAEMATOLOGY,   {}),
    ("UA",    "Urinalysis",                        LabTestCategory.URINALYSIS,    {}),
    ("CXR",   "Chest X-Ray (Radiograph)",          LabTestCategory.OCULAR,        {}),
    ("ECG",   "Electrocardiogram (ECG)",           LabTestCategory.OCULAR,        {}),
    ("AQ",    "Aqueous Humour Culture",            LabTestCategory.OCULAR,        {}),
]

lab_type_map = {}
for code, name, cat, nr in LAB_TYPES:
    obj = LabTestType.objects.filter(code=code).first()
    if not obj:
        obj = LabTestType.objects.filter(name=name).first()
        if obj:
            obj.code = code
            obj.save(update_fields=["code"])
        else:
            obj = LabTestType.objects.create(
                code=code, name=name, category=cat, normal_range=nr, is_active=True
            )
    lab_type_map[code] = obj

print(f"  OK {len(lab_type_map)} lab test types ready")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — DRUGS + STOCK
# ─────────────────────────────────────────────────────────────────────────────
print("[3/9] Drug formulary + stock...")
from apps.pharmacy.models import Drug, DrugStock, DrugCategory as PharmDrugCat, DrugForm as PharmDrugForm

DRUGS = [
    # name, generic, brand, category, form, strength, unit, cost, sell
    ("Chloramphenicol 0.5% Eye Drops",    "Chloramphenicol",       "Chloromycetin",  PharmDrugCat.ANTIBIOTIC,  PharmDrugForm.EYE_DROP,     "0.5%",   "bottle", 1500,  3000),
    ("Ofloxacin 0.3% Eye Drops",          "Ofloxacin",             "Exocin",         PharmDrugCat.ANTIBIOTIC,  PharmDrugForm.EYE_DROP,     "0.3%",   "bottle", 2500,  5000),
    ("Dexamethasone 0.1% Eye Drops",      "Dexamethasone",         "Maxidex",        PharmDrugCat.STEROID,     PharmDrugForm.EYE_DROP,     "0.1%",   "bottle", 2000,  4500),
    ("Prednisolone 1% Eye Drops",         "Prednisolone",          "Pred Forte",     PharmDrugCat.STEROID,     PharmDrugForm.EYE_DROP,     "1%",     "bottle", 3000,  6500),
    ("Timolol 0.5% Eye Drops",            "Timolol Maleate",       "Timoptol",       PharmDrugCat.GLAUCOMA,    PharmDrugForm.EYE_DROP,     "0.5%",   "bottle", 2000,  4000),
    ("Latanoprost 0.005% Eye Drops",      "Latanoprost",           "Xalatan",        PharmDrugCat.GLAUCOMA,    PharmDrugForm.EYE_DROP,     "0.005%", "bottle", 8000, 16000),
    ("Brimonidine 0.2% Eye Drops",        "Brimonidine Tartrate",  "Alphagan",       PharmDrugCat.GLAUCOMA,    PharmDrugForm.EYE_DROP,     "0.2%",   "bottle", 6000, 12000),
    ("Atropine 1% Eye Drops",             "Atropine Sulphate",     "Isopto Atropine",PharmDrugCat.MYDRIATIC,   PharmDrugForm.EYE_DROP,     "1%",     "bottle", 1500,  3000),
    ("Tropicamide 1% Eye Drops",          "Tropicamide",           "Mydriacyl",      PharmDrugCat.MYDRIATIC,   PharmDrugForm.EYE_DROP,     "1%",     "bottle", 2000,  4000),
    ("Carboxymethylcellulose Eye Drops",  "Carboxymethylcellulose","Refresh Tears",  PharmDrugCat.LUBRICANT,   PharmDrugForm.EYE_DROP,     "0.5%",   "bottle", 1000,  2500),
    ("Diclofenac 0.1% Eye Drops",         "Diclofenac",            "Voltaren Ophtha",PharmDrugCat.NSAID,       PharmDrugForm.EYE_DROP,     "0.1%",   "bottle", 3500,  7000),
    ("Betamethasone Eye Ointment",        "Betamethasone",         "Betnovate",      PharmDrugCat.STEROID,     PharmDrugForm.EYE_OINTMENT, "0.1%",   "tube",   1500,  3500),
    ("Ciprofloxacin 500mg Tablet",        "Ciprofloxacin",         "Ciprobay",       PharmDrugCat.ANTIBIOTIC,  PharmDrugForm.TABLET,       "500mg",  "tablet",  200,   500),
    ("Ibuprofen 400mg Tablet",            "Ibuprofen",             "Brufen",         PharmDrugCat.ANALGESIC,   PharmDrugForm.TABLET,       "400mg",  "tablet",  100,   250),
    ("Vitamin A + E Supplement",          "Vitamins A & E",        "Ocuvite",        PharmDrugCat.VITAMIN,     PharmDrugForm.TABLET,       "5000IU", "tablet",  300,   700),
    ("Acetazolamide 250mg Tablet",        "Acetazolamide",         "Diamox",         PharmDrugCat.GLAUCOMA,    PharmDrugForm.TABLET,       "250mg",  "tablet",  500,  1200),
    ("Cyclopentolate 1% Eye Drops",       "Cyclopentolate",        "Cyclogyl",       PharmDrugCat.MYDRIATIC,   PharmDrugForm.EYE_DROP,     "1%",     "bottle", 2500,  5500),
    ("Betaxolol 0.5% Eye Drops",          "Betaxolol",             "Betoptic",       PharmDrugCat.GLAUCOMA,    PharmDrugForm.EYE_DROP,     "0.5%",   "bottle", 3000,  6000),
]

drug_map = {}
for row in DRUGS:
    name, gen, brand, cat, form, strength, unit, cost, sell = row
    drug, _ = Drug.objects.get_or_create(
        name=name,
        defaults=dict(generic_name=gen, brand_name=brand, category=cat, form=form,
                      strength=strength, unit=unit, cost_price=cost, selling_price=sell,
                      is_active=True, requires_prescription=True, reorder_level=10)
    )
    drug_map[name] = drug
    # Add stock if none exists
    if not drug.stock_items.filter(is_deleted=False).exists():
        DrugStock.objects.create(
            drug=drug, batch_number=f"BATCH-{str(drug.pk)[:8].upper()}",
            expiry_date=date(2027, 12, 31),
            quantity_received=500, quantity_remaining=500,
            supplier="Cameroon Pharma Ltd", purchase_price=cost
        )

print(f"  OK {len(drug_map)} drugs ready with stock")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — WARDS + BEDS
# ─────────────────────────────────────────────────────────────────────────────
print("[4/9] Wards and beds...")
from apps.ipd.models import Ward, Bed, WardType, BedStatus

wards_data = [
    ("General Ophthalmic Ward",  WardType.GENERAL,     "Ground Floor", 20, 15000),
    ("Private Room A",           WardType.PRIVATE,     "1st Floor",     4, 60000),
    ("Semi-Private Ward",        WardType.SEMI_PRIVATE,"Ground Floor",  8, 30000),
    ("Day Case Surgical Unit",   WardType.DAY_CASE,    "Theatre Block",12, 20000),
]

ward_map = {}
bed_map = {}
for wname, wtype, floor, total, price in wards_data:
    ward, _ = Ward.objects.get_or_create(
        name=wname,
        defaults=dict(ward_type=wtype, floor=floor, total_beds=total,
                      price_per_night=price, is_active=True)
    )
    ward_map[wname] = ward
    for i in range(1, total + 1):
        bed, _ = Bed.objects.get_or_create(
            ward=ward, bed_number=f"{wtype[0].upper()}{i:02d}",
            defaults=dict(status=BedStatus.AVAILABLE)
        )
        bed_map[(wname, i)] = bed

print(f"  OK {len(ward_map)} wards, {len(bed_map)} beds ready")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 5 — CSSD INSTRUMENTS + SETS
# ─────────────────────────────────────────────────────────────────────────────
print("[5/9] CSSD instruments and sets...")
from apps.cssd.models import Instrument, InstrumentSet, SterilizationCycle, SterilizationMethod, DispatchRecord, InstrumentStatus

INSTRUMENTS = [
    ("Phaco Handpiece",           "PHACO-001"),
    ("Cataract Irrigating Cannula","CANL-001"),
    ("Iris Repositor",            "IRIS-001"),
    ("Scleral Fixation Forceps",  "SCLE-001"),
    ("Corneal Scissors",          "CSCIS-001"),
    ("Vitrectomy Probe",          "VITR-001"),
    ("Retinal Forceps",           "RFOR-001"),
    ("Indirect Ophthalmoscope",   "IDO-001"),
    ("Slit Lamp",                 "SL-001"),
    ("Tonometer Probe",           "TONO-001"),
    ("Lid Speculum",              "SPEC-001"),
    ("Needle Holder",             "NDH-001"),
    ("Tissue Forceps",            "TFOR-001"),
    ("Suture Scissors",           "SSCIS-001"),
    ("Lacrimal Probe Set",        "LAC-001"),
    ("Chalazion Clamp",           "CHAL-001"),
    ("Strabismus Hook",           "STRAB-001"),
    ("Keratoscope",               "KERA-001"),
]

instr_map = {}
from apps.departments.models import Department
theatre_dept = Department.objects.filter(name__icontains="Theatre").first() or Department.objects.filter(name__icontains="Cataract").first()

for name, code in INSTRUMENTS:
    instr, _ = Instrument.objects.get_or_create(
        instrument_code=code,
        defaults=dict(name=name, department=theatre_dept,
                      status=InstrumentStatus.AVAILABLE, is_active=True)
    )
    instr_map[code] = instr

# Create instrument sets
phaco_set, _ = InstrumentSet.objects.get_or_create(
    set_code="SET-PHACO",
    defaults=dict(name="Phacoemulsification Set", department=theatre_dept, is_active=True)
)
if phaco_set.instruments.count() == 0:
    phaco_set.instruments.set([instr_map.get("PHACO-001"), instr_map.get("CANL-001"),
                                instr_map.get("IRIS-001"), instr_map.get("SPEC-001"),
                                instr_map.get("NDH-001")])

vitr_set, _ = InstrumentSet.objects.get_or_create(
    set_code="SET-VITR",
    defaults=dict(name="Vitrectomy Instrument Set", department=theatre_dept, is_active=True)
)
if vitr_set.instruments.count() == 0:
    vitr_set.instruments.set([instr_map.get("VITR-001"), instr_map.get("RFOR-001"),
                               instr_map.get("SPEC-001"), instr_map.get("NDH-001")])

general_set, _ = InstrumentSet.objects.get_or_create(
    set_code="SET-GEN",
    defaults=dict(name="General Ophthalmic Minor Set", department=theatre_dept, is_active=True)
)
if general_set.instruments.count() == 0:
    general_set.instruments.set([instr_map.get("NDH-001"), instr_map.get("TFOR-001"),
                                  instr_map.get("SSCIS-001"), instr_map.get("SPEC-001")])

print(f"  OK {len(instr_map)} instruments, 3 sets ready")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 6 — STAFF ACCOUNTS (get existing or create demo accounts)
# ─────────────────────────────────────────────────────────────────────────────
print("[6/9] Demo staff accounts...")
from apps.accounts.models import User, UserRole

def get_or_create_staff(username, role, first, last, dept_name=None):
    # Derive a short unique employee_id from username (max 20 chars)
    emp_id = username.upper()[:20]
    user = User.objects.filter(username=username).first()
    if not user:
        user = User.objects.filter(employee_id=emp_id).first()
    if not user:
        user = User(
            username=username, first_name=first, last_name=last,
            role=role, email=f"{username}@gludd.cm",
            is_active=True, must_change_password=False,
            employee_id=emp_id,
        )
        user.set_password("Demo@12345")
        if dept_name:
            dept = Department.objects.filter(name__icontains=dept_name).first()
            if dept:
                user.department = dept
        user.save()
    return user

# Get real departments
def get_dept(kw):
    return Department.objects.filter(name__icontains=kw).first()

# Create staff for all key roles
ophtho      = get_or_create_staff("dr_ekane",    UserRole.OPHTHALMOLOGIST,          "Samuel",  "Ekane",        "General")
cataract_sx = get_or_create_staff("dr_nguema",   UserRole.CATARACT_SURGEON,         "Marie",   "Nguema",       "Cataract")
retina_sp   = get_or_create_staff("dr_bello",    UserRole.RETINA_SPECIALIST,        "Ibrahim", "Bello",        "Retina")
glaucoma_sp = get_or_create_staff("dr_fotso",    UserRole.GLAUCOMA_SPECIALIST,      "Paul",    "Fotso",        "Glaucoma")
optometrist = get_or_create_staff("mr_tamba",    UserRole.OPTOMETRIST,              "Jean",    "Tamba",        "Refraction")
paed_ophtho = get_or_create_staff("dr_abe",      UserRole.PEDIATRIC_OPHTHALMOLOGIST,"Celine",  "Abé",          "Pediatric")
oculoplast  = get_or_create_staff("dr_mvondo",   UserRole.OCULOPLASTICS_SURGEON,    "Eric",    "Mvondo",       "Oculoplastics")
uveitis_sp  = get_or_create_staff("dr_nkemdirim",UserRole.UVEITIS_SPECIALIST,       "Chidi",   "Nkemdirim",    "Uveitis")

opd_nurse   = get_or_create_staff("nrs_mebara",  UserRole.NURSE,                    "Grace",   "Mebara",       None)
theatre_nrs = get_or_create_staff("nrs_atangana",UserRole.THEATRE_NURSE,            "Berthe",  "Atangana",     None)
ward_nrs    = get_or_create_staff("nrs_ebale",   UserRole.WARD_NURSE,               "Agnes",   "Ebale",        None)
counsel_nrs = get_or_create_staff("nrs_ewane",   UserRole.COUNSELING_NURSE,         "Patience","Ewane",        None)
inv_tech    = get_or_create_staff("tech_ndongo", UserRole.INVESTIGATION_TECHNICIAN, "Michel",  "Ndongo",       None)
lab_tech    = get_or_create_staff("tech_okoro",  UserRole.LAB_TECHNICIAN,           "Emeka",   "Okoro",        None)
pharmacist  = get_or_create_staff("pharm_ndi",   UserRole.PHARMACIST,               "Sylvie",  "Ndi",          None)
opt_disp    = get_or_create_staff("opt_manga",   UserRole.OPTICAL_DISPENSER,        "Roger",   "Manga",        None)
cssd_tech   = get_or_create_staff("cssd_abomo",  UserRole.CSSD_TECHNICIAN,          "Colette", "Abomo",        None)
adm_officer = get_or_create_staff("adm_bekono",  UserRole.ADMISSION_OFFICER,        "Vincent", "Bekono",       None)

print("  OK Demo staff accounts ready")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 7 — GET EXISTING PATIENTS (from seed_demo_300)
# ─────────────────────────────────────────────────────────────────────────────
print("[7/9] Fetching patients for journey assignment...")
from apps.patients.models import Patient, Visit, VisitStatus

# Get patients by diagnosis type using existing consultations
from apps.consultations.models import (
    Consultation, ConsultationDiagnosis, Diagnosis,
    ConsultationStatus
)

# We'll pick real patients from the seeded data and build full journeys on them.
# Select ~20 patients that already exist
patients_pool = list(Patient.objects.filter(is_active=True).order_by('?')[:40])
if len(patients_pool) < 20:
    print(f"  ! Only {len(patients_pool)} patients found — journeys may be fewer than 20")

print(f"  OK {len(patients_pool)} patients available for full journeys")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 8 — BUILD FULL JOURNEYS
# ─────────────────────────────────────────────────────────────────────────────
print("[8/9] Building full patient journeys...")

from apps.investigations.models import InvestigationOrder, InvestigationResult
from apps.laboratory.models import (LabOrder, LabOrderItem, SampleCollection, LabResult)
from apps.prescriptions.models import DrugPrescription, DrugPrescriptionItem, OpticalPrescription
from apps.pharmacy.models import Dispensing, DispensingItem
from apps.ipd.models import (Admission, AdmissionStatus, SurgicalBooking, SurgicalBookingStatus,
                               SurgeryType, NursingNote, MAREntry, TheatreSession, TheatreProcedure,
                               TheatreSessionStatus, ProcedureOutcome)
from apps.billing.models import Invoice, InvoiceItem, InvoiceStatus, Payment, PaymentMethod, ServiceCategory

dx_map = {d.icd10_code: d for d in Diagnosis.objects.all()}

def get_available_bed(ward_name):
    """Get first available bed in ward."""
    ward = ward_map.get(ward_name)
    if not ward:
        return None
    return ward.beds.filter(status=BedStatus.AVAILABLE, is_deleted=False).first()

def make_invoice(patient, consultation, items_list, days_ago=0):
    """Create a paid invoice. items_list = [(desc, cat, qty, unit_price), ...]"""
    inv = Invoice.objects.create(
        patient=patient,
        consultation=consultation,
        status=InvoiceStatus.PAID,
        notes="Auto-generated demo invoice",
        created_by=ophtho,
    )
    total = Decimal("0")
    for desc, cat, qty, price in items_list:
        InvoiceItem.objects.create(
            invoice=inv, description=desc,
            category=cat, quantity=qty, unit_price=Decimal(str(price))
        )
        total += qty * Decimal(str(price))
    Invoice.objects.filter(pk=inv.pk).update(issue_date=past(days_ago))
    Payment.objects.create(
        invoice=inv, amount=total,
        payment_method=PaymentMethod.CASH,
        received_by=ophtho,
        notes="Demo payment",
    )
    return inv

# =============================================================================
# JOURNEY TEMPLATES — 20 defined scenarios
# =============================================================================

journeys_done = 0

with transaction.atomic():

  # ── Grab patients (may reuse some if pool is small) ───────────────────────
  def patient(n):
      return patients_pool[n % len(patients_pool)]

  # ╔══════════════════════════════════════════════════════════════════════╗
  # ║  JOURNEY 1 — Cataract → Phaco + IOL Surgery (complete)             ║
  # ╚══════════════════════════════════════════════════════════════════════╝
  p1 = patient(0)
  dept_gen = get_dept("General") or get_dept("Ophthal")
  dept_cat = get_dept("Cataract") or dept_gen

  # Visit
  v1 = Visit.objects.create(
      patient=p1, chief_complaint="Progressive blurred vision both eyes for 2 years, worse right eye",
      status="DISCHARGED", billing_type="SELF_PAY", service_tier="STANDARD",
      created_by=ophtho, attending_doctor=cataract_sx,
  )
  Visit.objects.filter(pk=v1.pk).update(visit_date=past_dt(45))

  # Consultation
  c1 = Consultation.objects.create(
      visit=v1, patient=p1, department=dept_cat, consulting_doctor=cataract_sx,
      status=ConsultationStatus.COMPLETED,
      presenting_complaint="Painless progressive loss of vision both eyes. Worse in bright light. Difficulty driving at night.",
      history_of_presenting_complaint="2-year history of gradually worsening vision. No pain, no redness. Has difficulty reading and recognising faces.",
      ocular_history="No previous surgery. No spectacles. Diagnosed with hypertension 5 years ago.",
      systemic_history="Hypertension on Amlodipine 5mg OD. No diabetes. No known drug allergies.",
      drug_history="Amlodipine 5mg OD",
      family_history="Father had similar eye problems in old age.",
      examination_findings={
          "visual_acuity": {"right": "CF 1m", "left": "6/60", "right_pinhole": "CF 2m", "left_pinhole": "6/24"},
          "iop": {"right": 14, "left": 16, "method": "Goldmann"},
          "slit_lamp": {
              "right": {"lids": "Normal", "conjunctiva": "Clear", "cornea": "Clear", "AC": "Deep and quiet", "iris": "Normal", "lens": "Dense nuclear sclerosis grade 4, posterior subcapsular opacity", "vitreous": "Hazy"},
              "left":  {"lids": "Normal", "conjunctiva": "Clear", "cornea": "Clear", "AC": "Deep and quiet", "iris": "Normal", "lens": "Nuclear sclerosis grade 3, cortical spokes", "vitreous": "Clear"}
          },
          "fundus": {
              "right": {"disc": "Not clearly visible due to dense cataract", "macula": "Not visible", "vessels": "Not visible"},
              "left":  {"disc": "Healthy, 0.3 C:D ratio", "macula": "Flat and even, no drusen", "vessels": "Normal calibre, no AV nipping"}
          },
          "cover_test": "No deviation",
          "motility": "Full in all directions of gaze",
      },
      management_plan="Bilateral cataract surgery planned. Right eye first. Biometry ordered. Pre-op workup requested. Counseled on procedure, risks and expected outcomes.",
      follow_up_date=past(30),
      created_by=cataract_sx,
  )
  Consultation.objects.filter(pk=c1.pk).update(consultation_date=past_dt(45,10,0))

  # Assign diagnoses
  ConsultationDiagnosis = __import__('apps.consultations.models', fromlist=['ConsultationDiagnosis']).ConsultationDiagnosis
  for code in ("H25.9", "H26.9"):
      dx = dx_map.get(code)
      if dx:
          ConsultationDiagnosis.objects.get_or_create(consultation=c1, diagnosis=dx, defaults={"is_primary": code=="H25.9"})

  # Biometry investigation
  io1 = InvestigationOrder.objects.create(
      consultation=c1, patient=p1, ordered_by=cataract_sx,
      investigation_type=inv_type_map["ABIOM"],
      urgency="ROUTINE", clinical_indication="Pre-op biometry for cataract surgery. Right eye phaco + IOL planned.",
      eye="RE", status="COMPLETED", created_by=cataract_sx,
  )
  InvestigationResult.objects.create(
      order=io1, performed_by=inv_tech, is_normal=True, is_verified=True,
      result_data={"AL_RE": "23.45 mm", "AL_LE": "23.52 mm", "K1_RE": "43.25 D @ 90deg", "K2_RE": "44.00 D @ 180deg",
                   "IOL_power_recommended": "+22.50 D", "formula": "SRK/T", "target_refraction": "-0.25 D"},
      interpretation="IOL power for RE: +22.50 D (Monofocal Acrylic). Target: emmetropia.",
      created_by=inv_tech,
  )

  # Pre-op Lab orders
  lo1 = LabOrder.objects.create(
      consultation=c1, patient=p1, ordered_by=cataract_sx,
      urgency="ROUTINE", status="COMPLETED",
      clinical_indication="Pre-operative workup for elective cataract surgery under local anaesthesia.",
      created_by=cataract_sx,
  )
  for lab_code in ["CBC","FBS","HIV","HBsAg","ECG","COAG"]:
      lt = lab_type_map.get(lab_code)
      if lt:
          item = LabOrderItem.objects.create(order=lo1, test_type=lt, status="COMPLETED")
          results = {
              "CBC": ("14.2 g/dL", "g/dL", "12.0–16.5", False, False, "Haemoglobin within normal range. WBC 7.2x109/L, PLT 215x109/L"),
              "FBS": ("5.1 mmol/L", "mmol/L", "3.9–5.6", False, False, "Fasting blood sugar normal"),
              "HIV": ("Non-reactive", "", "Non-reactive", False, False, "HIV screening negative"),
              "HBsAg": ("Non-reactive", "", "Non-reactive", False, False, "Hepatitis B surface antigen negative"),
              "ECG": ("Normal sinus rhythm, rate 72/min", "", "Normal", False, False, "No ischaemic changes. Axis normal. Normal ECG."),
              "COAG": ("PT 12.5s, APTT 30.2s, INR 1.0", "s", "PT: 11–14s", False, False, "Coagulation within normal limits. Cleared for surgery."),
          }.get(lab_code, ("See report","","",False,False,""))
          LabResult.objects.create(
              order_item=item, performed_by=lab_tech, is_verified=True,
              result_value=results[0], result_unit=results[1], reference_range=results[2],
              is_abnormal=results[3], is_critical=results[4], comment=results[5],
              created_by=lab_tech,
          )
  SampleCollection.objects.create(
      order=lo1, collected_by=lab_tech, sample_type="BLOOD_EDTA", notes="Pre-op samples collected"
  )

  # Drug prescription (pre-op eye drops)
  rx1 = DrugPrescription.objects.create(
      consultation=c1, patient=p1, prescribed_by=cataract_sx,
      notes="Pre-operative medication. Start 3 days before surgery.", created_by=cataract_sx,
  )
  DrugPrescriptionItem.objects.create(
      prescription=rx1, drug_name="Chloramphenicol 0.5% Eye Drops", drug_form="EYE_DROP",
      concentration="0.5%", dose="1 drop", frequency="QID", duration="3 days",
      route="TOPICAL", eye="RE", quantity=1,
      special_instructions="Start 3 days before surgery, 4 times daily"
  )

  # Surgical booking
  sb1 = SurgicalBooking.objects.create(
      patient=p1, consultation=c1, surgeon=cataract_sx, admission_officer=adm_officer,
      procedure=SurgeryType.PHACO, procedure_notes="Phacoemulsification + posterior chamber IOL, right eye",
      eye_laterality="RE", anaesthesia_type="LOCAL",
      theatre="Main Theatre", status=SurgicalBookingStatus.COMPLETED,
      surgery_category="CATARACT",
      pre_op_requirements="Fasting 4 hours. Stop Aspirin 5 days before. Dilate RE with Tropicamide 1% x3.",
      pre_op_checklist={"CBC": True, "FBS": True, "HIV": True, "HBsAg": True, "ECG": True, "COAG": True, "consent": True},
      counseling_notes="Patient fully counseled on procedure, risks (posterior capsule rupture, infection, vision loss), expected outcomes, post-op care. Patient understands and agrees.",
      consent_signed=True, consent_date=past_dt(35,14,0),
      total_amount=250000, deposit_required=125000, deposit_paid=125000,
      payment_notes="50% deposit paid at booking. Balance on day of surgery.",
      surgery_date=past_dt(30, 8, 0),
      created_by=adm_officer,
  )

  # Admission (day case)
  bed1 = get_available_bed("Day Case Surgical Unit")
  if bed1:
      bed1.status = "OCCUPIED"
      bed1.save()
      adm1 = Admission.objects.create(
          patient=p1, bed=bed1, admitting_doctor=cataract_sx,
          surgical_booking=sb1,
          status=AdmissionStatus.DISCHARGED,
          diagnosis_on_admission="Right eye age-related nuclear cataract, grade 4. For Phacoemulsification + IOL.",
          discharge_summary="Phacoemulsification + posterior chamber IOL performed right eye. Procedure uneventful. IOL well centred. Patient instructed on post-op drops and reviewed at 1 week.",
          notes="Day case admission for cataract surgery.",
          created_by=adm_officer,
      )
      Admission.objects.filter(pk=adm1.pk).update(
          admission_date=past_dt(30,7,30),
          discharge_date=past_dt(30,16,0)
      )
      bed1.status = "AVAILABLE"
      bed1.save()

      # Nursing notes
      NursingNote.objects.create(
          admission=adm1, note_type="ASSESSMENT",
          content="Patient admitted for elective day-case cataract surgery. Alert and oriented. BP 138/84 mmHg, PR 76/min, SpO2 98%. Right eye dilated with Tropicamide 1% x 3 doses. Pre-op checks completed. Surgical consent signed.",
          vital_signs={"bp": "138/84", "pr": "76", "spo2": "98", "temp": "36.7"},
          nurse=theatre_nrs, created_by=theatre_nrs,
      )
      NursingNote.objects.create(
          admission=adm1, note_type="PROCEDURE",
          content="Patient transferred to theatre at 09:00. WHO surgical safety checklist completed — Sign In, Time Out, and Sign Out all done. Patient returned from theatre at 10:30. Eye pad and shield applied to right eye. Stable post-operatively.",
          vital_signs={"bp": "132/80", "pr": "74", "spo2": "99"},
          nurse=theatre_nrs, created_by=theatre_nrs,
      )
      NursingNote.objects.create(
          admission=adm1, note_type="OBSERVATION",
          content="Post-op 2 hours review: Patient comfortable. No pain. No nausea. Eye pad intact. IV cannula removed. Post-op drops prescribed. Discharge instructions given. Patient discharged at 16:00 with escort.",
          vital_signs={"bp": "130/78", "pr": "72", "spo2": "99"},
          nurse=ward_nrs, created_by=ward_nrs,
      )

  # Theatre session + procedure
  ts1, _ = TheatreSession.objects.get_or_create(
      session_date=past(30), theatre_name="Main Theatre",
      defaults=dict(
          start_time=dtime(8,0), end_time=dtime(13,0),
          status=TheatreSessionStatus.COMPLETED,
          lead_surgeon=cataract_sx, anaesthetist_name="Dr. Yossa Pierre",
          scrub_nurse=theatre_nrs, circulating_nurse=theatre_nrs,
          notes="Cataract list — 6 cases scheduled", created_by=cataract_sx,
      )
  )
  tp1 = TheatreProcedure.objects.create(
      session=ts1, surgical_booking=sb1, patient=p1, surgeon=cataract_sx,
      procedure=SurgeryType.PHACO, procedure_notes="Phaco + PC IOL, RE",
      eye_laterality="RE", anaesthesia_type="LOCAL", position_on_list=1,
      knife_time=dtime(9,5), closure_time=dtime(9,40),
      iol_model="Acrysof SN60WF", iol_power="+22.50 D",
      iol_lot_number="LOT-2025-4892", iol_type="Monofocal Acrylic",
      sign_in_done=True, sign_in_time=dtime(8,55),
      sign_in_identity_confirmed=True, sign_in_site_marked=True,
      sign_in_anaesthesia_safe=True, sign_in_pulse_oximeter=True, sign_in_allergies=True,
      time_out_done=True, time_out_time=dtime(9,3),
      time_out_team_introduced=True, time_out_site_confirmed=True,
      time_out_antibiotics=True, time_out_imaging_displayed=True,
      sign_out_done=True, sign_out_time=dtime(9,42),
      sign_out_instrument_count_correct=True, sign_out_specimen_labelled=False,
      sign_out_equipment_issues=False, sign_out_recovery_plan=True,
      intraop_findings="Clear cornea incision made. Capsulorrhexis performed. Hydrodissection and hydrodelineation done. Phacoemulsification with divide and conquer technique. Cortex aspirated. Bag inflated with viscoelastic. IOL inserted in bag.",
      complications="None. Procedure uneventful.",
      outcome=ProcedureOutcome.SUCCESS,
      post_op_notes="RE padded and shielded. Review tomorrow for pad removal and visual acuity check.",
      post_op_medications="Chloramphenicol 0.5% drops QID x 2 weeks, Prednisolone 1% drops QID tapering x 6 weeks, Diclofenac 0.1% drops QID x 2 weeks. Avoid rubbing. No heavy lifting.",
      created_by=cataract_sx,
  )

  # CSSD — sterilization cycle for theatre
  sc1 = SterilizationCycle.objects.create(
      cycle_number=f"SEED-CSSD-{past(30).strftime('%Y%m%d')}-001",
      method=SterilizationMethod.AUTOCLAVE,
      start_time=past_dt(30,6,30), end_time=past_dt(30,7,30),
      temperature=Decimal("134.0"), pressure=Decimal("2.20"),
      duration_minutes=60, operator=cssd_tech,
      is_successful=True, bi_test_result="PASS",
      notes="Pre-operative autoclave cycle for cataract theatre list.",
      created_by=cssd_tech,
  )
  sc1.instruments.add(instr_map["PHACO-001"], instr_map["SPEC-001"], instr_map["NDH-001"])
  sc1.sets.add(phaco_set)

  dr1 = DispatchRecord.objects.create(
      dispatch_number=f"SEED-DR-{past(30).strftime('%Y%m%d')}-001",
      to_department=dept_cat or theatre_dept,
      dispatch_time=past_dt(30,7,45), dispatched_by=cssd_tech,
      received_by="Nurse Berthe Atangana (Theatre)",
      notes="Phaco set dispatched to theatre for cataract list",
      created_by=cssd_tech,
  )
  dr1.sets.add(phaco_set)

  # Billing — surgery invoice
  make_invoice(p1, c1, [
      ("Consultation Fee — Cataract Surgeon",  ServiceCategory.CONSULTATION, 1, 20000),
      ("Biometry (A-Scan / IOL Master)",       ServiceCategory.INVESTIGATION, 1, 15000),
      ("Pre-operative Lab Package",            ServiceCategory.LABORATORY,   1, 35000),
      ("Phacoemulsification + IOL (RE)",       ServiceCategory.SURGICAL,    1, 200000),
      ("Day Case Admission (1 day)",           ServiceCategory.SURGICAL,    1, 20000),
      ("Post-op medications",                  ServiceCategory.PHARMACY,     1, 25000),
  ], days_ago=30)

  journeys_done += 1
  print(f"    Journey 1 OK  Cataract surgery (phaco + IOL, RE) — {p1.full_name}")

  # ╔══════════════════════════════════════════════════════════════════════╗
  # ║  JOURNEY 2 — Glaucoma with visual field loss                        ║
  # ╚══════════════════════════════════════════════════════════════════════╝
  p2 = patient(1)
  dept_glauc = get_dept("Glaucoma") or dept_gen

  v2 = Visit.objects.create(
      patient=p2, chief_complaint="Headache and seeing halos around lights",
      status="DISCHARGED", billing_type="SELF_PAY", service_tier="STANDARD",
      created_by=glaucoma_sp, attending_doctor=glaucoma_sp,
  )
  Visit.objects.filter(pk=v2.pk).update(visit_date=past_dt(20))

  c2 = Consultation.objects.create(
      visit=v2, patient=p2, department=dept_glauc, consulting_doctor=glaucoma_sp,
      status=ConsultationStatus.COMPLETED,
      presenting_complaint="Headache over brow for 3 months. Halos around lights. Occasional nausea.",
      history_of_presenting_complaint="Gradual onset headache and blurring. No eye redness or pain initially but worsening. Peripheral vision seems reduced.",
      ocular_history="Wears spectacles for presbyopia. No previous eye surgery.",
      systemic_history="No hypertension, no diabetes. BMI 28.",
      drug_history="Paracetamol PRN for headaches",
      family_history="Mother had glaucoma.",
      examination_findings={
          "visual_acuity": {"right": "6/9", "left": "6/12"},
          "iop": {"right": 28, "left": 32, "method": "Goldmann", "time": "10:00"},
          "slit_lamp": {
              "right": {"cornea": "Clear", "AC": "Shallow anteriorly — Van Herick grade 2", "iris": "Normal", "lens": "Clear", "angle": "Narrow"},
              "left":  {"cornea": "Mild corneal oedema", "AC": "Very shallow — Van Herick grade 1", "iris": "Fixed mid-dilated pupil", "lens": "Clear"}
          },
          "fundus": {
              "right": {"disc": "0.7 C:D ratio, superior rim thinning", "macula": "Flat", "vessels": "Normal"},
              "left":  {"disc": "0.8 C:D ratio, inferior notching, rim haemorrhage", "macula": "Flat", "vessels": "Normal"}
          },
          "gonioscopy": "Both eyes: narrow angles. Left: appositional closure inferiorly.",
          "pachymetry": {"right": "528 um", "left": "531 um"},
      },
      management_plan="Primary angle closure glaucoma. Commence Timolol 0.5% BD both eyes + Latanoprost 0.005% ON both eyes. Acetazolamide 250mg stat to lower IOP. YAG PI planned. Visual field and OCT optic nerve ordered. Review in 1 week.",
      follow_up_date=past(13),
      created_by=glaucoma_sp,
  )
  Consultation.objects.filter(pk=c2.pk).update(consultation_date=past_dt(20,9,30))

  for code in ("H40.20",):
      dx = dx_map.get(code)
      if dx:
          ConsultationDiagnosis.objects.get_or_create(consultation=c2, diagnosis=dx, defaults={"is_primary": True})

  # Investigations
  for inv_code, eye_str, indication, r_data, interpretation in [
      ("VF", "BE", "Glaucoma — bilateral perimetry",
       {"RE_MD": "-4.2 dB", "LE_MD": "-8.7 dB", "RE_pattern": "Superior arcuate defect", "LE_pattern": "Inferior and superior arcuate scotoma"},
       "Left eye: significant superior and inferior arcuate scotoma consistent with moderate glaucoma damage. Right eye: early superior arcuate defect."),
      ("OCT", "BE", "OCT optic nerve head and RNFL — glaucoma staging",
       {"RE_RNFL_avg": "82 um (yellow — borderline)", "LE_RNFL_avg": "64 um (red — outside normal)", "RE_GCC": "Within normal", "LE_GCC": "Inferior thinning"},
       "Left eye RNFL significantly thinned inferiorly consistent with moderate glaucomatous damage. Right eye borderline inferior RNFL."),
      ("PACH", "BE", "Corneal pachymetry for IOP correction",
       {"RE_CCT": "528 um", "LE_CCT": "531 um"},
       "Corneal thickness within average range. IOP measurements reliable."),
  ]:
      io = InvestigationOrder.objects.create(
          consultation=c2, patient=p2, ordered_by=glaucoma_sp,
          investigation_type=inv_type_map[inv_code],
          urgency="URGENT", clinical_indication=indication, eye=eye_str,
          status="COMPLETED", created_by=glaucoma_sp,
      )
      InvestigationResult.objects.create(
          order=io, performed_by=inv_tech, is_normal=False, is_verified=True,
          result_data=r_data, interpretation=interpretation, created_by=inv_tech,
      )

  # Drug prescription
  rx2 = DrugPrescription.objects.create(
      consultation=c2, patient=p2, prescribed_by=glaucoma_sp,
      notes="Start immediately. Critical — IOP 32 left eye.", created_by=glaucoma_sp,
  )
  for drug_name, eye_str, freq, duration in [
      ("Timolol 0.5% Eye Drops",    "BE", "BD",  "Ongoing — do not stop"),
      ("Latanoprost 0.005% Eye Drops","BE","OD nocte","Ongoing"),
      ("Acetazolamide 250mg Tablet", "NA", "BD",  "7 days then review"),
  ]:
      DrugPrescriptionItem.objects.create(
          prescription=rx2, drug_name=drug_name, drug_form="EYE_DROP" if "Drop" in drug_name else "TABLET",
          concentration="", dose="1 drop" if "Drop" in drug_name else "1 tablet",
          frequency=freq, duration=duration, route="TOPICAL" if "Drop" in drug_name else "ORAL",
          eye=eye_str, quantity=1,
      )

  # Dispensing
  d2 = Dispensing.objects.create(
      patient=p2, prescription=rx2, dispensed_by=pharmacist,
      status="DISPENSED", total_amount=Decimal("32000"), amount_paid=Decimal("32000"),
      notes="All medications dispensed. Patient counseled on glaucoma drops — importance of compliance.",
      created_by=pharmacist,
  )
  for dname, qty, price in [("Timolol 0.5% Eye Drops",1,4000),("Latanoprost 0.005% Eye Drops",1,16000),("Acetazolamide 250mg Tablet",14,200)]:
      drug_obj = drug_map.get(dname)
      stock = drug_obj.stock_items.filter(is_deleted=False).first() if drug_obj else None
      if drug_obj:
          DispensingItem.objects.create(
              dispensing=d2, drug=drug_obj, stock_batch=stock,
              quantity_dispensed=qty, unit_price=Decimal(str(price)),
          )

  make_invoice(p2, c2, [
      ("Glaucoma Specialist Consultation",  ServiceCategory.CONSULTATION, 1, 25000),
      ("Visual Field (Perimetry)",          ServiceCategory.INVESTIGATION, 1, 20000),
      ("OCT Optic Nerve + RNFL",           ServiceCategory.INVESTIGATION, 1, 25000),
      ("Corneal Pachymetry",               ServiceCategory.INVESTIGATION, 1, 10000),
      ("Glaucoma Medications x3",          ServiceCategory.PHARMACY,      1, 32000),
  ], days_ago=20)
  journeys_done += 1
  print(f"    Journey 2 OK  Glaucoma with visual field loss — {p2.full_name}")

  # ╔══════════════════════════════════════════════════════════════════════╗
  # ║  JOURNEY 3 — Diabetic Retinopathy                                   ║
  # ╚══════════════════════════════════════════════════════════════════════╝
  p3 = patient(2)
  dept_ret = get_dept("Retina") or dept_gen

  v3 = Visit.objects.create(
      patient=p3, chief_complaint="Blurred central vision, floaters",
      status="DISCHARGED", billing_type="INSURANCE", service_tier="STANDARD",
      created_by=retina_sp, attending_doctor=retina_sp,
  )
  Visit.objects.filter(pk=v3.pk).update(visit_date=past_dt(10))

  c3 = Consultation.objects.create(
      visit=v3, patient=p3, department=dept_ret, consulting_doctor=retina_sp,
      status=ConsultationStatus.COMPLETED,
      presenting_complaint="Blurring central vision right eye for 3 months. Floating spots both eyes.",
      history_of_presenting_complaint="Known diabetic for 12 years (Type 2). Poor glycaemic control. HbA1c 11.2% at last check. No previous retinal treatment.",
      ocular_history="Bilateral diabetic retinopathy, previously followed by general ophthalmologist. No laser treatment.",
      systemic_history="Type 2 DM on Metformin + Glibenclamide. Hypertension on Lisinopril. BMI 32.",
      drug_history="Metformin 1g BD, Glibenclamide 5mg OD, Lisinopril 10mg OD",
      family_history="Mother has diabetes.",
      examination_findings={
          "visual_acuity": {"right": "6/36", "left": "6/18"},
          "iop": {"right": 15, "left": 14},
          "slit_lamp": {
              "right": {"lens": "Mild nuclear sclerosis", "vitreous": "Floaters visible"},
              "left":  {"lens": "Mild nuclear sclerosis", "vitreous": "Clear"},
          },
          "fundus": {
              "right": {"disc": "Normal", "macula": "Hard exudates at fovea, macular oedema suspected, circinate exudate ring", "vessels": "Microaneurysms, blot haemorrhages, venous beading. Neovascularisation of disc.", "periphery": "Pre-retinal haemorrhage superiorly"},
              "left":  {"disc": "Normal 0.4 C:D", "macula": "Hard exudates temporal to fovea, mild CSME", "vessels": "Scattered microaneurysms, dot haemorrhages, no NVD/NVE", "periphery": "Dot blot haemorrhages peripherally"},
          },
      },
      management_plan="Proliferative diabetic retinopathy RE. CSME both eyes. Urgent pan-retinal photocoagulation RE. OCT macula both eyes + FFA ordered. Urgent diabetologist referral for glycaemic control. FBS and HbA1c ordered.",
      follow_up_date=past(3),
      created_by=retina_sp,
  )
  Consultation.objects.filter(pk=c3.pk).update(consultation_date=past_dt(10,11,0))

  for code in ("H35.02", "H35.01"):
      dx = dx_map.get(code)
      if dx:
          ConsultationDiagnosis.objects.get_or_create(consultation=c3, diagnosis=dx, defaults={"is_primary": code=="H35.02"})

  for inv_code, eye_str, indication, r_data, interp in [
      ("OCT", "BE", "Macular OCT for CSME assessment",
       {"RE_CMT": "489 um (abnormal >280)", "LE_CMT": "325 um (mildly elevated)", "RE_pattern": "Diffuse macular oedema with SRF", "LE_pattern": "Cystoid macular oedema"},
       "Right eye: significant cystoid macular oedema with subretinal fluid. Left eye: mild cystoid macular oedema. Both eyes require treatment."),
      ("FFA", "BE", "Fluorescein angiography for DR staging and treatment planning",
       {"RE": "NVD confirmed, pre-retinal haemorrhage, late leakage at fovea, ischaemia zones", "LE": "Microaneurysms, focal leakage at macula, no NVD"},
       "Right eye: proliferative DR with NVD — urgent PRP required. Left eye: moderate non-proliferative DR with CSME."),
  ]:
      io = InvestigationOrder.objects.create(
          consultation=c3, patient=p3, ordered_by=retina_sp,
          investigation_type=inv_type_map[inv_code],
          urgency="URGENT", clinical_indication=indication, eye=eye_str,
          status="COMPLETED", created_by=retina_sp,
      )
      InvestigationResult.objects.create(
          order=io, performed_by=inv_tech, is_normal=False, is_verified=True,
          result_data=r_data, interpretation=interp, created_by=inv_tech,
      )

  lo3 = LabOrder.objects.create(
      consultation=c3, patient=p3, ordered_by=retina_sp, urgency="URGENT", status="COMPLETED",
      clinical_indication="Diabetic retinopathy — metabolic workup and renal function.",
      created_by=retina_sp,
  )
  lab_results_3 = {
      "FBS": ("14.3 mmol/L", "mmol/L", "3.9–5.6", True, False, "Markedly elevated FBS — very poor glycaemic control. Urgent diabetes review."),
      "HBA1C": ("11.2%", "%", "<7%", True, False, "HbA1c severely elevated. 3-month average blood sugar ~280 mg/dL. Urgent optimisation needed."),
      "CREAT": ("98 umol/L", "umol/L", "50–110", False, False, "Renal function within normal limits."),
      "UA": ("Glucose 3+, Protein 1+, No casts", "", "No glucose/protein", True, False, "Glycosuria and microproteinuria — early diabetic nephropathy."),
  }
  for lab_code, res_tuple in lab_results_3.items():
      lt = lab_type_map.get(lab_code)
      if lt:
          item = LabOrderItem.objects.create(order=lo3, test_type=lt, status="COMPLETED")
          LabResult.objects.create(
              order_item=item, performed_by=lab_tech, is_verified=True,
              result_value=res_tuple[0], result_unit=res_tuple[1],
              reference_range=res_tuple[2], is_abnormal=res_tuple[3],
              is_critical=res_tuple[4], comment=res_tuple[5], created_by=lab_tech,
          )

  make_invoice(p3, c3, [
      ("Retina Specialist Consultation",   ServiceCategory.CONSULTATION, 1, 30000),
      ("OCT Macula Bilateral",             ServiceCategory.INVESTIGATION, 1, 30000),
      ("Fundus Fluorescein Angiography",   ServiceCategory.INVESTIGATION, 1, 45000),
      ("Diabetic Metabolic Lab Panel",     ServiceCategory.LABORATORY,   1, 25000),
  ], days_ago=10)
  journeys_done += 1
  print(f"    Journey 3 OK  Diabetic retinopathy — {p3.full_name}")

  # ╔══════════════════════════════════════════════════════════════════════╗
  # ║  JOURNEY 4 — Refraction + Optical Prescription                      ║
  # ╚══════════════════════════════════════════════════════════════════════╝
  p4 = patient(3)
  dept_ref = get_dept("Refraction") or get_dept("Optometry") or dept_gen

  v4 = Visit.objects.create(
      patient=p4, chief_complaint="Eye strain and headaches, difficulty reading",
      status="DISCHARGED", billing_type="SELF_PAY", service_tier="STANDARD",
      created_by=optometrist, attending_doctor=optometrist,
  )
  Visit.objects.filter(pk=v4.pk).update(visit_date=past_dt(5))

  c4 = Consultation.objects.create(
      visit=v4, patient=p4, department=dept_ref, consulting_doctor=optometrist,
      status=ConsultationStatus.COMPLETED,
      presenting_complaint="Difficulty reading and close work. Headaches at end of day. Squinting to see distant objects.",
      history_of_presenting_complaint="Symptoms for 6 months. Never had spectacles before. Worse after prolonged computer use.",
      ocular_history="No previous spectacles. No surgery. No significant eye disease.",
      systemic_history="Generally healthy. Occasional tension headaches.",
      drug_history="None",
      examination_findings={
          "visual_acuity": {
              "right_unaided": "6/18", "left_unaided": "6/24",
              "right_ph": "6/6", "left_ph": "6/6",
              "right_best": "6/6 with -1.50/-0.75x90", "left_best": "6/6 with -2.00/-0.50x80",
          },
          "iop": {"right": 12, "left": 13},
          "cover_test": "Orthophoria at distance and near",
          "motility": "Full",
          "slit_lamp": {
              "right": {"cornea": "Clear", "lens": "Clear", "AC": "Normal depth"},
              "left":  {"cornea": "Clear", "lens": "Clear", "AC": "Normal depth"},
          },
          "fundus": {
              "right": {"disc": "0.3 C:D, healthy", "macula": "Normal", "vessels": "Normal"},
              "left":  {"disc": "0.3 C:D, healthy", "macula": "Normal", "vessels": "Normal"},
          },
          "near_vision": {"right": "N8 with +1.00 add", "left": "N8 with +1.00 add"},
      },
      management_plan="Compound myopic astigmatism both eyes with early presbyopia. Bifocal or progressive spectacles prescribed. Review in 12 months.",
      follow_up_date=past(0) + timedelta(days=365),
      created_by=optometrist,
  )
  Consultation.objects.filter(pk=c4.pk).update(consultation_date=past_dt(5,10,0))

  for code in ("H52.10", "H52.4"):
      dx = dx_map.get(code)
      if dx:
          ConsultationDiagnosis.objects.get_or_create(consultation=c4, diagnosis=dx, defaults={"is_primary": code=="H52.10"})

  # Optical prescription
  OpticalPrescription.objects.create(
      consultation=c4, patient=p4, prescribed_by=optometrist,
      prescription_type="SPECTACLE",
      re_sphere=Decimal("-1.50"), re_cylinder=Decimal("-0.75"), re_axis=90,
      re_add=Decimal("1.00"), re_visual_acuity="6/6",
      le_sphere=Decimal("-2.00"), le_cylinder=Decimal("-0.50"), le_axis=80,
      le_add=Decimal("1.00"), le_visual_acuity="6/6",
      interpupillary_distance=Decimal("63.0"), near_ipd=Decimal("60.0"),
      lens_type="Progressive (Anti-Reflection coating)",
      frame_advice="Light frame recommended due to mild minus lenses.",
      notes="Progressive lenses for distance and near. Patient educated on progressive lens adaptation.",
      is_dispensed=True, created_by=optometrist,
  )

  make_invoice(p4, c4, [
      ("Optometry Consultation + Refraction",  ServiceCategory.CONSULTATION, 1, 10000),
      ("Progressive Spectacle Lenses (Pair)",  ServiceCategory.SURGICAL,    1, 45000),
      ("Spectacle Frame",                      ServiceCategory.SURGICAL,    1, 20000),
  ], days_ago=5)
  journeys_done += 1
  print(f"    Journey 4 OK  Refraction + optical prescription — {p4.full_name}")

  # ╔══════════════════════════════════════════════════════════════════════╗
  # ║  JOURNEY 5 — Paediatric Strabismus Surgery                         ║
  # ╚══════════════════════════════════════════════════════════════════════╝
  p5 = patient(4)
  dept_paed = get_dept("Pediatric") or get_dept("Paediatric") or dept_gen

  v5 = Visit.objects.create(
      patient=p5, chief_complaint="Squinting eye since childhood",
      status="DISCHARGED", billing_type="SELF_PAY", service_tier="STANDARD",
      created_by=paed_ophtho, attending_doctor=paed_ophtho,
  )
  Visit.objects.filter(pk=v5.pk).update(visit_date=past_dt(60))

  c5 = Consultation.objects.create(
      visit=v5, patient=p5, department=dept_paed, consulting_doctor=paed_ophtho,
      status=ConsultationStatus.COMPLETED,
      presenting_complaint="Child with in-turning left eye since age 2. Worsening.",
      history_of_presenting_complaint="Parents noticed left eye turning inwards at age 2. Seems worse when child is tired. Wore spectacles from age 3 with minimal improvement.",
      ocular_history="Spectacle correction since age 3. Patching therapy tried for 6 months with partial improvement.",
      systemic_history="Normal birth, developmental milestones met. No systemic illness.",
      drug_history="None",
      family_history="Uncle had squint surgery as a child.",
      examination_findings={
          "visual_acuity": {"right": "6/9", "left": "6/24", "right_cyclo": "-1.00/-0.50x90", "left_cyclo": "-2.50/-1.00x80"},
          "cover_test": "Left esotropia ~30 prism dioptres at distance and near",
          "hirschberg": "Light reflex: RE central, LE displaced nasally ~2mm (≈30PD esotropia)",
          "prism_cover": {"distance": "ET 30 PD", "near": "ET 28 PD"},
          "motility": "Full range both eyes. No A/V pattern.",
          "binocular_vision": "Absent stereopsis. Alternating suppression left eye.",
          "fundus": {"right": "Normal", "left": "Normal disc and macula"},
          "cycloplegic_refraction": {"right": "-1.00/-0.50x90", "left": "-2.50/-1.00x80"},
      },
      management_plan="Left accommodative-partially accommodative esotropia with amblyopia. Surgery planned: left medial rectus recession + lateral rectus resection. Pre-op under GA biometry done. Counseled parents on surgical risks and amblyopia treatment continuing post-op.",
      follow_up_date=past(30),
      created_by=paed_ophtho,
  )
  Consultation.objects.filter(pk=c5.pk).update(consultation_date=past_dt(60,9,0))

  for code in ("H50.00", "H53.00"):
      dx = dx_map.get(code)
      if dx:
          ConsultationDiagnosis.objects.get_or_create(consultation=c5, diagnosis=dx, defaults={"is_primary": code=="H50.00"})

  sb5 = SurgicalBooking.objects.create(
      patient=p5, consultation=c5, surgeon=paed_ophtho, admission_officer=adm_officer,
      procedure=SurgeryType.STRABISMUS,
      procedure_notes="Left medial rectus recession 5mm + left lateral rectus resection 7mm",
      eye_laterality="LE", anaesthesia_type="GENERAL",
      theatre="Paediatric Theatre", status=SurgicalBookingStatus.COMPLETED,
      surgery_category="STRABISMUS",
      pre_op_requirements="Fasting: no solids 6h, clear fluids 2h. Paediatric GA consent from parents.",
      counseling_notes="Both parents counseled extensively on strabismus surgery. Risks: over/undercorrection, infection, re-operation. Benefits: improved alignment, better binocular vision potential. Consent signed by father.",
      consent_signed=True,
      total_amount=180000, deposit_required=90000, deposit_paid=90000,
      surgery_date=past_dt(40, 8, 0),
      created_by=adm_officer,
  )

  # Day case admission for strabismus
  bed5 = get_available_bed("Day Case Surgical Unit")
  if bed5:
      bed5.status = "OCCUPIED"
      bed5.save()
      adm5 = Admission.objects.create(
          patient=p5, bed=bed5, admitting_doctor=paed_ophtho, surgical_booking=sb5,
          status=AdmissionStatus.DISCHARGED,
          diagnosis_on_admission="Left esotropia 30PD with left amblyopia. For strabismus surgery under GA.",
          discharge_summary="Strabismus surgery performed under GA. Left MR recession + LR resection. Alignment improved to near orthophoria post-op. Child stable and discharged with parents.",
          created_by=adm_officer,
      )
      Admission.objects.filter(pk=adm5.pk).update(admission_date=past_dt(40,7,0), discharge_date=past_dt(40,15,0))
      bed5.status = "AVAILABLE"
      bed5.save()
      NursingNote.objects.create(
          admission=adm5, note_type="ASSESSMENT",
          content="Child admitted for elective strabismus surgery under general anaesthesia. Pre-op fasting confirmed. Consent signed by parents. Weight 22kg. Paediatric anaesthetist reviewed. IV access inserted. Atropine eye drops instilled.",
          vital_signs={"wt": "22kg", "hr": "96", "rr": "22", "temp": "36.8", "spo2": "99"},
          nurse=theatre_nrs, created_by=theatre_nrs,
      )

  ts5, _ = TheatreSession.objects.get_or_create(
      session_date=past(40), theatre_name="Paediatric Theatre",
      defaults=dict(
          start_time=dtime(8,0), end_time=dtime(12,0), status=TheatreSessionStatus.COMPLETED,
          lead_surgeon=paed_ophtho, anaesthetist_name="Dr. Amadou Sow (Paediatric Anaesthetist)",
          scrub_nurse=theatre_nrs, notes="Paediatric strabismus list", created_by=paed_ophtho,
      )
  )
  TheatreProcedure.objects.create(
      session=ts5, surgical_booking=sb5, patient=p5, surgeon=paed_ophtho,
      procedure=SurgeryType.STRABISMUS,
      procedure_notes="Left MR recession 5mm + LE LR resection 7mm. Adjustable sutures placed.",
      eye_laterality="LE", anaesthesia_type="GENERAL", position_on_list=1,
      knife_time=dtime(9,0), closure_time=dtime(9,55),
      sign_in_done=True, time_out_done=True, sign_out_done=True,
      sign_in_identity_confirmed=True, sign_in_site_marked=True, sign_in_anaesthesia_safe=True,
      sign_in_pulse_oximeter=True, sign_in_allergies=True,
      time_out_team_introduced=True, time_out_site_confirmed=True, time_out_antibiotics=True,
      intraop_findings="MR identified. 5mm recession performed with 6/0 Vicryl sutures. LR resection 7mm. Good muscle tension. Alignment checked with forced duction.",
      complications="None. GA uneventful.",
      outcome=ProcedureOutcome.SUCCESS,
      post_op_notes="Alignment near orthophoria. Chloramphenicol ointment applied. Ice pack to lids. Review in 1 week.",
      post_op_medications="Chloramphenicol 0.5% drops QID x 2 weeks. Ibuprofen syrup 100mg/5ml TDS PRN for pain.",
      created_by=paed_ophtho,
  )

  make_invoice(p5, c5, [
      ("Paediatric Ophthalmology Consultation",  ServiceCategory.CONSULTATION, 1, 15000),
      ("Strabismus Surgery (GA)",                ServiceCategory.SURGICAL,    1, 180000),
      ("Paediatric Day Case Admission",          ServiceCategory.SURGICAL,    1, 20000),
      ("Post-op Medications",                    ServiceCategory.PHARMACY,     1, 8000),
  ], days_ago=40)
  journeys_done += 1
  print(f"    Journey 5 OK  Paediatric strabismus surgery — {p5.full_name}")

  # ╔══════════════════════════════════════════════════════════════════════╗
  # ║  JOURNEY 6 — Retinal Detachment Emergency + Vitrectomy             ║
  # ╚══════════════════════════════════════════════════════════════════════╝
  p6 = patient(5)

  v6 = Visit.objects.create(
      patient=p6, chief_complaint="EMERGENCY: sudden vision loss right eye, flashes and floaters",
      status="DISCHARGED", billing_type="SELF_PAY", service_tier="EMERGENCY",
      created_by=retina_sp, attending_doctor=retina_sp,
  )
  Visit.objects.filter(pk=v6.pk).update(visit_date=past_dt(15))

  c6 = Consultation.objects.create(
      visit=v6, patient=p6, department=dept_ret, consulting_doctor=retina_sp,
      status=ConsultationStatus.COMPLETED,
      presenting_complaint="Sudden loss of vision right eye this morning. Saw flashes and curtain shadow from below.",
      history_of_presenting_complaint="Woke up with floaters yesterday. Today a dark curtain shadow from inferior field moving upwards. High myope.",
      ocular_history="High myopia RE: -10.00D, LE: -9.50D. Lattice degeneration previously noted.",
      systemic_history="No significant systemic illness.",
      examination_findings={
          "visual_acuity": {"right": "CF 30cm", "left": "6/18 with correction"},
          "iop": {"right": 8, "left": 14},
          "slit_lamp": {"right": {"vitreous": "Tobacco dust (Shafer's sign) ++", "lens": "Clear"}, "left": {"vitreous": "Clear"}},
          "fundus": {
              "right": {"disc": "Normal", "macula": "Macula flat but threatened — detachment approaching", "vessels": "Normal", "periphery": "Rhegmatogenous RD — superior bullous detachment, horseshoe tear at 11 o'clock superonasally"},
              "left":  {"disc": "Normal", "macula": "Normal", "vessels": "Normal", "periphery": "Lattice at 10–11 o'clock — no breaks identified"},
          },
          "bscan": "Confirmed retinal detachment RE. Macula on — no PVR.",
      },
      management_plan="Rhegmatogenous retinal detachment RE — macula on. EMERGENCY: PPV + SF6 gas tamponade planned today. Urgent pre-op workup ordered. Booked as emergency case.",
      created_by=retina_sp,
  )
  Consultation.objects.filter(pk=c6.pk).update(consultation_date=past_dt(15,8,30))

  dx = dx_map.get("H33.00")
  if dx:
      ConsultationDiagnosis.objects.get_or_create(consultation=c6, diagnosis=dx, defaults={"is_primary": True})

  io6 = InvestigationOrder.objects.create(
      consultation=c6, patient=p6, ordered_by=retina_sp,
      investigation_type=inv_type_map["BSCAN"],
      urgency="EMERGENCY", clinical_indication="Suspected retinal detachment RE — B-scan urgently needed",
      eye="RE", status="COMPLETED", created_by=retina_sp,
  )
  InvestigationResult.objects.create(
      order=io6, performed_by=inv_tech, is_normal=False, is_verified=True,
      result_data={"finding": "Echogenic membrane arising from disc to periphery, bullous, macula still attached"},
      interpretation="B-scan confirms total rhegmatogenous RD right eye. Macula on. No PVR features. Urgent surgical repair needed.",
      created_by=inv_tech,
  )

  # Emergency lab
  lo6 = LabOrder.objects.create(
      consultation=c6, patient=p6, ordered_by=retina_sp, urgency="EMERGENCY", status="COMPLETED",
      clinical_indication="Emergency pre-op workup for retinal detachment surgery.", created_by=retina_sp,
  )
  for lab_code in ["CBC","COAG","GTYPE"]:
      lt = lab_type_map.get(lab_code)
      if lt:
          item = LabOrderItem.objects.create(order=lo6, test_type=lt, status="COMPLETED")
          vals = {
              "CBC": ("Hb 13.8 g/dL, WBC 8.2, PLT 198", "","Normal range", False, False, "CBC within normal limits"),
              "COAG": ("PT 12.8s, INR 1.0, APTT 29s", "","Normal", False, False, "Normal coagulation"),
              "GTYPE": ("Blood group O positive", "","", False, False, "O+ — 2 units available if needed"),
          }.get(lab_code, ("Normal","","",False,False,""))
          LabResult.objects.create(
              order_item=item, performed_by=lab_tech, is_verified=True,
              result_value=vals[0], result_unit=vals[1], reference_range=vals[2],
              is_abnormal=vals[3], is_critical=vals[4], comment=vals[5], created_by=lab_tech,
          )

  sb6 = SurgicalBooking.objects.create(
      patient=p6, consultation=c6, surgeon=retina_sp, admission_officer=adm_officer,
      procedure=SurgeryType.VITRECTOMY, procedure_notes="PPV + SF6 gas tamponade for RRD with superior horseshoe tear",
      eye_laterality="RE", anaesthesia_type="LOCAL",
      theatre="Main Theatre", status=SurgicalBookingStatus.COMPLETED,
      surgery_category="RETINA",
      counseling_notes="Emergency counseling done. Patient understands vision-threatening nature. Risks of GA/local, re-detachment, PVR, cataract, gas tamponade positioning requirements. Consented.",
      consent_signed=True,
      total_amount=400000, deposit_required=200000, deposit_paid=200000,
      surgery_date=past_dt(15,14,0),
      created_by=adm_officer,
  )

  bed6 = get_available_bed("General Ophthalmic Ward")
  if bed6:
      bed6.status = "OCCUPIED"
      bed6.save()
      adm6 = Admission.objects.create(
          patient=p6, bed=bed6, admitting_doctor=retina_sp, surgical_booking=sb6,
          status=AdmissionStatus.DISCHARGED,
          diagnosis_on_admission="Rhegmatogenous retinal detachment right eye — macula on. Emergency PPV.",
          discharge_summary="PPV + endolaser + SF6 25% gas performed RE. Retina reattached. Postured face-down for 1 week. VA at discharge: HM. Reviewed at 1 week: retina attached, VA 6/60. Gas 70% fill.",
          created_by=adm_officer,
      )
      Admission.objects.filter(pk=adm6.pk).update(admission_date=past_dt(15,11,0), discharge_date=past_dt(10,10,0))
      bed6.status = "AVAILABLE"
      bed6.save()
      for day_offset, note_type, content in [
          (15, "ASSESSMENT", "Emergency admission for RRD. Patient anxious. Pupil dilated. IV access x2. NBM for emergency surgery this afternoon. BP 140/88, PR 90, SpO2 99%."),
          (14, "PROCEDURE", "Returned from theatre. PPV + endolaser + SF6 25% performed. Stable post-op. Face-down positioning commenced. Analgesia given."),
          (13, "OBSERVATION", "Day 1 post-op. Patient compliant with face-down position. IOP 12mmHg. No pain. Gas bubble filling ~90% of vitreous cavity. VA HM."),
          (12, "MEDICATION", "Post-op drops: Prednisolone 1% QID, Chloramphenicol 0.5% QID, Timolol 0.5% BD commenced (prophylactic). Ibuprofen 400mg TDS given."),
          (10, "HANDOVER", "Day 5 post-op. Gas bubble 80%. Retina attached on B-scan. Patient discharged home with face-down instruction for further 2 days. Review outpatient in 1 week."),
      ]:
          NursingNote.objects.create(
              admission=adm6, note_type=note_type, content=content,
              vital_signs={"bp": "138/86", "pr": "84", "spo2": "98"},
              nurse=ward_nrs, created_by=ward_nrs,
          )

  ts6, _ = TheatreSession.objects.get_or_create(
      session_date=past(15), theatre_name="Main Theatre",
      defaults=dict(
          start_time=dtime(14,0), end_time=dtime(18,0), status=TheatreSessionStatus.COMPLETED,
          lead_surgeon=retina_sp, anaesthetist_name="Dr. Yossa Pierre",
          scrub_nurse=theatre_nrs, notes="Emergency vitreoretinal case", created_by=retina_sp,
      )
  )
  TheatreProcedure.objects.create(
      session=ts6, surgical_booking=sb6, patient=p6, surgeon=retina_sp,
      procedure=SurgeryType.VITRECTOMY, procedure_notes="23G PPV + endolaser + SF6 25% gas tamponade",
      eye_laterality="RE", anaesthesia_type="LOCAL", position_on_list=1,
      knife_time=dtime(14,30), closure_time=dtime(16,15),
      sign_in_done=True, time_out_done=True, sign_out_done=True,
      sign_in_identity_confirmed=True, sign_in_site_marked=True, sign_in_anaesthesia_safe=True,
      sign_in_pulse_oximeter=True, sign_in_allergies=True,
      time_out_team_introduced=True, time_out_site_confirmed=True, time_out_antibiotics=True,
      intraop_findings="Core vitrectomy done 23G. Subretinal fluid drained via retinotomy. Horseshoe tear at 11 o'clock treated with endolaser (3 rows surround). Fluid-air exchange. SF6 25% tamponade. Sclerotomies sutured.",
      complications="Minor intraoperative haemorrhage — controlled with diathermy.",
      outcome=ProcedureOutcome.SUCCESS,
      post_op_notes="Strict face-down positioning x 7 days. Post-op drops as prescribed. Urgent review if pain or sudden vision change.",
      created_by=retina_sp,
  )

  # CSSD for vitrectomy
  sc6 = SterilizationCycle.objects.create(
      cycle_number=f"SEED-CSSD-{past(15).strftime('%Y%m%d')}-001",
      method=SterilizationMethod.PLASMA,
      start_time=past_dt(15,12,0), end_time=past_dt(15,13,30),
      temperature=Decimal("55.0"), pressure=Decimal("1.00"),
      duration_minutes=90, operator=cssd_tech,
      is_successful=True, bi_test_result="PASS",
      notes="Hydrogen peroxide plasma sterilization for vitreoretinal instruments.",
      created_by=cssd_tech,
  )
  sc6.sets.add(vitr_set)

  make_invoice(p6, c6, [
      ("Emergency Retina Consultation",        ServiceCategory.CONSULTATION, 1, 35000),
      ("B-Scan Ultrasonography",               ServiceCategory.INVESTIGATION, 1, 20000),
      ("Emergency Lab Package",                ServiceCategory.LABORATORY,   1, 20000),
      ("PPV + Endolaser + SF6 Gas",            ServiceCategory.SURGICAL,    1, 400000),
      ("Inpatient Admission (5 nights)",       ServiceCategory.SURGICAL,    5, 15000),
  ], days_ago=10)
  journeys_done += 1
  print(f"    Journey 6 OK  Retinal detachment emergency vitrectomy — {p6.full_name}")

  # ╔══════════════════════════════════════════════════════════════════════╗
  # ║  JOURNEY 7 — Pterygium Excision + Conjunctival Autograft           ║
  # ╚══════════════════════════════════════════════════════════════════════╝
  p7 = patient(6)
  dept_corn = get_dept("Cornea") or dept_gen

  v7 = Visit.objects.create(
      patient=p7, chief_complaint="Growing white tissue on right eye, blurring vision",
      status="DISCHARGED", billing_type="SELF_PAY", service_tier="STANDARD",
      created_by=oculoplast, attending_doctor=oculoplast,
  )
  Visit.objects.filter(pk=v7.pk).update(visit_date=past_dt(25))

  c7 = Consultation.objects.create(
      visit=v7, patient=p7, department=dept_corn, consulting_doctor=oculoplast,
      status=ConsultationStatus.COMPLETED,
      presenting_complaint="Fleshy growth on white of right eye for 5 years, now affecting vision.",
      history_of_presenting_complaint="Slow growing nasal growth right eye. Started as redness, now affecting the cornea. Works outdoors — farmer. Redness and foreign body sensation.",
      ocular_history="No previous surgery. No spectacles.",
      systemic_history="Healthy farmer. Works outdoors daily.",
      examination_findings={
          "visual_acuity": {"right": "6/18", "left": "6/6"},
          "iop": {"right": 13, "left": 12},
          "slit_lamp": {
              "right": {"pterygium": "Grade 3 nasal pterygium encroaching on cornea 4mm past limbus, involving visual axis, vessels and fibrous tissue, cap at pupillary margin", "cornea": "Inferior to pterygium clear. Superior and temporal clear."},
              "left":  {"cornea": "Clear, no pterygium"},
          },
          "corneal_topography": {"right": "Irregular astigmatism 3.50D nasally due to pterygium traction"},
          "fundus": {"right": "Normal", "left": "Normal"},
      },
      management_plan="Grade 3 pterygium right eye involving visual axis. Surgery recommended: pterygium excision + conjunctival autograft (CAG). Pre-op workup. Counseled on recurrence rate and importance of UV protection.",
      follow_up_date=past(11),
      created_by=oculoplast,
  )
  Consultation.objects.filter(pk=c7.pk).update(consultation_date=past_dt(25,10,0))

  dx = dx_map.get("H11.00")
  if dx:
      ConsultationDiagnosis.objects.get_or_create(consultation=c7, diagnosis=dx, defaults={"is_primary": True})

  io7 = InvestigationOrder.objects.create(
      consultation=c7, patient=p7, ordered_by=oculoplast,
      investigation_type=inv_type_map["CORNTO"],
      urgency="ROUTINE", clinical_indication="Corneal topography to document pterygium-induced irregular astigmatism",
      eye="RE", status="COMPLETED", created_by=oculoplast,
  )
  InvestigationResult.objects.create(
      order=io7, performed_by=inv_tech, is_normal=False, is_verified=True,
      result_data={"RE": "Irregular astigmatism 3.50D nasal, SAI elevated, SRI elevated"},
      interpretation="Significant irregular astigmatism secondary to pterygium traction. Surgery will likely improve corneal regularity.",
      created_by=inv_tech,
  )

  rx7 = DrugPrescription.objects.create(
      consultation=c7, patient=p7, prescribed_by=oculoplast,
      notes="Pre-op and post-op medications for pterygium excision + CAG.", created_by=oculoplast,
  )
  DrugPrescriptionItem.objects.create(
      prescription=rx7, drug_name="Chloramphenicol 0.5% Eye Drops", drug_form="EYE_DROP",
      concentration="0.5%", dose="1 drop", frequency="QID", duration="2 weeks",
      route="TOPICAL", eye="RE", quantity=2,
  )
  DrugPrescriptionItem.objects.create(
      prescription=rx7, drug_name="Dexamethasone 0.1% Eye Drops", drug_form="EYE_DROP",
      concentration="0.1%", dose="1 drop", frequency="QID tapering over 6 weeks",
      duration="6 weeks", route="TOPICAL", eye="RE", quantity=3,
  )

  sb7 = SurgicalBooking.objects.create(
      patient=p7, consultation=c7, surgeon=oculoplast, admission_officer=adm_officer,
      procedure=SurgeryType.PTERYGIUM_EXC, procedure_notes="RE pterygium excision + free conjunctival autograft",
      eye_laterality="RE", anaesthesia_type="LOCAL",
      theatre="Minor Theatre", status=SurgicalBookingStatus.COMPLETED,
      surgery_category="PTERYGIUM",
      counseling_notes="Patient counseled on pterygium surgery. Recurrence rate 5–10% with CAG technique. Importance of UV protection/sunglasses post-operatively. Consent signed.",
      consent_signed=True,
      total_amount=120000, deposit_required=60000, deposit_paid=60000,
      surgery_date=past_dt(14, 10, 0),
      created_by=adm_officer,
  )

  ts7, _ = TheatreSession.objects.get_or_create(
      session_date=past(14), theatre_name="Minor Theatre",
      defaults=dict(
          start_time=dtime(9,0), end_time=dtime(13,0), status=TheatreSessionStatus.COMPLETED,
          lead_surgeon=oculoplast, scrub_nurse=theatre_nrs,
          notes="Minor oculoplastics + cornea list", created_by=oculoplast,
      )
  )
  TheatreProcedure.objects.create(
      session=ts7, surgical_booking=sb7, patient=p7, surgeon=oculoplast,
      procedure=SurgeryType.PTERYGIUM_EXC, procedure_notes="Pterygium excision + free CAG, fibrin glue",
      eye_laterality="RE", anaesthesia_type="LOCAL", position_on_list=1,
      knife_time=dtime(10,0), closure_time=dtime(10,50),
      sign_in_done=True, time_out_done=True, sign_out_done=True,
      sign_in_identity_confirmed=True, sign_in_site_marked=True, sign_in_anaesthesia_safe=True,
      sign_in_pulse_oximeter=True, sign_in_allergies=True,
      time_out_team_introduced=True, time_out_site_confirmed=True, time_out_antibiotics=True,
      intraop_findings="Pterygium excised at limbus. Bare sclera 7x4mm. Free conjunctival autograft harvested from superotemporal bulbar conjunctiva. Graft secured with fibrin glue (Tisseel). Good graft take.",
      complications="Minor oozing controlled with cautery.",
      outcome=ProcedureOutcome.SUCCESS,
      post_op_notes="Eye padded for 24 hours. Topical antibiotics + steroids. Wear UV sunglasses outdoors permanently.",
      created_by=oculoplast,
  )

  make_invoice(p7, c7, [
      ("Pterygium / Cornea Consultation",    ServiceCategory.CONSULTATION, 1, 20000),
      ("Corneal Topography",                 ServiceCategory.INVESTIGATION, 1, 15000),
      ("Pterygium Excision + CAG (Minor Theatr.)", ServiceCategory.SURGICAL, 1, 120000),
      ("Post-op Medications",                ServiceCategory.PHARMACY,     1, 18000),
  ], days_ago=14)
  journeys_done += 1
  print(f"    Journey 7 OK  Pterygium excision + autograft — {p7.full_name}")

  # ╔══════════════════════════════════════════════════════════════════════╗
  # ║  JOURNEY 8 — Uveitis (Acute Anterior)                               ║
  # ╚══════════════════════════════════════════════════════════════════════╝
  p8 = patient(7)
  dept_uveit = get_dept("Uveitis") or dept_gen

  v8 = Visit.objects.create(
      patient=p8, chief_complaint="Painful red eye, photophobia, blurred vision",
      status="DISCHARGED", billing_type="SELF_PAY", service_tier="STANDARD",
      created_by=uveitis_sp, attending_doctor=uveitis_sp,
  )
  Visit.objects.filter(pk=v8.pk).update(visit_date=past_dt(8))

  c8 = Consultation.objects.create(
      visit=v8, patient=p8, department=dept_uveit, consulting_doctor=uveitis_sp,
      status=ConsultationStatus.COMPLETED,
      presenting_complaint="Right eye pain, photophobia, redness and blurred vision for 3 days.",
      history_of_presenting_complaint="Sudden onset right eye pain, redness, sensitivity to light, tearing. Similar episode 1 year ago in same eye treated elsewhere.",
      ocular_history="Previous acute anterior uveitis RE 1 year ago — treated with drops, resolved.",
      systemic_history="HLA-B27 positive (tested last year during previous episode). No known ankylosing spondylitis on rheumatology review.",
      drug_history="None current",
      examination_findings={
          "visual_acuity": {"right": "6/24", "left": "6/6"},
          "iop": {"right": 8, "left": 14},
          "slit_lamp": {
              "right": {
                  "lids": "Normal", "conjunctiva": "Ciliary injection ++",
                  "cornea": "KPs — fine stellate KPs on inferior endothelium, 15–20 KPs",
                  "AC": "2+ flare, 2+ cells. Fibrin strand visible inferiorly",
                  "iris": "Posterior synechiae at 6 and 8 o'clock. Miosis.",
                  "lens": "Clear",
              },
              "left": {"cornea": "Clear", "AC": "Quiet", "lens": "Clear"},
          },
          "fundus": {"right": "Disc and macula normal. No vitreous haze. No choroidal lesions.", "left": "Normal"},
          "posterior_pole": "No posterior segment involvement this episode.",
      },
      management_plan="Recurrent HLA-B27 associated acute anterior uveitis RE. Commence intensive topical steroids + cycloplegic. Monitor IOP closely. Synechiae need to be broken. Rheumatology referral maintained.",
      follow_up_date=past(3),
      created_by=uveitis_sp,
  )
  Consultation.objects.filter(pk=c8.pk).update(consultation_date=past_dt(8,9,0))

  for code in ("H20.00",):
      dx = dx_map.get(code)
      if dx:
          ConsultationDiagnosis.objects.get_or_create(consultation=c8, diagnosis=dx, defaults={"is_primary": True})

  rx8 = DrugPrescription.objects.create(
      consultation=c8, patient=p8, prescribed_by=uveitis_sp,
      notes="Intensive steroid and cycloplegic therapy for acute anterior uveitis.", created_by=uveitis_sp,
  )
  for dname, eye, freq, dur, special in [
      ("Prednisolone 1% Eye Drops",  "RE","Hourly while awake x 2 days, then QID taper","6 weeks","Taper slowly — do not stop abruptly"),
      ("Atropine 1% Eye Drops",      "RE","BD x 2 weeks","2 weeks","Dilates pupil to prevent synechiae"),
      ("Diclofenac 0.1% Eye Drops",  "RE","QID","2 weeks","Anti-inflammatory adjunct"),
  ]:
      DrugPrescriptionItem.objects.create(
          prescription=rx8, drug_name=dname, drug_form="EYE_DROP",
          concentration="", dose="1 drop", frequency=freq, duration=dur,
          route="TOPICAL", eye=eye, quantity=2 if "Pred" in dname else 1,
          special_instructions=special,
      )

  d8 = Dispensing.objects.create(
      patient=p8, prescription=rx8, dispensed_by=pharmacist,
      status="DISPENSED", total_amount=Decimal("27000"), amount_paid=Decimal("27000"),
      notes="Medications dispensed. Patient counseled on intensive steroid use — compliance critical.",
      created_by=pharmacist,
  )
  for dname, qty, price in [("Prednisolone 1% Eye Drops",2,6500),("Atropine 1% Eye Drops",1,3000),("Diclofenac 0.1% Eye Drops",2,7000)]:
      dobj = drug_map.get(dname)
      stock = dobj.stock_items.filter(is_deleted=False).first() if dobj else None
      if dobj:
          DispensingItem.objects.create(dispensing=d8, drug=dobj, stock_batch=stock, quantity_dispensed=qty, unit_price=Decimal(str(price)))

  make_invoice(p8, c8, [
      ("Uveitis Specialist Consultation",   ServiceCategory.CONSULTATION, 1, 25000),
      ("Uveitis Medications",               ServiceCategory.PHARMACY,     1, 27000),
  ], days_ago=8)
  journeys_done += 1
  print(f"    Journey 8 OK  Acute anterior uveitis — {p8.full_name}")

  # ╔══════════════════════════════════════════════════════════════════════╗
  # ║  JOURNEYS 9-15 — Multiple shorter OPD consultations                 ║
  # ╚══════════════════════════════════════════════════════════════════════╝

  short_journeys = [
      # (patient_idx, doctor, dept_kw, days_ago, chief_complaint, dx_code, exam_findings, plan, drugs, inv_codes)
      (8, ophtho, "General", 3,
       "Dry eyes, burning sensation",
       "H57.10",
       {"visual_acuity": {"right": "6/9", "left": "6/9"},
        "slit_lamp": {"right": {"TBUT": "4 seconds (low)", "staining": "Inferior punctate staining 2+", "meibomian": "Meibomian gland plugging"}, "left": {"TBUT": "5 seconds"}}},
       "Dry eye syndrome — aqueous deficient type. Lubricants + warm compresses. Review in 3 months.",
       [("Carboxymethylcellulose Eye Drops", "BE","6x daily PRN","Ongoing",1,2500)],
       []),

      (9, ophtho, "General", 2,
       "Red eyes, discharge for 2 days",
       "H10.30",
       {"visual_acuity": {"right": "6/6", "left": "6/6"},
        "slit_lamp": {"right": {"conjunctiva": "Papillary reaction ++, mucopurulent discharge", "cornea": "Clear"}, "left": {"conjunctiva": "Mild papillary reaction", "cornea": "Clear"}}},
       "Acute bacterial conjunctivitis. Chloramphenicol drops QID x 1 week. Hygiene advice given.",
       [("Chloramphenicol 0.5% Eye Drops", "BE","QID","1 week",1,3000)],
       []),

      (10, glaucoma_sp, "Glaucoma", 7,
       "Glaucoma follow-up — check IOP",
       "H40.11",
       {"visual_acuity": {"right": "6/9", "left": "6/6"},
        "iop": {"right": 16, "left": 17, "method": "Goldmann"},
        "slit_lamp": {"right": {"cornea": "Clear", "AC": "Deep"}, "left": {"cornea": "Clear"}},
        "fundus": {"right": {"disc": "0.6 C:D stable — no new changes"}, "left": {"disc": "0.5 C:D stable"}}},
       "POAG — IOP well controlled on Latanoprost + Timolol. Continue current drops. VF + OCT repeat in 6 months.",
       [("Latanoprost 0.005% Eye Drops","BE","OD nocte","3 months",1,16000),
        ("Timolol 0.5% Eye Drops","BE","BD","3 months",1,4000)],
       ["VF","OCT"]),

      (11, retina_sp, "Retina", 12,
       "Floaters and reduced vision right eye — known BRVO",
       "H34.20",
       {"visual_acuity": {"right": "6/60", "left": "6/9"},
        "iop": {"right": 14, "left": 13},
        "fundus": {"right": {"macula": "Cystoid macular oedema, hard exudates, flame haemorrhages along superotemporal arcade"}, "left": {"macula": "Normal"}}},
       "Branch retinal vein occlusion RE with CSME. Anti-VEGF injection (Bevacizumab) planned. OCT confirms macular oedema. Monthly injections x3.",
       [],
       ["OCT","FFA"]),

      (12, optometrist, "Refraction", 1,
       "School-age child failing school — suspected vision problem",
       "H52.00",
       {"visual_acuity": {"right_unaided": "6/60", "left_unaided": "6/36", "right_best": "6/6 with +3.50", "left_best": "6/6 with +3.50"},
        "cover_test": "Orthophoria", "motility": "Full"},
       "High hypermetropia both eyes. First spectacle prescription. Parents counseled. Annual review.",
       [],
       []),

      (13, oculoplast, "Oculoplastics", 18,
       "Drooping right eyelid since birth",
       "H53.00",
       {"visual_acuity": {"right": "6/36", "left": "6/6"},
        "ptosis": {"MRD1_RE": "-1mm (upper lid covers pupil)", "MRD1_LE": "+4mm", "LPS_RE": "5mm (poor)", "LPS_LE": "14mm (normal)", "levator_function": "Poor"},
        "slit_lamp": {"right": {"lid": "Unilateral congenital ptosis — complete ptosis RE"}}},
       "Congenital ptosis right eye with amblyopia. Levator function poor — FRD or Whitnall sling planned. Amblyopia patching started. Surgery consent obtained.",
       [("Atropine 1% Eye Drops","RE","OD for patching","Until surgery",1,3000)],
       []),

      (14, uveitis_sp, "Uveitis", 22,
       "Follow-up — HZO with uveitis",
       "H20.10",
       {"visual_acuity": {"right": "6/12", "left": "6/6"},
        "iop": {"right": 22, "left": 14},
        "slit_lamp": {"right": {"cornea": "Inferior dendritic keratitis resolving, pseudodendrites", "AC": "Trace flare, 1+ cells — improving", "iris": "Posterior synechiae at 5 and 7 o'clock resolving"}},
        "skin": "Previous right V1 dermatomal HZO vesicles now crusted — resolving"},
       "Herpes zoster ophthalmicus RE with stromal keratitis + anterior uveitis — improving. Continue tapering steroids + antiviral.",
       [("Prednisolone 1% Eye Drops","RE","QID tapering","4 weeks",2,6500),
        ("Timolol 0.5% Eye Drops","RE","BD","4 weeks — steroid-induced IOP",1,4000)],
       ["VF"]),
  ]

  for idx, (pt_idx, doctor, dept_kw, days_ago, complaint, dx_code, exam, plan, drugs, inv_codes) in enumerate(short_journeys):
      pt = patient(pt_idx)
      dept = get_dept(dept_kw) or dept_gen

      v = Visit.objects.create(
          patient=pt, chief_complaint=complaint,
          status="DISCHARGED", billing_type="SELF_PAY", service_tier="STANDARD",
          created_by=doctor, attending_doctor=doctor,
      )
      Visit.objects.filter(pk=v.pk).update(visit_date=past_dt(days_ago))

      c = Consultation.objects.create(
          visit=v, patient=pt, department=dept, consulting_doctor=doctor,
          status=ConsultationStatus.COMPLETED,
          presenting_complaint=complaint,
          history_of_presenting_complaint=f"{complaint}. Duration varies. Full history taken.",
          systemic_history="No significant systemic illness unless stated.",
          examination_findings=exam,
          management_plan=plan,
          created_by=doctor,
      )
      Consultation.objects.filter(pk=c.pk).update(consultation_date=past_dt(days_ago,10,0))

      dx = dx_map.get(dx_code)
      if dx:
          ConsultationDiagnosis.objects.get_or_create(consultation=c, diagnosis=dx, defaults={"is_primary": True})

      if drugs:
          rxn = DrugPrescription.objects.create(
              consultation=c, patient=pt, prescribed_by=doctor, created_by=doctor,
          )
          for dname, eye, freq, dur, qty, price in drugs:
              DrugPrescriptionItem.objects.create(
                  prescription=rxn, drug_name=dname, drug_form="EYE_DROP",
                  dose="1 drop", frequency=freq, duration=dur,
                  route="TOPICAL", eye=eye, quantity=qty,
              )
          dn = Dispensing.objects.create(
              patient=pt, prescription=rxn, dispensed_by=pharmacist,
              status="DISPENSED",
              total_amount=Decimal(str(sum(q*p for _,_,_,_,q,p in drugs))),
              amount_paid=Decimal(str(sum(q*p for _,_,_,_,q,p in drugs))),
              created_by=pharmacist,
          )

      for inv_code in inv_codes:
          if inv_code in inv_type_map:
              io = InvestigationOrder.objects.create(
                  consultation=c, patient=pt, ordered_by=doctor,
                  investigation_type=inv_type_map[inv_code],
                  urgency="ROUTINE", clinical_indication=f"Ordered for {complaint}",
                  eye="BE", status="COMPLETED", created_by=doctor,
              )
              InvestigationResult.objects.create(
                  order=io, performed_by=inv_tech, is_normal=True, is_verified=True,
                  result_data={"finding": f"Results for {inv_type_map[inv_code].name}"},
                  interpretation=f"Results reviewed — see report for details.",
                  created_by=inv_tech,
              )

      make_invoice(pt, c, [
          (f"Consultation — {dept_kw if dept_kw else 'General Ophthalmology'}", ServiceCategory.CONSULTATION, 1, 15000),
          ("Medications / Investigations", ServiceCategory.PHARMACY, 1, sum(q*p for _,_,_,_,q,p in drugs) if drugs else 0),
      ] + [(f"{inv_type_map[ic].name}", ServiceCategory.INVESTIGATION, 1, 12000) for ic in inv_codes if ic in inv_type_map],
      days_ago=days_ago)

      journeys_done += 1
      print(f"    Journey {journeys_done} OK  {complaint[:55]} — {pt.full_name}")

  # ╔══════════════════════════════════════════════════════════════════════╗
  # ║  BONUS — CSSD: 5 more sterilization cycles + dispatches            ║
  # ╚══════════════════════════════════════════════════════════════════════╝
  for i in range(1, 6):
      sc = SterilizationCycle.objects.create(
          cycle_number=f"SEED-CSSD-{past(i*5).strftime('%Y%m%d')}-{i:03d}",
          method=random.choice([SterilizationMethod.AUTOCLAVE, SterilizationMethod.DRY_HEAT, SterilizationMethod.CHEMICAL]),
          start_time=past_dt(i*5, 6, 0), end_time=past_dt(i*5, 7, 30),
          temperature=Decimal("134.0"), pressure=Decimal("2.20"),
          duration_minutes=90, operator=cssd_tech,
          is_successful=True, bi_test_result="PASS",
          notes=f"Routine sterilization cycle {i}",
          created_by=cssd_tech,
      )
      sc.sets.add(general_set)
      dr = DispatchRecord.objects.create(
          dispatch_number=f"SEED-DR-{past(i*5).strftime('%Y%m%d')}-{i:03d}",
          to_department=dept_gen or theatre_dept,
          dispatch_time=past_dt(i*5, 7, 45), dispatched_by=cssd_tech,
          received_by="Charge Nurse OPD",
          notes=f"General instruments dispatched to OPD — cycle {i}",
          created_by=cssd_tech,
      )
      dr.sets.add(general_set)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 9 — SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n[9/9] Done!\n")
print("=" * 68)

from apps.investigations.models import InvestigationOrder, InvestigationResult
from apps.laboratory.models import LabOrder, LabResult
from apps.prescriptions.models import DrugPrescription, OpticalPrescription
from apps.pharmacy.models import Dispensing
from apps.ipd.models import Admission, SurgicalBooking, TheatreProcedure, NursingNote
from apps.cssd.models import SterilizationCycle, DispatchRecord
from apps.billing.models import Invoice

print("  SYSTEM TOTALS AFTER SEED:")
print(f"  Patients         : {Patient.objects.filter(is_active=True).count()}")
print(f"  Consultations    : {Consultation.objects.filter(is_deleted=False).count()}")
print(f"  Investigations   : {InvestigationOrder.objects.filter(is_deleted=False).count()}")
print(f"  Investigation Results : {InvestigationResult.objects.filter(is_deleted=False).count()}")
print(f"  Lab Orders       : {LabOrder.objects.filter(is_deleted=False).count()}")
print(f"  Lab Results      : {LabResult.objects.filter(is_deleted=False).count()}")
print(f"  Drug Prescriptions   : {DrugPrescription.objects.filter(is_deleted=False).count()}")
print(f"  Optical Prescriptions: {OpticalPrescription.objects.filter(is_deleted=False).count()}")
print(f"  Pharmacy Dispensing  : {Dispensing.objects.filter(is_deleted=False).count()}")
print(f"  Surgical Bookings: {SurgicalBooking.objects.filter(is_deleted=False).count()}")
print(f"  Admissions       : {Admission.objects.filter(is_deleted=False).count()}")
print(f"  Theatre Procedures   : {TheatreProcedure.objects.filter(is_deleted=False).count()}")
print(f"  Nursing Notes    : {NursingNote.objects.filter(is_deleted=False).count()}")
print(f"  CSSD Cycles      : {SterilizationCycle.objects.filter(is_deleted=False).count()}")
print(f"  CSSD Dispatches  : {DispatchRecord.objects.filter(is_deleted=False).count()}")
print(f"  Invoices         : {Invoice.objects.filter(is_deleted=False).count()}")
print("=" * 68)
print("\nRun command:")
print("  python manage.py shell -c \"exec(open('seed_full_journey.py').read())\"")
print("=" * 68)
