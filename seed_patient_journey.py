"""
EHR Africa — Patient Journey Seed Data
========================================
Seeds service prices and demo patients so you can walk through the
full journey from gate arrival → registration → cashier → triage.

Run with:
    python manage.py shell < seed_patient_journey.py
"""
from decimal import Decimal
from django.utils import timezone

print("=" * 60)
print("EHR AFRICA — Patient Journey Seed Data")
print("=" * 60)

# ── 1. SERVICE PRICE CATALOG ──────────────────────────────────────────────────
print("\n[1/4] Seeding service prices...")
from apps.billing.models import ServicePrice, ServiceCategory

PRICES = [
    # Registration
    dict(name="New Patient Registration",       code="REG-NEW",    category="REG",      price=1000,  nhis_price=500,  insurance_price=800),
    dict(name="Returning Patient Registration", code="REG-RET",    category="REG",      price=500,   nhis_price=200,  insurance_price=400),

    # Consultation
    dict(name="General Eye Consultation",       code="CONS-GEN",   category="CONSULT",  price=3000,  nhis_price=1500, insurance_price=2500),
    dict(name="Specialist Consultation",        code="CONS-SPEC",  category="CONSULT",  price=5000,  nhis_price=2500, insurance_price=4000),
    dict(name="Paediatric Consultation",        code="CONS-PED",   category="CONSULT",  price=3000,  nhis_price=1500, insurance_price=2500),
    dict(name="Follow-up Consultation",         code="CONS-FU",    category="CONSULT",  price=1500,  nhis_price=800,  insurance_price=1200),

    # Investigations / Diagnostics
    dict(name="Visual Acuity Test",             code="INV-VA",     category="INVEST",   price=1000),
    dict(name="Tonometry (IOP Measurement)",    code="INV-IOP",    category="INVEST",   price=1500),
    dict(name="Fundus Photography",             code="INV-FP",     category="INVEST",   price=5000,  nhis_price=3000, insurance_price=4000),
    dict(name="Optical Coherence Tomography (OCT)", code="INV-OCT", category="INVEST",  price=15000, nhis_price=8000, insurance_price=12000),
    dict(name="Visual Field Test",              code="INV-VF",     category="INVEST",   price=8000,  nhis_price=5000, insurance_price=6500),
    dict(name="B-Scan Ultrasound",              code="INV-BSC",    category="INVEST",   price=10000, nhis_price=6000, insurance_price=8000),
    dict(name="Refraction",                     code="INV-REF",    category="INVEST",   price=2000,  nhis_price=1000, insurance_price=1500),
    dict(name="Biometry (IOL Calculation)",     code="INV-BIO",    category="INVEST",   price=10000, nhis_price=6000, insurance_price=8000),

    # Laboratory
    dict(name="Full Blood Count",               code="LAB-FBC",    category="LAB",      price=3000),
    dict(name="Random Blood Sugar",             code="LAB-RBS",    category="LAB",      price=1500),
    dict(name="HIV Screening",                  code="LAB-HIV",    category="LAB",      price=2000),

    # Pharmacy
    dict(name="Antibiotic Eye Drops",           code="PH-ABX",     category="PHARMACY", price=2500,  requires_price_entry=True),
    dict(name="Anti-glaucoma Drops",            code="PH-AGL",     category="PHARMACY", price=5000,  requires_price_entry=True),
    dict(name="Steroid Eye Drops",              code="PH-STR",     category="PHARMACY", price=3000,  requires_price_entry=True),
    dict(name="Lubricating Eye Drops",          code="PH-LUB",     category="PHARMACY", price=2000,  requires_price_entry=True),

    # Optical
    dict(name="Single Vision Glasses",          code="OPT-SV",     category="OPTICAL",  price=15000, requires_price_entry=True),
    dict(name="Bifocal Glasses",                code="OPT-BF",     category="OPTICAL",  price=25000, requires_price_entry=True),
    dict(name="Progressive Glasses",            code="OPT-PRG",    category="OPTICAL",  price=35000, requires_price_entry=True),
    dict(name="Contact Lenses (pair)",          code="OPT-CL",     category="OPTICAL",  price=20000, requires_price_entry=True),

    # Surgical
    dict(name="Cataract Surgery (PHACO) — 1 Eye", code="SUR-CAT",  category="SURGICAL", price=200000, nhis_price=150000, insurance_price=180000),
    dict(name="Glaucoma Surgery (Trabeculectomy)", code="SUR-TRAB", category="SURGICAL", price=250000, nhis_price=200000, insurance_price=220000),
    dict(name="Retinal Laser Treatment",        code="SUR-RLT",    category="SURGICAL", price=50000, nhis_price=35000, insurance_price=45000),
    dict(name="Pterygium Excision",             code="SUR-PTX",    category="SURGICAL", price=80000, nhis_price=60000, insurance_price=70000),
    dict(name="Minor Procedure (lid/lashes)",   code="SUR-MIN",    category="SURGICAL", price=15000),

    # Admission
    dict(name="Inpatient Admission — per day",  code="ADM-DAY",    category="ADMISSION", price=20000),
    dict(name="Theatre Fee",                    code="ADM-THT",    category="ADMISSION", price=30000, nhis_price=20000, insurance_price=25000),

    # Other
    dict(name="Medical Report / Certificate",   code="OTH-RPT",    category="OTHER",    price=5000),
    dict(name="Referral Letter",                code="OTH-REF",    category="OTHER",    price=2000),
]

created_count = 0
for p in PRICES:
    obj, created = ServicePrice.objects.get_or_create(
        code=p['code'],
        defaults={
            'name': p['name'],
            'category': p['category'],
            'price': Decimal(str(p['price'])),
            'nhis_price': Decimal(str(p.get('nhis_price', ''))) if p.get('nhis_price') else None,
            'insurance_price': Decimal(str(p.get('insurance_price', ''))) if p.get('insurance_price') else None,
            'requires_price_entry': p.get('requires_price_entry', False),
            'is_active': True,
        }
    )
    if created:
        created_count += 1

print(f"  ✓ {created_count} new service prices created ({len(PRICES)} total in catalog)")

# ── 2. DEMO PATIENTS ──────────────────────────────────────────────────────────
print("\n[2/4] Seeding demo patients...")
from apps.patients.models import Patient

DEMO_PATIENTS = [
    dict(
        first_name="Jean-Pierre", last_name="MBARGA",
        date_of_birth="1985-03-15", gender="M",
        phone_number="+237677001001", email="",
        address="Bastos, Yaoundé",
        occupation="Teacher",
    ),
    dict(
        first_name="Aïcha", last_name="FOUDA",
        date_of_birth="1972-08-22", gender="F",
        phone_number="+237691002002", email="",
        address="Bonanjo, Douala",
        occupation="Nurse",
    ),
    dict(
        first_name="Emmanuel", last_name="NKOLO",
        date_of_birth="1955-11-05", gender="M",
        phone_number="+237699003003", email="",
        address="Ngousso, Yaoundé",
        occupation="Retired",
    ),
    dict(
        first_name="Marie-Claire", last_name="BIYONG",
        date_of_birth="1990-01-30", gender="F",
        phone_number="+237675004004", email="",
        address="Akwa, Douala",
        occupation="Trader",
    ),
    dict(
        first_name="Christophe", last_name="TAMBA",
        date_of_birth="2010-06-18", gender="M",
        phone_number="+237699005005", email="",  # parent's phone
        address="Mendong, Yaoundé",
        occupation="Student",
    ),
]

patient_created = 0
demo_patients = []
for pd in DEMO_PATIENTS:
    existing = Patient.objects.filter(
        first_name=pd['first_name'], last_name=pd['last_name']
    ).first()
    if not existing:
        p = Patient.objects.create(
            first_name=pd['first_name'],
            last_name=pd['last_name'],
            date_of_birth=pd['date_of_birth'],
            gender=pd['gender'],
            phone_number=pd.get('phone_number', ''),
            address=pd.get('address', ''),
            occupation=pd.get('occupation', ''),
        )
        demo_patients.append(p)
        patient_created += 1
        print(f"  ✓ Created patient: {p.full_name}  (ID: {p.patient_id})")
    else:
        demo_patients.append(existing)
        print(f"  · Exists: {existing.full_name}  (ID: {existing.patient_id})")

# ── 3. CORPORATE ACCOUNTS ─────────────────────────────────────────────────────
print("\n[3/4] Seeding corporate accounts...")
from apps.billing.models import CorporateAccount, CorporateAccountMember

CORPORATE = [
    dict(name="TOTAL Energies Cameroun", code="CORP-TOT", contact_name="DRH Dept", phone="+237222201010", payment_terms_days=30, credit_limit=5000000, discount_pct=10),
    dict(name="CAMTEL",                  code="CORP-CAM", contact_name="HR Manager", phone="+237222202020", payment_terms_days=30, credit_limit=2000000, discount_pct=5),
    dict(name="CNPS (National Social Insurance)", code="NHIS-CNPS", contact_name="Claims Dept", phone="+237222203030", payment_terms_days=60, credit_limit=0, discount_pct=20),
]

for c in CORPORATE:
    acc, created = CorporateAccount.objects.get_or_create(
        account_code=c['code'],
        defaults={
            'name': c['name'],
            'contact_name': c.get('contact_name', ''),
            'phone': c.get('phone', ''),
            'payment_terms_days': c['payment_terms_days'],
            'credit_limit': Decimal(str(c['credit_limit'])),
            'discount_pct': Decimal(str(c['discount_pct'])),
            'is_active': True,
        }
    )
    action = "Created" if created else "Exists "
    print(f"  ✓ {action}: {acc.name}")

# Link demo patients to corporate account
if demo_patients:
    corp = CorporateAccount.objects.filter(account_code="CORP-TOT").first()
    if corp:
        for patient in demo_patients[:2]:
            member, created = CorporateAccountMember.objects.get_or_create(
                corporate_account=corp,
                patient=patient,
                defaults={'employee_id': f'EMP-{patient.patient_id}', 'is_active': True}
            )
            if created:
                print(f"  ✓ Linked {patient.full_name} → {corp.name}")

# ── 4. SUMMARY ────────────────────────────────────────────────────────────────
print("\n[4/4] Summary")
print("-" * 60)
print(f"  Service prices in catalog : {ServicePrice.objects.filter(is_active=True).count()}")
print(f"  Demo patients             : {Patient.objects.count()}")
print(f"  Corporate accounts        : {CorporateAccount.objects.count()}")
print("")
print("  DEMO PATIENT IDs (use these to test the journey):")
for p in demo_patients:
    print("    " + p.patient_id + "  -  " + p.full_name)
print("")
print("=" * 60)
print("DONE — Seed data ready!")
print("=" * 60)
