"""
Seed GL sub-accounts and Service Sub-Categories.
Run: python manage.py shell < _seed_subcategories.py
"""
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.base')
django.setup()

from apps.billing.models import GLAccount, ServiceSubCategory

print("=" * 60)
print("SEEDING GL SUB-ACCOUNTS & SERVICE SUB-CATEGORIES")
print("=" * 60)

# ── GL Revenue Sub-Accounts (OHADA Class 7) ──────────────────
gl_accounts = [
    # Consultation sub-accounts
    ('701100', 'Standard Consultation Revenue', 'REVENUE'),
    ('701200', 'Specialist Consultation Revenue', 'REVENUE'),
    ('701300', 'Emergency Consultation Revenue', 'REVENUE'),
    ('701400', 'Pediatric Consultation Revenue', 'REVENUE'),
    # Investigation / Diagnostics sub-accounts
    ('702100', 'Imaging & Radiology Revenue', 'REVENUE'),
    ('702200', 'Visual Field & Perimetry Revenue', 'REVENUE'),
    ('702300', 'OCT & Scanning Revenue', 'REVENUE'),
    # Laboratory sub-accounts
    ('703100', 'Biochemistry Lab Revenue', 'REVENUE'),
    ('703200', 'Hematology Lab Revenue', 'REVENUE'),
    ('703300', 'Microbiology Lab Revenue', 'REVENUE'),
    # Pharmacy sub-accounts
    ('704100', 'Prescription Drugs Revenue', 'REVENUE'),
    ('704200', 'OTC Drugs Revenue', 'REVENUE'),
    ('704300', 'Ophthalmic Preparations Revenue', 'REVENUE'),
    # Surgical sub-accounts
    ('705100', 'Cataract Surgery Revenue', 'REVENUE'),
    ('705200', 'Glaucoma Surgery Revenue', 'REVENUE'),
    ('705300', 'Retinal Surgery Revenue', 'REVENUE'),
    ('705400', 'Oculoplastic Surgery Revenue', 'REVENUE'),
    # Optical sub-accounts
    ('706100', 'Frame Sales Revenue', 'REVENUE'),
    ('706200', 'Lens Sales Revenue', 'REVENUE'),
    ('706300', 'Contact Lens Revenue', 'REVENUE'),
    ('706400', 'Optical Accessories Revenue', 'REVENUE'),
    # IPD / Admission sub-accounts
    ('707100', 'Ward Bed Revenue', 'REVENUE'),
    ('707200', 'VIP Suite Revenue', 'REVENUE'),
    ('707300', 'Day Case Revenue', 'REVENUE'),
    # Registration
    ('708100', 'New Patient Registration Revenue', 'REVENUE'),
    ('708200', 'Medical Records Revenue', 'REVENUE'),
    # Clinical Exam
    ('709100', 'Refraction Revenue', 'REVENUE'),
    ('709200', 'Tonometry Revenue', 'REVENUE'),
    ('709300', 'Fundoscopy Revenue', 'REVENUE'),
]

created_gl = 0
for code, name, acct_type in gl_accounts:
    _, c = GLAccount.objects.get_or_create(
        code=code,
        defaults={'name': name, 'account_type': acct_type, 'is_active': True}
    )
    if c:
        created_gl += 1
        print(f"  GL {code}: {name}")

print(f"\nGL sub-accounts: {created_gl} created, {len(gl_accounts) - created_gl} already existed")


# ── Service Sub-Categories ───────────────────────────────────
sub_cats = [
    # (category, name, code, gl_code)
    ('CONSULT', 'Standard Consultation', 'STD', '701100'),
    ('CONSULT', 'Specialist Consultation', 'SPEC', '701200'),
    ('CONSULT', 'Emergency Consultation', 'EMRG', '701300'),
    ('CONSULT', 'Pediatric Consultation', 'PED', '701400'),
    ('INVEST', 'Imaging & Radiology', 'IMG', '702100'),
    ('INVEST', 'Visual Field & Perimetry', 'VF', '702200'),
    ('INVEST', 'OCT & Scanning', 'OCT', '702300'),
    ('CLINICAL', 'Refraction', 'REF', '709100'),
    ('CLINICAL', 'Tonometry', 'TONO', '709200'),
    ('CLINICAL', 'Fundoscopy', 'FUND', '709300'),
    ('LAB', 'Biochemistry', 'BIOC', '703100'),
    ('LAB', 'Hematology', 'HEMA', '703200'),
    ('LAB', 'Microbiology', 'MICR', '703300'),
    ('PHARMACY', 'Prescription Drugs', 'RX', '704100'),
    ('PHARMACY', 'OTC Drugs', 'OTC', '704200'),
    ('PHARMACY', 'Ophthalmic Preparations', 'OPH', '704300'),
    ('SURGICAL', 'Cataract Surgery', 'CAT', '705100'),
    ('SURGICAL', 'Glaucoma Surgery', 'GLAU', '705200'),
    ('SURGICAL', 'Retinal Surgery', 'RET', '705300'),
    ('SURGICAL', 'Oculoplastic Surgery', 'OCUL', '705400'),
    ('OPTICAL', 'Frames', 'FRM', '706100'),
    ('OPTICAL', 'Lenses', 'LNS', '706200'),
    ('OPTICAL', 'Contact Lenses', 'CLN', '706300'),
    ('OPTICAL', 'Accessories', 'ACC', '706400'),
    ('ADMISSION', 'Ward Bed', 'WARD', '707100'),
    ('ADMISSION', 'VIP Suite', 'VIPS', '707200'),
    ('ADMISSION', 'Day Case', 'DAY', '707300'),
    ('REG', 'New Patient Registration', 'NREG', '708100'),
    ('REG', 'Medical Records', 'MREC', '708200'),
]

created_sc = 0
for cat, name, code, gl_code in sub_cats:
    gl_acct = GLAccount.objects.filter(code=gl_code).first()
    _, c = ServiceSubCategory.objects.update_or_create(
        category=cat, name=name,
        defaults={'code': code, 'gl_account': gl_acct}
    )
    if c:
        created_sc += 1
        print(f"  SubCat [{cat}] {name} -> {gl_code}")

print(f"\nSub-categories: {created_sc} created, {len(sub_cats) - created_sc} updated")
print("\nDone!")
