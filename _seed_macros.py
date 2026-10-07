"""Seed clinical macros for Doctor Ayuk Ndifor and Doctor Fru Arnold."""
import django, os, sys
os.environ['DJANGO_SETTINGS_MODULE'] = 'ehr_project.settings.base'
django.setup()

from apps.accounts.models import User
from apps.consultations.models import ClinicalTemplate

# Find doctors
doctors = []
for u in User.objects.filter(is_active=True):
    nl = u.get_full_name().lower()
    if 'ayuk' in nl or 'ndifor' in nl or 'fru' in nl or 'arnold' in nl or 'armold' in nl:
        doctors.append(u)
        print(f"Found: {u.username} | {u.get_full_name()} | role={u.role} | dept={u.department}")

if not doctors:
    print("ERROR: No matching doctors found!")
    sys.exit(1)

# Sample macros — ophthalmology focused
MACROS = [
    # EXAM templates
    ("Normal Anterior Segment", "EXAM",
     "Lids: Normal, no ptosis, no swelling\nConjunctiva: White and quiet\nCornea: Clear, no staining\nAnterior Chamber: Deep, quiet, no cells/flare\nIris: Normal pattern, no synechiae\nPupils: Round, reactive, no RAPD\nLens: Clear"),
    ("Normal Posterior Segment", "EXAM",
     "Disc: Pink, well-defined margins, CDR 0.3\nMacula: Normal foveal reflex\nVessels: Normal caliber, no AV nipping\nPeriphery: Flat, no breaks, no degeneration"),
    ("Cataract Exam — Nuclear Sclerosis", "EXAM",
     "Lids: Normal\nConjunctiva: White and quiet\nCornea: Clear\nAC: Deep, quiet\nPupils: RAPD negative\nLens: Nuclear sclerosis grade II-III, brunescent\nFundus: View hazy due to cataract, disc and macula appear normal where visible"),
    ("Glaucoma Suspect Exam", "EXAM",
     "Lids: Normal\nConjunctiva: White\nCornea: Clear\nAC: Deep, open angles on Van Herick\nPupils: Round, reactive, RAPD negative\nLens: Early NS\nDisc OD: CDR 0.6, thin rim inferiorly, no notch\nDisc OS: CDR 0.5, healthy rim\nMacula: Normal OU\nPeriphery: Flat OU"),
    ("Diabetic Retinopathy Exam", "EXAM",
     "Disc: Normal OU\nMacula: Few microaneurysms, no CSME\nVessels: Dot-blot hemorrhages scattered, no NVE\nPeriphery: Hard exudates temporal to macula\nGrading: Mild NPDR OU"),
    ("Red Eye — Conjunctivitis", "EXAM",
     "Lids: Mild edema\nConjunctiva: Diffuse injection, papillae present, no follicles\nCornea: Clear, no staining with fluorescein\nAC: Deep, quiet\nPupils: Normal\nLens: Clear\nFundus: Normal"),
    ("Pterygium Exam", "EXAM",
     "Lids: Normal\nConjunctiva: Nasal pterygium extending onto cornea approximately 2mm past limbus\nCornea: Iron line (Stocker line) at head of pterygium\nAC: Deep, quiet\nPupils: Normal\nLens: Clear\nFundus: Normal"),
    ("Post-Cataract Surgery Day 1", "EXAM",
     "Lids: Mild edema, wound site clean\nConjunctiva: Mild injection at incision\nCornea: Clear, Descemet folds minimal\nAC: Deep, trace cells, no hypopyon\nIOL: Well-centered in bag\nPupils: Round\nFundus: Normal where visible"),

    # HISTORY templates
    ("Blurred Vision — Gradual", "HISTORY",
     "Gradual progressive painless decrease in vision over the past months. More pronounced in dim lighting / bright conditions. No flashes, floaters, or field loss. No trauma. No redness or discharge."),
    ("Red Eye — Acute", "HISTORY",
     "Acute onset redness of the eye since this morning. Associated with tearing and mild discomfort. No significant pain, no photophobia, no vision loss. No trauma, no contact lens use. No recent URTI."),
    ("Diabetic Eye Screening", "HISTORY",
     "Known diabetic for years, on oral hypoglycemics / insulin. Last HbA1c: . Referred for annual diabetic eye screening. No visual complaints currently. No previous laser treatment. No history of diabetic eye disease."),
    ("Glaucoma Follow-up", "HISTORY",
     "Known glaucoma patient on topical medications. Compliant with drops. No new visual complaints. No pain or redness. Last visual field done on: . Current medications: Timolol 0.5% BD, Latanoprost 0.005% ON."),
    ("Trauma — Blunt", "HISTORY",
     "Blunt trauma to the eye with fist / ball / object. Immediate pain, tearing, and reduced vision. No penetrating injury. No loss of consciousness. No previous eye problems."),

    # PLAN templates
    ("Cataract Surgery Plan", "PLAN",
     "Plan: Phacoemulsification + IOL implantation\nPre-op: Biometry, blood work (FBC, RBS, PT/INR), anesthesia review\nCounseling: Explained procedure, risks (infection, RD, PCR), benefits, and alternatives\nSchedule for surgical waiting list\nReview with results before booking"),
    ("Glaucoma Medical Management", "PLAN",
     "Start Timolol 0.5% eye drops BD OU\nAdd Latanoprost 0.005% eye drops ON OU\nTarget IOP: below 18 mmHg\nBaseline VF and OCT RNFL ordered\nFollow-up in 4-6 weeks with IOP check\nPatient education: importance of compliance, side effects"),
    ("Diabetic Retinopathy Follow-up Plan", "PLAN",
     "Current grading: Mild NPDR\nNo treatment required at this stage\nOptimize blood sugar control (target HbA1c < 7%)\nBlood pressure control\nAnnual dilated fundus examination\nRefer to physician/endocrinologist for metabolic optimization\nReturn sooner if new visual symptoms"),
    ("Refraction & Glasses Prescription", "PLAN",
     "Refractive error corrected with spectacle lenses\nPrescription issued for distance / near / progressive lenses\nAnti-reflective coating recommended\nFollow-up PRN or in 1 year for routine check\nPatient advised on proper spectacle care"),
    ("Allergic Conjunctivitis Management", "PLAN",
     "Cold compresses QID\nOlopatadine 0.1% eye drops BD x 2 weeks\nAvoid allergen exposure where possible\nArtificial tears PRN for comfort\nReview in 2 weeks if not improved\nAvoid eye rubbing"),

    # DIAGNOSIS templates
    ("POAG Description", "DIAG",
     "Primary Open Angle Glaucoma — characterized by progressive optic neuropathy with open drainage angles, elevated IOP, and corresponding visual field loss. Risk factors include age, family history, and elevated IOP."),
    ("Mature Cataract Description", "DIAG",
     "Mature cataract with significant visual impairment affecting daily activities. Nuclear sclerosis / cortical / posterior subcapsular type. Surgical intervention recommended."),
    ("Allergic Conjunctivitis", "DIAG",
     "Allergic conjunctivitis — bilateral papillary conjunctival reaction with itching, tearing, and seasonal/perennial pattern. No corneal involvement. Mild to moderate severity."),

    # PROCEDURE templates
    ("Phaco + IOL Note", "PROC",
     "Procedure: Phacoemulsification with posterior chamber IOL implantation\nAnesthesia: Topical + intracameral lidocaine\nIncision: 2.4mm clear corneal temporal\nCapsulorhexis: Continuous curvilinear, well-centered\nHydrodissection: Complete\nPhaco: Divide and conquer / stop and chop technique\nIOL: Foldable acrylic, power Diopters, in the bag\nViscoelastic: Removed\nWound: Self-sealing, watertight\nComplications: None\nEBL: Minimal"),
    ("Intravitreal Injection Note", "PROC",
     "Procedure: Intravitreal injection of Anti-VEGF (Bevacizumab / Ranibizumab)\nEye: OD / OS\nAnesthesia: Topical proparacaine + povidone-iodine 5%\nInjection site: 3.5mm from limbus inferotemporal\nDrug: 0.05ml injected into vitreous cavity\nPost-injection: IOP checked — finger tension soft, optic disc perfused\nComplications: None\nPost-op: Topical antibiotic x 3 days, follow-up in 4 weeks"),
]

created = 0
for doctor in doctors:
    for title, ttype, content in MACROS:
        obj, was_created = ClinicalTemplate.objects.get_or_create(
            title=title,
            template_type=ttype,
            created_by=doctor,
            defaults={
                'content': content,
                'is_shared': True,
                'is_active': True,
            }
        )
        if was_created:
            created += 1

print(f"\nSeeded {created} macros for {len(doctors)} doctor(s).")
print("Done.")
