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

        # 10. Print backup reminder
        self.stdout.write(self.style.SUCCESS('\n Setup complete!\n'))
        self.stdout.write('  Schedule daily backups:')
        self.stdout.write('    python manage.py backup_db --keep 30')
        self.stdout.write('  Or add to crontab (runs at 02:00 every night):')
        self.stdout.write('    0 2 * * * cd /opt/ehr-africa && venv/bin/python manage.py backup_db --keep 30\n')

    def _seed_diagnoses(self):
        from apps.consultations.models import Diagnosis
        diagnoses = [
            # ── CATARACT ──────────────────────────────────────────────────────
            ('H25.0', 'Age-related nuclear cataract', True),
            ('H25.1', 'Age-related cortical cataract', True),
            ('H25.2', 'Age-related anterior subcapsular polar cataract', True),
            ('H25.8', 'Other age-related cataract', True),
            ('H25.9', 'Age-related cataract, unspecified', True),
            ('H26.0', 'Infantile and juvenile cataract', True),
            ('H26.1', 'Traumatic cataract', True),
            ('H26.2', 'Complicated cataract (secondary to ocular disease)', True),
            ('H26.3', 'Drug-induced cataract', True),
            ('H26.9', 'Cataract, unspecified', True),
            ('H27.0', 'Aphakia', True),
            ('H27.1', 'Dislocation of lens (subluxation / luxation)', True),
            # ── GLAUCOMA ──────────────────────────────────────────────────────
            ('H40.00', 'Glaucoma suspect, unspecified', True),
            ('H40.10', 'Open-angle glaucoma, unspecified', True),
            ('H40.11', 'Primary open-angle glaucoma (POAG)', True),
            ('H40.12', 'Low-tension (normal-tension) glaucoma', True),
            ('H40.13', 'Pigmentary glaucoma', True),
            ('H40.14', 'Capsular glaucoma (pseudoexfoliation)', True),
            ('H40.20', 'Acute angle-closure glaucoma', True),
            ('H40.21', 'Chronic angle-closure glaucoma', True),
            ('H40.22', 'Intermittent angle-closure glaucoma', True),
            ('H40.30', 'Glaucoma secondary to eye trauma', True),
            ('H40.40', 'Glaucoma secondary to eye inflammation', True),
            ('H40.50', 'Glaucoma secondary to other eye disorders', True),
            ('H40.6', 'Glaucoma secondary to drugs', True),
            ('H42', 'Glaucoma in diseases classified elsewhere', True),
            # ── RETINA ────────────────────────────────────────────────────────
            ('H33.0', 'Retinal detachment with retinal break', True),
            ('H33.1', 'Retinoschisis and retinal cysts', True),
            ('H33.2', 'Serous retinal detachment', True),
            ('H33.4', 'Traction retinal detachment', True),
            ('H34.0', 'Transient retinal artery occlusion (TRAO)', True),
            ('H34.1', 'Central retinal artery occlusion (CRAO)', True),
            ('H34.23', 'Branch retinal artery occlusion (BRAO)', True),
            ('H34.81', 'Central retinal vein occlusion (CRVO)', True),
            ('H34.82', 'Branch retinal vein occlusion (BRVO)', True),
            ('H35.00', 'Hypertensive retinopathy', True),
            ('H35.10', 'Retinopathy of prematurity (ROP)', True),
            ('H35.20', 'Other non-diabetic proliferative retinopathy', True),
            ('H35.30', 'Age-related macular degeneration (AMD), unspecified', True),
            ('H35.31', 'Non-exudative (dry) AMD', True),
            ('H35.32', 'Exudative (wet) AMD', True),
            ('H35.33', 'Angioid streaks of macula', True),
            ('H35.35', 'Cystoid macular edema', True),
            ('H35.4', 'Peripheral retinal degeneration (lattice)', True),
            ('H35.50', 'Hereditary retinal dystrophy, unspecified', True),
            ('H35.51', 'Retinitis pigmentosa', True),
            ('H35.52', 'Cone-rod dystrophy', True),
            ('H35.6', 'Retinal haemorrhage', True),
            ('H36.0', 'Diabetic retinopathy (in Type 2 diabetes)', True),
            ('H36.01', 'Non-proliferative diabetic retinopathy (NPDR)', True),
            ('H36.02', 'Proliferative diabetic retinopathy (PDR)', True),
            ('H36.03', 'Diabetic macular edema (DME)', True),
            # ── CORNEA ────────────────────────────────────────────────────────
            ('H16.0', 'Corneal ulcer', True),
            ('H16.01', 'Central corneal ulcer', True),
            ('H16.02', 'Ring corneal ulcer', True),
            ('H16.03', 'Corneal ulcer with hypopyon', True),
            ('H16.10', 'Superficial keratitis, unspecified', True),
            ('H16.11', 'Macular keratitis', True),
            ('H16.13', 'Filamentary keratitis', True),
            ('H16.14', 'Punctate keratitis', True),
            ('H16.20', 'Keratoconjunctivitis, unspecified', True),
            ('H16.21', 'Exposure keratoconjunctivitis', True),
            ('H16.22', 'Keratoconjunctivitis sicca (dry eye)', True),
            ('H16.30', 'Interstitial keratitis, unspecified', True),
            ('H17.0', 'Adherent leukoma', True),
            ('H17.8', 'Corneal scar and opacity', True),
            ('H18.00', 'Corneal oedema, unspecified', True),
            ('H18.01', 'Corneal oedema due to contact lens', True),
            ('H18.02', 'Bullous keratopathy', True),
            ('H18.10', 'Fuchs endothelial dystrophy', True),
            ('H18.30', 'Changes in corneal membranes', True),
            ('H18.40', 'Corneal degeneration, unspecified', True),
            ('H18.41', 'Arcus senilis', True),
            ('H18.42', 'Band-shaped keratopathy', True),
            ('H18.50', 'Hereditary corneal dystrophy, unspecified', True),
            ('H18.60', 'Keratoconus, unspecified', True),
            ('H18.61', 'Keratoconus, stable', True),
            ('H18.62', 'Keratoconus, unstable', True),
            ('H18.70', 'Corneal ectasia', True),
            ('H18.71', 'Corneal staphyloma', True),
            ('H19.3', 'Keratitis in herpes simplex (HSV keratitis)', True),
            # ── CONJUNCTIVA ───────────────────────────────────────────────────
            ('H10.0', 'Acute mucopurulent conjunctivitis', True),
            ('H10.01', 'Bacterial conjunctivitis', True),
            ('H10.02', 'Viral conjunctivitis', True),
            ('H10.03', 'Chlamydial conjunctivitis (trachoma)', True),
            ('H10.1', 'Acute atopic conjunctivitis', True),
            ('H10.10', 'Allergic conjunctivitis, unspecified', True),
            ('H10.40', 'Chronic conjunctivitis, unspecified', True),
            ('H10.41', 'Vernal keratoconjunctivitis (VKC)', True),
            ('H10.42', 'Atopic keratoconjunctivitis (AKC)', True),
            ('H11.0', 'Pterygium', True),
            ('H11.01', 'Stationary pterygium', True),
            ('H11.02', 'Progressive pterygium', True),
            ('H11.30', 'Conjunctival haemorrhage (subconjunctival)', True),
            ('H11.40', 'Conjunctival degeneration', True),
            ('H11.41', 'Pinguecula', True),
            # ── REFRACTIVE ERRORS ─────────────────────────────────────────────
            ('H52.0', 'Hypermetropia (hyperopia / far-sightedness)', True),
            ('H52.1', 'Myopia (near-sightedness)', True),
            ('H52.11', 'High myopia (>6D)', True),
            ('H52.2', 'Astigmatism', True),
            ('H52.20', 'Regular astigmatism', True),
            ('H52.21', 'Irregular astigmatism', True),
            ('H52.3', 'Anisometropia', True),
            ('H52.4', 'Presbyopia', True),
            ('H53.0', 'Amblyopia ex anopsia', True),
            ('H53.01', 'Deprivation amblyopia', True),
            ('H53.02', 'Refractive amblyopia', True),
            ('H53.03', 'Strabismic amblyopia', True),
            # ── UVEITIS / INFLAMMATION ────────────────────────────────────────
            ('H20.0', 'Acute and subacute iridocyclitis (anterior uveitis)', True),
            ('H20.00', 'Acute anterior uveitis, unspecified', True),
            ('H20.01', 'Acute iritis', True),
            ('H20.02', 'Acute cyclitis', True),
            ('H20.03', 'Acute anterior uveitis — primary', True),
            ('H20.1', 'Chronic iridocyclitis (chronic anterior uveitis)', True),
            ('H20.9', 'Unspecified iridocyclitis', True),
            ('H30.0', 'Focal chorioretinal inflammation (toxoplasmosis)', True),
            ('H30.1', 'Disseminated chorioretinal inflammation', True),
            ('H30.2', 'Posterior cyclitis (pars planitis)', True),
            ('H30.8', 'Other chorioretinal inflammations (VKH / Birdshot)', True),
            ('H30.9', 'Unspecified chorioretinal inflammation', True),
            ('H44.1', 'Endophthalmitis', True),
            ('H44.11', 'Panophthalmitis', True),
            ('H44.12', 'Parasitic endophthalmitis', True),
            ('H44.13', 'Sympathetic uveitis', True),
            # ── OCULOPLASTICS / ORBIT / LIDS ──────────────────────────────────
            ('H00.0', 'Hordeolum (stye)', True),
            ('H00.1', 'Chalazion', True),
            ('H01.0', 'Blepharitis', True),
            ('H01.00', 'Unspecified blepharitis', True),
            ('H01.01', 'Ulcerative blepharitis', True),
            ('H02.0', 'Entropion and trichiasis of eyelid', True),
            ('H02.1', 'Ectropion of eyelid', True),
            ('H02.2', 'Lagophthalmos', True),
            ('H02.3', 'Blepharochalasis', True),
            ('H02.4', 'Ptosis (blepharoptosis)', True),
            ('H02.41', 'Mechanical ptosis', True),
            ('H02.42', 'Myogenic ptosis', True),
            ('H02.43', 'Paralytic ptosis', True),
            ('H02.5', 'Other disorders affecting eyelid function', True),
            ('H02.7', 'Eyelid neoplasm (benign)', True),
            ('H04.0', 'Dacryoadenitis', True),
            ('H04.1', 'Chronic dacryocystitis', True),
            ('H04.11', 'Acute dacryocystitis', True),
            ('H04.12', 'Chronic dacryocystitis', True),
            ('H04.20', 'Epiphora (watering eye)', True),
            ('H04.30', 'Nasolacrimal duct obstruction', True),
            ('H05.0', 'Acute inflammation of orbit (orbital cellulitis)', True),
            ('H05.1', 'Chronic inflammatory disorders of orbit', True),
            ('H05.2', 'Exophthalmos (proptosis)', True),
            ('H05.20', 'Proptosis, unspecified', True),
            ('H05.21', 'Displacement of globe', True),
            # ── STRABISMUS / PEDIATRIC ────────────────────────────────────────
            ('H49.0', 'Third nerve (oculomotor) palsy', True),
            ('H49.1', 'Fourth nerve (trochlear) palsy', True),
            ('H49.2', 'Sixth nerve (abducent) palsy', True),
            ('H49.3', 'Complete (external) ophthalmoplegia', True),
            ('H49.4', 'Progressive external ophthalmoplegia', True),
            ('H50.0', 'Convergent concomitant strabismus (esotropia)', True),
            ('H50.1', 'Divergent concomitant strabismus (exotropia)', True),
            ('H50.2', 'Vertical strabismus', True),
            ('H50.3', 'Intermittent heterotropia', True),
            ('H50.4', 'Other and unspecified heterotropia', True),
            ('H50.5', 'Heterophoria (esophoria/exophoria)', True),
            # ── NEURO-OPHTHALMOLOGY ───────────────────────────────────────────
            ('H46.0', 'Optic papillitis', True),
            ('H46.1', 'Retrobulbar neuritis (optic neuritis)', True),
            ('H46.2', 'Nutritional optic neuropathy', True),
            ('H46.3', 'Toxic optic neuropathy', True),
            ('H47.0', 'Disorders of optic nerve', True),
            ('H47.01', 'Ischaemic optic neuropathy (AION)', True),
            ('H47.1', 'Papilloedema', True),
            ('H47.2', 'Optic atrophy', True),
            ('H47.3', 'Other disorders of optic disc (optic disc drusen)', True),
            ('H47.4', 'Disorders of optic chiasm', True),
            ('H47.5', 'Disorders of visual pathways', True),
            ('H53.1', 'Subjective visual disturbances', True),
            ('H53.2', 'Diplopia (double vision)', True),
            ('H53.4', 'Visual field defects', True),
            ('H54.0', 'Blindness — both eyes', True),
            ('H54.1', 'Blindness — one eye, low vision other', True),
            ('H54.2', 'Low vision — both eyes', True),
            ('H54.3', 'Unqualified visual loss — both eyes', True),
            ('H54.4', 'Blindness — one eye', True),
            # ── SYSTEMIC / NON-OPHTHALMIC ─────────────────────────────────────
            ('E11.3', 'Type 2 diabetes mellitus with ophthalmic complications', False),
            ('E10.3', 'Type 1 diabetes mellitus with ophthalmic complications', False),
            ('I10', 'Essential (primary) hypertension', False),
            ('B02.3', 'Zoster ocular disease (Herpes zoster ophthalmicus)', False),
            ('A30.9', 'Leprosy (ocular involvement)', False),
            ('A71.9', 'Trachoma, unspecified', True),
            ('B44.8', 'Aspergillosis (ocular)', False),
            # ── TRAUMA ────────────────────────────────────────────────────────
            ('S05.0', 'Injury of conjunctiva and corneal abrasion', True),
            ('S05.1', 'Contusion of eyeball and orbital tissues', True),
            ('S05.2', 'Ocular laceration and rupture', True),
            ('S05.3', 'Ocular laceration without prolapse', True),
            ('S05.4', 'Penetrating wound of orbit without foreign body', True),
            ('S05.5', 'Penetrating wound with foreign body in orbit', True),
            ('S05.6', 'Penetrating wound of eyeball with foreign body', True),
            ('T26.0', 'Burn of eyelid and periocular area', True),
            ('T26.1', 'Burn of cornea and conjunctival sac', True),
            # ── OTHER ─────────────────────────────────────────────────────────
            ('H57.0', 'Anomalies of pupillary function', True),
            ('H57.1', 'Ocular pain', True),
            ('H57.8', 'Other specified disorders of eye and adnexa', True),
            ('H57.9', 'Disorder of eye and adnexa, unspecified', True),
            ('H44.0', 'Purulent endophthalmitis', True),
            ('H44.2', 'Degenerative myopia (pathologic myopia)', True),
            ('H44.3', 'Other degenerative disorders of globe (phthisis bulbi)', True),
            ('H44.4', 'Hypotony of eye', True),
            ('H44.5', 'Degenerated conditions of globe', True),
            ('H44.6', 'Retained intraocular foreign body, magnetic', True),
            ('H44.7', 'Retained intraocular foreign body, nonmagnetic', True),
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
            # ── HAEMATOLOGY ──────────────────────────────────────────────
            ('CBC Complète (Hémogramme)', 'LAB-04', LabTestCategory.HAEMATOLOGY),
            ('Groupe Sanguin + RH', 'LAB-57', LabTestCategory.HAEMATOLOGY),
            ('Hémoglobine Electrophorèse', 'LAB-55', LabTestCategory.HAEMATOLOGY),
            ('Temps de Saignement (TS)', 'LAB-08', LabTestCategory.HAEMATOLOGY),
            ('Taux de Prothrombine (TP/PT)', 'LAB-06', LabTestCategory.HAEMATOLOGY),
            ('Temps de Céphaline Activée (TCA/PTT)', 'LAB-07', LabTestCategory.HAEMATOLOGY),
            ('Vitesse de Sédimentation (VS/ESR)', 'LAB-50', LabTestCategory.HAEMATOLOGY),
            # ── PARASITOLOGY ─────────────────────────────────────────────
            ('Skin Snip (Onchocercose)', 'LAB-26', LabTestCategory.PARASITOLOGY),
            ('Frottis Sanguin — Paludisme', 'LAB-25', LabTestCategory.PARASITOLOGY),
            ('Examen Parasitologique des Selles', 'LAB-37', LabTestCategory.PARASITOLOGY),
            # ── MICROBIOLOGY ─────────────────────────────────────────────
            ('Culture + Antibiogramme (Prélèvement Oculaire)', 'LAB-02', LabTestCategory.MICROBIOLOGY),
            ('Culture des Selles', 'LAB-60', LabTestCategory.MICROBIOLOGY),
            ('Culture des Urines (ECBU)', 'LAB-61', LabTestCategory.MICROBIOLOGY),
            ('Eye Swab M/C/S', 'EYE-MCS', LabTestCategory.MICROBIOLOGY),
            # ── URINALYSIS ───────────────────────────────────────────────
            ('Examen Cytobactériologique des Urines (ECBU)', 'LAB-24', LabTestCategory.URINALYSIS),
            # ── FEBRILE PROFILE ──────────────────────────────────────────
            ('Sérodiagnostic de Widal', 'LAB-05', LabTestCategory.FEBRILE),
            ('Hépatite C (HCV Ab)', 'LAB-15', LabTestCategory.FEBRILE),
            # ── BIOCHEMISTRY ─────────────────────────────────────────────
            ('Glycémie à Jeun (Fasting)', 'LAB-01', LabTestCategory.BIOCHEMISTRY),
            ('Glycémie Post-Prandiale (2h)', 'LAB-39', LabTestCategory.BIOCHEMISTRY),
            ('Glycémie Aléatoire (Random)', 'LAB-33', LabTestCategory.BIOCHEMISTRY),
            ('Test de Tolérance au Glucose (OGTT)', 'LAB-34', LabTestCategory.BIOCHEMISTRY),
            ('Hémoglobine Glyquée (HbA1c)', 'LAB-19', LabTestCategory.BIOCHEMISTRY),
            ('Bilirubine Totale', 'LAB-41', LabTestCategory.BIOCHEMISTRY),
            ('Bilirubine Directe', 'LAB-42', LabTestCategory.BIOCHEMISTRY),
            ('ALAT (SGPT)', 'LAB-14', LabTestCategory.BIOCHEMISTRY),
            ('ASAT (SGOT)', 'LAB-17', LabTestCategory.BIOCHEMISTRY),
            ('Gamma GT (GGT)', 'LAB-35', LabTestCategory.BIOCHEMISTRY),
            ('Protéines Totales', 'LAB-56', LabTestCategory.BIOCHEMISTRY),
            # ── LIPID PROFILE ────────────────────────────────────────────
            ('Cholestérol Total', 'LAB-10', LabTestCategory.LIPID),
            ('HDL Cholestérol', 'LAB-11', LabTestCategory.LIPID),
            ('Triglycérides', 'LAB-12', LabTestCategory.LIPID),
            ('LDL Cholestérol', 'LAB-13', LabTestCategory.LIPID),
            ('Lipides Totaux', 'LAB-40', LabTestCategory.LIPID),
            # ── RENAL PROFILE ────────────────────────────────────────────
            ('Urée Sanguine', 'LAB-31', LabTestCategory.RENAL),
            ('Créatinine Sérique', 'LAB-09', LabTestCategory.RENAL),
            ('Acide Urique', 'LAB-18', LabTestCategory.RENAL),
            # ── ELECTROLYTES ─────────────────────────────────────────────
            ('Sodium (Na+)', 'LAB-20', LabTestCategory.ELECTROLYTES),
            ('Potassium (K+)', 'LAB-21', LabTestCategory.ELECTROLYTES),
            ('Chlore (Cl-)', 'LAB-22', LabTestCategory.ELECTROLYTES),
            ('Calcium (Ca2+)', 'LAB-23', LabTestCategory.ELECTROLYTES),
            # ── THYROID ──────────────────────────────────────────────────
            ('T3 (Triiodothyronine)', 'LAB-52', LabTestCategory.THYROID),
            ('T4 (Thyroxine)', 'LAB-53', LabTestCategory.THYROID),
            ('TSH (Thyroid Stimulating Hormone)', 'LAB-54', LabTestCategory.THYROID),
            # ── SEROLOGY ─────────────────────────────────────────────────
            ('Chlamydia Antigène (AG)', 'LAB-43', LabTestCategory.SEROLOGY),
            ('Chlamydia Anticorps (AB)', 'LAB-44', LabTestCategory.SEROLOGY),
            ('HSV Antigène (AG)', 'LAB-45', LabTestCategory.SEROLOGY),
            ('HSV Anticorps (ABS)', 'LAB-46', LabTestCategory.SEROLOGY),
            ('Antigène de Surface Hépatite B (HBsAg)', 'LAB-16', LabTestCategory.SEROLOGY),
            ('HIV Anticorps (HIV ABS)', 'LAB-29', LabTestCategory.SEROLOGY),
            ('VDRL (Syphilis)', 'LAB-36', LabTestCategory.SEROLOGY),
            ('TPHA (Syphilis Confirmatoire)', 'LAB-28', LabTestCategory.SEROLOGY),
            ('Toxoplasma IgG', 'LAB-30', LabTestCategory.SEROLOGY),
            ('CRP (C-Reactive Protein)', 'LAB-27', LabTestCategory.SEROLOGY),
            ('H. Pylori Antigène', 'LAB-59', LabTestCategory.SEROLOGY),
            ('ASLO (Antistreptolysine O)', 'LAB-47', LabTestCategory.SEROLOGY),
            # ── RHEUMATOID PROFILE ───────────────────────────────────────
            ('Facteur Rhumatoïde (RF)', 'LAB-48', LabTestCategory.RHEUMATOID),
            # ── OCULAR SPECIMENS ─────────────────────────────────────────
            ('Ocular Fluid Culture', 'OCC', LabTestCategory.OCULAR),
            ('Corneal Scraping M/C/S', 'CORN-MCS', LabTestCategory.OCULAR),
            ('Vitreous Tap Culture', 'VIT-CX', LabTestCategory.OCULAR),
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
