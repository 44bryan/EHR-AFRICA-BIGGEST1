"""
Management command: seed_demo_patient
Creates a fully-fledged demo patient with realistic clinical records across
all major ophthalmology services for demo / LinkedIn / screenshot purposes.

Patient: Emmanuel Nguema Mbarga — 58 y/o diabetic Cameroonian male
Journey: Refraction → General Oph → Glaucoma → Retina → Cataract Surgery → Discharge
"""
import datetime
import uuid
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = 'Seeds a complete demo patient across all ophthalmology clinical services'

    def add_arguments(self, parser):
        parser.add_argument('--delete', action='store_true',
                            help='Delete existing Emmanuel Nguema Mbarga record first')

    def handle(self, *args, **options):
        from apps.patients.models import Patient, Visit, VisitType
        from apps.consultations.models import Consultation, SurgicalRequest
        from apps.accounts.models import User, UserRole
        from apps.departments.models import Department
        from apps.prescriptions.models import DrugPrescription, DrugPrescriptionItem, OpticalPrescription
        from apps.investigations.models import InvestigationOrder, InvestigationType, InvestigationResult
        from apps.ipd.models import (
            Admission, Ward, Bed, BedStatus, SurgicalBooking, SurgicalBookingStatus,
            TheatreSession, TheatreSessionStatus, TheatreProcedure,
            PreOpCounsellingChecklist, PreOpInvestigation, PreOpInvType, PreOpInvStatus,
            SurgicalMaterial, SurgicalMaterialType, OperativeReport, IncisionType,
            RecoveryRoomRecord, RecoveryDischargeStatus, DischargeChecklist,
            AdmissionStatus, AdmissionType,
        )

        self.stdout.write(self.style.MIGRATE_HEADING('=== EHR Africa — Demo Patient Seed ==='))

        # ── Optionally delete existing record ──────────────────────────────────
        if options['delete']:
            from apps.ipd.models import SurgicalBooking, Admission, TheatreSession, TheatreProcedure
            from apps.consultations.models import SurgicalRequest, Consultation
            from apps.prescriptions.models import DrugPrescription, OpticalPrescription
            from apps.investigations.models import InvestigationOrder
            from apps.patients.models import Visit
            patients = Patient.objects.filter(first_name='Emmanuel', last_name='Nguema Mbarga')
            for p in patients:
                # Delete in dependency order (most dependent first)
                TheatreProcedure.objects.filter(patient=p).delete()
                Admission.objects.filter(patient=p).delete()
                SurgicalBooking.objects.filter(patient=p).delete()
                SurgicalRequest.objects.filter(patient=p).delete()
                DrugPrescription.objects.filter(patient=p).delete()
                OpticalPrescription.objects.filter(patient=p).delete()
                InvestigationOrder.objects.filter(patient=p).delete()
                Consultation.objects.filter(patient=p).delete()
                Visit.objects.filter(patient=p).delete()
            patients.delete()
            self.stdout.write(self.style.WARNING('Existing record deleted.'))

        # ── Resolve key users ──────────────────────────────────────────────────
        def _doc(role, name_fragment):
            """Get first doctor matching role + name fragment."""
            return User.objects.filter(role=role, last_name__icontains=name_fragment).first() \
                or User.objects.filter(role=role).first()

        def _dept(code):
            return Department.objects.filter(code=code).first()

        admin       = User.objects.filter(role=UserRole.SUPER_ADMIN).first()
        optometrist = User.objects.filter(role=UserRole.OPTOMETRIST).first()
        gen_oph     = User.objects.filter(role=UserRole.OPHTHALMOLOGIST, last_name__icontains='Doctor').first() \
                      or User.objects.filter(role=UserRole.OPHTHALMOLOGIST).first()
        glaucoma_dr = User.objects.filter(role=UserRole.OPHTHALMOLOGIST, last_name__icontains='Emade').first() \
                      or gen_oph
        retina_dr   = User.objects.filter(role=UserRole.OPHTHALMOLOGIST, last_name__icontains='Britha').first() \
                      or gen_oph
        surgeon     = User.objects.filter(role=UserRole.OPHTHALMOLOGIST, last_name__icontains='CataractSurg').first() \
                      or gen_oph
        nurse       = User.objects.filter(role=UserRole.NURSE).first() or admin
        adm_officer = User.objects.filter(role=UserRole.ADMISSION_OFFICER).first() or admin

        dept_refrac   = _dept('REFRAC')   or _dept('OPTOMETRY')
        dept_gen_oph  = _dept('GEN_OPH')
        dept_glaucoma = _dept('GLAUCOMA') or _dept('GLAUC')
        dept_retina   = _dept('RETINA')
        dept_cataract = _dept('CATARACT')

        self.stdout.write(f'  Doctors: optom={optometrist}, gen_oph={gen_oph}, glaucoma={glaucoma_dr}, retina={retina_dr}, surgeon={surgeon}')

        # ── 1. CREATE PATIENT ──────────────────────────────────────────────────
        patient, created = Patient.objects.get_or_create(
            first_name='Emmanuel',
            last_name='Nguema Mbarga',
            defaults=dict(
                date_of_birth=datetime.date(1966, 3, 15),
                gender='M',
                blood_group='B+',
                genotype='AA',
                phone_number='+237677123456',
                email='e.nguema@example.cm',
                address='Quartier Omnisports, Yaoundé',
                occupation='Civil Servant — Ministry of Finance',
                religion='Christian',
                marital_status='married',
                nationality='Cameroonian',
                quarter='Omnisports',
                village_town='Yaoundé',
            )
        )
        pid = patient.patient_id
        self.stdout.write(self.style.SUCCESS(f'  Patient: {patient.first_name} {patient.last_name} [{pid}] {"(new)" if created else "(existing)"}'))

        today = timezone.localdate()
        now   = timezone.now()

        # helper: visit date N months ago
        def _vdate(months_ago):
            d = today - datetime.timedelta(days=months_ago * 30)
            return d

        # ── 2. OPTOMETRY / REFRACTION VISIT ───────────────────────────────────
        self.stdout.write('  Creating Optometry visit...')
        v1 = Visit.objects.create(
            patient=patient,
            visit_date=_vdate(6),
            visit_type='OUTPATIENT',
            chief_complaint='Blurring of vision both eyes for 2 years. Difficulty reading and driving.',
            status='COMPLETED',
            service_tier='STANDARD',
            billing_type='CASH',
            created_by=admin,
        )
        c1 = Consultation.objects.create(
            visit=v1,
            patient=patient,
            department=dept_refrac,
            consulting_doctor=optometrist,
            consultation_date=_vdate(6),
            status='COMPLETED',
            presenting_complaint='Progressive blurring both eyes × 2 years. Worse at night. Difficulty reading small print.',
            history_of_presenting_complaint=(
                'Mr Nguema Mbarga is a 58-year-old civil servant who presents with a 2-year history of '
                'gradually worsening vision in both eyes. He reports difficulty reading documents at work '
                'and has recently stopped driving at night due to glare. No eye pain, no redness, no discharge. '
                'He has type 2 diabetes mellitus (on metformin + glibenclamide × 8 years) and hypertension '
                '(on amlodipine 5 mg).'
            ),
            ocular_history='No previous eye surgery. No spectacles worn previously. No trauma.',
            systemic_history='T2DM × 8 years (HbA1c 8.2% last month). HTN × 5 years. No known allergies.',
            drug_history='Metformin 500 mg BD, Glibenclamide 5 mg OD, Amlodipine 5 mg OD.',
            family_history='Father had glaucoma. Mother had cataracts, operated age 65.',
            examination_findings=(
                'VA sc: OD 6/36 — OS 6/18\n'
                'VA cc (trial): OD 6/12 (-2.50 / -0.75 × 90°) — OS 6/9 (-1.75 / -0.50 × 85°)\n'
                'Add: +2.50 both eyes\n'
                'NVA: OD N8 — OS N6 (with addition)\n'
                'IOP (NCT): OD 26 mmHg — OS 24 mmHg (!!  ELEVATED — refer Gen Oph)\n'
                'Cover test: Orthophoria\n'
                'Pupils: Equal, reactive, no RAPD\n'
                'Colour vision: Normal OU'
            ),
            department_specific_data={
                'va_od_sc': '6/36',
                'va_os_sc': '6/18',
                'va_od_cc': '6/12',
                'va_os_cc': '6/9',
                'iop_od': '26',
                'iop_os': '24',
                'sph_od': '-2.50',
                'cyl_od': '-0.75',
                'axis_od': '90',
                'sph_os': '-1.75',
                'cyl_os': '-0.50',
                'axis_os': '85',
                'add': '+2.50',
            },
            diagnosis_re='Compound myopic astigmatism OD. Presbyopia.',
            diagnosis_le='Compound myopic astigmatism OS. Presbyopia.',
            diagnosis_general='Bilateral compound myopic astigmatism with presbyopia. Elevated IOP bilateral — refer urgently to General Ophthalmology.',
            management_plan=(
                '1. Prescription for distance + reading spectacles issued.\n'
                '2. URGENT referral to General Ophthalmology — IOP elevated OD 26, OS 24. Family history of glaucoma.\n'
                '3. Patient counselled on importance of follow-up and blood sugar control.\n'
                '4. Review in 3 months post-spectacles or earlier if symptomatic.'
            ),
            follow_up_date=_vdate(3),
            created_by=optometrist or admin,
        )

        # Optical prescription
        OpticalPrescription.objects.create(
            patient=patient,
            consultation=c1,
            prescribed_by=optometrist or admin,
            prescription_date=_vdate(6),
            re_sphere=Decimal('-2.50'),
            re_cylinder=Decimal('-0.75'),
            re_axis=90,
            re_add=Decimal('2.50'),
            re_visual_acuity='6/12',
            le_sphere=Decimal('-1.75'),
            le_cylinder=Decimal('-0.50'),
            le_axis=85,
            le_add=Decimal('2.50'),
            le_visual_acuity='6/9',
            interpupillary_distance=64,
            lens_type='PROGRESSIVE',
            frame_advice='Lightweight progressive lenses. Anti-reflection coating recommended.',
            notes='Patient is new spectacle wearer. Advise progressive lens adaptation period (1–2 weeks).',
            created_by=optometrist or admin,
        )

        # Refraction investigation order
        inv_type_va   = InvestigationType.objects.filter(code='VA').first()
        inv_type_ncT  = InvestigationType.objects.filter(code='NCT').first()
        if inv_type_va:
            InvestigationOrder.objects.create(
                patient=patient, visit=v1, investigation_type=inv_type_va,
                ordered_by=optometrist or admin,
                clinical_indication='Routine VA assessment', status='RESULTED',
                eye='OU', payment_status='PAID', created_by=admin,
            )

        self.stdout.write(self.style.SUCCESS('    OK:Optometry visit + optical Rx + VA order'))

        # ── 3. GENERAL OPHTHALMOLOGY VISIT ────────────────────────────────────
        self.stdout.write('  Creating General Ophthalmology visit...')
        v2 = Visit.objects.create(
            patient=patient,
            visit_date=_vdate(5),
            visit_type='OUTPATIENT',
            chief_complaint='Referred from optometry — elevated IOP bilateral. Blurring of vision. Family history of glaucoma.',
            status='COMPLETED',
            service_tier='STANDARD',
            billing_type='CASH',
            created_by=admin,
        )
        c2 = Consultation.objects.create(
            visit=v2,
            patient=patient,
            department=dept_gen_oph,
            consulting_doctor=gen_oph,
            consultation_date=_vdate(5),
            status='COMPLETED',
            presenting_complaint='Referred for elevated IOP. Blurring of vision OU × 2 years.',
            history_of_presenting_complaint=(
                'Known hypertensive diabetic. Referred by optometrist with IOP OD 26 OS 24 mmHg and family history '
                'of glaucoma (father). Patient reports mild difficulty with peripheral vision recently. '
                'No headache, no haloes, no pain.'
            ),
            ocular_history='Compound myopic astigmatism. Spectacles prescribed 5 months ago.',
            systemic_history='T2DM, HTN. On metformin, glibenclamide, amlodipine.',
            examination_findings=(
                'VA sc: OD 6/36 OS 6/18\n'
                'VA cc: OD 6/12 OS 6/9\n'
                'IOP (GAT): OD 28 mmHg — OS 25 mmHg (Goldmann applanation)\n'
                'Pupils: PERRL, no RAPD OU\n'
                'Anterior segment:\n'
                '  OD: Cornea clear. Anterior chamber 3+. NS Grade II cataract. Iris normal.\n'
                '  OS: Cornea clear. Anterior chamber 3+. NS Grade I cataract. Iris normal.\n'
                'Posterior segment (dilated):\n'
                '  OD: C/D ratio 0.7. Superior notching of NRR. No disc haemorrhage. Macula: mild CSME suspect.\n'
                '  OS: C/D ratio 0.65. Mild inferotemporal thinning. Macula: dot/blot haemorrhages, hard exudates — diabetic maculopathy.\n'
                '  Peripheral retina: Flat OU. No new vessels.'
            ),
            department_specific_data={
                'va_od_sc': '6/36', 'va_os_sc': '6/18',
                'iop_od': '28', 'iop_os': '25',
                'cd_ratio_od': '0.7', 'cd_ratio_os': '0.65',
                'lens_od': 'NS Grade II', 'lens_os': 'NS Grade I',
            },
            diagnosis_re='Suspect primary open angle glaucoma OD. NS Grade II cataract OD.',
            diagnosis_le='Suspect primary open angle glaucoma OS. NS Grade I cataract OS. Diabetic maculopathy OS.',
            diagnosis_general=(
                'Bilateral suspect primary open angle glaucoma (elevated IOP + C/D > 0.6 + family history). '
                'Bilateral nuclear sclerotic cataract. Diabetic maculopathy OS.'
            ),
            management_plan=(
                '1. REFER to Glaucoma Clinic urgently — POAG workup (VF 24-2, OCT RNFL, Pachymetry, Gonioscopy).\n'
                '2. REFER to Retina Clinic — diabetic maculopathy OS, possible CSME.\n'
                '3. REFER to Cataract Clinic — NS Grade II OD, vision-limiting.\n'
                '4. Order OCT Macula OU, OCT RNFL OU, VF 24-2 OU.\n'
                '5. Optimise diabetic control — target HbA1c < 7%. Letter to physician.\n'
                '6. Review in 4 weeks with investigation results.'
            ),
            follow_up_date=_vdate(4),
            created_by=gen_oph or admin,
        )

        # Investigation orders
        for code in ['OCT-RNFL', 'VF-24', 'PACHY', 'GONIO', 'OCT-MAC', 'FP']:
            itype = InvestigationType.objects.filter(code=code).first()
            if itype:
                InvestigationOrder.objects.create(
                    patient=patient, visit=v2, investigation_type=itype,
                    ordered_by=gen_oph or admin,
                    clinical_indication='Suspect POAG + diabetic maculopathy workup',
                    status='RESULTED', eye='OU', payment_status='PAID', created_by=admin,
                )

        self.stdout.write(self.style.SUCCESS('    OK:General Oph visit + 6 investigation orders'))

        # ── 4. GLAUCOMA CLINIC VISIT ───────────────────────────────────────────
        self.stdout.write('  Creating Glaucoma Clinic visit...')
        v3 = Visit.objects.create(
            patient=patient,
            visit_date=_vdate(4),
            visit_type='OUTPATIENT',
            chief_complaint='Glaucoma workup referral from General Ophthalmology. IOP elevated bilateral.',
            status='COMPLETED',
            service_tier='STANDARD',
            billing_type='CASH',
            created_by=admin,
        )
        c3 = Consultation.objects.create(
            visit=v3,
            patient=patient,
            department=dept_glaucoma,
            consulting_doctor=glaucoma_dr,
            consultation_date=_vdate(4),
            status='COMPLETED',
            presenting_complaint='Referred for elevated IOP, C/D 0.7 OD, family history of glaucoma.',
            history_of_presenting_complaint=(
                'Patient referred for comprehensive glaucoma evaluation. Reports no pain. '
                'Mild difficulty with peripheral vision on the right more than left. '
                'Father was blind from glaucoma. Patient is hypertensive and diabetic.'
            ),
            examination_findings=(
                'IOP (GAT): OD 27 mmHg — OS 24 mmHg (09:00 AM)\n'
                'Pachymetry: OD 521 µm — OS 528 µm (thin corneas — IOP likely underestimated)\n'
                'Corrected IOP: OD ~30 mmHg — OS ~27 mmHg\n'
                'Gonioscopy: Open angles grade IV (Shaffer) OU. No PAS. No neovascularisation.\n'
                'Disc: OD C/D 0.7, superior notch, nasal shift of vessels. OS C/D 0.65, inferior thinning.\n'
                'OCT RNFL:\n'
                '  OD: Superior RNFL 68 µm (< 1% = RED). Inferior 82 µm (borderline). Global 76 µm.\n'
                '  OS: Superior 78 µm (borderline). Inferior 71 µm (< 1% = RED). Global 80 µm.\n'
                'Visual Field (HVF 24-2):\n'
                '  OD: Superior arcuate defect (MD -6.8 dB, PSD 7.2 dB). Moderate loss.\n'
                '  OS: Inferior paracentral scotoma (MD -3.2 dB). Early loss.\n'
                'MD: Both fields reliable. No fixation loss, no false positives/negatives.'
            ),
            department_specific_data={
                'iop_od': '27', 'iop_os': '24',
                'pachy_od': '521', 'pachy_os': '528',
                'cd_od': '0.7', 'cd_os': '0.65',
                'rnfl_od_global': '76', 'rnfl_os_global': '80',
                'hvf_od_md': '-6.8', 'hvf_os_md': '-3.2',
                'gonioscopy': 'Open angles grade IV OU',
            },
            diagnosis_re='Primary open angle glaucoma OD — moderate stage (Hodapp-Parrish-Anderson).',
            diagnosis_le='Primary open angle glaucoma OS — early stage.',
            diagnosis_general=(
                'Bilateral primary open angle glaucoma confirmed. OD moderate stage, OS early stage. '
                'Target IOP: OD ≤ 15 mmHg (≥ 50% reduction), OS ≤ 18 mmHg.'
            ),
            management_plan=(
                '1. Start: Latanoprost 0.005% eye drops — ONE drop to BOTH eyes at BEDTIME.\n'
                '2. Return in 4 weeks for IOP recheck post-prostaglandin.\n'
                '3. Visual field every 6 months. OCT RNFL every 6 months.\n'
                '4. Educate patient: glaucoma is silent and lifelong. Adherence is critical.\n'
                '5. Proceed with cataract surgery OD (may lower IOP post-phaco).\n'
                '6. Copied to GP — optimise BP and diabetes control urgently.'
            ),
            follow_up_date=_vdate(3),
            created_by=glaucoma_dr or admin,
        )

        # Glaucoma medications prescription
        rx3 = DrugPrescription.objects.create(
            patient=patient, consultation=c3,
            prescribed_by=glaucoma_dr or admin,
            prescription_date=_vdate(4),
            notes='Start immediately. Administer at bedtime. Avoid touching eye with dropper tip.',
            created_by=glaucoma_dr or admin,
        )
        DrugPrescriptionItem.objects.create(
            prescription=rx3,
            drug_name='Latanoprost 0.005% eye drops',
            dose='1 drop', frequency='Once daily at bedtime',
            duration='Ongoing — do not stop without doctor advice',
            route='Topical',
            eye='OU',
            quantity=1,
            special_instructions='Refrigerate after opening. Apply ONE drop to EACH eye at bedtime. Press inner corner of eye for 1 minute after instillation.',
        )

        self.stdout.write(self.style.SUCCESS('    OK:Glaucoma visit + POAG diagnosis + latanoprost Rx'))

        # ── 5. RETINA CLINIC VISIT ────────────────────────────────────────────
        self.stdout.write('  Creating Retina Clinic visit...')
        v4 = Visit.objects.create(
            patient=patient,
            visit_date=_vdate(3),
            visit_type='OUTPATIENT',
            chief_complaint='Referred for diabetic maculopathy assessment. Distortion of central vision OS.',
            status='COMPLETED',
            service_tier='STANDARD',
            billing_type='CASH',
            created_by=admin,
        )
        c4 = Consultation.objects.create(
            visit=v4,
            patient=patient,
            department=dept_retina,
            consulting_doctor=retina_dr,
            consultation_date=_vdate(3),
            status='COMPLETED',
            presenting_complaint='Central vision distortion OS. Referred for diabetic macular oedema assessment.',
            history_of_presenting_complaint=(
                'T2DM × 8 years, HbA1c 8.2%. Referred from Gen Oph with dot/blot haemorrhages and hard exudates OS. '
                'Patient reports metamorphopsia and reduced reading vision left eye × 3 months. '
                'Currently on latanoprost OU for POAG. Last HbA1c 8.2% (suboptimal control).'
            ),
            examination_findings=(
                'VA sc: OD 6/36 OS 6/24\n'
                'VA cc: OD 6/12 OS 6/18 (reduced from 6/9 — macular involvement)\n'
                'IOP: OD 18 mmHg OS 16 mmHg (improved on latanoprost)\n'
                'Anterior segment: NS Grade II OD, NS Grade I OS\n'
                'Fundus exam (dilated):\n'
                '  OD: C/D 0.7. Macula: 1-2 hard exudates temporal to fovea. No CSME.\n'
                '  OS: C/D 0.65. Macula: CSME confirmed — circinate hard exudates surrounding fovea, '
                '      dot/blot haemorrhages within 1 DD of fovea, retinal thickening present.\n'
                '      Peripheral: Microaneurysms. No NVD/NVE. No pre-retinal haemorrhage.\n'
                'OCT Macula:\n'
                '  OD: CMT 265 µm. No SRF. Mild HRF.\n'
                '  OS: CMT 412 µm (ABNORMAL). Subretinal fluid present. Disrupted IS/OS layer fovea.\n'
                'FFA: OS shows late leakage at fovea confirming centre-involving DME.'
            ),
            department_specific_data={
                'va_od_cc': '6/12', 'va_os_cc': '6/18',
                'iop_od': '18', 'iop_os': '16',
                'cmt_od': '265', 'cmt_os': '412',
                'srf_os': 'Present',
                'ffa': 'Late leakage OS fovea — CI-DME confirmed',
            },
            diagnosis_re='Non-centre-involving diabetic macular oedema OD. Non-proliferative diabetic retinopathy.',
            diagnosis_le='Centre-involving diabetic macular oedema OS (CI-DME). Non-proliferative diabetic retinopathy.',
            diagnosis_general='Bilateral diabetic retinopathy. Centre-involving DME OS — treatment indicated.',
            management_plan=(
                '1. INTRAVITREAL ANTI-VEGF OS — Bevacizumab (Avastin) 1.25 mg/0.05 mL × 3 monthly injections (loading dose).\n'
                '2. Schedule injection 1: next week in procedure room (OS).\n'
                '3. URGENT: Optimise glycaemic control — letter to internist. Target HbA1c < 7%.\n'
                '4. OCT Macula OS at 4 weeks post-injection 1 to assess response.\n'
                '5. Continue latanoprost OU for POAG (IOP now 18/16 — good response).\n'
                '6. OD — monitor annually, no treatment needed at this stage.\n'
                '7. Proceed with cataract surgery OD after anti-VEGF loading course.'
            ),
            follow_up_date=_vdate(2),
            created_by=retina_dr or admin,
        )

        # Retina investigations
        for code in ['OCT-MAC', 'FFA']:
            itype = InvestigationType.objects.filter(code=code).first()
            if itype:
                InvestigationOrder.objects.create(
                    patient=patient, visit=v4, investigation_type=itype,
                    ordered_by=retina_dr or admin,
                    clinical_indication='CI-DME OS workup', status='RESULTED',
                    eye='OU', payment_status='PAID', created_by=admin,
                )

        # Anti-VEGF prescription
        rx4 = DrugPrescription.objects.create(
            patient=patient, consultation=c4,
            prescribed_by=retina_dr or admin,
            prescription_date=_vdate(3),
            notes='Intravitreal injection series. Procedure room to schedule.',
            created_by=retina_dr or admin,
        )
        DrugPrescriptionItem.objects.create(
            prescription=rx4,
            drug_name='Bevacizumab (Avastin) 25 mg/mL',
            dose='1.25 mg / 0.05 mL intravitreal injection',
            frequency='Monthly × 3 loading doses, then PRN',
            duration='3 months loading, then assess',
            route='Intravitreal', eye='OS', quantity=1,
            special_instructions='Intravitreal injection OS under aseptic conditions. Post-injection: tobramycin 0.3% TDS × 5 days.',
        )

        self.stdout.write(self.style.SUCCESS('    OK:Retina visit + CI-DME diagnosis + anti-VEGF Rx'))

        # ── 6. SURGICAL BOOKING — CATARACT OD ────────────────────────────────
        self.stdout.write('  Creating Surgical Booking (Phacoemulsification OD)...')
        v5 = Visit.objects.create(
            patient=patient,
            visit_date=_vdate(2),
            visit_type='OUTPATIENT',
            chief_complaint='Cataract surgical consultation OD. Referred from Gen Oph.',
            status='COMPLETED',
            service_tier='STANDARD',
            billing_type='CASH',
            created_by=admin,
        )
        c5 = Consultation.objects.create(
            visit=v5,
            patient=patient,
            department=dept_cataract,
            consulting_doctor=surgeon,
            consultation_date=_vdate(2),
            status='COMPLETED',
            presenting_complaint='NS Grade II cataract OD. Best corrected VA 6/12. Patient struggling with daily activities.',
            history_of_presenting_complaint=(
                'Known POAG (on latanoprost OU), T2DM, HTN. Referred for cataract assessment OD. '
                'BCVA OD 6/12 despite optimal spectacle correction — cataract is limiting. '
                'Anti-VEGF loading course OS ongoing (2 of 3 done). '
                'IOP on latanoprost: OD 18 mmHg, OS 16 mmHg.'
            ),
            examination_findings=(
                'VA sc: OD 6/60\n'
                'VA cc: OD 6/12 (glare test: 6/60 — significant glare disability)\n'
                'IOP: OD 18 mmHg OS 16 mmHg\n'
                'Anterior segment OD:\n'
                '  Cornea: Clear. Specular count 2180 cells/mm².\n'
                '  Anterior chamber: Deep, quiet.\n'
                '  Lens: Dense NS Grade III. No PSC. No phacodonesis.\n'
                '  Iris: Normal. No rubeosis.\n'
                'Biometry (IOLMaster 700):\n'
                '  Axial length OD: 23.42 mm\n'
                '  K1: 43.50 D @ 90°   K2: 44.25 D @ 180°\n'
                '  Target refraction: -0.25 D (slight myopic target for POAG patient)\n'
                '  IOL formula (Barrett Universal II): SN60WF +21.5 D\n'
                'Fundus OD (indirect): C/D 0.7. Macula: Flat, mild hard exudates temporal. No CSME.'
            ),
            department_specific_data={
                'va_od_sc': '6/60', 'va_od_cc': '6/12',
                'iop_od': '18',
                'lens_od': 'NS Grade III',
                'axial_length_od': '23.42',
                'k1_od': '43.50', 'k2_od': '44.25',
                'iol_formula': 'Barrett Universal II',
                'recommended_iol': 'Alcon SN60WF +21.5 D',
                'target_refraction': '-0.25 D',
            },
            diagnosis_re='Dense nuclear sclerotic cataract OD Grade III — visually significant. Surgical candidate.',
            diagnosis_general='Vision-limiting cataract OD. POAG (well-controlled on latanoprost). Surgical plan: Phacoemulsification + IOL OD.',
            management_plan=(
                '1. PLAN: Phacoemulsification + posterior chamber IOL implantation OD (monofocal toric-free: SN60WF +21.5 D).\n'
                '2. Anaesthesia: Topical + intracameral (avoid GA given diabetic risk).\n'
                '3. Pre-op investigations: Biometry (done), OCT anterior, CBC, RBG, HbA1c, ECG.\n'
                '4. Optimise HbA1c and BP pre-operatively. RBG < 10 mmol/L on day of surgery.\n'
                '5. Continue latanoprost OU — do NOT stop pre-op.\n'
                '6. Counselling nurse appointment for G001–G007 counselling session.\n'
                '7. Surgical booking: 2 weeks from today.'
            ),
            follow_up_date=_vdate(1),
            created_by=surgeon or admin,
        )

        # Create surgical request
        sr = SurgicalRequest.objects.create(
            consultation=c5,
            patient=patient,
            surgery_type='PHACO',
            eye='OD',
            urgency='ELECTIVE',
            status='COUNSELED',
            requested_by=surgeon or admin,
            pre_op_notes=(
                'Dense NSIII cataract OD. BCVA 6/12 cc (6/60 with glare). '
                'Known POAG — continue latanoprost pre and post-op. '
                'Diabetic patient — target RBG < 10 mmol/L on day of surgery. '
                'IOL plan: Alcon SN60WF +21.5 D. Target refraction -0.25 D.'
            ),
            scheduled_date=_vdate(1),
            theatre_notes='Topical + intracameral anaesthesia. Phaco with divide and conquer technique.',
            created_by=surgeon or admin,
        )

        # Biometry investigation
        itype_bio = InvestigationType.objects.filter(code='BIO-IOL').first() \
                    or InvestigationType.objects.filter(code='BIOM').first()
        if itype_bio:
            InvestigationOrder.objects.create(
                patient=patient, visit=v5, investigation_type=itype_bio,
                ordered_by=surgeon or admin,
                clinical_indication='Pre-op biometry for IOL power calculation',
                status='RESULTED', eye='OD', payment_status='PAID', created_by=admin,
            )

        self.stdout.write(self.style.SUCCESS('    OK:Surgical consultation + SurgicalRequest (COUNSELED)'))

        # ── 7. SURGICAL BOOKING RECORD ────────────────────────────────────────
        self.stdout.write('  Creating SurgicalBooking record...')
        ward_obj  = Ward.objects.filter(ward_type__in=['SURGICAL', 'GENERAL']).first() \
                    or Ward.objects.first()
        bed_obj   = Bed.objects.filter(ward=ward_obj, status=BedStatus.AVAILABLE).first() \
                    if ward_obj else None

        booking = SurgicalBooking.objects.create(
            patient=patient,
            consultation=c5,
            surgeon=surgeon or admin,
            procedure='PHACO',
            eye_laterality='OD',
            anaesthesia_type='TOPICAL',
            surgery_date=timezone.make_aware(datetime.datetime.combine(_vdate(1), datetime.time(8, 0))),
            status=SurgicalBookingStatus.COMPLETED,
            pre_op_requirements='Biometry done. CBC, RBG, ECG ordered. Continue latanoprost.',
            surgery_category='ELECTIVE',
            total_amount=Decimal('350000'),
            deposit_required=Decimal('175000'),
            deposit_paid=Decimal('175000'),
            consent_signed=True,
            admission_officer=adm_officer,
            notes='IOL plan: Alcon SN60WF +21.5 D. Target refraction -0.25 D. Continue latanoprost pre/post-op.',
            created_by=adm_officer or admin,
        )
        self.stdout.write(self.style.SUCCESS(f'    OK:SurgicalBooking: {booking.booking_number}'))

        # ── 8. PRE-OP COUNSELLING CHECKLIST ────────────────────────────────────
        self.stdout.write('  Creating Pre-Op Counselling Checklist...')
        PreOpCounsellingChecklist.objects.create(
            booking=booking,
            counsellor=nurse or admin,
            date=_vdate(1) - datetime.timedelta(days=7),
            g001_surgery_date_confirmed=True,
            g001_transport_arranged=True,
            g001_companion_informed=True,
            g001_notes='Wife will accompany patient. Transport arranged — personal vehicle.',
            g002_fasting_instructions=True,
            g002_medications_reviewed=True,
            g002_blood_tests_ordered=True,
            g002_bp_sugar_checked=True,
            g002_notes='Continue latanoprost. Stop metformin 48h pre-op. Glibenclamide: skip morning dose on surgery day. Target RBG < 10 mmol/L.',
            g003_procedure_explained=True,
            g003_risks_explained=True,
            g003_alternatives_discussed=True,
            g003_consent_signed=True,
            g003_notes='Risks explained: PCR < 1%, endophthalmitis < 0.1%, refractive surprise. Patient understood and signed consent form.',
            g004_ward_explained=True,
            g004_stay_duration='Day case (discharge same day)',
            g004_items_to_bring=True,
            g005_total_fees_quoted=Decimal('350000'),
            g005_deposit_amount=Decimal('175000'),
            g005_insurance_share=Decimal('0'),
            g005_patient_share=Decimal('350000'),
            g005_payment_plan_discussed=True,
            g005_notes='Patient paying cash. Deposit of 175,000 FCFA paid. Balance due on discharge.',
            g006_post_op_instructions=True,
            g006_eye_drop_schedule=True,
            g006_followup_date=_vdate(0) + datetime.timedelta(days=1),
            g006_activity_restrictions=True,
            g006_emergency_contact=True,
            g006_notes='No driving for 2 weeks. No rubbing of operated eye. Eye shield at night for 1 week.',
            g007_notes='Patient is a known glaucoma patient — continue latanoprost both eyes post-op. Diabetic — glucose monitoring twice daily.',
            patient_understood=True,
            patient_signature_obtained=True,
            counsellor_signature=True,
            created_by=nurse or admin,
        )
        self.stdout.write(self.style.SUCCESS('    OK:Pre-Op Counselling Checklist G001–G007'))

        # ── 9. PRE-OP INVESTIGATIONS ───────────────────────────────────────────
        self.stdout.write('  Creating Pre-Op Investigation records...')
        preop_invs = [
            ('BIOMETRY', PreOpInvStatus.CLEARED, 'IOLMaster 700: AL 23.42 mm, K1 43.50@90, K2 44.25@180. Barrett UII: SN60WF +21.5 D.'),
            ('OCT', PreOpInvStatus.CLEARED, 'OCT anterior segment OD: No zonular issues. Anterior chamber depth 3.2 mm.'),
            ('SPECULAR_MICRO', PreOpInvStatus.CLEARED, 'Specular microscopy OD: ECD 2180 cells/mm². Adequate for surgery.'),
            ('CBC', PreOpInvStatus.CLEARED, 'Hb 13.2 g/dL, WBC 7.4×10³, Plt 215×10³. Normal.'),
            ('RBG', PreOpInvStatus.CLEARED, 'RBG on day of surgery: 7.8 mmol/L. Acceptable (< 10 target).'),
            ('HBA1C', PreOpInvStatus.CLEARED, 'HbA1c 7.6% (improved from 8.2% — better control after intensification).'),
            ('ECG', PreOpInvStatus.CLEARED, 'Normal sinus rhythm. No ischaemic changes. Rate 72 bpm.'),
            ('ANAESTHESIA', PreOpInvStatus.CLEARED, 'Anaesthetic fitness: ASA Grade II. Fit for topical anaesthesia. No GA required.'),
        ]
        for inv_type, status, summary in preop_invs:
            PreOpInvestigation.objects.create(
                booking=booking,
                inv_type=inv_type,
                status=status,
                result_summary=summary,
                result_at=timezone.make_aware(datetime.datetime.combine(_vdate(1) - datetime.timedelta(days=3), datetime.time(10, 0))),
                cleared_at=timezone.make_aware(datetime.datetime.combine(_vdate(1) - datetime.timedelta(days=2), datetime.time(14, 0))),
                cleared_by=surgeon or admin,
                created_by=admin,
            )
        self.stdout.write(self.style.SUCCESS('    OK:8 Pre-Op Investigations — all CLEARED'))

        # ── 10. IPD ADMISSION ─────────────────────────────────────────────────
        self.stdout.write('  Creating IPD Admission...')
        admission = Admission.objects.create(
            patient=patient,
            bed=bed_obj,
            surgical_booking=booking,
            admission_date=timezone.make_aware(datetime.datetime.combine(_vdate(1), datetime.time(6, 30))),
            admission_type='DAY_CASE',
            status=AdmissionStatus.POST_OP,
            blood_group='B+',
            height_cm=Decimal('172.0'),
            weight_kg=Decimal('78.5'),
            primary_nurse=nurse or admin,
            admitting_doctor=surgeon or admin,
            expected_discharge_date=_vdate(1),
            diagnosis_on_admission='Dense NS Grade III cataract OD. POAG. T2DM. HTN.',
            notes=(
                'Day case admission for phacoemulsification + IOL OD. '
                'Patient NBM since midnight. RBG 7.8 mmol/L on arrival. '
                'BP 138/86 mmHg. Latanoprost instilled 22:00 last night. '
                'Consent signed. Surgical site marked: RIGHT EYE (OD).'
            ),
            is_readmission=False,
            created_by=adm_officer or admin,
        )
        self.stdout.write(self.style.SUCCESS('    OK:IPD Admission (Day Case)'))

        # ── 11. THEATRE SESSION + PROCEDURE ───────────────────────────────────
        self.stdout.write('  Creating Theatre Session + Procedure...')
        surgery_dt = timezone.make_aware(datetime.datetime.combine(_vdate(1), datetime.time(8, 0)))

        session = TheatreSession.objects.create(
            theatre_name='OR-1 — Cataract Suite',
            session_date=_vdate(1),
            start_time=datetime.time(7, 30),
            end_time=datetime.time(13, 0),
            lead_surgeon=surgeon or admin,
            anaesthetist=User.objects.filter(role=UserRole.ANAESTHETIST).first() or admin,
            scrub_nurse=nurse or admin,
            circulating_nurse=nurse or admin,
            status=TheatreSessionStatus.COMPLETED,
            notes='Elective cataract list. 4 cases. Mr Nguema Mbarga — Case 1.',
            created_by=admin,
        )

        procedure = TheatreProcedure.objects.create(
            session=session,
            patient=patient,
            surgical_booking=booking,
            surgeon=surgeon or admin,
            procedure='PHACO',
            eye_laterality='OD',
            anaesthesia_type='TOPICAL',
            knife_time=datetime.time(8, 5),
            closure_time=datetime.time(8, 42),
            position_on_list=1,
            # WHO Sign-In
            sign_in_done=True,
            sign_in_identity_confirmed=True,
            sign_in_site_marked=True,
            sign_in_anaesthesia_safe=True,
            sign_in_pulse_oximeter=True,
            sign_in_allergies=False,
            sign_in_time=datetime.time(8, 5),
            # WHO Time-Out
            time_out_done=True,
            time_out_team_introduced=True,
            time_out_site_confirmed=True,
            time_out_antibiotics=True,
            time_out_imaging_displayed=True,
            time_out_time=datetime.time(8, 10),
            # WHO Sign-Out
            sign_out_done=True,
            sign_out_instrument_count_correct=True,
            sign_out_specimen_labelled=False,
            sign_out_equipment_issues=False,
            sign_out_recovery_plan=True,
            sign_out_time=datetime.time(8, 42),
            # IOL details
            iol_type='MONOFOCAL',
            iol_model='Alcon AcrySof IQ SN60WF',
            iol_power='21.5',
            iol_lot_number='0064792314',
            # Outcome
            outcome='COMPLETED',
            intraop_findings='Dense NS Grade III nucleus. Good red reflex. Posterior capsule intact.',
            complications='None.',
            post_op_notes='Uneventful phacoemulsification. IOL well centred. IOP 16 mmHg at end of case.',
            created_by=admin,
        )
        self.stdout.write(self.style.SUCCESS('    OK:Theatre session + Procedure (WHO checklist complete)'))

        # ── 12. SURGICAL MATERIALS ────────────────────────────────────────────
        self.stdout.write('  Recording Surgical Materials...')
        materials_data = [
            ('IOL',           'Alcon AcrySof IQ SN60WF +21.5 D',         'Alcon',     'SN60WF',    '0064792314', '',           None,                        1, Decimal('85000')),
            ('VISCOELASTIC',  'Provisc (sodium hyaluronate 1%)',           'Alcon',     'ProVisc',   'PV23091A',   '',           datetime.date(2026, 6, 30),  1, Decimal('12000')),
            ('VISCOELASTIC',  'DisCoVisc (dispersive OVD)',                'Alcon',     'DisCoVisc', 'DV23115B',   '',           datetime.date(2026, 9, 30),  1, Decimal('15000')),
            ('IRRIGATING_SOL','BSS Plus 500 mL',                          'Alcon',     'BSS Plus',  'BP240801',   '',           datetime.date(2026, 12, 31), 1, Decimal('8000')),
            ('SUTURE',        'Nylon 10-0 suture (corneal closure)',       'Ethicon',   '2830G',     '1MHLY423',   '',           datetime.date(2027, 3, 31),  1, Decimal('3500')),
        ]
        for mtype, desc, mfr, model, lot, serial, expiry, qty, cost in materials_data:
            SurgicalMaterial.objects.create(
                procedure=procedure,
                material_type=mtype,
                description=desc,
                manufacturer=mfr,
                model_reference=model,
                lot_number=lot,
                serial_number=serial,
                expiry_date=expiry,
                quantity_used=qty,
                unit_cost=cost,
                eye='OD',
                recorded_by=nurse or admin,
                created_by=admin,
            )
        self.stdout.write(self.style.SUCCESS('    OK:5 surgical materials recorded (IOL + OVDs + BSS + suture)'))

        # ── 13. OPERATIVE REPORT ──────────────────────────────────────────────
        self.stdout.write('  Creating Operative Report...')
        OperativeReport.objects.create(
            procedure=procedure,
            procedure_start=surgery_dt + datetime.timedelta(minutes=5),
            procedure_end=surgery_dt + datetime.timedelta(minutes=37),
            operating_eye='OD',
            incision_type='CLEAR_CORNEAL',
            incision_size_mm=Decimal('2.75'),
            anaesthesia_used='Topical (proxymetacaine 0.5%) + intracameral lignocaine 1%',
            preop_va='6/60 (sc)',
            preop_iop=Decimal('18.0'),
            lens_status='Dense nuclear sclerosis Grade III. Amber-brown nucleus. No phacodonesis.',
            vitreous_status='Not encountered',
            fundus_intraop='Good red reflex throughout. Posterior capsule intact.',
            procedure_description=(
                'Patient positioned supine. Topical anaesthesia instilled × 3. Eye prepped with '
                'betadine 5% and draped in standard fashion. Lid speculum inserted.\n\n'
                'Clear corneal incision made at 12 o\'clock position with 2.75 mm keratome. '
                'Paracentesis at 3 o\'clock. DisCoVisc injected into anterior chamber to coat corneal '
                'endothelium. Continuous curvilinear capsulorhexis (CCC) performed — 5.5 mm diameter, '
                'well-centred. Hydrodissection performed with balanced salt solution — good nuclear rotation achieved.\n\n'
                'Phacoemulsification performed using divide-and-conquer technique. Nucleus divided into '
                '4 quadrants. Each quadrant emulsified at iris plane. Energy settings: 40% phaco power, '
                'torsional ultrasound, IOP compensating infusion. Epinucleus removed with bimanual I&A. '
                'Cortex aspirated with automated I&A — capsule thoroughly cleaned including subincisional cortex.\n\n'
                'ProVisc injected into capsular bag. Alcon SN60WF +21.5 D IOL (LOT 0064792314) loaded and '
                'injected into capsular bag. IOL unfolded and positioned. OVD removed with I&A. '
                'Capsular bag and anterior chamber formed with balanced salt solution. '
                'Main wound self-sealing — no sutures required. Paracentesis hydrated and sealed.\n\n'
                'Subconjunctival injection: Dexamethasone 2 mg + Gentamicin 20 mg given inferiorly. '
                'Tobramycin/Dexamethasone ointment applied. Eye pad and shield applied.'
            ),
            iol_inserted=True,
            iol_type='MONOFOCAL',
            iol_model='Alcon AcrySof IQ SN60WF',
            iol_power=Decimal('21.5'),
            iol_lot='0064792314',
            intraop_complications='None.',
            posterior_capsule_rupture=False,
            vitreous_loss=False,
            expulsive_haemorrhage=False,
            sutures_placed='Main wound self-sealing — no sutures required. Paracentesis hydrated.',
            subconj_injection='Dexamethasone 2 mg + Gentamicin 20 mg subconjunctival inferiorly.',
            eye_pad_shield=True,
            eop_iop=Decimal('16.0'),
            surgeon=surgeon or admin,
            is_finalised=True,
            finalised_at=surgery_dt + datetime.timedelta(minutes=45),
            created_by=surgeon or admin,
        )
        self.stdout.write(self.style.SUCCESS('    OK:Operative Report (finalised)'))

        # ── 14. RECOVERY ROOM ─────────────────────────────────────────────────
        self.stdout.write('  Creating Recovery Room Record...')
        RecoveryRoomRecord.objects.create(
            procedure=procedure,
            arrival_time=surgery_dt + datetime.timedelta(minutes=40),
            discharge_time=surgery_dt + datetime.timedelta(minutes=100),
            recovery_nurse=nurse or admin,
            aldrete_activity=2,
            aldrete_respiration=2,
            aldrete_circulation=2,
            aldrete_consciousness=2,
            aldrete_colour=2,
            bp_systolic=136,
            bp_diastolic=84,
            heart_rate=74,
            spo2=Decimal('98.0'),
            temperature_c=Decimal('36.8'),
            pain_score=2,
            nausea_vomiting=False,
            eye_shield_in_place=True,
            recovery_va='CF 1m OD',
            recovery_iop=Decimal('14.0'),
            anterior_segment_check='Cornea slightly oedematous (expected). AC formed. IOL in situ. No hyphema.',
            eye_drops_given='Tobramycin/Dexamethasone (TobraDex) oint OD applied. Eye shield secured.',
            status=RecoveryDischargeStatus.DISCHARGED,
            discharge_criteria_met=True,
            discharged_by=nurse or admin,
            notes=(
                'Patient fully awake and oriented × 3. Topical anaesthesia fully worn off. '
                'No nausea, no pain beyond mild discomfort (2/10). '
                'Aldrete total 10/10 — safe for discharge. '
                'IOP 14 mmHg post-op (good). Eye shield intact.'
            ),
            created_by=nurse or admin,
        )
        self.stdout.write(self.style.SUCCESS('    OK:Recovery Room (Aldrete 10/10 — discharged)'))

        # ── 15. DISCHARGE CHECKLIST ───────────────────────────────────────────
        self.stdout.write('  Creating Discharge Checklist...')
        dc = DischargeChecklist.objects.create(
            admission=admission,
            completed_by=nurse or admin,
            final_va_od='CF 1m OD (day 0)',
            final_va_os='6/18 cc',
            final_iop_od=Decimal('14.0'),
            final_iop_os=Decimal('15.0'),
            wound_check_ok=True,
            anterior_segment_stable=True,
            no_active_infection=True,
            pain_controlled=True,
            discharge_medications_prescribed=True,
            eye_drop_schedule_given=True,
            systemic_meds_reconciled=True,
            medication_counselling=True,
            followup_1_date=_vdate(0) + datetime.timedelta(days=1),
            followup_2_date=_vdate(0) + datetime.timedelta(days=7),
            followup_3_date=_vdate(0) + datetime.timedelta(days=30),
            followup_appointment_booked=True,
            referral_required=False,
            referral_letter_given=False,
            activity_restrictions_explained=True,
            protective_shield_given=True,
            sun_protection_advised=True,
            emergency_signs_explained=True,
            patient_discharge_summary_given=True,
            final_invoice_settled=True,
            insurance_forms_completed=False,
            patient_transport_arranged=True,
            patient_agrees_to_discharge=True,
            doctor_discharge_order=True,
            notes=(
                'Patient discharged home 5 hours post-phaco. Wife present as escort. '
                'Discharge medications dispensed: TobraDex ointment, Latanoprost, Prednisolone 1% drops. '
                'Written eye drop schedule given. Day 1 appointment confirmed for tomorrow 08:00. '
                'Warned: any sudden pain, severe redness, or vision loss — RETURN IMMEDIATELY.'
            ),
            created_by=nurse or admin,
        )
        self.stdout.write(self.style.SUCCESS('    OK:Discharge Checklist (complete — ready for discharge)'))

        # ── 16. POST-OP DISCHARGE PRESCRIPTION ───────────────────────────────
        self.stdout.write('  Creating post-op discharge prescription...')
        rx_dc = DrugPrescription.objects.create(
            patient=patient, consultation=c5,
            prescribed_by=surgeon or admin,
            prescription_date=_vdate(0),
            notes='Post-operative eye drop regimen following phacoemulsification OD.',
            created_by=surgeon or admin,
        )
        postop_meds = [
            ('Prednisolone acetate 1% eye drops', '1 drop', 'Hourly day1, then taper weekly', 'OD', '4 weeks (taper)', 'Taper as instructed. Do not stop abruptly.'),
            ('Moxifloxacin 0.5% eye drops (Vigamox)', '1 drop', '4× daily', 'OD', '1 week', 'Continue for full 7 days even if eye looks normal.'),
            ('Latanoprost 0.005% eye drops', '1 drop', 'Once daily at bedtime', 'OU', 'Ongoing (POAG)', 'Continue for BOTH eyes. Do not stop.'),
            ('Ketorolac 0.5% eye drops (NSAID)', '1 drop', '4× daily', 'OD', '4 weeks', 'For post-op inflammation and CMO prevention.'),
            ('Paracetamol 1000 mg tablets', '1 tablet', 'Every 6 hours as needed for pain', 'Oral', '3 days', 'Take with food. Max 4 g/day.'),
        ]
        for drug, dose, freq, eye, duration, instr in postop_meds:
            DrugPrescriptionItem.objects.create(
                prescription=rx_dc,
                drug_name=drug, dose=dose, frequency=freq,
                eye=eye, duration=duration, route='Topical' if eye in ('OD','OS','OU') else 'Oral',
                special_instructions=instr, quantity=1,
            )
        self.stdout.write(self.style.SUCCESS('    OK:Post-op prescription (5 medications)'))

        # ── SUMMARY ───────────────────────────────────────────────────────────
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('  DEMO PATIENT SEEDED SUCCESSFULLY'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(f'  Patient ID : {patient.patient_id}')
        self.stdout.write(f'  Name       : {patient.first_name} {patient.last_name}')
        self.stdout.write(f'  DOB        : 15 March 1966 (age 58)')
        self.stdout.write(f'  Booking    : {booking.booking_number}')
        self.stdout.write('')
        self.stdout.write('  Clinical visits created:')
        self.stdout.write('    1. Optometry / Refraction      — compound myopia + presbyopia + elevated IOP')
        self.stdout.write('    2. General Ophthalmology        — C/D 0.7, NS Grade II/III, diabetic retinopathy')
        self.stdout.write('    3. Glaucoma Clinic              — POAG confirmed, VF defect, latanoprost started')
        self.stdout.write('    4. Retina Clinic                — CI-DME OS, anti-VEGF × 3 planned')
        self.stdout.write('    5. Cataract Surgery Consult     — Phaco plan, biometry, IOL calculation')
        self.stdout.write('    6. Pre-Op Counselling G001–G007 — all groups completed + signed')
        self.stdout.write('    7. 8 Pre-Op Investigations      — all cleared by surgeon')
        self.stdout.write('    8. IPD Day Case Admission       — blood group, vitals, nursing')
        self.stdout.write('    9. Theatre (WHO checklist)      — Sign-In + Time-Out + Sign-Out')
        self.stdout.write('   10. Surgical Materials           — IOL lot traced, OVDs, BSS, suture')
        self.stdout.write('   11. Operative Report             — dictated + FINALISED (locked)')
        self.stdout.write('   12. Recovery Room                — Aldrete 10/10, IOP 14 mmHg')
        self.stdout.write('   13. Discharge Checklist          — all 20 items complete')
        self.stdout.write('   14. Post-op Prescription         — 5 medications dispensed')
        self.stdout.write('')
        self.stdout.write(self.style.WARNING(
            f'  Login as admin and search for patient: {patient.first_name} {patient.last_name}'
        ))
        self.stdout.write(self.style.SUCCESS('=' * 60))
