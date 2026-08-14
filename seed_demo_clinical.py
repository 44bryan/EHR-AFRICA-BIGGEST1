"""
seed_demo_clinical.py
=====================
Creates 3 fully-populated demo patients with complete clinical records:

  EHR-0037  Gervais Biyong   — Glaucoma (lab + investigations + drugs)
  EHR-0025  Appolinaire Zoa  — Cataract surgery (lab + biometry + drugs + counseling + surgery + admission)
  EHR-0038  Monique Tsafack  — Myopia/Refraction (drugs + optical prescription)

Run:
  python manage.py shell < seed_demo_clinical.py
  -- OR --
  python seed_demo_clinical.py   (if Django settings are already configured)
"""

import os, sys, django
from datetime import date, timedelta, datetime
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.base')
django.setup()

from django.utils import timezone

from apps.patients.models import Patient, Visit
from apps.consultations.models import Consultation
from apps.accounts.models import User
from apps.departments.models import Department
from apps.laboratory.models import LabOrder, LabOrderItem, LabResult, LabTestType
from apps.investigations.models import InvestigationOrder, InvestigationType
from apps.prescriptions.models import DrugPrescription, DrugPrescriptionItem, OpticalPrescription
from apps.pharmacy.models import Drug
from apps.ipd.models import SurgicalBooking, SurgicalBookingStatus, Admission, AdmissionStatus, Bed

# ── helpers ────────────────────────────────────────────────────────────────────

def ok(msg):  print(f'  OK {msg}')
def err(msg): print(f'  FAIL {msg}')

def get(model, **kw):
    try:    return model.objects.get(**kw)
    except: return None

def first(model, **kw):
    return model.objects.filter(**kw).first()

# ── fixed PKs from the live DB ─────────────────────────────────────────────────
PATIENT_GERVAIS  = 'eaf5f823-f6b9-4492-b7ec-31d253081e52'  # Gervais Biyong   EHR-0037
PATIENT_APPOL    = 'f3831834-5acd-43c7-aacd-2af76ec129a0'  # Appolinaire Zoa  EHR-0025
PATIENT_MONIQUE  = '6e36f060-3035-417d-9eb9-947f6c0fc0cb'  # Monique Tsafack  EHR-0038

DR_FOTSO   = '59124da5-ca2d-4dea-975a-43ada36131d8'   # Paul Fotso       glaucoma
DR_NGUEMA  = '56e87309-486d-4422-8418-036cb229261c'   # Marie Nguema     cataract
DR_ESSIEN  = '341b789d-657a-46b2-a214-a14a76646c4e'   # Amara Essien     optometrist

DEPT_GLAUC   = '6c28441d-2200-457f-9b7e-6976db41d28f'
DEPT_CATARACT = '7e66502d-4ba1-4b3a-9133-0cc63d742d3f'
DEPT_REFRAC  = 'b96184d9-06f6-4906-914b-77f6d8fa848a'

LAB_FBS       = '8bd3f20e-594b-4abe-98a6-e412dfd36fa5'   # Fasting Blood Sugar
LAB_FBG       = '0152b3a7-601f-4d70-b945-41d0bebcfbe8'   # Fasting Blood Glucose
LAB_CREAT     = '411fb328-5db4-45ea-a5bc-7882b206d13f'   # Serum Creatinine

INV_GONIO     = '3c9eaf91-9476-4c2d-bed9-7dc2183c66ef'   # Gonioscopy
INV_OCT       = '96bdf0ae-5fdb-43e0-b447-081f71f016cc'   # Anterior Segment OCT
INV_BIOMETRY  = '14a62dcf-29f0-4087-9906-3ef432cea289'   # Biometry / A-Scan

DRUG_BRIMON   = '17e50cd2-4134-43de-aed9-bc67f8800cb0'   # Brimonidine 0.2%
DRUG_BETAX    = '5b872eaa-c6dc-4430-97cc-897d22d00297'   # Betaxolol 0.5%
DRUG_ART_TEAR = '244cc4da-516e-466d-9afb-345b11ae15d2'   # Artificial Tears

NURSE_PATIENCE = 'cf08e5ff-df92-4821-88e7-3c4f95dd5e83'  # Patience Ewane counseling
ADM_OFFICER    = 'aeaceec7-9d6c-4762-89e3-f278e1cedb18'  # Vincent Bekono admission
BED_D01        = '40de9766-cba4-4d5e-947b-47c5c398df27'  # Day Case D01

today     = timezone.localdate()
yesterday = today - timedelta(days=1)
two_ago   = today - timedelta(days=2)
week_ago  = today - timedelta(days=7)


def make_visit(patient, dept, doctor, visit_date, status='COMPLETED', complaint=''):
    """Create a completed visit with vital signs."""
    v = Visit(
        patient=patient,
        department=dept,
        attending_doctor=doctor,
        visit_date=timezone.make_aware(datetime.combine(visit_date, datetime.min.time().replace(hour=9))),
        visit_type='OPD',
        status=status,
        chief_complaint=complaint,
        vital_signs={
            'visual_acuity_right': '6/9',
            'visual_acuity_left':  '6/12',
            'intraocular_pressure_right': '22',
            'intraocular_pressure_left':  '24',
            'blood_pressure': '130/80',
            'weight': '72',
            'height': '168',
        },
        created_by=doctor,
    )
    v.save()
    return v


def make_consultation(patient, visit, dept, doctor, complaint, plan, dx_data=None):
    """Create a consultation with department-specific exam data."""
    c = Consultation(
        patient=patient,
        visit=visit,
        department=dept,
        consulting_doctor=doctor,
        presenting_complaint=complaint,
        management_plan=plan,
        status='COMPLETED',
        consultation_date=visit.visit_date,
        department_specific_data=dx_data or {},
        created_by=doctor,
    )
    c.save()
    return c


# ==============================================================================
# PATIENT 1 — GERVAIS BIYONG (EHR-0037) — Glaucoma
# ==============================================================================
print('\n== PATIENT 1: Gervais Biyong (Glaucoma) ==')

p1 = first(Patient, id=PATIENT_GERVAIS)
if not p1:
    err('Patient not found — run base seed first'); sys.exit(1)
dr_fotso = first(User, id=DR_FOTSO)
dept_glauc = first(Department, id=DEPT_GLAUC)

try:
    v1 = make_visit(p1, dept_glauc, dr_fotso, week_ago,
                    complaint='Blurred vision, eye pain, halos around lights at night')
    ok(f'Visit created: {v1.visit_number}')
except Exception as e:
    err(f'Visit: {e}'); v1 = None

if v1:
    try:
        c1 = make_consultation(
            p1, v1, dept_glauc, dr_fotso,
            complaint='Bilateral elevated IOP, visual field defects, cupping OD>OS',
            plan='Start topical IOP-lowering therapy. Monitor visual fields monthly. Review in 4 weeks.',
            dx_data={
                'va_re_unaided': '6/12',
                'va_le_unaided': '6/9',
                'iop_re': '26',
                'iop_le': '28',
                'cup_disc_re': '0.7',
                'cup_disc_le': '0.8',
                'anterior_segment_re': 'Anterior chamber deep, angle open',
                'anterior_segment_le': 'Anterior chamber deep, angle open',
                'fundus_re': 'Large cup, inferior RNFL thinning',
                'fundus_le': 'Large cup, inferior and superior RNFL thinning',
                'clinical_notes': 'Suspected primary open-angle glaucoma. VF shows arcuate scotoma OU.',
            }
        )
        ok(f'Consultation created: {c1.pk}')
    except Exception as e:
        err(f'Consultation: {e}'); c1 = None

    # ── Lab Order — FBS + Creatinine ──────────────────────────────────────────
    lab_fbs_type   = first(LabTestType, id=LAB_FBS)
    lab_creat_type = first(LabTestType, id=LAB_CREAT)
    if c1 and lab_fbs_type and lab_creat_type:
        try:
            lo1 = LabOrder.objects.create(
                patient=p1, consultation=c1,
                ordered_by=dr_fotso,
                urgency='ROUTINE',
                clinical_indication='Pre-treatment metabolic baseline for glaucoma medication',
                status='COMPLETED',
                created_by=dr_fotso,
            )
            item_fbs = LabOrderItem.objects.create(
                order=lo1, test_type=lab_fbs_type, status='COMPLETED'
            )
            LabResult.objects.create(
                order_item=item_fbs,
                performed_by=dr_fotso,
                result_value='5.8',
                result_unit='mmol/L',
                reference_range='3.9–6.1 mmol/L',
                is_abnormal=False, is_critical=False, is_verified=True,
                result_date=v1.visit_date,
                comment='Normal fasting blood sugar.',
                created_by=dr_fotso,
            )
            item_creat = LabOrderItem.objects.create(
                order=lo1, test_type=lab_creat_type, status='COMPLETED'
            )
            LabResult.objects.create(
                order_item=item_creat,
                performed_by=dr_fotso,
                result_value='88',
                result_unit='µmol/L',
                reference_range='62–106 µmol/L',
                is_abnormal=False, is_critical=False, is_verified=True,
                result_date=v1.visit_date,
                comment='Renal function normal.',
                created_by=dr_fotso,
            )
            ok(f'Lab order + 2 results created')
        except Exception as e:
            err(f'Lab order: {e}')

    # ── Investigation Orders — Gonioscopy + OCT ───────────────────────────────
    inv_gonio_type = first(InvestigationType, id=INV_GONIO)
    inv_oct_type   = first(InvestigationType, id=INV_OCT)
    if c1 and inv_gonio_type:
        try:
            InvestigationOrder.objects.create(
                patient=p1, consultation=c1, ordered_by=dr_fotso,
                investigation_type=inv_gonio_type,
                urgency='ROUTINE', eye='OU',
                clinical_indication='Assess angle anatomy in suspected POAG',
                status='COMPLETED',
                notes='Open angle confirmed OU. Van Herick grade 3 OU.',
                created_by=dr_fotso,
            )
            ok('Gonioscopy investigation created')
        except Exception as e:
            err(f'Gonioscopy: {e}')
    if c1 and inv_oct_type:
        try:
            InvestigationOrder.objects.create(
                patient=p1, consultation=c1, ordered_by=dr_fotso,
                investigation_type=inv_oct_type,
                urgency='ROUTINE', eye='OU',
                clinical_indication='RNFL analysis for glaucomatous damage',
                status='COMPLETED',
                notes='Inferior RNFL thinning OD. Superior+inferior RNFL thinning OS. GCC abnormal OU.',
                created_by=dr_fotso,
            )
            ok('OCT investigation created')
        except Exception as e:
            err(f'OCT: {e}')

    # ── Drug Prescription — Brimonidine + Betaxolol ───────────────────────────
    drug_brimon = first(Drug, id=DRUG_BRIMON)
    drug_betax  = first(Drug, id=DRUG_BETAX)
    if c1:
        try:
            rx1 = DrugPrescription.objects.create(
                consultation=c1, patient=p1,
                prescribed_by=dr_fotso,
                notes='Use as directed. Do not stop without consulting doctor.',
                created_by=dr_fotso,
            )
            if drug_brimon:
                DrugPrescriptionItem.objects.create(
                    prescription=rx1,
                    drug_name='Brimonidine 0.2% Eye Drops',
                    drug_form='EYE_DROP',
                    concentration='0.2%',
                    dose='1 drop',
                    frequency='BD (twice daily)',
                    duration='Indefinite',
                    route='TOPICAL',
                    eye='OU',
                    quantity=2,
                    special_instructions='Apply 10 minutes apart from other drops.',
                )
            if drug_betax:
                DrugPrescriptionItem.objects.create(
                    prescription=rx1,
                    drug_name='Betaxolol 0.5% Eye Drops',
                    drug_form='EYE_DROP',
                    concentration='0.5%',
                    dose='1 drop',
                    frequency='BD (twice daily)',
                    duration='Indefinite',
                    route='TOPICAL',
                    eye='OU',
                    quantity=2,
                    special_instructions='Shake well before use.',
                )
            ok(f'Drug prescription created with 2 items')
        except Exception as e:
            err(f'Drug Rx: {e}')


# ==============================================================================
# PATIENT 2 — APPOLINAIRE ZOA (EHR-0025) — Cataract Surgery
# ==============================================================================
print('\n== PATIENT 2: Appolinaire Zoa (Cataract Surgery) ==')

p2 = first(Patient, id=PATIENT_APPOL)
dr_nguema    = first(User, id=DR_NGUEMA)
dept_cataract = first(Department, id=DEPT_CATARACT)
nurse_patience = first(User, id=NURSE_PATIENCE)
adm_officer    = first(User, id=ADM_OFFICER)
bed_d01        = first(Bed, id=BED_D01)

try:
    v2 = make_visit(p2, dept_cataract, dr_nguema, two_ago,
                    complaint='Gradual painless visual loss right eye, difficulty reading, glare sensitivity')
    ok(f'Visit created: {v2.visit_number}')
except Exception as e:
    err(f'Visit: {e}'); v2 = None

if v2:
    try:
        c2 = make_consultation(
            p2, v2, dept_cataract, dr_nguema,
            complaint='Dense nuclear sclerosis OD grade III, posterior subcapsular OS grade II',
            plan='Phacoemulsification with IOL implant OD. Pre-op biometry and FBS done. Surgery scheduled.',
            dx_data={
                'va_re_unaided': '6/60',
                'va_le_unaided': '6/18',
                'iop_re': '14',
                'iop_le': '15',
                'anterior_segment_re': 'Dense nuclear cataract Grade III. No RAPD.',
                'anterior_segment_le': 'Posterior subcapsular cataract Grade II.',
                'fundus_re': 'Difficult to view due to cataract. B-scan normal.',
                'fundus_le': 'Normal disc and macula.',
                'target_refraction': '-0.25 D',
                'iol_power_re': '21.5 D (SRK/T)',
                'clinical_notes': 'Pre-op workup complete. Phaco OD planned.',
            }
        )
        ok(f'Consultation created')
    except Exception as e:
        err(f'Consultation: {e}'); c2 = None

    # ── Lab — FBG pre-op ─────────────────────────────────────────────────────
    lab_fbg_type = first(LabTestType, id=LAB_FBG)
    if c2 and lab_fbg_type:
        try:
            lo2 = LabOrder.objects.create(
                patient=p2, consultation=c2,
                ordered_by=dr_nguema,
                urgency='ROUTINE',
                clinical_indication='Pre-operative assessment',
                status='COMPLETED',
                created_by=dr_nguema,
            )
            item_fbg = LabOrderItem.objects.create(
                order=lo2, test_type=lab_fbg_type, status='COMPLETED'
            )
            LabResult.objects.create(
                order_item=item_fbg,
                performed_by=dr_nguema,
                result_value='5.2',
                result_unit='mmol/L',
                reference_range='3.9–6.1 mmol/L',
                is_abnormal=False, is_critical=False, is_verified=True,
                result_date=v2.visit_date,
                comment='Normal. Fit for surgery.',
                created_by=dr_nguema,
            )
            ok('Pre-op FBG lab result created')
        except Exception as e:
            err(f'Lab: {e}')

    # ── Investigation — Biometry ──────────────────────────────────────────────
    inv_bio_type = first(InvestigationType, id=INV_BIOMETRY)
    if c2 and inv_bio_type:
        try:
            InvestigationOrder.objects.create(
                patient=p2, consultation=c2, ordered_by=dr_nguema,
                investigation_type=inv_bio_type,
                urgency='ROUTINE', eye='OD',
                clinical_indication='IOL power calculation for phacoemulsification',
                status='COMPLETED',
                notes='AL=23.42mm, ACD=3.45mm, K1=43.25D, K2=44.00D. IOL power: 21.5D (SRK/T target -0.25D).',
                created_by=dr_nguema,
            )
            ok('Biometry investigation created')
        except Exception as e:
            err(f'Biometry: {e}')

    # ── Pre-op Drug Rx ────────────────────────────────────────────────────────
    if c2:
        try:
            rx2 = DrugPrescription.objects.create(
                consultation=c2, patient=p2,
                prescribed_by=dr_nguema,
                notes='Pre-operative regimen. Start 3 days before surgery.',
                created_by=dr_nguema,
            )
            DrugPrescriptionItem.objects.create(
                prescription=rx2,
                drug_name='Ciprofloxacin 0.3% Eye Drops',
                drug_form='EYE_DROP',
                concentration='0.3%',
                dose='1 drop',
                frequency='QID (4 times daily)',
                duration='3 days pre-op and 2 weeks post-op',
                route='TOPICAL',
                eye='OD',
                quantity=1,
                special_instructions='Start 3 days before surgery.',
            )
            DrugPrescriptionItem.objects.create(
                prescription=rx2,
                drug_name='Prednisolone Acetate 1% Eye Drops',
                drug_form='EYE_DROP',
                concentration='1%',
                dose='1 drop',
                frequency='QID (4 times daily)',
                duration='Post-op 4 weeks (taper)',
                route='TOPICAL',
                eye='OD',
                quantity=1,
                special_instructions='Shake well. Do not stop abruptly — taper as instructed.',
            )
            ok('Pre-op drug prescription created')
        except Exception as e:
            err(f'Drug Rx: {e}')

    # ── Surgical Booking ──────────────────────────────────────────────────────
    if c2:
        try:
            counseling_note = (
                'Patient counseled on phacoemulsification procedure, risks (infection, TASS, PCR, '
                'dropped nucleus), benefits and alternatives. IOL type explained. '
                'Written consent obtained. Patient accompanied by family member.'
            )
            sb = SurgicalBooking.objects.create(
                patient=p2,
                consultation=c2,
                surgeon=dr_nguema,
                admission_officer=adm_officer,
                procedure='Phacoemulsification + IOL Implant',
                procedure_notes='Phaco OD. Target IOL 21.5D. Topical anaesthesia planned.',
                eye_laterality='OD',
                anaesthesia_type='TOPICAL',
                surgery_date=timezone.make_aware(datetime.combine(yesterday, datetime.min.time().replace(hour=9))),
                status=SurgicalBookingStatus.COMPLETED,
                surgery_category='ELECTIVE',
                total_amount=Decimal('180000'),
                deposit_required=Decimal('90000'),
                deposit_paid=Decimal('90000'),
                payment_notes='50% deposit paid. Balance to be settled post-op.',
                counseling_notes=counseling_note,
                consent_signed=True,
                consent_date=timezone.make_aware(datetime.combine(two_ago, datetime.min.time().replace(hour=10))),
                notes='Routine phaco OD. No intraoperative complications.',
                created_by=dr_nguema,
            )
            ok(f'Surgical booking created: {sb.booking_number}')

            # ── Admission ─────────────────────────────────────────────────────
            admission_note = (
                'Patient admitted to Day Case Surgical Unit at 07:00. Pre-op checklist completed. '
                'Pupil dilated with Tropicamide + Phenylephrine. Surgery performed at 09:30. '
                'Uncomplicated phacoemulsification. IOL in bag. Patch applied. Patient discharged at 14:00.'
            )
            adm = Admission.objects.create(
                patient=p2,
                surgical_booking=sb,
                bed=bed_d01,
                admitting_doctor=dr_nguema,
                admission_date=timezone.make_aware(datetime.combine(yesterday, datetime.min.time().replace(hour=7))),
                discharge_date=timezone.make_aware(datetime.combine(yesterday, datetime.min.time().replace(hour=14))),
                status=AdmissionStatus.DISCHARGED,
                diagnosis_on_admission='Dense nuclear cataract OD for phacoemulsification',
                discharge_summary=(
                    'Uncomplicated phacoemulsification OD with in-the-bag IOL implantation. '
                    'Post-op VA OD: 6/12 unaided (6/6 with pinhole). '
                    'IOP OD: 12 mmHg. No inflammation. Discharged home stable. '
                    'Review in 1 week.'
                ),
                notes=admission_note,
                created_by=adm_officer,
            )
            ok(f'Admission + discharge created')
        except Exception as e:
            err(f'Surgical booking/admission: {e}')


# ==============================================================================
# PATIENT 3 — MONIQUE TSAFACK (EHR-0038) — Myopia / Refraction
# ==============================================================================
print('\n== PATIENT 3: Monique Tsafack (Myopia/Refraction) ==')

p3 = first(Patient, id=PATIENT_MONIQUE)
dr_essien   = first(User, id=DR_ESSIEN)
dept_refrac = first(Department, id=DEPT_REFRAC)
drug_art    = first(Drug, id=DRUG_ART_TEAR)

try:
    v3 = make_visit(p3, dept_refrac, dr_essien, yesterday,
                    complaint='Blurred distance vision, headaches after reading, wants new spectacles')
    ok(f'Visit created: {v3.visit_number}')
except Exception as e:
    err(f'Visit: {e}'); v3 = None

if v3:
    try:
        c3 = make_consultation(
            p3, v3, dept_refrac, dr_essien,
            complaint='Myopia OU, asthenopia. Existing glasses inadequate.',
            plan='New spectacle prescription issued. Artificial tears for dry eye. Review in 6 months.',
            dx_data={
                'va_re_unaided': '6/60',
                'va_le_unaided': '6/36',
                'va_re_aided': '6/6',
                'va_le_aided': '6/6',
                'iop_re': '14',
                'iop_le': '13',
                'cover_test': 'Orthophoric',
                'motility': 'Full, no restriction',
                'npc': '5cm',
                'anterior_segment_re': 'Clear cornea, deep AC, no anterior segment pathology',
                'anterior_segment_le': 'Clear cornea, deep AC, no anterior segment pathology',
                'fundus_re': 'Healthy disc, macula intact, mild temporal crescent',
                'fundus_le': 'Healthy disc, macula intact, mild temporal crescent',
                'dry_refraction_re': '-3.00/-0.50x180',
                'dry_refraction_le': '-2.75/-0.25x175',
                'clinical_notes': 'Simple myopia OU with mild astigmatism. Mild dry eye symptoms.',
            }
        )
        ok(f'Consultation created')
    except Exception as e:
        err(f'Consultation: {e}'); c3 = None

    # ── Optical Prescription ──────────────────────────────────────────────────
    if c3:
        try:
            opt_rx = OpticalPrescription.objects.create(
                consultation=c3,
                patient=p3,
                prescribed_by=dr_essien,
                prescription_type='DISTANCE',
                # Right eye
                re_sphere=Decimal('-3.00'),
                re_cylinder=Decimal('-0.50'),
                re_axis=180,
                re_add=None,
                re_visual_acuity='6/6',
                re_prism=None,
                # Left eye
                le_sphere=Decimal('-2.75'),
                le_cylinder=Decimal('-0.25'),
                le_axis=175,
                le_add=None,
                le_visual_acuity='6/6',
                le_prism=None,
                interpupillary_distance=Decimal('63.0'),
                lens_type='Single Vision Anti-Reflection Lens',
                notes='For full-time wear. First pair of spectacles.',
                created_by=dr_essien,
            )
            ok(f'Optical prescription created: {opt_rx.pk}')
        except Exception as e:
            err(f'Optical Rx: {e}')

    # ── Drug Prescription — Artificial Tears ─────────────────────────────────
    if c3:
        try:
            rx3 = DrugPrescription.objects.create(
                consultation=c3, patient=p3,
                prescribed_by=dr_essien,
                notes='For dry eye relief.',
                created_by=dr_essien,
            )
            DrugPrescriptionItem.objects.create(
                prescription=rx3,
                drug_name='Artificial Tears (Carboxymethylcellulose 0.5%)',
                drug_form='EYE_DROP',
                concentration='0.5%',
                dose='1–2 drops',
                frequency='PRN (as needed)',
                duration='3 months',
                route='TOPICAL',
                eye='OU',
                quantity=2,
                special_instructions='Use when eyes feel dry or irritated. Safe for long-term use.',
            )
            ok('Drug prescription (artificial tears) created')
        except Exception as e:
            err(f'Drug Rx: {e}')


# ==============================================================================
print('\n' + '='*60)
print('DONE. Patient records populated:')
print('  EHR-0037 Gervais Biyong  - Glaucoma: lab + investigations + 2 drugs')
print('  EHR-0025 Appolinaire Zoa - Cataract: lab + biometry + drugs + surgery + admission')
print('  EHR-0038 Monique Tsafack - Myopia:   optical Rx + artificial tears')
print('\nOpen any of these in the Patient Record to see all tabs populated.')
