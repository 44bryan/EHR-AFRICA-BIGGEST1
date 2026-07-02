"""
Seed common ophthalmic drugs into the pharmacy formulary.
Run: python manage.py shell < seed_pharmacy_drugs.py
"""
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.production')
django.setup()

from apps.pharmacy.models import Drug

DRUGS = [
    # ── ANTIBIOTICS (Eye Drops) ───────────────────────────────────────────
    dict(name='Tobramycin Eye Drops', generic_name='Tobramycin', brand_name='Tobrex', category='ANTIBIOTIC', form='EYE_DROP', strength='0.3%', unit='bottle', cost_price=2500, selling_price=3500, reorder_level=10),
    dict(name='Ciprofloxacin Eye Drops', generic_name='Ciprofloxacin', brand_name='Ciloxan', category='ANTIBIOTIC', form='EYE_DROP', strength='0.3%', unit='bottle', cost_price=2000, selling_price=3000, reorder_level=10),
    dict(name='Ofloxacin Eye Drops', generic_name='Ofloxacin', brand_name='Exocin', category='ANTIBIOTIC', form='EYE_DROP', strength='0.3%', unit='bottle', cost_price=2200, selling_price=3200, reorder_level=10),
    dict(name='Moxifloxacin Eye Drops', generic_name='Moxifloxacin', brand_name='Vigamox', category='ANTIBIOTIC', form='EYE_DROP', strength='0.5%', unit='bottle', cost_price=4500, selling_price=6500, reorder_level=8),
    dict(name='Levofloxacin Eye Drops', generic_name='Levofloxacin', brand_name='Oftaquix', category='ANTIBIOTIC', form='EYE_DROP', strength='0.5%', unit='bottle', cost_price=3500, selling_price=5000, reorder_level=8),
    dict(name='Gentamicin Eye Drops', generic_name='Gentamicin', brand_name='Genoptic', category='ANTIBIOTIC', form='EYE_DROP', strength='0.3%', unit='bottle', cost_price=1500, selling_price=2500, reorder_level=10),
    dict(name='Chloramphenicol Eye Drops', generic_name='Chloramphenicol', brand_name='Chlorsig', category='ANTIBIOTIC', form='EYE_DROP', strength='0.5%', unit='bottle', cost_price=1200, selling_price=2000, reorder_level=10),
    dict(name='Azithromycin Eye Drops', generic_name='Azithromycin', brand_name='Azyter', category='ANTIBIOTIC', form='EYE_DROP', strength='1.5%', unit='bottle', cost_price=5000, selling_price=7000, reorder_level=6),

    # ── ANTIBIOTICS (Eye Ointments) ───────────────────────────────────────
    dict(name='Chloramphenicol Eye Ointment', generic_name='Chloramphenicol', brand_name='Chloromycetin', category='ANTIBIOTIC', form='EYE_OINT', strength='1%', unit='tube', cost_price=1500, selling_price=2500, reorder_level=8),
    dict(name='Tetracycline Eye Ointment', generic_name='Tetracycline', brand_name='Achromycin', category='ANTIBIOTIC', form='EYE_OINT', strength='1%', unit='tube', cost_price=1200, selling_price=2000, reorder_level=8),
    dict(name='Erythromycin Eye Ointment', generic_name='Erythromycin', brand_name='Ilosone', category='ANTIBIOTIC', form='EYE_OINT', strength='0.5%', unit='tube', cost_price=1800, selling_price=2800, reorder_level=8),
    dict(name='Tobramycin Eye Ointment', generic_name='Tobramycin', brand_name='Tobrex', category='ANTIBIOTIC', form='EYE_OINT', strength='0.3%', unit='tube', cost_price=3000, selling_price=4500, reorder_level=6),

    # ── CORTICOSTEROIDS ───────────────────────────────────────────────────
    dict(name='Prednisolone Eye Drops', generic_name='Prednisolone Acetate', brand_name='Pred Forte', category='STEROID', form='EYE_DROP', strength='1%', unit='bottle', cost_price=3500, selling_price=5000, reorder_level=8),
    dict(name='Dexamethasone Eye Drops', generic_name='Dexamethasone', brand_name='Maxidex', category='STEROID', form='EYE_DROP', strength='0.1%', unit='bottle', cost_price=2800, selling_price=4000, reorder_level=8),
    dict(name='Fluorometholone Eye Drops', generic_name='Fluorometholone', brand_name='FML', category='STEROID', form='EYE_DROP', strength='0.1%', unit='bottle', cost_price=4000, selling_price=5800, reorder_level=6),
    dict(name='Loteprednol Eye Drops', generic_name='Loteprednol Etabonate', brand_name='Lotemax', category='STEROID', form='EYE_DROP', strength='0.5%', unit='bottle', cost_price=6000, selling_price=8500, reorder_level=5),
    dict(name='Betamethasone Eye Drops', generic_name='Betamethasone', brand_name='Betnesol', category='STEROID', form='EYE_DROP', strength='0.1%', unit='bottle', cost_price=2500, selling_price=3800, reorder_level=8),
    dict(name='Dexamethasone Eye Ointment', generic_name='Dexamethasone', brand_name='Maxitrol', category='STEROID', form='EYE_OINT', strength='0.1%', unit='tube', cost_price=3000, selling_price=4500, reorder_level=6),

    # ── ANTIBIOTIC + STEROID COMBINATIONS ────────────────────────────────
    dict(name='Tobramycin + Dexamethasone Eye Drops', generic_name='Tobramycin + Dexamethasone', brand_name='TobraDex', category='ANTIBIOTIC', form='EYE_DROP', strength='0.3%/0.1%', unit='bottle', cost_price=5000, selling_price=7500, reorder_level=8),
    dict(name='Tobramycin + Dexamethasone Eye Ointment', generic_name='Tobramycin + Dexamethasone', brand_name='TobraDex', category='ANTIBIOTIC', form='EYE_OINT', strength='0.3%/0.1%', unit='tube', cost_price=5500, selling_price=8000, reorder_level=6),
    dict(name='Ciprofloxacin + Dexamethasone Eye Drops', generic_name='Ciprofloxacin + Dexamethasone', brand_name='Ciprodex', category='ANTIBIOTIC', form='EYE_DROP', strength='0.3%/0.1%', unit='bottle', cost_price=4500, selling_price=6500, reorder_level=6),
    dict(name='Neomycin + Dexamethasone Eye Drops', generic_name='Neomycin + Dexamethasone', brand_name='Maxitrol', category='ANTIBIOTIC', form='EYE_DROP', strength='3500IU/0.1%', unit='bottle', cost_price=3500, selling_price=5000, reorder_level=6),

    # ── ANTI-GLAUCOMA (Beta-blockers) ─────────────────────────────────────
    dict(name='Timolol Eye Drops', generic_name='Timolol Maleate', brand_name='Timoptic', category='GLAUCOMA', form='EYE_DROP', strength='0.5%', unit='bottle', cost_price=2500, selling_price=4000, reorder_level=10),
    dict(name='Timolol Eye Drops 0.25%', generic_name='Timolol Maleate', brand_name='Timoptic', category='GLAUCOMA', form='EYE_DROP', strength='0.25%', unit='bottle', cost_price=2000, selling_price=3200, reorder_level=8),
    dict(name='Betaxolol Eye Drops', generic_name='Betaxolol', brand_name='Betoptic', category='GLAUCOMA', form='EYE_DROP', strength='0.5%', unit='bottle', cost_price=3500, selling_price=5000, reorder_level=6),

    # ── ANTI-GLAUCOMA (Prostaglandins) ────────────────────────────────────
    dict(name='Latanoprost Eye Drops', generic_name='Latanoprost', brand_name='Xalatan', category='GLAUCOMA', form='EYE_DROP', strength='0.005%', unit='bottle', cost_price=8000, selling_price=12000, reorder_level=6),
    dict(name='Bimatoprost Eye Drops', generic_name='Bimatoprost', brand_name='Lumigan', category='GLAUCOMA', form='EYE_DROP', strength='0.03%', unit='bottle', cost_price=8500, selling_price=13000, reorder_level=6),
    dict(name='Travoprost Eye Drops', generic_name='Travoprost', brand_name='Travatan', category='GLAUCOMA', form='EYE_DROP', strength='0.004%', unit='bottle', cost_price=8000, selling_price=12000, reorder_level=6),
    dict(name='Tafluprost Eye Drops', generic_name='Tafluprost', brand_name='Saflutan', category='GLAUCOMA', form='EYE_DROP', strength='0.0015%', unit='bottle', cost_price=9000, selling_price=14000, reorder_level=4),

    # ── ANTI-GLAUCOMA (Alpha agonists) ────────────────────────────────────
    dict(name='Brimonidine Eye Drops', generic_name='Brimonidine Tartrate', brand_name='Alphagan', category='GLAUCOMA', form='EYE_DROP', strength='0.2%', unit='bottle', cost_price=5000, selling_price=7500, reorder_level=8),
    dict(name='Brimonidine Eye Drops 0.15%', generic_name='Brimonidine Tartrate', brand_name='Alphagan P', category='GLAUCOMA', form='EYE_DROP', strength='0.15%', unit='bottle', cost_price=5500, selling_price=8000, reorder_level=6),
    dict(name='Apraclonidine Eye Drops', generic_name='Apraclonidine', brand_name='Iopidine', category='GLAUCOMA', form='EYE_DROP', strength='0.5%', unit='bottle', cost_price=6000, selling_price=9000, reorder_level=4),

    # ── ANTI-GLAUCOMA (Carbonic Anhydrase Inhibitors) ────────────────────
    dict(name='Dorzolamide Eye Drops', generic_name='Dorzolamide', brand_name='Trusopt', category='GLAUCOMA', form='EYE_DROP', strength='2%', unit='bottle', cost_price=5000, selling_price=7500, reorder_level=8),
    dict(name='Brinzolamide Eye Drops', generic_name='Brinzolamide', brand_name='Azopt', category='GLAUCOMA', form='EYE_DROP', strength='1%', unit='bottle', cost_price=5500, selling_price=8000, reorder_level=6),
    dict(name='Dorzolamide + Timolol Eye Drops', generic_name='Dorzolamide + Timolol', brand_name='Cosopt', category='GLAUCOMA', form='EYE_DROP', strength='2%/0.5%', unit='bottle', cost_price=7000, selling_price=10000, reorder_level=6),
    dict(name='Brimonidine + Timolol Eye Drops', generic_name='Brimonidine + Timolol', brand_name='Combigan', category='GLAUCOMA', form='EYE_DROP', strength='0.2%/0.5%', unit='bottle', cost_price=7500, selling_price=11000, reorder_level=5),
    dict(name='Acetazolamide Tablet', generic_name='Acetazolamide', brand_name='Diamox', category='GLAUCOMA', form='TABLET', strength='250mg', unit='tablet', cost_price=200, selling_price=350, reorder_level=50),

    # ── MYDRIATICS / CYCLOPLEGICS ─────────────────────────────────────────
    dict(name='Tropicamide Eye Drops 1%', generic_name='Tropicamide', brand_name='Mydriacyl', category='MYDRIATIC', form='EYE_DROP', strength='1%', unit='bottle', cost_price=2500, selling_price=4000, reorder_level=10),
    dict(name='Tropicamide Eye Drops 0.5%', generic_name='Tropicamide', brand_name='Mydriacyl', category='MYDRIATIC', form='EYE_DROP', strength='0.5%', unit='bottle', cost_price=2000, selling_price=3200, reorder_level=10),
    dict(name='Cyclopentolate Eye Drops', generic_name='Cyclopentolate', brand_name='Cyclogyl', category='MYDRIATIC', form='EYE_DROP', strength='1%', unit='bottle', cost_price=3000, selling_price=4500, reorder_level=8),
    dict(name='Atropine Eye Drops', generic_name='Atropine Sulfate', brand_name='Isopto Atropine', category='MYDRIATIC', form='EYE_DROP', strength='1%', unit='bottle', cost_price=1500, selling_price=2500, reorder_level=8),
    dict(name='Atropine Eye Ointment', generic_name='Atropine Sulfate', brand_name='Isopto Atropine', category='MYDRIATIC', form='EYE_OINT', strength='1%', unit='tube', cost_price=2000, selling_price=3200, reorder_level=6),
    dict(name='Phenylephrine Eye Drops 2.5%', generic_name='Phenylephrine', brand_name='Minims', category='MYDRIATIC', form='EYE_DROP', strength='2.5%', unit='bottle', cost_price=2500, selling_price=4000, reorder_level=8),
    dict(name='Phenylephrine Eye Drops 10%', generic_name='Phenylephrine', brand_name='Minims', category='MYDRIATIC', form='EYE_DROP', strength='10%', unit='bottle', cost_price=3000, selling_price=4500, reorder_level=6),
    dict(name='Homatropine Eye Drops', generic_name='Homatropine', brand_name='Isopto Homatropine', category='MYDRIATIC', form='EYE_DROP', strength='2%', unit='bottle', cost_price=2200, selling_price=3500, reorder_level=6),

    # ── LUBRICANTS / ARTIFICIAL TEARS ─────────────────────────────────────
    dict(name='Carmellose Eye Drops', generic_name='Carmellose Sodium', brand_name='Celluvisc', category='LUBRICANT', form='EYE_DROP', strength='0.5%', unit='bottle', cost_price=1500, selling_price=2500, reorder_level=15),
    dict(name='Hyaluronic Acid Eye Drops', generic_name='Sodium Hyaluronate', brand_name='Hylabak', category='LUBRICANT', form='EYE_DROP', strength='0.2%', unit='bottle', cost_price=4000, selling_price=6000, reorder_level=10),
    dict(name='Polyvinyl Alcohol Eye Drops', generic_name='Polyvinyl Alcohol', brand_name='Liquifilm', category='LUBRICANT', form='EYE_DROP', strength='1.4%', unit='bottle', cost_price=1800, selling_price=3000, reorder_level=10),
    dict(name='Hydroxypropyl Methylcellulose', generic_name='Hydroxypropyl Methylcellulose', brand_name='Isopto Tears', category='LUBRICANT', form='EYE_DROP', strength='0.3%', unit='bottle', cost_price=1500, selling_price=2500, reorder_level=10),
    dict(name='Sodium Hyaluronate Eye Drops', generic_name='Sodium Hyaluronate', brand_name='Vismed', category='LUBRICANT', form='EYE_DROP', strength='0.1%', unit='bottle', cost_price=3500, selling_price=5500, reorder_level=10),
    dict(name='Carbomer Eye Gel', generic_name='Carbomer', brand_name='Viscotears', category='LUBRICANT', form='OTHER', strength='0.2%', unit='tube', cost_price=2500, selling_price=4000, reorder_level=8),
    dict(name='Simple Eye Ointment', generic_name='Paraffin', brand_name='Lacrilube', category='LUBRICANT', form='EYE_OINT', strength='', unit='tube', cost_price=1500, selling_price=2500, reorder_level=8),

    # ── ANTIVIRALS ────────────────────────────────────────────────────────
    dict(name='Acyclovir Eye Ointment', generic_name='Acyclovir', brand_name='Zovirax', category='ANTIVIRAL', form='EYE_OINT', strength='3%', unit='tube', cost_price=3500, selling_price=5500, reorder_level=6),
    dict(name='Ganciclovir Eye Drops', generic_name='Ganciclovir', brand_name='Virgan', category='ANTIVIRAL', form='EYE_DROP', strength='0.15%', unit='tube', cost_price=8000, selling_price=12000, reorder_level=4),
    dict(name='Acyclovir Tablet', generic_name='Acyclovir', brand_name='Zovirax', category='ANTIVIRAL', form='TABLET', strength='400mg', unit='tablet', cost_price=150, selling_price=250, reorder_level=50),
    dict(name='Valacyclovir Tablet', generic_name='Valacyclovir', brand_name='Valtrex', category='ANTIVIRAL', form='TABLET', strength='500mg', unit='tablet', cost_price=500, selling_price=800, reorder_level=30),

    # ── ANTIFUNGALS ───────────────────────────────────────────────────────
    dict(name='Natamycin Eye Drops', generic_name='Natamycin', brand_name='Natacyn', category='ANTIFUNGAL', form='EYE_DROP', strength='5%', unit='bottle', cost_price=10000, selling_price=15000, reorder_level=4),
    dict(name='Voriconazole Eye Drops', generic_name='Voriconazole', brand_name='Vfend', category='ANTIFUNGAL', form='EYE_DROP', strength='1%', unit='bottle', cost_price=12000, selling_price=18000, reorder_level=3),
    dict(name='Fluconazole Tablet', generic_name='Fluconazole', brand_name='Diflucan', category='ANTIFUNGAL', form='TABLET', strength='150mg', unit='tablet', cost_price=500, selling_price=800, reorder_level=20),

    # ── NSAIDs ────────────────────────────────────────────────────────────
    dict(name='Diclofenac Eye Drops', generic_name='Diclofenac Sodium', brand_name='Voltaren', category='NSAID', form='EYE_DROP', strength='0.1%', unit='bottle', cost_price=2500, selling_price=4000, reorder_level=8),
    dict(name='Ketorolac Eye Drops', generic_name='Ketorolac Tromethamine', brand_name='Acular', category='NSAID', form='EYE_DROP', strength='0.5%', unit='bottle', cost_price=3500, selling_price=5500, reorder_level=6),
    dict(name='Nepafenac Eye Drops', generic_name='Nepafenac', brand_name='Nevanac', category='NSAID', form='EYE_DROP', strength='0.1%', unit='bottle', cost_price=5000, selling_price=7500, reorder_level=5),
    dict(name='Bromfenac Eye Drops', generic_name='Bromfenac', brand_name='Yellox', category='NSAID', form='EYE_DROP', strength='0.09%', unit='bottle', cost_price=4500, selling_price=7000, reorder_level=5),

    # ── ANTI-ALLERGY ──────────────────────────────────────────────────────
    dict(name='Olopatadine Eye Drops', generic_name='Olopatadine', brand_name='Pataday', category='OTHER', form='EYE_DROP', strength='0.1%', unit='bottle', cost_price=4000, selling_price=6000, reorder_level=8),
    dict(name='Ketotifen Eye Drops', generic_name='Ketotifen Fumarate', brand_name='Zaditen', category='OTHER', form='EYE_DROP', strength='0.025%', unit='bottle', cost_price=3000, selling_price=4500, reorder_level=8),
    dict(name='Sodium Cromoglycate Eye Drops', generic_name='Sodium Cromoglycate', brand_name='Opticrom', category='OTHER', form='EYE_DROP', strength='2%', unit='bottle', cost_price=2500, selling_price=4000, reorder_level=8),
    dict(name='Levocabastine Eye Drops', generic_name='Levocabastine', brand_name='Livostin', category='OTHER', form='EYE_DROP', strength='0.05%', unit='bottle', cost_price=3500, selling_price=5500, reorder_level=6),
    dict(name='Azelastine Eye Drops', generic_name='Azelastine', brand_name='Optilast', category='OTHER', form='EYE_DROP', strength='0.05%', unit='bottle', cost_price=3500, selling_price=5500, reorder_level=6),
    dict(name='Emedastine Eye Drops', generic_name='Emedastine', brand_name='Emadine', category='OTHER', form='EYE_DROP', strength='0.05%', unit='bottle', cost_price=4000, selling_price=6000, reorder_level=5),

    # ── LOCAL ANAESTHETICS ────────────────────────────────────────────────
    dict(name='Proxymetacaine Eye Drops', generic_name='Proxymetacaine', brand_name='Alcaine', category='ANAESTHETIC', form='EYE_DROP', strength='0.5%', unit='bottle', cost_price=3000, selling_price=5000, reorder_level=8),
    dict(name='Tetracaine Eye Drops', generic_name='Tetracaine', brand_name='Minims', category='ANAESTHETIC', form='EYE_DROP', strength='0.5%', unit='bottle', cost_price=2500, selling_price=4000, reorder_level=8),
    dict(name='Oxybuprocaine Eye Drops', generic_name='Oxybuprocaine', brand_name='Benoxinate', category='ANAESTHETIC', form='EYE_DROP', strength='0.4%', unit='bottle', cost_price=2500, selling_price=4000, reorder_level=8),
    dict(name='Lidocaine Injection', generic_name='Lidocaine', brand_name='Xylocaine', category='ANAESTHETIC', form='INJECTION', strength='2%', unit='vial', cost_price=1500, selling_price=2500, reorder_level=10),

    # ── ORAL ANALGESICS ───────────────────────────────────────────────────
    dict(name='Paracetamol Tablet', generic_name='Paracetamol', brand_name='Panadol', category='ANALGESIC', form='TABLET', strength='500mg', unit='tablet', cost_price=30, selling_price=50, reorder_level=100),
    dict(name='Ibuprofen Tablet', generic_name='Ibuprofen', brand_name='Brufen', category='ANALGESIC', form='TABLET', strength='400mg', unit='tablet', cost_price=80, selling_price=150, reorder_level=50),
    dict(name='Tramadol Capsule', generic_name='Tramadol', brand_name='Tramal', category='ANALGESIC', form='CAPSULE', strength='50mg', unit='capsule', cost_price=200, selling_price=350, reorder_level=30),

    # ── ORAL STEROIDS ─────────────────────────────────────────────────────
    dict(name='Prednisolone Tablet', generic_name='Prednisolone', brand_name='Deltacortril', category='STEROID', form='TABLET', strength='5mg', unit='tablet', cost_price=100, selling_price=180, reorder_level=50),
    dict(name='Prednisolone Tablet 25mg', generic_name='Prednisolone', brand_name='Deltacortril', category='STEROID', form='TABLET', strength='25mg', unit='tablet', cost_price=200, selling_price=350, reorder_level=30),
    dict(name='Dexamethasone Injection', generic_name='Dexamethasone', brand_name='Decadron', category='STEROID', form='INJECTION', strength='4mg/ml', unit='vial', cost_price=1000, selling_price=1800, reorder_level=10),

    # ── ORAL ANTIBIOTICS ─────────────────────────────────────────────────
    dict(name='Doxycycline Capsule', generic_name='Doxycycline', brand_name='Vibramycin', category='ANTIBIOTIC', form='CAPSULE', strength='100mg', unit='capsule', cost_price=150, selling_price=250, reorder_level=30),
    dict(name='Azithromycin Tablet', generic_name='Azithromycin', brand_name='Zithromax', category='ANTIBIOTIC', form='TABLET', strength='500mg', unit='tablet', cost_price=300, selling_price=500, reorder_level=30),
    dict(name='Ciprofloxacin Tablet', generic_name='Ciprofloxacin', brand_name='Ciprobay', category='ANTIBIOTIC', form='TABLET', strength='500mg', unit='tablet', cost_price=150, selling_price=250, reorder_level=30),
    dict(name='Amoxicillin Capsule', generic_name='Amoxicillin', brand_name='Amoxil', category='ANTIBIOTIC', form='CAPSULE', strength='500mg', unit='capsule', cost_price=100, selling_price=180, reorder_level=50),

    # ── UVEITIS / IMMUNOSUPPRESSANTS ─────────────────────────────────────
    dict(name='Hydroxychloroquine Tablet', generic_name='Hydroxychloroquine', brand_name='Plaquenil', category='OTHER', form='TABLET', strength='200mg', unit='tablet', cost_price=500, selling_price=800, reorder_level=20),
    dict(name='Methotrexate Tablet', generic_name='Methotrexate', brand_name='Methofar', category='OTHER', form='TABLET', strength='2.5mg', unit='tablet', cost_price=300, selling_price=500, reorder_level=20),
    dict(name='Mycophenolate Tablet', generic_name='Mycophenolate Mofetil', brand_name='CellCept', category='OTHER', form='TABLET', strength='500mg', unit='tablet', cost_price=1500, selling_price=2500, reorder_level=10),

    # ── INTRAVITREAL / INJECTIONS ─────────────────────────────────────────
    dict(name='Bevacizumab Injection', generic_name='Bevacizumab', brand_name='Avastin', category='OTHER', form='INJECTION', strength='25mg/ml', unit='vial', cost_price=25000, selling_price=40000, reorder_level=2),
    dict(name='Ranibizumab Injection', generic_name='Ranibizumab', brand_name='Lucentis', category='OTHER', form='INJECTION', strength='10mg/ml', unit='vial', cost_price=80000, selling_price=120000, reorder_level=2),
    dict(name='Triamcinolone Acetonide Injection', generic_name='Triamcinolone Acetonide', brand_name='Kenalog', category='STEROID', form='INJECTION', strength='40mg/ml', unit='vial', cost_price=8000, selling_price=12000, reorder_level=4),
    dict(name='Aflibercept Injection', generic_name='Aflibercept', brand_name='Eylea', category='OTHER', form='INJECTION', strength='40mg/ml', unit='vial', cost_price=100000, selling_price=150000, reorder_level=2),

    # ── VITAMINS / SUPPLEMENTS ────────────────────────────────────────────
    dict(name='Lutein + Zeaxanthin Capsule', generic_name='Lutein + Zeaxanthin', brand_name='Macushield', category='VITAMIN', form='CAPSULE', strength='10mg/2mg', unit='capsule', cost_price=500, selling_price=800, reorder_level=20),
    dict(name='Vitamin A Capsule', generic_name='Retinol', brand_name='Vit A', category='VITAMIN', form='CAPSULE', strength='50000IU', unit='capsule', cost_price=200, selling_price=350, reorder_level=20),
    dict(name='Omega-3 Capsule', generic_name='Omega-3 Fatty Acids', brand_name='Oculeve', category='VITAMIN', form='CAPSULE', strength='1000mg', unit='capsule', cost_price=300, selling_price=500, reorder_level=20),

    # ── DIAGNOSTIC / STAINING DROPS ──────────────────────────────────────
    dict(name='Fluorescein Eye Drops', generic_name='Fluorescein Sodium', brand_name='Fluorets', category='OTHER', form='EYE_DROP', strength='2%', unit='bottle', cost_price=1500, selling_price=2500, reorder_level=6),
    dict(name='Rose Bengal Eye Drops', generic_name='Rose Bengal', brand_name='Minims', category='OTHER', form='EYE_DROP', strength='1%', unit='bottle', cost_price=2000, selling_price=3500, reorder_level=4),
    dict(name='Lissamine Green Eye Drops', generic_name='Lissamine Green', brand_name='Lissamine', category='OTHER', form='EYE_DROP', strength='1%', unit='bottle', cost_price=2500, selling_price=4000, reorder_level=4),
]


created = 0
skipped = 0
for d in DRUGS:
    obj, new = Drug.objects.get_or_create(
        name=d['name'],
        defaults={
            'generic_name': d['generic_name'],
            'brand_name':   d.get('brand_name', ''),
            'category':     d['category'],
            'form':         d['form'],
            'strength':     d.get('strength', ''),
            'unit':         d.get('unit', 'unit'),
            'cost_price':   d.get('cost_price', 0),
            'selling_price':d.get('selling_price', 0),
            'reorder_level':d.get('reorder_level', 10),
            'is_active':    True,
            'requires_prescription': True,
        }
    )
    if new:
        created += 1
    else:
        skipped += 1

print(f"Done — {created} drugs created, {skipped} already existed.")
