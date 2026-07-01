"""
Seed the Charge Description Master with default ophthalmology hospital services.
Finance Manager can update prices in Django Admin without code changes.
"""
from django.db import migrations


SERVICES = [
    # Registration
    ('New Patient Registration',          'REG',     5000,  None,  None, False, 'REG-NEW'),
    ('Patient Re-registration',           'REG',     2000,  None,  None, False, 'REG-RE'),

    # Consultation
    ('Standard Consultation',             'CONSULT', 15000, 8000,  10000, False, 'CONS-STD'),
    ('Express Consultation',              'CONSULT', 25000, None,  None,  False, 'CONS-EXP'),
    ('Fast Track Consultation',           'CONSULT', 35000, None,  None,  False, 'CONS-FT'),
    ('VIP Consultation',                  'CONSULT', 50000, None,  None,  False, 'CONS-VIP'),
    ('Follow-up Consultation',            'CONSULT',  8000, 4000,  5000,  False, 'CONS-FU'),
    ('Refraction / Optometry',            'CONSULT', 10000, 5000,  6000,  False, 'CONS-REFRAC'),
    ('Contact Lens Fitting',              'CONSULT', 15000, None,  None,  False, 'CONS-CL'),

    # Investigations / Diagnostics
    ('Tonometry (IOP)',                   'INVEST',  3000,  2000,  2500,  False, 'INV-IOP'),
    ('OCT Scan',                          'INVEST', 35000, 20000, 25000, False, 'INV-OCT'),
    ('Visual Field Test',                 'INVEST', 20000, 12000, 15000, False, 'INV-VF'),
    ('Fundus Photography',                'INVEST', 15000, 8000,  10000, False, 'INV-FP'),
    ('Biometry (A-scan)',                 'INVEST', 15000, 10000, 12000, False, 'INV-BIOM'),
    ('B-scan Ultrasound',                 'INVEST', 15000, 10000, 12000, False, 'INV-BSCAN'),
    ('Corneal Topography',                'INVEST', 25000, 15000, 18000, False, 'INV-TOPO'),
    ('Pachymetry',                        'INVEST', 10000, 6000,  8000,  False, 'INV-PACH'),
    ('Fluorescein Angiography (FFA)',     'INVEST', 50000, 30000, 35000, False, 'INV-FFA'),
    ('Electroretinogram (ERG)',           'INVEST', 40000, 25000, 30000, False, 'INV-ERG'),
    ('Slit Lamp Examination',             'INVEST',  5000, 3000,  4000,  False, 'INV-SL'),
    ('Fundoscopy',                        'INVEST',  5000, 3000,  4000,  False, 'INV-FUND'),

    # Laboratory
    ('Blood Sugar (Fasting)',             'LAB',     3000, 2000,  2500,  False, 'LAB-BSF'),
    ('Blood Sugar (Random)',              'LAB',     2500, 1500,  2000,  False, 'LAB-BSR'),
    ('Full Blood Count (FBC)',            'LAB',     8000, 5000,  6000,  False, 'LAB-FBC'),
    ('Sickle Cell Screen',               'LAB',     5000, 3000,  4000,  False, 'LAB-SCS'),
    ('HIV Screen',                        'LAB',     5000, 3000,  4000,  False, 'LAB-HIV'),
    ('HBsAg Test',                        'LAB',     5000, 3000,  4000,  False, 'LAB-HBS'),
    ('Renal Function Test',               'LAB',    10000, 7000,  8000,  False, 'LAB-RFT'),
    ('Liver Function Test',               'LAB',    10000, 7000,  8000,  False, 'LAB-LFT'),
    ('Coagulation Profile (PT/INR)',      'LAB',     8000, 5000,  6000,  False, 'LAB-COAG'),
    ('Urine Analysis',                    'LAB',     3000, 2000,  2500,  False, 'LAB-URINE'),
    ('Culture & Sensitivity',             'LAB',    12000, 8000,  10000, False, 'LAB-CS'),

    # Pharmacy
    ('Drug Dispensing',                   'PHARMACY', 0,   None,  None,  True,  'PHARM-DISP'),

    # Opticals
    ('Spectacle Frame',                   'OPTICAL',  0,   None,  None,  True,  'OPT-FRAME'),
    ('Single Vision Lenses (pair)',       'OPTICAL', 15000, None, None,  False, 'OPT-SV'),
    ('Bifocal Lenses (pair)',             'OPTICAL', 25000, None, None,  False, 'OPT-BF'),
    ('Progressive Lenses (pair)',         'OPTICAL', 45000, None, None,  False, 'OPT-PROG'),
    ('Anti-Reflective Coating',           'OPTICAL',  5000, None, None,  False, 'OPT-ARC'),
    ('UV400 Tint',                        'OPTICAL',  3000, None, None,  False, 'OPT-UV'),
    ('Photochromic Lenses (pair)',        'OPTICAL', 55000, None, None,  False, 'OPT-PHOTO'),
    ('Contact Lenses (pair)',             'OPTICAL',  0,   None,  None,  True,  'OPT-CL'),
    ('Lens Fitting Charge',              'OPTICAL',  3000, None,  None,  False, 'OPT-FIT'),
    ('Spectacle Repair',                 'OPTICAL',  5000, None,  None,  False, 'OPT-REP'),

    # Surgical Procedures
    ('Cataract Surgery (Phaco)',         'SURGICAL', 350000, 200000, 250000, False, 'SUR-CAT-P'),
    ('Cataract Surgery (ECCE)',          'SURGICAL', 250000, 150000, 180000, False, 'SUR-CAT-E'),
    ('Glaucoma Surgery (Trabeculectomy)','SURGICAL', 300000, 180000, 220000, False, 'SUR-GLAUC'),
    ('Pterygium Excision',               'SURGICAL', 150000, 90000, 110000, False, 'SUR-PTER'),
    ('Chalazion Incision & Drainage',    'SURGICAL',  80000, 50000,  60000, False, 'SUR-CHAL'),
    ('Lid Surgery',                      'SURGICAL', 200000, 120000, 150000, False, 'SUR-LID'),
    ('Retinal Laser (per session)',      'SURGICAL', 200000, 120000, 150000, False, 'SUR-RET-LASER'),
    ('Intravitreal Injection',           'SURGICAL', 250000, 150000, 180000, False, 'SUR-IVI'),
    ('Yag Laser Capsulotomy',            'SURGICAL', 100000, 60000,  75000, False, 'SUR-YAG'),
    ('Strabismus Surgery',               'SURGICAL', 250000, 150000, 180000, False, 'SUR-STRAB'),

    # Admission / Ward
    ('Ward Admission (per day)',         'ADMISSION', 15000, 10000, 12000, False, 'ADM-WARD'),
    ('Private Room (per day)',           'ADMISSION', 35000, None,  None,  False, 'ADM-PRIV'),
    ('Nursing Care (per shift)',         'ADMISSION',  5000, 3000,  4000,  False, 'ADM-NURS'),
]


def seed_prices(apps, schema_editor):
    ServicePrice = apps.get_model('billing', 'ServicePrice')
    for row in SERVICES:
        name, category, price, nhis_price, ins_price, requires_entry, code = row
        ServicePrice.objects.get_or_create(
            code=code,
            defaults={
                'name': name,
                'category': category,
                'price': price,
                'nhis_price': nhis_price,
                'insurance_price': ins_price,
                'requires_price_entry': requires_entry,
                'is_active': True,
            }
        )


def unseed_prices(apps, schema_editor):
    ServicePrice = apps.get_model('billing', 'ServicePrice')
    codes = [row[6] for row in SERVICES]
    ServicePrice.objects.filter(code__in=codes).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0002_service_price_refund'),
    ]

    operations = [
        migrations.RunPython(seed_prices, reverse_code=unseed_prices),
    ]
