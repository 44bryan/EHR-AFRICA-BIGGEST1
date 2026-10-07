"""Seed investigation + lab exam data on production for stats pages."""
import paramiko

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'

REMOTE_SCRIPT = r'''
import django, os, random
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ehr_project.settings.base")
django.setup()

from django.utils import timezone
from django.contrib.auth import get_user_model
from datetime import timedelta, date
User = get_user_model()
admin = User.objects.filter(username="admin").first()

from apps.patients.models import Patient
patients = list(Patient.objects.filter(is_deleted=False)[:30])
print(f"Using {len(patients)} patients")

from apps.consultations.models import Consultation
from apps.patients.models import Visit, VisitType
def get_consult(patient):
    c = Consultation.objects.filter(patient=patient, is_deleted=False).order_by("-created_at").first()
    if not c:
        visit = Visit.objects.filter(patient=patient, is_deleted=False).order_by("-visit_date").first()
        if not visit:
            visit = Visit(
                patient=patient, visit_type=VisitType.NEW,
                chief_complaint="Routine eye examination",
                created_by=admin,
            )
            visit.save()
        c = Consultation.objects.create(
            visit=visit, patient=patient, consulting_doctor=admin,
            presenting_complaint="Routine eye examination", created_by=admin,
        )
    return c

# ============ INVESTIGATION TYPES ============
from apps.investigations.models import InvestigationType, InvestigationOrder, InvestigationResult

INV_TYPES = [
    ("OCT Macula", "OCT-MAC", "OCT", "AFTER"),
    ("OCT RNFL", "OCT-RNFL", "OCT", "AFTER"),
    ("OCT Anterior Segment", "OCT-ANT", "OCT", "BEFORE"),
    ("Visual Field 24-2", "VF-24", "PERIMETRY", "BEFORE"),
    ("Visual Field 10-2", "VF-10", "PERIMETRY", "BEFORE"),
    ("Fundus Photography", "FP-COL", "FUNDUS_PHOTO", "AFTER"),
    ("Fluorescein Angiography", "FFA", "ANGIOGRAPHY", "AFTER"),
    ("A-Scan Biometry", "BIO-A", "BIOMETRY", "BEFORE"),
    ("IOL Master Biometry", "BIO-IOL", "BIOMETRY", "BEFORE"),
    ("Corneal Topography", "TOPO", "TOPOGRAPHY", "BEFORE"),
    ("Specular Microscopy", "SPEC-M", "SPECULAR", "BEFORE"),
    ("Pachymetry", "PACHY", "PACHYMETRY", "BEFORE"),
    ("B-Scan Ultrasound", "BSCAN", "ULTRASOUND", "INDIFFERENT"),
    ("Anterior Segment Photography", "AS-PHOTO", "FUNDUS_PHOTO", "BEFORE"),
    ("Keratometry", "KERAT", "TOPOGRAPHY", "BEFORE"),
]

inv_types = []
for name, code, cat, dilation in INV_TYPES:
    # Try by code first, then by name
    obj = InvestigationType.objects.filter(code=code).first()
    if not obj:
        obj = InvestigationType.objects.filter(name=name).first()
    if not obj:
        try:
            obj = InvestigationType.objects.create(
                code=code, name=name, category=cat,
                dilation_requirement=dilation,
                unit_price=random.choice([3000, 5000, 8000, 10000, 15000, 20000]),
                typical_duration_minutes=random.choice([10, 15, 20, 30]),
            )
            print(f"  Created InvestigationType: {name}")
        except Exception as e:
            print(f"  SKIP InvestigationType {name}: {e}")
            continue
    inv_types.append(obj)
print(f"Investigation types ready: {len(inv_types)}")

# ============ SEED INVESTIGATION ORDERS ============
today = timezone.localdate()
month_start = today.replace(day=1)
days_in_month = (today - month_start).days
urgencies = ["ROUTINE"] * 12 + ["URGENT"] * 3 + ["STAT"] + ["EMERGENCY"]
statuses = ["COMPLETED"] * 10 + ["ORDERED"] * 2 + ["IN_PROGRESS"] * 2 + ["CANCELLED"]
lateralities = ["OD", "OS", "OU"]
indications = [
    "Glaucoma suspect", "Diabetic retinopathy screening",
    "Cataract pre-op", "Macular degeneration follow-up",
    "Optic nerve evaluation", "Corneal assessment",
    "Post-surgical follow-up", "Uveitis workup",
    "Visual field defect evaluation", "Retinal detachment assessment",
]
interpretations = [
    "Within normal limits.",
    "Mild changes noted, recommend follow-up.",
    "Significant pathology detected.",
    "Borderline findings, correlate clinically.",
    "Normal anatomy, no pathology.",
]

created_inv = 0
for i in range(180):
    pt = random.choice(patients)
    consult = get_consult(pt)
    inv_type = random.choice(inv_types)
    day_offset = random.randint(0, max(days_in_month, 1))
    order_dt = timezone.make_aware(
        timezone.datetime(month_start.year, month_start.month,
                          month_start.day + day_offset,
                          random.randint(7, 17), random.randint(0, 59))
    )
    status = random.choice(statuses)

    order = InvestigationOrder(
        consultation=consult, patient=pt, ordered_by=admin,
        investigation_type=inv_type,
        urgency=random.choice(urgencies),
        status=status,
        clinical_indication=random.choice(indications),
        eye=random.choice(lateralities),
        location=random.choice(["CLINIC"] * 9 + ["OUTREACH"]),
        payment_status=random.choice(["PAID"] * 8 + ["UNPAID", "INSURED", "WAIVED"]),
        acquisition_status="ACQUIRED" if status == "COMPLETED" else "SCHEDULED",
        created_by=admin,
    )
    order.save()
    InvestigationOrder.objects.filter(id=order.id).update(created_at=order_dt)

    if status == "COMPLETED":
        is_normal = random.random() > 0.25
        result = InvestigationResult(
            order=order, performed_by=admin,
            result_data={"finding": "Normal" if is_normal else "Abnormal",
                         "quality": random.randint(6, 10)},
            interpretation=random.choice(interpretations),
            is_normal=is_normal,
            is_verified=random.random() > 0.3,
            version_number=1, created_by=admin,
        )
        result.save()
        InvestigationResult.objects.filter(id=result.id).update(
            created_at=order_dt + timedelta(minutes=30))
    created_inv += 1
    if (i + 1) % 50 == 0:
        print(f"  ... {i + 1} investigation orders")

print(f"Created {created_inv} investigation orders")

# ============ LAB TEST TYPES ============
from apps.laboratory.models import LabTestType, LabOrder, LabOrderItem, LabResult

LAB_TESTS = [
    ("Full Blood Count", "FBC", "HAEMATOLOGY", "QUANTITATIVE"),
    ("Hemoglobin", "HGB", "HAEMATOLOGY", "QUANTITATIVE"),
    ("Blood Glucose (Fasting)", "GLU-F", "BIOCHEMISTRY", "QUANTITATIVE"),
    ("Blood Glucose (Random)", "GLU-R", "BIOCHEMISTRY", "QUANTITATIVE"),
    ("HbA1c", "HBA1C", "BIOCHEMISTRY", "QUANTITATIVE"),
    ("Creatinine", "CREAT", "BIOCHEMISTRY", "QUANTITATIVE"),
    ("Urea", "UREA", "BIOCHEMISTRY", "QUANTITATIVE"),
    ("ESR", "ESR", "HAEMATOLOGY", "QUANTITATIVE"),
    ("CRP", "CRP", "BIOCHEMISTRY", "QUANTITATIVE"),
    ("HIV Rapid Test", "HIV-R", "SEROLOGY", "QUALITATIVE"),
    ("Hepatitis B Surface Antigen", "HBSAG", "SEROLOGY", "QUALITATIVE"),
    ("Hepatitis C Antibody", "HCV-AB", "SEROLOGY", "QUALITATIVE"),
    ("Malaria RDT", "MALARIA", "PARASITOLOGY", "QUALITATIVE"),
    ("Urinalysis", "UA", "URINALYSIS", "SEMI_QUANT"),
    ("Liver Function Tests", "LFT", "BIOCHEMISTRY", "QUANTITATIVE"),
    ("Electrolytes (Na/K/Cl)", "ELEC", "BIOCHEMISTRY", "QUANTITATIVE"),
    ("Lipid Profile", "LIPID", "BIOCHEMISTRY", "QUANTITATIVE"),
    ("PT/INR", "PTINR", "HAEMATOLOGY", "QUANTITATIVE"),
    ("Blood Group & Rh", "BGRh", "BLOOD_BANK", "QUALITATIVE"),
    ("Widal Test", "WIDAL", "SEROLOGY", "SEMI_QUANT"),
]

lab_types = []
for name, code, cat, rtype in LAB_TESTS:
    obj = LabTestType.objects.filter(code=code).first()
    if not obj:
        obj = LabTestType.objects.filter(name=name).first()
    if not obj:
        try:
            obj = LabTestType.objects.create(
                code=code, name=name, category=cat, result_type=rtype,
                normal_range={}, turnaround_hours=random.choice([2, 4, 6, 24]),
                sample_type=random.choice(["Blood-EDTA", "Blood-Plain", "Urine", "Serum"]),
            )
            print(f"  Created LabTestType: {name}")
        except Exception as e:
            print(f"  SKIP LabTestType {name}: {e}")
            continue
    lab_types.append(obj)
print(f"Lab test types ready: {len(lab_types)}")

# ============ SEED LAB ORDERS ============
lab_indications = [
    "Pre-operative workup", "Diabetes monitoring",
    "Infection screen", "Routine check-up",
    "Fever investigation", "Anemia workup",
    "Liver function assessment", "Renal function check",
    "Malaria screening", "STI screening",
]
lab_statuses = ["COMPLETED"] * 10 + ["ORDERED"] * 2 + ["PROCESSING"] * 2 + ["CANCELLED"]

created_lab = 0
for i in range(150):
    pt = random.choice(patients)
    consult = get_consult(pt)
    day_offset = random.randint(0, max(days_in_month, 1))
    order_dt = timezone.make_aware(
        timezone.datetime(month_start.year, month_start.month,
                          month_start.day + day_offset,
                          random.randint(7, 17), random.randint(0, 59))
    )
    status = random.choice(lab_statuses)

    order = LabOrder(
        consultation=consult, patient=pt, ordered_by=admin,
        urgency=random.choice(urgencies),
        status=status,
        clinical_indication=random.choice(lab_indications),
        payment_status=random.choice(["PAID"] * 8 + ["UNPAID", "INSURED"]),
        specimen_status="RECEIVED" if status in ["COMPLETED", "PROCESSING"] else "PENDING",
        created_by=admin,
    )
    order.save()
    LabOrder.objects.filter(id=order.id).update(created_at=order_dt)

    num_items = random.randint(1, 4)
    chosen_tests = random.sample(lab_types, min(num_items, len(lab_types)))
    for test_type in chosen_tests:
        item_status = status if status != "CANCELLED" else "ORDERED"
        try:
            item = LabOrderItem.objects.create(
                order=order, test_type=test_type, status=item_status,
            )
        except Exception:
            continue

        if item_status == "COMPLETED":
            is_abn = random.random() > 0.7
            is_crit = is_abn and random.random() > 0.8
            if test_type.result_type == "QUALITATIVE":
                val = random.choice(["Negative"] * 7 + ["Positive"] * 3)
                is_abn = val == "Positive"
            elif test_type.result_type == "SEMI_QUANT":
                val = random.choice(["Negative", "+", "++", "+++"])
                is_abn = val != "Negative"
            else:
                val = str(round(random.uniform(2.0, 20.0), 1))
            try:
                result = LabResult(
                    order_item=item, performed_by=admin,
                    result_value=val, result_unit="",
                    is_abnormal=is_abn, is_critical=is_crit,
                    is_verified=random.random() > 0.2,
                    result_status="VERIFIED" if random.random() > 0.3 else "PRELIMINARY",
                    version_number=1, created_by=admin,
                )
                result.save()
                LabResult.objects.filter(id=result.id).update(
                    created_at=order_dt + timedelta(hours=random.randint(1, 6)))
            except Exception:
                pass

    created_lab += 1
    if (i + 1) % 50 == 0:
        print(f"  ... {i + 1} lab orders")

print(f"Created {created_lab} lab orders")

# Clear cache
from django.core.cache import cache
cache.delete(f"inv_stats_{today.year}_{today.month}")
cache.delete(f"lab_stats_{today.year}_{today.month}")

print()
print(f"DONE: {created_inv} investigations + {created_lab} lab orders seeded for {today.strftime('%B %Y')}")
'''

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS)
sftp = ssh.open_sftp()
with sftp.open('/opt/ehr-africa/_seed_stats.py', 'w') as f:
    f.write(REMOTE_SCRIPT)
sftp.close()
stdin, stdout, stderr = ssh.exec_command(
    'cd /opt/ehr-africa && /opt/ehr-africa/venv/bin/python _seed_stats.py 2>&1'
)
print(stdout.read().decode('utf-8', errors='replace'))
err = stderr.read().decode().strip()
if err:
    print('STDERR:', err[-800:])
ssh.exec_command('rm /opt/ehr-africa/_seed_stats.py')
ssh.close()
