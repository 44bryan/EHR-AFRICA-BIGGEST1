"""
Management command: python manage.py setup_ehr
Runs first-time setup: departments, ICD-10 seed data, superuser.
"""
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = 'First-time EHR setup: creates departments, seeds ICD-10 data, and creates superuser'

    def add_arguments(self, parser):
        parser.add_argument('--skip-superuser', action='store_true', help='Skip superuser creation')

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('\nEHR Africa - First-time Setup\n'))

        # 1. Create departments
        self.stdout.write('Creating departments...')
        from apps.departments.models import create_default_departments
        create_default_departments()
        self.stdout.write(self.style.SUCCESS('  OK Departments created'))

        # 2. Seed common ophthalmic ICD-10 diagnoses
        self.stdout.write('Seeding ICD-10 ophthalmic diagnoses...')
        self._seed_diagnoses()
        self.stdout.write(self.style.SUCCESS('  OK Diagnoses seeded'))

        # 3. Seed investigation types
        self.stdout.write('Seeding investigation types...')
        self._seed_investigation_types()
        self.stdout.write(self.style.SUCCESS('  OK Investigation types seeded'))

        # 4. Seed common lab tests
        self.stdout.write('Seeding lab test types...')
        self._seed_lab_tests()
        self.stdout.write(self.style.SUCCESS('  OK Lab test types seeded'))

        # 5. Seed QMS counters
        self.stdout.write('Seeding QMS service counters...')
        self._seed_qms_counters()
        self.stdout.write(self.style.SUCCESS('  OK QMS counters created'))

        # 6. Seed common ophthalmic drugs
        self.stdout.write('Seeding pharmacy drug formulary...')
        self._seed_drugs()
        self.stdout.write(self.style.SUCCESS('  OK Drug formulary seeded'))

        # 7. Seed HRMS leave types
        self.stdout.write('Seeding leave types...')
        self._seed_leave_types()
        self.stdout.write(self.style.SUCCESS('  OK Leave types seeded'))

        # 8. Seed IPD wards and beds
        self.stdout.write('Seeding IPD wards and beds...')
        self._seed_ipd_wards()
        self.stdout.write(self.style.SUCCESS('  OK IPD wards and beds created'))

        # 9. Create superuser
        if not options['skip_superuser']:
            self.stdout.write('Creating superuser...')
            self._create_superuser()

        self.stdout.write(self.style.SUCCESS('\n Setup complete! Run: python manage.py runserver\n'))

    def _seed_diagnoses(self):
        from apps.consultations.models import Diagnosis
        diagnoses = [
            # Cataract
            ('H26.9', 'Cataract, unspecified', True),
            ('H25.0', 'Age-related nuclear cataract', True),
            ('H25.1', 'Age-related cortical cataract', True),
            ('H26.0', 'Infantile and juvenile cataract', True),
            # Glaucoma
            ('H40.10', 'Open-angle glaucoma, unspecified', True),
            ('H40.20', 'Acute angle-closure glaucoma', True),
            ('H40.11', 'Primary open-angle glaucoma', True),
            ('H40.12', 'Low-tension glaucoma', True),
            ('H40.13', 'Pigmentary glaucoma', True),
            # Retina
            ('H35.30', 'Unspecified macular degeneration', True),
            ('H35.81', 'Retinal edema', True),
            ('E11.3', 'Type 2 diabetes mellitus with ophthalmic complications', False),
            ('H36.0', 'Diabetic retinopathy', True),
            ('H33.0', 'Retinal detachment with retinal break', True),
            ('H34.1', 'Central retinal artery occlusion', True),
            ('H34.81', 'Central retinal vein occlusion', True),
            # Cornea
            ('H16.0', 'Corneal ulcer', True),
            ('H16.10', 'Unspecified superficial keratitis', True),
            ('H18.60', 'Keratoconus, unspecified', True),
            ('H18.40', 'Corneal degeneration, unspecified', True),
            # Refractive
            ('H52.1', 'Myopia', True),
            ('H52.0', 'Hypermetropia', True),
            ('H52.2', 'Astigmatism', True),
            ('H52.4', 'Presbyopia', True),
            # Inflammation
            ('H20.0', 'Acute and subacute iridocyclitis', True),
            ('H20.1', 'Chronic iridocyclitis', True),
            # Paediatric
            ('H50.0', 'Convergent concomitant strabismus (esotropia)', True),
            ('H50.1', 'Divergent concomitant strabismus (exotropia)', True),
            ('H53.0', 'Amblyopia ex anopsia', True),
            # Other
            ('H04.1', 'Chronic dacryocystitis', True),
            ('H02.0', 'Entropion', True),
            ('H02.1', 'Ectropion', True),
            ('H57.1', 'Ocular pain', True),
            ('H57.0', 'Anomalies of pupillary function', True),
        ]
        for code, desc, is_ophthalmic in diagnoses:
            Diagnosis.objects.get_or_create(icd10_code=code, defaults={
                'description': desc,
                'is_ophthalmic': is_ophthalmic,
            })

    def _seed_investigation_types(self):
        from apps.investigations.models import InvestigationType, InvestigationCategory
        types = [
            ('Visual Acuity', 'VA', InvestigationCategory.REFRACTION),
            ('Subjective Refraction', 'REF', InvestigationCategory.REFRACTION),
            ('Auto-Refraction', 'AUTO-REF', InvestigationCategory.REFRACTION),
            ('Applanation Tonometry (Goldmann)', 'GAT', InvestigationCategory.TONOMETRY),
            ('Non-Contact Tonometry', 'NCT', InvestigationCategory.TONOMETRY),
            ('Fundus Photography', 'FP', InvestigationCategory.IMAGING),
            ('Optical Coherence Tomography (OCT)', 'OCT', InvestigationCategory.IMAGING),
            ('Fundus Fluorescein Angiography (FFA)', 'FFA', InvestigationCategory.IMAGING),
            ('B-Scan Ultrasonography', 'BSCAN', InvestigationCategory.IMAGING),
            ('Perimetry / Visual Field (Humphrey)', 'HVF', InvestigationCategory.VISUAL_FIELD),
            ('Biometry / A-Scan (IOL Master)', 'BIOM', InvestigationCategory.BIOMETRY),
            ('Pachymetry (Corneal Thickness)', 'PACH', InvestigationCategory.PACHYMETRY),
            ('Slit Lamp Examination', 'SLE', InvestigationCategory.ANTERIOR_SEGMENT),
            ('Anterior Segment OCT', 'AS-OCT', InvestigationCategory.ANTERIOR_SEGMENT),
            ('Gonioscopy', 'GONIO', InvestigationCategory.ANTERIOR_SEGMENT),
            ('Electroretinography (ERG)', 'ERG', InvestigationCategory.ELECTROPHYSIOLOGY),
            ('Visual Evoked Potential (VEP)', 'VEP', InvestigationCategory.ELECTROPHYSIOLOGY),
            ('Cover Test / Orthoptic Assessment', 'ORTHO', InvestigationCategory.OTHER),
        ]
        for name, code, category in types:
            InvestigationType.objects.get_or_create(code=code, defaults={
                'name': name,
                'category': category,
            })

    def _seed_lab_tests(self):
        from apps.laboratory.models import LabTestType, LabTestCategory
        tests = [
            ('Full Blood Count (FBC)', 'FBC', LabTestCategory.HAEMATOLOGY),
            ('Erythrocyte Sedimentation Rate (ESR)', 'ESR', LabTestCategory.HAEMATOLOGY),
            ('Sickling Test', 'SICK', LabTestCategory.HAEMATOLOGY),
            ('Haemoglobin Electrophoresis', 'HbEP', LabTestCategory.HAEMATOLOGY),
            ('Prothrombin Time (PT)', 'PT', LabTestCategory.HAEMATOLOGY),
            ('Fasting Blood Glucose (FBG)', 'FBG', LabTestCategory.BIOCHEMISTRY),
            ('HbA1c', 'HBA1C', LabTestCategory.BIOCHEMISTRY),
            ('Urea, Electrolytes & Creatinine (U&E)', 'UEC', LabTestCategory.BIOCHEMISTRY),
            ('Liver Function Tests (LFT)', 'LFT', LabTestCategory.BIOCHEMISTRY),
            ('Total Cholesterol / Lipid Profile', 'LIPID', LabTestCategory.BIOCHEMISTRY),
            ('CRP (C-Reactive Protein)', 'CRP', LabTestCategory.BIOCHEMISTRY),
            ('Thyroid Function Tests (TFT)', 'TFT', LabTestCategory.BIOCHEMISTRY),
            ('Toxoplasma IgG/IgM', 'TOXO', LabTestCategory.SEROLOGY),
            ('CMV IgG/IgM', 'CMV', LabTestCategory.SEROLOGY),
            ('HSV IgG/IgM', 'HSV', LabTestCategory.SEROLOGY),
            ('HIV Screening', 'HIV', LabTestCategory.SEROLOGY),
            ('VDRL (Syphilis)', 'VDRL', LabTestCategory.SEROLOGY),
            ('Urinalysis', 'UA', LabTestCategory.URINALYSIS),
            ('Eye Swab M/C/S', 'EYE-MCS', LabTestCategory.MICROBIOLOGY),
            ('Ocular Fluid Culture', 'OCC', LabTestCategory.OCULAR),
        ]
        for name, code, category in tests:
            LabTestType.objects.get_or_create(code=code, defaults={
                'name': name,
                'category': category,
            })

    def _create_superuser(self):
        from apps.accounts.models import User, UserRole
        from apps.departments.models import Department
        import getpass

        print()
        email = input('  Superuser email: ').strip()
        if not email:
            self.stdout.write(self.style.WARNING('  Skipped — no email entered.'))
            return

        if User.objects.filter(email=email).exists():
            self.stdout.write(self.style.WARNING(f'  User {email} already exists. Skipped.'))
            return

        password = getpass.getpass('  Password: ')
        first_name = input('  First name: ').strip()
        last_name = input('  Last name: ').strip()

        user = User.objects.create_superuser(
            email=email,
            username=email,
            password=password,
            first_name=first_name or 'Medical',
            last_name=last_name or 'Director',
            employee_id='MD-001',
            role=UserRole.MEDICAL_DIRECTOR,
            must_change_password=False,
        )
        self.stdout.write(self.style.SUCCESS(f'  OK Superuser created: {user.full_name} ({email})'))

    def _seed_qms_counters(self):
        from apps.qms.models import ServiceCounter, ServiceType
        # (name, code, service_type, serves_tiers)
        # serves_tiers: comma-separated tier codes, '' = all tiers
        counters = [
            # ── Entry / Registration ──────────────────────────────────────────
            # Standard + returning patients → Cashier 1 & 2
            ('Cashier 1 (Standard)',       'CASH-01', ServiceType.CASHIER,    'STANDARD'),
            ('Cashier 2 (Standard)',       'CASH-02', ServiceType.CASHIER,    'STANDARD'),
            # VIP dedicated cashier (also handles VIP new patient registration)
            ('VIP Cashier',               'CASH-VIP', ServiceType.CASHIER,   'VIP'),
            # Express / Fast Track cashier (registration + billing for FT/Express)
            ('Express / FT Cashier',      'CASH-03',  ServiceType.CASHIER,   'FAST_TRACK,EXPRESS'),
            # Optical Shop cashier (all tiers)
            ('Optical Cashier',           'CASH-OPT', ServiceType.CASHIER,   ''),
            # Receptionist desks — standard new patients only (VIP/Express handled at their cashier)
            ('Receptionist 1',            'RECEP-01', ServiceType.RECEPTIONIST, 'STANDARD'),
            ('Receptionist 2',            'RECEP-02', ServiceType.RECEPTIONIST, 'STANDARD'),
            # ── Parameters / Triage ──────────────────────────────────────────
            # Standard patients (main parameters hall)
            ('Parameters Standard',        'PARAM-01', ServiceType.PARAMETERS,     'STANDARD'),
            # VIP / Express / Fast Track dedicated triage room
            ('Parameters VIP / Express',   'PVIP-01',  ServiceType.PARAMETERS_VIP, 'VIP,FAST_TRACK,EXPRESS'),
            # Insurance Consultation Room
            ('Insurance Consultation',     'INS-01',   ServiceType.INSURANCE_CONSULT, 'EXPRESS,FAST_TRACK'),
            # ── Tier-dedicated consultation rooms ────────────────────────────
            # VIP Consultation Room — specialist comes to patient (all specialties)
            ('VIP Consultation Room',      'VIP-CONS', ServiceType.VIP_CONSULT,    'VIP'),
            # Express / Fast Track Consultation — GEN OPH + Uveitis on-site
            ('Express Consultation',       'EXP-CONS', ServiceType.EXPRESS_CONSULT,'FAST_TRACK,EXPRESS'),
            # ── Standard consultation units (all tiers, priority-sorted) ─────
            ('General Ophthalmology',      'GEN-01',   ServiceType.GENERAL,    'STANDARD'),
            ('Retina Clinic',              'RET-01',   ServiceType.RETINA,     ''),
            ('Glaucoma Clinic',            'GLAUC-01', ServiceType.GLAUCOMA,   ''),
            ('Cataract / Surgical',        'CAT-01',   ServiceType.CATARACT,   ''),
            ('Pediatric Ophthalmology',    'PEDS-01',  ServiceType.PEDIATRIC,  ''),
            ('Neuro-ophthalmology',        'NEURO-01', ServiceType.NEURO,      ''),
            ('Oculoplastics',              'OCUP-01',  ServiceType.OCULOPLASTY,''),
            ('Cornea Clinic',              'CORN-01',  ServiceType.CORNEA,     ''),
            ('Uveitis Clinic',             'UVE-01',   ServiceType.UVEITIS,    ''),
            # ── Diagnostics ──────────────────────────────────────────────────
            ('Refraction / Optometry',     'REF-01',   ServiceType.REFRACTION, ''),
            ('Eye Investigations',         'INV-01',   ServiceType.INVESTIGATION,''),
            ('Laboratory',                 'LAB-01',   ServiceType.LABORATORY, ''),
            # ── Dispensing ───────────────────────────────────────────────────
            ('Pharmacy',                   'RX-01',    ServiceType.PHARMACY,   ''),
            ('Optical Shop',               'OPT-01',   ServiceType.OPTICAL,    ''),
            # ── Pre-surgical / Billing ───────────────────────────────────────
            ('Surgical Counseling',        'COUNS-01', ServiceType.COUNSELING, ''),
            ('Billing',                    'BILL-01',  ServiceType.BILLING,    ''),
        ]
        for name, code, service_type, serves_tiers in counters:
            ServiceCounter.objects.update_or_create(code=code, defaults={
                'name': name,
                'service_type': service_type,
                'serves_tiers': serves_tiers,
                'is_active': True,
            })

    def _seed_drugs(self):
        from apps.pharmacy.models import Drug, DrugCategory, DrugForm
        drugs = [
            # Antibiotics
            ('Chloramphenicol Eye Drops', 'Chloramphenicol', 'Minims', DrugCategory.ANTIBIOTIC, DrugForm.EYE_DROP, '0.5%', 1500),
            ('Ciprofloxacin Eye Drops', 'Ciprofloxacin', 'Ciloxan', DrugCategory.ANTIBIOTIC, DrugForm.EYE_DROP, '0.3%', 2000),
            ('Tobramycin Eye Drops', 'Tobramycin', 'Tobrex', DrugCategory.ANTIBIOTIC, DrugForm.EYE_DROP, '0.3%', 2500),
            ('Gentamicin Eye Drops', 'Gentamicin', 'Garamycin', DrugCategory.ANTIBIOTIC, DrugForm.EYE_DROP, '0.3%', 1800),
            # Anti-glaucoma
            ('Timolol Eye Drops', 'Timolol Maleate', 'Timoptol', DrugCategory.GLAUCOMA, DrugForm.EYE_DROP, '0.5%', 3000),
            ('Latanoprost Eye Drops', 'Latanoprost', 'Xalatan', DrugCategory.GLAUCOMA, DrugForm.EYE_DROP, '0.005%', 5500),
            ('Brimonidine Eye Drops', 'Brimonidine Tartrate', 'Alphagan', DrugCategory.GLAUCOMA, DrugForm.EYE_DROP, '0.2%', 4500),
            ('Dorzolamide Eye Drops', 'Dorzolamide', 'Trusopt', DrugCategory.GLAUCOMA, DrugForm.EYE_DROP, '2%', 4000),
            # Steroids
            ('Prednisolone Eye Drops', 'Prednisolone Acetate', 'Pred Forte', DrugCategory.STEROID, DrugForm.EYE_DROP, '1%', 2800),
            ('Dexamethasone Eye Drops', 'Dexamethasone', 'Maxidex', DrugCategory.STEROID, DrugForm.EYE_DROP, '0.1%', 2500),
            # Lubricants
            ('Artificial Tears', 'Hypromellose', 'Tears Naturale', DrugCategory.LUBRICANT, DrugForm.EYE_DROP, '0.3%', 1200),
            ('Carmellose Eye Drops', 'Carmellose Sodium', 'Celluvisc', DrugCategory.LUBRICANT, DrugForm.EYE_DROP, '1%', 2000),
            # Mydriatics
            ('Tropicamide Eye Drops', 'Tropicamide', 'Mydriacyl', DrugCategory.MYDRIATIC, DrugForm.EYE_DROP, '1%', 1500),
            ('Cyclopentolate Eye Drops', 'Cyclopentolate', 'Cyclogyl', DrugCategory.MYDRIATIC, DrugForm.EYE_DROP, '1%', 2200),
            # Antifungals
            ('Natamycin Eye Drops', 'Natamycin', 'Natacyn', DrugCategory.ANTIFUNGAL, DrugForm.EYE_DROP, '5%', 6000),
            # Anaesthetic
            ('Proxymetacaine Eye Drops', 'Proxymetacaine', 'Alcaine', DrugCategory.ANAESTHETIC, DrugForm.EYE_DROP, '0.5%', 2000),
            # Oral
            ('Acetazolamide Tablets', 'Acetazolamide', 'Diamox', DrugCategory.GLAUCOMA, DrugForm.TABLET, '250mg', 150),
            ('Prednisolone Tablets', 'Prednisolone', 'Predsol', DrugCategory.STEROID, DrugForm.TABLET, '5mg', 80),
            ('Ibuprofen Tablets', 'Ibuprofen', 'Brufen', DrugCategory.ANALGESIC, DrugForm.TABLET, '400mg', 50),
            ('Amoxicillin Capsules', 'Amoxicillin', 'Amoxil', DrugCategory.ANTIBIOTIC, DrugForm.CAPSULE, '500mg', 100),
        ]
        for name, generic, brand, category, form, strength, price in drugs:
            code = generic[:3].upper() + form[:2].upper()
            Drug.objects.get_or_create(
                generic_name=generic,
                form=form,
                defaults={
                    'name': name,
                    'brand_name': brand,
                    'category': category,
                    'strength': strength,
                    'selling_price': price,
                    'cost_price': int(price * 0.6),
                    'reorder_level': 20,
                    'unit': 'bottle' if form in ['EYE_DROP', 'EYE_OINT'] else 'pack',
                }
            )

    def _seed_leave_types(self):
        from apps.hrms.models import LeaveType
        leave_types = [
            ('Annual Leave', 21, True),
            ('Sick Leave', 14, True),
            ('Maternity Leave', 90, True),
            ('Paternity Leave', 5, True),
            ('Study Leave', 10, True),
            ('Compassionate Leave', 5, True),
            ('Unpaid Leave', 30, False),
        ]
        for name, days, is_paid in leave_types:
            LeaveType.objects.get_or_create(name=name, defaults={
                'days_allowed_per_year': days,
                'is_paid': is_paid,
            })

    def _seed_ipd_wards(self):
        from apps.ipd.models import Ward, Bed, WardType, BedStatus
        wards = [
            ('General Eye Ward', WardType.GENERAL, 'Ground Floor', 10),
            ('Private Rooms', WardType.PRIVATE, '1st Floor', 4),
            ('Semi-Private Ward', WardType.SEMI_PRIVATE, '1st Floor', 6),
            ('Day Case / Surgical', WardType.DAY_CASE, 'Ground Floor', 8),
        ]
        for ward_name, ward_type, floor, bed_count in wards:
            ward, created = Ward.objects.get_or_create(name=ward_name, defaults={
                'ward_type': ward_type,
                'floor': floor,
                'total_beds': bed_count,
                'is_active': True,
            })
            # Create beds only if newly created ward
            if created:
                prefix = ''.join(w[0] for w in ward_name.split())
                for i in range(1, bed_count + 1):
                    Bed.objects.get_or_create(
                        ward=ward,
                        bed_number=f'{prefix}-{i:02d}',
                        defaults={'status': BedStatus.AVAILABLE},
                    )
