import os, sys
sys.path.insert(0, '/opt/ehr-africa')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.production')
import django; django.setup()
from datetime import date
from django.utils import timezone
from apps.patients.models import (Patient, Visit, VisitType, VisitStatus,
    PatientConsent, ConsentType, NextOfKin, MedicalHistory, InsuranceInfo)
from apps.qms.models import QueueToken, TokenStatus, ServiceType, ServiceTier
from apps.accounts.models import User

admin = User.objects.filter(username='admin').first() or User.objects.first()
today = timezone.localdate()
now   = timezone.now()
TPRI  = {ServiceTier.VIP:30, ServiceTier.FAST_TRACK:20, ServiceTier.EXPRESS:10, ServiceTier.STANDARD:0}

def make_token(pat, visit, tier):
    ex = QueueToken.objects.filter(
        patient=pat, token_date=today, service_type=ServiceType.CASHIER,
        status__in=[TokenStatus.WAITING, TokenStatus.CALLED, TokenStatus.SERVING],
        is_deleted=False).first()
    if ex: return ex, False
    try:
        from apps.qms.models import DailyTokenSequence
        num = DailyTokenSequence.next_dept_token(ServiceType.CASHIER)
    except Exception:
        import random; num = random.randint(100, 999)
    t = QueueToken.objects.create(
        patient=pat, visit=visit, token_date=today, token_number=num,
        service_type=ServiceType.CASHIER, service_tier=tier,
        status=TokenStatus.WAITING, priority=TPRI[tier])
    return t, True

PATIENTS = [
  dict(tier=ServiceTier.VIP, vt=VisitType.FOLLOW_UP,
    fn="Alphonse", mn="Ghislain", ln="Nkemdirim",
    dob=date(1958,4,12), g="M", bg="B+", ge="AA",
    ph="+237677100001", em="a.nkemdirim@cabinet.cm",
    occ="Senior Advocate", rel="Catholic", ms="MARRIED",
    qt="Bastos", town="Yaounde", div="Mfoundi", rgn="Centre", wa=True,
    note="VIP. Lawyer.",
    nok_n="Henriette Nkemdirim", nok_r="Wife", nok_p="+237677100002",
    al="Sulfonamides - severe rash.",
    eye_hx="POAG OD 2019. Latanoprost + timolol. IOP controlled 12/14 mmHg.",
    sys="HTN controlled. T2DM HbA1c 7.1%. Dyslipidaemia.",
    meds="Latanoprost 0.005% OD nocte. Timolol 0.5% BD. Amlodipine 10mg. Metformin 850mg BD.",
    cc="3-monthly glaucoma monitoring. No vision change. Mild evening headache OD.",
    bl="INSURANCE", ico="SAAR Assurances", iref="SAAR-VIP-2026-041887",
    cp="Glaucoma Follow-up - IOP, Visual Field and Optic Disc Photography",
    cr="IOP: brief discomfort. Fluorescein: yellow tinge transient. VF: no risk. Photography: bright flash."),
  dict(tier=ServiceTier.VIP, vt=VisitType.FOLLOW_UP,
    fn="Celestine", mn="Honorine", ln="Onana-Mengue",
    dob=date(1964,8,3), g="F", bg="A+", ge="AA",
    ph="+237677100003", em="celeste.onana@yahoo.fr",
    occ="Retired Supreme Court Judge", rel="Catholic", ms="WIDOWED",
    qt="Bastos", town="Yaounde", div="Mfoundi", rgn="Centre", wa=True,
    note="VIP. Retired judge. Son Arnaud handles appointments.",
    nok_n="Arnaud Onana", nok_r="Son", nok_p="+237699100010",
    al="Aspirin - bronchospasm. Metformin - GI intolerance.",
    eye_hx="Diabetic retinopathy bilateral non-proliferative. Pseudophakia OD 2022. Dry eye moderate.",
    sys="T2DM on insulin HbA1c 8.4%. HTN. Hyperlipidaemia.",
    meds="Insulin glargine 20u nocte. Amlodipine 5mg. Rosuvastatin 10mg. PF tears QID.",
    cc="3-monthly DR review. Mild increase floaters OS x4 weeks. Blurring when sugar elevated.",
    bl="INSURANCE", ico="BEAC Mutual Insurance", iref="BEAC-RET-2026-007741",
    cp="Diabetic Retinopathy Review - Fundus Photography, OCT and Dilated Fundus Exam",
    cr="Dilation: blurred vision 3-4h, light sensitivity, stinging. Photography: bright flash. OCT: no risk."),
  dict(tier=ServiceTier.STANDARD, vt=VisitType.NEW,
    fn="Emmanuel", mn="Junior", ln="Nguele-Abomo",
    dob=date(2003,12,11), g="M", bg="O-", ge="SS",
    ph="+237674200001", em="manu.nguele@gmail.com",
    occ="University Student UYI Year 2", rel="Protestant", ms="SINGLE",
    qt="Ngoa-Ekelle", town="Yaounde", div="Mfoundi", rgn="Centre", wa=True,
    note="Standard. Sickle cell HbSS. First ever eye exam.",
    nok_n="Thomas Nguele Abomo", nok_r="Father", nok_p="+237677200001",
    al="Penicillin - anaphylaxis CHU 2018. Codeine - severe nausea.",
    eye_hx="No prior eye exam. Headaches and blurring noted by nurse. SCD retinopathy screening overdue.",
    sys="Sickle cell HbSS. Anaemia Hb 7.8. Post-splenectomy 2011. On hydroxyurea.",
    meds="Hydroxyurea 500mg OD. Folic acid 5mg. Penicillin V 250mg BD. Paracetamol PRN.",
    cc="Daily headaches x3 months worse reading. Cannot see notes from back of hall. First eye exam. SCD retinopathy screening required.",
    bl="SELF_PAY", ico="", iref="",
    cp="Comprehensive Assessment - Refraction, IOP, Dilated Fundus and SCD Retinopathy Screening",
    cr="Dilation drops: stinging, blurred vision 4-6h. Tonometry: topical anaesthetic. SCD - cautious mydriasis, doctor alerted. Diagnostic only."),
  dict(tier=ServiceTier.STANDARD, vt=VisitType.NEW,
    fn="Fatima", mn="Aisha", ln="Oumarou",
    dob=date(1988,1,30), g="F", bg="B-", ge="AC",
    ph="+237674200002", em="fatima.oumarou@hotmail.fr",
    occ="Primary School Teacher", rel="Muslim", ms="MARRIED",
    qt="Mfoundi", town="Yaounde", div="Mfoundi", rgn="Centre", wa=False,
    note="Standard. Teacher. Husband accompanying.",
    nok_n="Moussa Oumarou", nok_r="Husband", nok_p="+237677200002",
    al="No known drug allergies.",
    eye_hx="No prior eye disease. Red painful eye with discharge 5 days. Pharmacy drops - no improvement.",
    sys="No chronic conditions. G3P3. Iron deficiency anaemia.",
    meds="Ferrous sulphate 200mg OD. Folic acid 5mg. Paracetamol PRN.",
    cc="Red painful right eye x5 days with mucopurulent discharge. Foreign body sensation, photophobia. Left eye mildly red. Pharmacy drops - no improvement. Possible conjunctivitis vs keratitis.",
    bl="SELF_PAY", ico="", iref="",
    cp="Anterior Segment Assessment - Slit Lamp, Corneal Staining and Conjunctival Swab if Indicated",
    cr="Slit-lamp: non-invasive. Fluorescein: transient stinging, yellow tinge. Swab: brief discomfort. Antibiotic drops may be prescribed."),
  dict(tier=ServiceTier.FAST_TRACK, vt=VisitType.NEW,
    fn="Rodrigue", mn="Gaetan", ln="Tchamba",
    dob=date(1995,11,5), g="M", bg="AB+", ge="AA",
    ph="+237655300001", em="rodrigue.tchamba@gmail.com",
    occ="Civil Engineer Socatraf Construction", rel="Protestant", ms="SINGLE",
    qt="Omnisport", town="Yaounde", div="Mfoundi", rgn="Centre", wa=True,
    note="Fast Track. Occupational eye injury this morning.",
    nok_n="Marie-Claire Tchamba", nok_r="Mother", nok_p="+237699300001",
    al="No known drug allergies.",
    eye_hx="No prior eye disease. Safety goggles worn but briefly removed at time of incident.",
    sys="No chronic conditions. Fit. BMI 24.1.",
    meds="None.",
    cc="Metal fragment entered right eye during angle grinding 2 hours ago. Immediate pain, tearing and blurred vision OD. First aid applied - no improvement. High risk intraocular foreign body.",
    bl="INSURANCE", ico="CNPS Cameroun", iref="CNPS-AT-2026-TC0338",
    cp="Urgent Ocular Foreign Body Assessment - Slit Lamp, B-Scan and Possible Surgical Removal",
    cr="Slit-lamp: topical anaesthetic. B-scan: non-invasive. If IOFB: vitreoretinal surgery - risks: infection, bleeding, retinal detachment. Risk of NOT operating: endophthalmitis, toxic siderosis."),
  dict(tier=ServiceTier.FAST_TRACK, vt=VisitType.FOLLOW_UP,
    fn="Nadege", mn="Beatrice", ln="Essomba",
    dob=date(1992,3,14), g="F", bg="O+", ge="AS",
    ph="+237655300002", em="nadege.essomba@gmail.com",
    occ="Pharmacist Pharmacie du Soleil Nlongkak", rel="Catholic", ms="MARRIED",
    qt="Nlongkak", town="Yaounde", div="Mfoundi", rgn="Centre", wa=True,
    note="Fast Track. Post-op day 7 trabeculectomy OS - possible hypotony.",
    nok_n="Gilbert Essomba", nok_r="Husband", nok_p="+237677300002",
    al="Penicillin - skin rash mild. Latex - contact urticaria.",
    eye_hx="Advanced POAG OS CD 0.95 MD -22dB. Trabeculectomy OS 7 days ago. On post-op drops.",
    sys="No chronic conditions.",
    meds="Predforte 1% hourly OS. Atropine 1% BD OS. Moxifloxacin 0.5% QID OS. Prednisolone 20mg OD.",
    cc="Post-op day 7 trabeculectomy left eye. Vision very blurred and eye feels soft. Pain this morning. Possible hypotony or wound leak - urgent bleb and IOP assessment.",
    bl="INSURANCE", ico="Activa Assurance Cameroun", iref="ACT-IND-2026-0072241",
    cp="Post-op Trabeculectomy Review - Bleb Assessment, IOP and Possible Suture Manipulation",
    cr="IOP and slit-lamp: topical anaesthetic. If hypotony: suture tightening or bleb revision - risks: bleb failure, infection, choroidal haemorrhage. Untreated hypotony can cause maculopathy."),
  dict(tier=ServiceTier.EXPRESS, vt=VisitType.NEW,
    fn="Paul-Eric", mn="Bertrand", ln="Talla-Nkembe",
    dob=date(1978,2,17), g="M", bg="O+", ge="AS",
    ph="+237691400001", em="pe.talla@entreprise.cm",
    occ="Managing Director Talla Import-Export SARL", rel="Protestant", ms="MARRIED",
    qt="Bonamoussadi", town="Douala", div="Wouri", rgn="Littoral", wa=True,
    note="Express. Referred urgently by GP. Possible acute angle closure.",
    nok_n="Nadine Talla", nok_r="Wife", nok_p="+237677400001",
    al="Iodine contrast - mild urticaria CT scan 2019.",
    eye_hx="No prior eye disease. Episode 6 months ago: severe headache, blurred vision, IOP high at Douala ER. GP today measured IOP right eye 38 mmHg.",
    sys="Hypertension Grade 1 poorly controlled.",
    meds="Amlodipine 5mg OD (poor compliance).",
    cc="Referred urgently: severe right-sided headache with eye pain and blurred vision, nausea. GP measured IOP right eye 38 mmHg. Similar episode 6 months ago. Possible acute angle-closure glaucoma.",
    bl="INSURANCE", ico="Activa Assurance Cameroun", iref="ACT-ENT-2026-0055129",
    cp="Emergency Glaucoma Assessment - IOP, Gonioscopy, Fundus Exam and Possible YAG Laser Iridotomy",
    cr="IOP applanation: brief discomfort. Gonioscopy: contact lens, mild discomfort. Dilation: blurred vision 4-6h. If ACG: YAG iridotomy - risks: IOP spike, glare, bleeding. Permanent vision loss if untreated."),
  dict(tier=ServiceTier.EXPRESS, vt=VisitType.NEW,
    fn="Brigitte", mn="Solange", ln="Essama-Fouda",
    dob=date(1986,5,29), g="F", bg="A-", ge="AA",
    ph="+237655400002", em="brigitte.essama@yahoo.fr",
    occ="Primary School Headmistress Ecole Bilingue de Melen", rel="Catholic", ms="MARRIED",
    qt="Melen", town="Yaounde", div="Mfoundi", rgn="Centre", wa=False,
    note="Express. Acute floaters and photopsia and shadow in vision. Possible retinal detachment.",
    nok_n="Rodrigue Essama", nok_r="Husband", nok_p="+237699400002",
    al="Amoxicillin - rash confirmed. No eye drop allergies.",
    eye_hx="High myopia OD -7.50 OS -8.00. Lattice degeneration 3 years ago - never attended ophthalmologist. Daily soft contact lenses.",
    sys="Iron deficiency anaemia on treatment. No HTN, no DM. G2P2.",
    meds="Ferrous gluconate 300mg OD. Multivitamin OD.",
    cc="Sudden onset floaters and photopsia in left eye this morning. Shadow at bottom of vision OS. No pain. Known high myopia and lattice degeneration and family history retinal detachment. Possible retinal tear or early detachment.",
    bl="SELF_PAY", ico="", iref="",
    cp="Urgent Retinal Assessment - Dilated Fundus Exam and Possible Same-day Laser Retinopexy",
    cr="Dilation: blurred vision 4-6h. Indirect ophthalmoscopy: mild discomfort. If retinal tear: laser retinopexy same day - risks: scotoma, rare macular damage. Risk of NOT treating: full detachment within hours, permanent vision loss, major surgery."),
]

print("\n" + "="*65)
print(f"  Seeding 8 patients -> cashier queue | {today}")
print("="*65 + "\n")

for p in PATIENTS:
    tier = p["tier"]; label = tier.replace("_"," ").title()
    pat, created = Patient.objects.get_or_create(
        first_name=p["fn"], last_name=p["ln"],
        defaults=dict(middle_name=p.get("mn",""), date_of_birth=p["dob"], gender=p["g"],
            blood_group=p.get("bg",""), genotype=p.get("ge",""),
            phone_number=p["ph"], email=p.get("em",""),
            occupation=p.get("occ",""), religion=p.get("rel",""),
            marital_status=p.get("ms","SINGLE"),
            quarter=p.get("qt",""), village_town=p.get("town",""),
            division=p.get("div",""), region=p.get("rgn",""),
            country="Cameroon", nationality="Cameroonian",
            phone_is_whatsapp=p.get("wa",False),
            notes=p.get("note",""), registered_by=admin))
    if created:
        if p.get("nok_n"): NextOfKin.objects.create(patient=pat, full_name=p["nok_n"], relationship=p["nok_r"], phone_number=p["nok_p"])
        MedicalHistory.objects.create(patient=pat, known_allergies=p.get("al",""), previous_eye_conditions=p.get("eye_hx",""), systemic_history=p.get("sys",""), current_medications=p.get("meds",""))
        if p.get("ico"): InsuranceInfo.objects.create(patient=pat, provider=p["ico"], policy_number=p["iref"], is_active=True)
    tag = "CREATED" if created else "EXISTS "
    print(f"[{tag}] {label:10s} | {pat.full_name:30s} | {pat.patient_id}")
    visit = Visit.objects.filter(patient=pat, visit_date__date=today, is_deleted=False).first()
    if not visit:
        kw = dict(patient=pat, visit_type=p["vt"], service_tier=tier, status=VisitStatus.AT_CASHIER, chief_complaint=p["cc"], billing_type=p.get("bl","SELF_PAY"), created_by=admin)
        if p.get("ico"): kw["insurance_company"]=p["ico"]; kw["insurance_policy_ref"]=p.get("iref","")
        visit = Visit.objects.create(**kw)
        print(f"           Visit  : {visit.visit_number} - AT_CASHIER")
    else:
        visit.status=VisitStatus.AT_CASHIER; visit.service_tier=tier
        visit.save(update_fields=["status","service_tier","updated_at"])
        print(f"           Visit  : {visit.visit_number} - updated AT_CASHIER")
    if not PatientConsent.objects.filter(patient=pat, consent_type=ConsentType.GENERAL, is_deleted=False).exists():
        PatientConsent.objects.create(patient=pat, consent_type=ConsentType.GENERAL,
            procedure_name=p["cp"], obtained_by=admin, signed_at=now, patient_has_capacity=True,
            risks_explained=p["cr"],
            is_valid=True, witness_name=p.get("nok_n",""), created_by=admin)
        print(f"           Consent: GENERAL - signed and approved")
    else:
        print(f"           Consent: already exists")
    token, new = make_token(pat, visit, tier)
    print(f"           Token  : #{token.token_number} | {tier} | priority={token.priority} | {'NEW' if new else 'already queued'}\n")

print("="*65)
print("  Done - 8 patients: 2 VIP / 2 Standard / 2 Fast Track / 2 Express")
print("="*65 + "\n")
