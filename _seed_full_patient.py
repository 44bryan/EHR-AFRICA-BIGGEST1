"""Seed ONE fully-loaded patient with complete medical records across all departments."""
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
from decimal import Decimal

User = get_user_model()
admin = User.objects.filter(username="admin").first()
today = timezone.localdate()

# ═══════════════════════════════════════════════════════════════════
# 1. CREATE THE PATIENT
# ═══════════════════════════════════════════════════════════════════
from apps.patients.models import (
    Patient, InsuranceInfo, MedicalHistory,
    Visit, VisitType, VisitStatus, ServiceTier,
    PatientAllergy, PatientProblem, ProblemStatus,
)

pt, created = Patient.objects.get_or_create(
    first_name="Jean-Pierre",
    last_name="Nkoulou",
    defaults={
        "middle_name": "Alain",
        "date_of_birth": date(1968, 3, 15),
        "gender": "M",
        "blood_group": "O+",
        "genotype": "AA",
        "phone_number": "+237677889900",
        "email": "jpnkoulou@example.com",
        "address": "Quartier Bastos, Rue 1024, Yaounde",
        "state_of_origin": "Centre",
        "occupation": "Civil Engineer",
        "religion": "Christian",
        "marital_status": "Married",
        "nationality": "Cameroonian",
        "created_by": admin,
    }
)
if created:
    print(f"Created patient: {pt.full_name} ({pt.patient_id})")
else:
    print(f"Using existing patient: {pt.full_name} ({pt.patient_id})")

# ═══════════════════════════════════════════════════════════════════
# 2. MEDICAL HISTORY
# ═══════════════════════════════════════════════════════════════════
mh, _ = MedicalHistory.objects.get_or_create(
    patient=pt,
    defaults={
        "known_allergies": "Sulfonamides (rash), Latex (contact dermatitis)",
        "previous_eye_surgeries": "None",
        "previous_eye_conditions": "Myopia diagnosed at age 12. Wearing corrective lenses since.",
        "spectacle_history": "Progressive lenses since 2018. Last refraction: -2.50/-0.75x180 OD, -3.00/-0.50x10 OS",
        "chronic_conditions": "Type 2 Diabetes Mellitus (diagnosed 2015), Hypertension Stage 1 (diagnosed 2018)",
        "previous_surgeries": "Appendectomy (2005)",
        "current_medications": "Metformin 1000mg BD, Amlodipine 5mg OD, Aspirin 75mg OD",
        "family_ocular_history": "Father: primary open angle glaucoma. Mother: age-related cataract.",
        "social_history": "Non-smoker. Occasional alcohol (social). Office work with significant screen time.",
        "systemic_history": "Well-controlled DM (last HbA1c 6.8%). BP on last check 138/82 mmHg.",
        "created_by": admin,
    }
)
print("  Medical history OK")

# ═══════════════════════════════════════════════════════════════════
# 3. ALLERGIES
# ═══════════════════════════════════════════════════════════════════
allergies_data = [
    ("Sulfonamides", "DRUG", "SEVERE", "Generalized maculopapular rash, facial swelling"),
    ("Latex", "LATEX", "MODERATE", "Contact dermatitis, itching"),
    ("Fluorescein sodium", "DRUG", "MILD", "Mild nausea, temporary skin yellowing"),
]
for allergen, atype, sev, reaction in allergies_data:
    PatientAllergy.objects.get_or_create(
        patient=pt, allergen=allergen,
        defaults={
            "allergy_type": atype, "severity": sev,
            "reaction": reaction, "date_noted": date(2020, 6, 1),
            "is_active": True, "recorded_by": admin,
        }
    )
print("  Allergies OK (3)")

# ═══════════════════════════════════════════════════════════════════
# 4. PROBLEM LIST
# ═══════════════════════════════════════════════════════════════════
problems_data = [
    ("Primary Open Angle Glaucoma suspect", "H40.1", "active", date(2025, 9, 10)),
    ("Type 2 Diabetes Mellitus", "E11.9", "chronic", date(2015, 3, 1)),
    ("Hypertension Stage 1", "I10", "chronic", date(2018, 7, 15)),
    ("Bilateral myopia", "H52.1", "chronic", date(2000, 1, 1)),
    ("Mild non-proliferative diabetic retinopathy", "H36.0", "monitored", date(2024, 11, 20)),
    ("Dry eye syndrome", "H04.1", "active", date(2025, 6, 1)),
    ("Allergic conjunctivitis (resolved)", "H10.1", "resolved", date(2024, 3, 15)),
]
for problem, icd, status, onset in problems_data:
    PatientProblem.objects.get_or_create(
        patient=pt, problem=problem,
        defaults={
            "icd10_code": icd, "status": status,
            "onset_date": onset, "recorded_by": admin,
            "resolved_date": date(2024, 5, 20) if status == "resolved" else None,
        }
    )
print("  Problem list OK (7)")

# ═══════════════════════════════════════════════════════════════════
# 5. INSURANCE
# ═══════════════════════════════════════════════════════════════════
InsuranceInfo.objects.get_or_create(
    patient=pt, provider="CNPS - Caisse Nationale de Prevoyance Sociale",
    defaults={
        "policy_number": "CNPS-2024-889900",
        "group_number": "GRP-YAOUNDE-042",
        "plan_name": "CNPS Standard Plan",
        "is_active": True,
        "expiry_date": date(2027, 12, 31),
        "notes": "Employee scheme via Ministry of Public Works. 80% coverage for consultations, 70% for procedures.",
    }
)
print("  Insurance OK")

# ═══════════════════════════════════════════════════════════════════
# 6. DEPARTMENTS & DIAGNOSES (ensure they exist)
# ═══════════════════════════════════════════════════════════════════
from apps.departments.models import Department

depts = {}
dept_data = [
    ("General Ophthalmology", "GEN_OPH", "#0d6efd", "bi-eye"),
    ("Glaucoma Clinic", "GLAUCOMA", "#dc3545", "bi-speedometer2"),
    ("Retina Clinic", "RETINA", "#fd7e14", "bi-bullseye"),
    ("Cornea & External Eye", "CORNEA", "#20c997", "bi-circle"),
    ("Pediatric Ophthalmology", "PEDIATRIC", "#6f42c1", "bi-people"),
    ("Oculoplastics", "OCULOPLASTY", "#d63384", "bi-scissors"),
    ("General Medicine", "GEN_MED", "#198754", "bi-heart-pulse"),
    ("Laboratory", "LAB", "#0dcaf0", "bi-droplet"),
]
for dname, dcode, dcolor, dicon in dept_data:
    d = Department.objects.filter(code=dcode).first()
    if not d:
        d = Department.objects.filter(name=dname).first()
    if not d:
        try:
            d = Department.objects.create(
                code=dcode, name=dname, color_code=dcolor, icon=dicon
            )
        except Exception as e:
            print(f"  SKIP dept {dname}: {e}")
            continue
    depts[dcode] = d
print(f"  Departments OK ({len(depts)})")

from apps.consultations.models import Diagnosis, Consultation, ConsultationDiagnosis, ConsultationNote

diag_data = [
    ("H40.11", "Primary open angle glaucoma, mild stage"),
    ("H36.0", "Diabetic retinopathy, non-proliferative, mild"),
    ("H52.1", "Myopia, bilateral"),
    ("H04.12", "Dry eye syndrome"),
    ("H10.1", "Acute allergic conjunctivitis"),
    ("H26.0", "Age-related incipient cataract"),
    ("E11.9", "Type 2 diabetes mellitus without complications"),
    ("I10", "Essential hypertension"),
    ("H35.3", "Macular degeneration (dry type)"),
    ("H40.0", "Glaucoma suspect"),
]
diags = {}
for icd, desc in diag_data:
    d = Diagnosis.objects.filter(icd10_code=icd).first()
    if not d:
        try:
            d = Diagnosis.objects.create(icd10_code=icd, description=desc, is_ophthalmic=icd.startswith("H"))
        except Exception:
            d = Diagnosis.objects.filter(icd10_code=icd).first()
    if d:
        diags[icd] = d
print(f"  Diagnoses OK ({len(diags)})")

# ═══════════════════════════════════════════════════════════════════
# 7. CREATE 5 VISITS (spanning 12 months)
# ═══════════════════════════════════════════════════════════════════
visit_dates = [
    date(2025, 11, 5),   # Visit 1: Initial comprehensive exam
    date(2026, 2, 12),   # Visit 2: Glaucoma follow-up
    date(2026, 5, 20),   # Visit 3: Diabetic retinopathy screening
    date(2026, 7, 8),    # Visit 4: Dry eye + refraction
    date(2026, 8, 25),   # Visit 5: Comprehensive review (this month)
]

visits = []
for i, vdate in enumerate(visit_dates):
    vtype = VisitType.NEW if i == 0 else VisitType.FOLLOW_UP
    complaints = [
        "Comprehensive eye examination. Known diabetic and hypertensive.",
        "Follow-up for glaucoma suspect status. IOP check requested.",
        "Annual diabetic retinopathy screening. No new visual complaints.",
        "Dry, gritty eyes for 3 weeks. Also needs new spectacles.",
        "Routine 3-month review. Blurry near vision worsening.",
    ]
    v = Visit(
        patient=pt, visit_type=vtype,
        chief_complaint=complaints[i],
        status=VisitStatus.IN_CONSULTATION if i == len(visit_dates) - 1 else VisitStatus.IN_CONSULTATION,
        service_tier=ServiceTier.STANDARD,
        created_by=admin,
    )
    v.save()
    # Backdate
    Visit.objects.filter(id=v.id).update(
        visit_date=timezone.make_aware(timezone.datetime(vdate.year, vdate.month, vdate.day, 9, 0)),
        status=VisitStatus.IN_CONSULTATION if i == len(visit_dates) - 1 else VisitStatus.IN_CONSULTATION,
    )
    v.refresh_from_db()

    # Vital signs
    v.vital_signs = {
        "blood_pressure": random.choice(["128/78", "135/82", "140/85", "132/80", "138/84"]),
        "pulse": random.randint(68, 82),
        "temperature": round(random.uniform(36.3, 36.8), 1),
        "weight": round(random.uniform(78, 83), 1),
        "height": 175.0,
        "visual_acuity_right": random.choice(["6/9", "6/12", "6/9-2"]),
        "visual_acuity_left": random.choice(["6/12", "6/18", "6/12-1"]),
        "intraocular_pressure_right": random.randint(16, 22),
        "intraocular_pressure_left": random.randint(15, 21),
        "spo2": random.randint(96, 99),
        "bmi": round(random.uniform(26.5, 28.0), 1),
    }
    v.save(update_fields=["vital_signs"])
    visits.append(v)

print(f"  Visits OK ({len(visits)})")

# ═══════════════════════════════════════════════════════════════════
# 8. CONSULTATIONS (one per visit, different departments)
# ═══════════════════════════════════════════════════════════════════
consult_configs = [
    # Visit 1: Initial — General Ophthalmology
    {
        "dept": "GEN_OPH",
        "complaint": "First visit. Known DM x10 years, HTN x7 years. Wearing glasses. No acute complaints.",
        "hpc": "Patient presents for a comprehensive eye examination. Has been diabetic for 10 years on Metformin. Hypertensive on Amlodipine. Father had glaucoma. Reports occasional dry eyes.",
        "ocular_hx": "Myopia since childhood. Last refraction 2 years ago. No prior surgeries.",
        "systemic_hx": "DM Type 2 on Metformin 1g BD. HTN on Amlodipine 5mg. Aspirin 75mg. Appendectomy 2005.",
        "drug_hx": "Metformin 1000mg BD, Amlodipine 5mg OD, Aspirin 75mg OD",
        "family_hx": "Father: POAG. Mother: cataract surgery at 72.",
        "social_hx": "Civil engineer, significant screen time. Non-smoker. Social alcohol.",
        "exam": {
            "visual_acuity": {"right_unaided": "6/18", "left_unaided": "6/24", "right_pinhole": "6/9", "left_pinhole": "6/12", "right_best_corrected": "6/6", "left_best_corrected": "6/9"},
            "intraocular_pressure": {"right": "19", "left": "20", "method": "Goldmann Applanation"},
            "anterior_segment": {"right": "Clear cornea, deep AC, no flare/cells. Mild nuclear sclerosis.", "left": "Clear cornea, deep AC, no flare/cells. Early cortical lens changes."},
            "posterior_segment": {"right": "CDR 0.5, healthy rim. Few microaneurysms supero-temporal.", "left": "CDR 0.5, healthy rim. Few dot haemorrhages temporal to macula."},
            "pupils": "RAPD negative. Brisk direct and consensual bilaterally.",
            "slit_lamp": {"lids_lashes": "Normal", "conjunctiva": "Mild papillary response inferiorly OU", "cornea": "Clear OU", "anterior_chamber": "Deep and quiet OU", "iris": "Normal pattern OU", "lens": "NS++ OD, early cortical OS"},
        },
        "plan": "1. Baseline OCT RNFL + macula OU\n2. Visual fields 24-2 OU\n3. Fundus photography OU\n4. FBC, HbA1c, Creatinine, Lipid Profile\n5. Review in 3 months with results\n6. Artificial tears for dry eye symptoms",
        "follow_up": 90,
        "diags": [("H40.0", True, "BE"), ("H36.0", False, "BE"), ("H52.1", False, "BE"), ("H04.12", False, "BE")],
    },
    # Visit 2: Glaucoma follow-up
    {
        "dept": "GLAUCOMA",
        "complaint": "Glaucoma suspect follow-up. OCT and VF results available.",
        "hpc": "Returns for glaucoma suspect evaluation. Previous IOP 19/20. Father has POAG. OCT shows borderline RNFL thinning superiorly OD.",
        "ocular_hx": "Myopia. No prior surgery.",
        "systemic_hx": "DM, HTN - stable on medications.",
        "drug_hx": "Metformin 1g BD, Amlodipine 5mg OD, Aspirin 75mg OD, Refresh Tears PRN",
        "family_hx": "Father: POAG on Timolol + Latanoprost.",
        "social_hx": "As before.",
        "exam": {
            "visual_acuity": {"right_unaided": "6/18", "left_unaided": "6/24", "right_best_corrected": "6/6", "left_best_corrected": "6/9"},
            "intraocular_pressure": {"right": "21", "left": "20", "method": "Goldmann Applanation"},
            "anterior_segment": {"right": "Open angles on gonioscopy. Schaffer grade 4 all quadrants.", "left": "Open angles. Schaffer grade 4."},
            "posterior_segment": {"right": "CDR 0.55, superior rim thinning. No disc haemorrhage.", "left": "CDR 0.5, healthy neuroretinal rim."},
        },
        "plan": "1. Pachymetry (CCT) OU\n2. Repeat VF 24-2 in 6 months\n3. Continue monitoring IOP 3-monthly\n4. If IOP >22 or VF progression: start Latanoprost 0.005% OU nocte\n5. Refer for Retina screening (DR)",
        "follow_up": 90,
        "diags": [("H40.0", True, "RE"), ("H40.0", False, "LE")],
    },
    # Visit 3: Retina — diabetic screening
    {
        "dept": "RETINA",
        "complaint": "Annual diabetic retinopathy screening.",
        "hpc": "Scheduled annual DR screening. No new visual complaints. HbA1c was 6.8% last check. Currently asymptomatic.",
        "ocular_hx": "Known mild NPDR OU. Glaucoma suspect under monitoring.",
        "systemic_hx": "DM 11 years, well-controlled. HTN stable.",
        "drug_hx": "Metformin 1g BD, Amlodipine 5mg OD, Aspirin 75mg, Refresh Tears QID",
        "family_hx": "Father: POAG.",
        "social_hx": "No change.",
        "exam": {
            "visual_acuity": {"right_unaided": "6/18", "left_unaided": "6/24", "right_best_corrected": "6/6", "left_best_corrected": "6/9"},
            "intraocular_pressure": {"right": "18", "left": "19", "method": "NCT"},
            "posterior_segment": {"right": "Microaneurysms supero-temporal. No hard exudates. No NVD/NVE. Macula: dry, no clinically significant oedema.", "left": "Scattered dot-blot haemorrhages temporal. One small hard exudate inferior to fovea. No NVD/NVE. Macula: mild thickening on OCT."},
        },
        "plan": "1. OCT Macula OU (done today - mild thickening OS)\n2. FFA deferred (patient allergic to fluorescein - mild reaction noted)\n3. Continue annual screening\n4. Strict glycaemic control (target HbA1c <7%)\n5. FBC + HbA1c + Creatinine ordered\n6. Review in 6 months or sooner if visual symptoms",
        "follow_up": 180,
        "diags": [("H36.0", True, "BE"), ("H26.0", False, "BE")],
    },
    # Visit 4: Cornea — dry eye + refraction
    {
        "dept": "CORNEA",
        "complaint": "Worsening dry, gritty eyes for 3 weeks. Also requesting new spectacles.",
        "hpc": "Reports increasing foreign body sensation, burning, and tearing worse in the evenings and after screen work. Current artificial tears provide transient relief only. Also notes blurry near vision.",
        "ocular_hx": "Known dry eye. Myopia. Glaucoma suspect.",
        "systemic_hx": "DM, HTN, on treatment.",
        "drug_hx": "Metformin 1g BD, Amlodipine 5mg OD, Aspirin 75mg, Refresh Tears QID",
        "family_hx": "As before.",
        "social_hx": "8+ hours screen time daily.",
        "exam": {
            "visual_acuity": {"right_unaided": "6/18", "left_unaided": "6/24", "right_best_corrected": "6/6", "left_best_corrected": "6/9"},
            "intraocular_pressure": {"right": "17", "left": "18", "method": "NCT"},
            "anterior_segment": {"right": "TBUT 5 seconds. Schirmer 8mm/5min. SPK inferiorly. Mild MGD.", "left": "TBUT 4 seconds. Schirmer 7mm/5min. SPK inferiorly. Moderate MGD."},
            "slit_lamp": {"lids_lashes": "Meibomian gland plugging OU, lid margin telangiectasia", "conjunctiva": "Mild injection inferiorly OU", "cornea": "Punctate epithelial erosions inferior 1/3 OU", "anterior_chamber": "Deep quiet", "iris": "Normal", "lens": "NS++ OD, cortical OS"},
        },
        "plan": "1. Upgrade to preservative-free artificial tears (Hyabak) QID\n2. Warm compresses + lid hygiene BD\n3. Add Ciclosporin 0.1% drops BD for 3 months\n4. Refraction: updated Rx given\n5. Screen time hygiene: 20-20-20 rule\n6. Review in 6 weeks for dry eye response",
        "follow_up": 42,
        "diags": [("H04.12", True, "BE"), ("H52.1", False, "BE")],
    },
    # Visit 5: Current — comprehensive review (today)
    {
        "dept": "GEN_OPH",
        "complaint": "3-month comprehensive review. Blurry near vision worsening despite new glasses.",
        "hpc": "Returns for scheduled review. Reports progressively worsening near vision over past 2 months. Dry eye symptoms improved with Ciclosporin. IOP stable on monitoring. Diabetic control good per GP.",
        "ocular_hx": "POAG suspect, mild NPDR, dry eye on treatment, myopic.",
        "systemic_hx": "DM well controlled (HbA1c 6.5%). HTN controlled.",
        "drug_hx": "Metformin 1g BD, Amlodipine 5mg, Aspirin 75mg, Hyabak QID, Ciclosporin 0.1% BD",
        "family_hx": "Father on glaucoma drops.",
        "social_hx": "Using 20-20-20 rule. Screen time reduced.",
        "exam": {
            "visual_acuity": {"right_unaided": "6/18", "left_unaided": "6/24", "right_pinhole": "6/9", "left_pinhole": "6/12", "right_best_corrected": "6/6", "left_best_corrected": "6/9"},
            "intraocular_pressure": {"right": "18", "left": "19", "method": "Goldmann Applanation"},
            "anterior_segment": {"right": "TBUT 8 sec (improved). Mild nuclear sclerosis. No SPK.", "left": "TBUT 7 sec (improved). Cortical lens opacities progressing."},
            "posterior_segment": {"right": "CDR 0.55 (stable). RNFL looks preserved. Few microaneurysms.", "left": "CDR 0.5 (stable). Dot haemorrhages stable. Macula flat."},
            "pupils": "RAPD negative OU.",
            "slit_lamp": {"lids_lashes": "Improved MGD, less plugging", "conjunctiva": "White and quiet OU", "cornea": "Clear OU, no SPK", "anterior_chamber": "Deep quiet OU", "iris": "Normal", "lens": "NS++ OD progressing, cortical+ OS"},
        },
        "plan": "1. IOP stable, continue monitoring 3-monthly\n2. OCT RNFL + VF to be repeated (due)\n3. Dry eye much improved - continue Ciclosporin 3 more months then taper\n4. Cataract counselling: lens changes progressing, likely surgery in 1-2 years OS first\n5. Continue diabetic screening annually\n6. Updated refraction: slight increase in add (+2.50 from +2.25)\n7. Next visit: 3 months",
        "follow_up": 90,
        "diags": [("H40.0", True, "BE"), ("H36.0", False, "BE"), ("H26.0", False, "LE"), ("H04.12", False, "BE")],
    },
]

consultations = []
for i, cfg in enumerate(consult_configs):
    v = visits[i]
    dept = depts.get(cfg["dept"])
    c = Consultation.objects.create(
        visit=v, patient=pt, department=dept, consulting_doctor=admin,
        presenting_complaint=cfg["complaint"],
        history_of_presenting_complaint=cfg["hpc"],
        ocular_history=cfg.get("ocular_hx", ""),
        systemic_history=cfg.get("systemic_hx", ""),
        drug_history=cfg.get("drug_hx", ""),
        family_history=cfg.get("family_hx", ""),
        social_history=cfg.get("social_hx", ""),
        examination_findings=cfg.get("exam", {}),
        management_plan=cfg["plan"],
        follow_up_date=today + timedelta(days=cfg["follow_up"]) if cfg.get("follow_up") else None,
        follow_up_instructions=cfg["plan"].split("\n")[-1] if cfg["plan"] else "",
        status="COMPLETED" if i < len(consult_configs) - 1 else "IN_PROGRESS",
        created_by=admin,
    )
    # Backdate
    vdate = visit_dates[i]
    Consultation.objects.filter(id=c.id).update(
        consultation_date=timezone.make_aware(timezone.datetime(vdate.year, vdate.month, vdate.day, 10, 30))
    )

    # Add diagnoses
    for icd, is_primary, lat in cfg.get("diags", []):
        if icd in diags:
            ConsultationDiagnosis.objects.get_or_create(
                consultation=c, diagnosis=diags[icd],
                defaults={"is_primary": is_primary, "laterality": lat}
            )

    # Add a progress note
    ConsultationNote.objects.create(
        consultation=c,
        note_type="PROGRESS",
        content=f"Visit {i+1}: {cfg['complaint']}\n\nExam completed. {cfg['plan'].split(chr(10))[0]}",
        created_by=admin,
    )

    consultations.append(c)

print(f"  Consultations OK ({len(consultations)}) across {len(set(cfg['dept'] for cfg in consult_configs))} departments")

# ═══════════════════════════════════════════════════════════════════
# 9. PRESCRIPTIONS (drug + optical)
# ═══════════════════════════════════════════════════════════════════
from apps.prescriptions.models import (
    DrugPrescription, DrugPrescriptionItem, DrugForm, RouteOfAdmin, EyeChoice,
    OpticalPrescription,
)

# Visit 1: Artificial tears
rx1 = DrugPrescription.objects.create(
    consultation=consultations[0], patient=pt, prescribed_by=admin,
    notes="Initial dry eye management", created_by=admin,
)
DrugPrescriptionItem.objects.create(
    prescription=rx1, drug_name="Refresh Tears (Carboxymethylcellulose 0.5%)",
    drug_form=DrugForm.EYE_DROP, concentration="0.5%",
    dose="1-2 drops", frequency="QID", duration="3 months",
    route=RouteOfAdmin.TOPICAL, eye=EyeChoice.BOTH, quantity=3,
    special_instructions="Use as needed for dryness. Safe to use with contact lenses.",
)

# Visit 4: Dry eye intensive
rx4 = DrugPrescription.objects.create(
    consultation=consultations[3], patient=pt, prescribed_by=admin,
    notes="Dry eye escalation therapy", created_by=admin,
)
DrugPrescriptionItem.objects.create(
    prescription=rx4, drug_name="Hyabak (Sodium Hyaluronate 0.15%)",
    drug_form=DrugForm.EYE_DROP, concentration="0.15%",
    dose="1 drop", frequency="QID", duration="Ongoing",
    route=RouteOfAdmin.TOPICAL, eye=EyeChoice.BOTH, quantity=3,
    special_instructions="Preservative-free. Use regularly even when eyes feel comfortable.",
)
DrugPrescriptionItem.objects.create(
    prescription=rx4, drug_name="Ikervis (Ciclosporin 0.1%)",
    drug_form=DrugForm.EYE_DROP, concentration="0.1%",
    dose="1 drop", frequency="BD (morning and evening)", duration="3 months",
    route=RouteOfAdmin.TOPICAL, eye=EyeChoice.BOTH, quantity=1,
    special_instructions="May sting initially - this is normal and improves after 1 week. Store in fridge.",
)

# Visit 5: Current prescriptions
rx5 = DrugPrescription.objects.create(
    consultation=consultations[4], patient=pt, prescribed_by=admin,
    notes="Review prescriptions - continue dry eye, add vitamin supplement", created_by=admin,
)
for item_data in [
    ("Hyabak (Sodium Hyaluronate 0.15%)", DrugForm.EYE_DROP, "0.15%", "1 drop", "QID", "Ongoing", EyeChoice.BOTH, 3, "Continue preservative-free tears."),
    ("Ikervis (Ciclosporin 0.1%)", DrugForm.EYE_DROP, "0.1%", "1 drop", "BD", "3 more months then taper", EyeChoice.BOTH, 1, "Continue BD for 3 months, then reduce to OD for 1 month, then stop."),
    ("Ocuvite Lutein", "CAPSULE", "", "1 capsule", "OD", "6 months", "NA", 6, "Antioxidant supplement for macular health."),
]:
    DrugPrescriptionItem.objects.create(
        prescription=rx5,
        drug_name=item_data[0], drug_form=item_data[1], concentration=item_data[2],
        dose=item_data[3], frequency=item_data[4], duration=item_data[5],
        route=RouteOfAdmin.TOPICAL if "drop" in str(item_data[3]).lower() else RouteOfAdmin.ORAL,
        eye=item_data[6], quantity=item_data[7],
        special_instructions=item_data[8],
    )

print("  Drug prescriptions OK (3 Rx with items)")

# Optical prescription (visit 4 refraction)
opt_rx = OpticalPrescription.objects.create(
    consultation=consultations[3], patient=pt, prescribed_by=admin,
    prescription_type="SPECTACLE",
    re_sphere=Decimal("-2.75"), re_cylinder=Decimal("-0.75"), re_axis=175,
    re_add=Decimal("2.25"), re_visual_acuity="6/6",
    re_sphere_near=Decimal("-0.50"), re_va_near="N5",
    le_sphere=Decimal("-3.25"), le_cylinder=Decimal("-0.50"), le_axis=10,
    le_add=Decimal("2.25"), le_visual_acuity="6/9",
    le_sphere_near=Decimal("-1.00"), le_va_near="N6",
    interpupillary_distance=Decimal("64.0"), near_ipd=Decimal("61.0"),
    lens_type="Progressive,Anti-reflective,Blue-light filter",
    frame_advice="Medium rectangular frame. Consider lighter materials (titanium) for comfort.",
    notes="Progressive lenses recommended. Patient counselled on adaptation period.",
    created_by=admin,
)

# Visit 5 updated refraction
opt_rx2 = OpticalPrescription.objects.create(
    consultation=consultations[4], patient=pt, prescribed_by=admin,
    prescription_type="SPECTACLE",
    re_sphere=Decimal("-2.75"), re_cylinder=Decimal("-0.75"), re_axis=175,
    re_add=Decimal("2.50"), re_visual_acuity="6/6",
    re_sphere_near=Decimal("-0.25"), re_va_near="N5",
    le_sphere=Decimal("-3.50"), le_cylinder=Decimal("-0.50"), le_axis=10,
    le_add=Decimal("2.50"), le_visual_acuity="6/9",
    le_sphere_near=Decimal("-1.00"), le_va_near="N6",
    interpupillary_distance=Decimal("64.0"), near_ipd=Decimal("61.0"),
    lens_type="Progressive,Anti-reflective,Blue-light filter,Photochromic",
    frame_advice="Upgrade to photochromic for outdoor use. Consider lightweight frame.",
    notes="Add increased to +2.50 OU (was +2.25). OS sphere increased -0.25 (cataract progression).",
    created_by=admin,
)
print("  Optical prescriptions OK (2)")

# ═══════════════════════════════════════════════════════════════════
# 10. INVESTIGATION ORDERS + RESULTS
# ═══════════════════════════════════════════════════════════════════
from apps.investigations.models import InvestigationType, InvestigationOrder, InvestigationResult

def get_inv_type(code):
    return InvestigationType.objects.filter(code=code).first()

inv_orders_data = [
    # Visit 1 investigations
    (0, "OCT-RNFL", "Baseline RNFL for glaucoma suspect evaluation", "ROUTINE", "OU", True,
     {"od_avg_rnfl": 92, "os_avg_rnfl": 95, "od_superior": 108, "od_inferior": 112, "os_superior": 110, "os_inferior": 115},
     "RNFL thickness within normal limits OU. Borderline thinning superior OD. Recommend serial monitoring.", True),
    (0, "OCT-MAC", "Baseline macular OCT - diabetic screening", "ROUTINE", "OU", True,
     {"od_central_thickness": 268, "os_central_thickness": 285, "od_volume": 10.2, "os_volume": 10.5},
     "OD: Normal foveal contour, no oedema. OS: Mild diffuse thickening (285um), no cysts.", True),
    (0, "VF-24", "Baseline visual field - glaucoma suspect", "ROUTINE", "OU", True,
     {"od_md": -1.2, "os_md": -0.8, "od_psd": 1.8, "os_psd": 1.5, "od_fixation_losses": "2/15", "os_fixation_losses": "1/14", "od_false_pos": "3%", "os_false_pos": "2%", "reliability": "Good"},
     "Reliable visual fields OU. No significant defect. MD and PSD within normal limits.", True),
    (0, "FP-COL", "Baseline fundus photography", "ROUTINE", "OU", True,
     {"quality": "Good", "findings": "Few microaneurysms OD, dot haemorrhages OS temporal to macula"},
     "Mild NPDR features documented. Baseline for future comparison.", False),
    # Visit 2 investigations
    (1, "PACHY", "Pachymetry for IOP correction - glaucoma evaluation", "ROUTINE", "OU", True,
     {"od_cct": 548, "os_cct": 552, "od_corrected_iop": 21.8, "os_corrected_iop": 20.5},
     "CCT slightly below average (548/552). IOP correction factor: +0.8/+0.5 mmHg. Corrected IOP: OD 21.8, OS 20.5.", True),
    # Visit 3 investigations
    (2, "OCT-MAC", "Diabetic macular OCT - annual screening", "ROUTINE", "OU", True,
     {"od_central_thickness": 270, "os_central_thickness": 290, "od_volume": 10.3, "os_volume": 10.6},
     "OD stable. OS: mild increase in central thickness (285->290um). No cystoid changes. Monitor.", False),
    # Visit 5 investigations (current)
    (4, "OCT-RNFL", "Repeat RNFL - glaucoma suspect monitoring", "ROUTINE", "OU", True,
     {"od_avg_rnfl": 90, "os_avg_rnfl": 94, "od_superior": 105, "od_inferior": 110, "os_superior": 109, "os_inferior": 114},
     "Stable RNFL OU compared to baseline (Nov 2025). No significant progression.", True),
    (4, "VF-24", "Repeat VF 24-2 - glaucoma monitoring", "ROUTINE", "OU", True,
     {"od_md": -1.5, "os_md": -0.9, "od_psd": 2.0, "os_psd": 1.6, "reliability": "Good"},
     "Reliable fields. OD: MD slightly worse (-1.2 to -1.5) but within normal variability. OS: stable. No scotoma.", True),
    (4, "TOPO", "Corneal topography pre-cataract evaluation", "ROUTINE", "OU", False,
     {"od_sim_k1": 43.5, "od_sim_k2": 44.2, "os_sim_k1": 43.8, "os_sim_k2": 44.5, "regularity": "Normal"},
     "Regular astigmatism OU. No keratoconus pattern. Suitable for standard IOL calculation.", True),
]

for visit_idx, inv_code, indication, urgency, eye, has_result, result_data, interp, is_normal in inv_orders_data:
    inv_type = get_inv_type(inv_code)
    if not inv_type:
        print(f"  SKIP investigation {inv_code} - type not found")
        continue
    order = InvestigationOrder.objects.create(
        consultation=consultations[visit_idx], patient=pt, ordered_by=admin,
        investigation_type=inv_type,
        urgency=urgency, status="COMPLETED" if has_result else "ORDERED",
        clinical_indication=indication, eye=eye,
        location="CLINIC",
        payment_status="PAID",
        acquisition_status="ACQUIRED" if has_result else "SCHEDULED",
        created_by=admin,
    )
    vdate = visit_dates[visit_idx]
    InvestigationOrder.objects.filter(id=order.id).update(
        created_at=timezone.make_aware(timezone.datetime(vdate.year, vdate.month, vdate.day, 11, 0))
    )
    if has_result:
        result = InvestigationResult.objects.create(
            order=order, performed_by=admin,
            result_data=result_data, interpretation=interp,
            is_normal=is_normal, is_verified=True,
            version_number=1, created_by=admin,
        )
        InvestigationResult.objects.filter(id=result.id).update(
            created_at=timezone.make_aware(timezone.datetime(vdate.year, vdate.month, vdate.day, 11, 30))
        )

print(f"  Investigation orders OK ({len(inv_orders_data)})")

# ═══════════════════════════════════════════════════════════════════
# 11. LAB ORDERS + RESULTS
# ═══════════════════════════════════════════════════════════════════
from apps.laboratory.models import LabTestType, LabOrder, LabOrderItem, LabResult

def get_lab_type(code):
    return LabTestType.objects.filter(code=code).first()

lab_orders_data = [
    # Visit 1: Baseline bloods
    (0, "Pre-operative workup and diabetic baseline", [
        ("FBC", "COMPLETED", "14.2", "g/dL", False, False),
        ("HBA1C", "COMPLETED", "6.8", "%", False, False),
        ("CREAT", "COMPLETED", "82", "umol/L", False, False),
        ("LIPID", "COMPLETED", "Total: 5.2, LDL: 3.1, HDL: 1.4, TG: 1.5", "mmol/L", False, False),
        ("GLU-F", "COMPLETED", "5.8", "mmol/L", True, False),
    ]),
    # Visit 3: Diabetic screening
    (2, "Diabetic monitoring", [
        ("HBA1C", "COMPLETED", "6.5", "%", False, False),
        ("CREAT", "COMPLETED", "85", "umol/L", False, False),
        ("GLU-R", "COMPLETED", "7.2", "mmol/L", False, False),
        ("FBC", "COMPLETED", "13.8", "g/dL", False, False),
        ("ESR", "COMPLETED", "12", "mm/hr", False, False),
    ]),
    # Visit 5: Current bloods
    (4, "Routine monitoring - DM/HTN", [
        ("HBA1C", "COMPLETED", "6.5", "%", False, False),
        ("CREAT", "COMPLETED", "88", "umol/L", False, False),
        ("ELEC", "COMPLETED", "Na 140, K 4.2, Cl 102", "mmol/L", False, False),
        ("FBC", "COMPLETED", "14.0", "g/dL", False, False),
        ("CRP", "COMPLETED", "2.1", "mg/L", False, False),
        ("GLU-F", "COMPLETED", "5.4", "mmol/L", False, False),
        ("LFT", "COMPLETED", "ALT 28, AST 22, ALP 65, Bili 12", "IU/L", False, False),
    ]),
]

for visit_idx, indication, items in lab_orders_data:
    order = LabOrder.objects.create(
        consultation=consultations[visit_idx], patient=pt, ordered_by=admin,
        urgency="ROUTINE", status="COMPLETED",
        clinical_indication=indication,
        payment_status="PAID", specimen_status="RECEIVED",
        created_by=admin,
    )
    vdate = visit_dates[visit_idx]
    LabOrder.objects.filter(id=order.id).update(
        created_at=timezone.make_aware(timezone.datetime(vdate.year, vdate.month, vdate.day, 9, 30))
    )
    for code, status, value, unit, is_abn, is_crit in items:
        tt = get_lab_type(code)
        if not tt:
            continue
        try:
            item = LabOrderItem.objects.create(order=order, test_type=tt, status=status)
            if status == "COMPLETED":
                LabResult.objects.create(
                    order_item=item, performed_by=admin,
                    result_value=value, result_unit=unit,
                    is_abnormal=is_abn, is_critical=is_crit,
                    is_verified=True, result_status="VERIFIED",
                    version_number=1, created_by=admin,
                )
        except Exception as e:
            print(f"  SKIP lab item {code}: {e}")

print(f"  Lab orders OK ({len(lab_orders_data)} orders, {sum(len(i) for _, _, i in lab_orders_data)} items)")

# ═══════════════════════════════════════════════════════════════════
# 12. BILLING (one invoice per visit)
# ═══════════════════════════════════════════════════════════════════
from apps.billing.models import Invoice, InvoiceItem, InvoiceStatus, ServiceCategory, Payment, PaymentMethod

invoice_data = [
    (0, [("Consultation - General Ophthalmology", "CONSULT", 15000),
         ("OCT RNFL OU", "INVEST", 20000), ("OCT Macula OU", "INVEST", 20000),
         ("Visual Field 24-2 OU", "INVEST", 15000), ("Fundus Photography OU", "INVEST", 10000),
         ("FBC", "LAB", 5000), ("HbA1c", "LAB", 8000), ("Creatinine", "LAB", 3000),
         ("Lipid Profile", "LAB", 8000), ("Fasting Glucose", "LAB", 2000)]),
    (1, [("Consultation - Glaucoma Clinic", "CONSULT", 20000),
         ("Pachymetry OU", "INVEST", 10000)]),
    (2, [("Consultation - Retina Clinic", "CONSULT", 20000),
         ("OCT Macula OU", "INVEST", 20000),
         ("HbA1c", "LAB", 8000), ("Creatinine", "LAB", 3000), ("FBC", "LAB", 5000),
         ("Random Glucose", "LAB", 2000), ("ESR", "LAB", 3000)]),
    (3, [("Consultation - Cornea Clinic", "CONSULT", 15000),
         ("Refraction", "REFRACTION", 5000),
         ("Hyabak eye drops x3", "PHARMACY", 12000),
         ("Ikervis (Ciclosporin) x1", "PHARMACY", 25000)]),
    (4, [("Consultation - General Ophthalmology", "CONSULT", 15000),
         ("OCT RNFL OU", "INVEST", 20000), ("Visual Field 24-2 OU", "INVEST", 15000),
         ("Corneal Topography OU", "INVEST", 12000),
         ("HbA1c", "LAB", 8000), ("Creatinine", "LAB", 3000), ("FBC", "LAB", 5000),
         ("Electrolytes", "LAB", 5000), ("CRP", "LAB", 4000),
         ("Fasting Glucose", "LAB", 2000), ("LFT", "LAB", 8000)]),
]

for visit_idx, items in invoice_data:
    vdate = visit_dates[visit_idx]
    inv = Invoice(patient=pt, status=InvoiceStatus.PAID, created_by=admin)
    inv.save()
    Invoice.objects.filter(id=inv.id).update(
        issue_date=vdate,
        created_at=timezone.make_aware(timezone.datetime(vdate.year, vdate.month, vdate.day, 8, 30)),
    )
    total = 0
    for desc, cat, price in items:
        InvoiceItem.objects.create(
            invoice=inv, description=desc, category=cat,
            quantity=1, unit_price=Decimal(str(price)), created_by=admin,
        )
        total += price
    # Record payment
    Payment.objects.create(
        invoice=inv, payment_method=PaymentMethod.CASH if visit_idx % 2 == 0 else "INSURANCE",
        amount=Decimal(str(total)), received_by=admin, created_by=admin,
    )

print(f"  Invoices OK ({len(invoice_data)})")

print()
print("=" * 60)
print(f"COMPLETE: Patient '{pt.full_name}' ({pt.patient_id}) fully loaded.")
print(f"  - 5 visits across 4 departments")
print(f"  - 5 consultations with full exam data + diagnoses")
print(f"  - 3 drug prescriptions + 2 optical prescriptions")
print(f"  - {len(inv_orders_data)} investigation orders with results")
print(f"  - {len(lab_orders_data)} lab orders with {sum(len(i) for _, _, i in lab_orders_data)} test results")
print(f"  - {len(invoice_data)} invoices (all paid)")
print(f"  - 7 problems, 3 allergies, insurance, full medical history")
print("=" * 60)
'''

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS)
sftp = ssh.open_sftp()
with sftp.open('/opt/ehr-africa/_seed_full_patient.py', 'w') as f:
    f.write(REMOTE_SCRIPT)
sftp.close()
stdin, stdout, stderr = ssh.exec_command(
    'cd /opt/ehr-africa && /opt/ehr-africa/venv/bin/python _seed_full_patient.py 2>&1'
)
print(stdout.read().decode('utf-8', errors='replace'))
err = stderr.read().decode().strip()
if err:
    print('STDERR:', err[-1000:])
ssh.exec_command('rm /opt/ehr-africa/_seed_full_patient.py')
ssh.close()
