#!/usr/bin/env python
"""Set realistic prices — match by actual DB names."""
import paramiko, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.30.169', username='grudd420', password='123456')

remote_script = r"""
import os, sys, django
os.environ['DJANGO_SETTINGS_MODULE'] = 'ehr_project.settings.base'
sys.path.insert(0, '/opt/ehr-africa')
sys.stdout.reconfigure(encoding='utf-8')
django.setup()

from decimal import Decimal
from apps.investigations.models import InvestigationType
from apps.laboratory.models import LabTestType
from apps.billing.models import ServicePrice, ServiceCategory

# =====================================================================
# INVESTIGATION PRICES — update unit_price on InvestigationType
# Match by substring / keyword for flexibility
# =====================================================================
INVEST_PRICES = {
    'Auto-Refraction': 5000,
    'Subjective Refraction': 10000,
    'Visual Acuity': 3000,
    'Applanation Tonometry': 5000,
    'Goldman Applanation': 5000,
    'Non-Contact Tonometry': 5000,
    'Fundus Photography': 15000,
    'Retinal Angiography': 35000,
    'Ultrasound B-Scan': 15000,
    'Anterior Segment Photo': 10000,
    'Anterior Segment OCT': 20000,
    'OCT Macula': 20000,
    'OCT RNFL': 15000,
    'Visual Field 10-2': 15000,
    'Visual Field 24-2': 15000,
    'A-Scan Biometry': 20000,
    'IOL Master': 25000,
    'Pachymetry': 10000,
    'Corneal Topography': 15000,
    'Keratometry': 10000,
    'Specular Microscopy': 20000,
    'Gonioscopy': 10000,
    'Slit Lamp': 5000,
    'Electroretinography': 25000,
    'Visual Evoked Potential': 25000,
    'Binocular Vision': 10000,
    'Colour Vision': 5000,
    'Hess Chart': 10000,
    'Muscle Balance': 10000,
    'Low Vision Assessment': 15000,
    'Cover Test': 10000,
}

# Catch-all by category for anything not specifically matched
INVEST_CAT_DEFAULT = {
    'OCT': 20000,
    'VISUAL_FIELD': 15000,
    'BIOMETRY': 20000,
    'IMAGING': 15000,
    'TONOMETRY': 5000,
    'REFRACTION': 5000,
    'PACHYMETRY': 10000,
    'TOPOGRAPHY': 15000,
    'SPECULAR': 20000,
    'ANT_SEG': 10000,
    'ELECTROPHYSIOLOGY': 25000,
    'ORTHOPTICS': 10000,
    'LOW_VISION': 15000,
    'OTHER': 10000,
}

updated_inv = 0
for t in InvestigationType.objects.filter(is_deleted=False):
    matched_price = None
    for key, price in INVEST_PRICES.items():
        if key.lower() in t.name.lower():
            matched_price = price
            break
    if matched_price is None:
        matched_price = INVEST_CAT_DEFAULT.get(t.category, 10000)

    new_price = Decimal(matched_price)
    if t.unit_price != new_price:
        old = t.unit_price
        t.unit_price = new_price
        t.save(update_fields=['unit_price'])
        updated_inv += 1
        print(f'  INV: {t.name:<45} {old} -> {new_price:>8,} FCFA')

print(f'\nUpdated {updated_inv} investigation type prices.\n')

# =====================================================================
# Update/create ServicePrice for each investigation type
# =====================================================================
sp_inv_created = 0
sp_inv_updated = 0
for t in InvestigationType.objects.filter(is_deleted=False):
    if t.unit_price and t.unit_price > 0:
        sp, created = ServicePrice.objects.get_or_create(
            name=t.name,
            category=ServiceCategory.INVESTIGATION,
            defaults={'price': t.unit_price, 'code': f'INV-{t.category[:6]}'},
        )
        if created:
            sp_inv_created += 1
        elif sp.price != t.unit_price:
            sp.price = t.unit_price
            sp.save(update_fields=['price'])
            sp_inv_updated += 1
            print(f'  SP~INV: {t.name:<40} -> {t.unit_price:>8,} FCFA')

print(f'ServicePrice INV: {sp_inv_created} created, {sp_inv_updated} updated.\n')


# =====================================================================
# LAB TEST PRICES — match by keyword in actual DB names
# =====================================================================
LAB_PRICE_MAP = {
    # Haematology
    'Full Blood Count': 5000,
    'FBC': 5000,
    'CBC': 5000,
    'Hemoglobin': 3000,
    'Haemoglobin': 3000,
    'Haematocrit': 3000,
    'PCV': 3000,
    'ESR': 3000,
    'Sedimentation Rate': 3000,
    'Blood Group': 3000,
    'Sickling': 3000,
    'Electrophoresis': 10000,
    'Peripheral Blood Film': 5000,
    'Morphology': 5000,
    'Reticulocyte': 5000,
    'MCV': 3000,
    'MCH ': 3000,
    'MCHC': 3000,
    'Platelet': 3000,
    'White Blood Cell': 3000,
    'WBC': 3000,
    'Differential': 3000,
    'Red Blood Cell Count': 3000,
    'RBC': 3000,

    # Coagulation
    'Prothrombin': 5000,
    'PT/INR': 5000,
    'PT ': 5000,
    'APTT': 5000,
    'D-Dimer': 10000,
    'Fibrinogen': 8000,
    'Bleeding Time': 3000,
    'Clotting Time': 3000,
    'Coagulation Screen': 8000,

    # Blood Bank
    'Coombs': 5000,
    'Cross-Match': 5000,

    # Biochemistry
    'Fasting Blood': 3000,
    'FBG': 3000,
    'FBS': 3000,
    'Random Blood': 3000,
    'RBG': 3000,
    'RBS': 3000,
    'HbA1c': 10000,
    'Glucose Tolerance': 8000,
    'BUN': 3000,
    'Urea': 3000,
    'Creatinine': 3000,
    'eGFR': 5000,
    'Uric Acid': 3000,
    'Liver Function': 10000,
    'ALT': 3000,
    'SGPT': 3000,
    'AST': 3000,
    'SGOT': 3000,
    'Alkaline Phosphatase': 3000,
    'ALP': 3000,
    'GGT': 5000,
    'Gamma-Glutamyl': 5000,
    'Total Bilirubin': 3000,
    'Direct Bilirubin': 3000,
    'Direct (Conjugated)': 3000,
    'Conjugated Bilirubin': 3000,
    'Albumin': 3000,
    'Total Protein': 3000,
    'Electrolytes': 8000,
    'Sodium': 5000,
    'Potassium': 5000,
    'Chloride': 5000,
    'Bicarbonate': 5000,
    'Calcium': 5000,
    'Magnesium': 5000,
    'Phosphate': 5000,
    'Iron': 5000,
    'TIBC': 5000,
    'Ferritin': 8000,
    'Lipid Profile': 10000,
    'Cholesterol': 5000,
    'Triglyceride': 3000,
    'HDL': 3000,
    'LDL': 3000,
    'Amylase': 5000,
    'Lipase': 5000,
    'LDH': 5000,
    'Lactate Dehydrogenase': 5000,
    'CRP': 5000,
    'C-Reactive': 5000,
    'Vitamin B12': 10000,
    'Folate': 10000,
    'Folic Acid': 10000,
    'Vitamin D': 15000,
    'Renal Function': 8000,
    'Liver + Renal': 15000,
    'Cardiac Panel': 20000,
    'CK-MB': 10000,
    'Troponin': 10000,
    'PSA': 8000,
    'CA-125': 15000,
    'CEA': 15000,
    'AFP': 15000,

    # Thyroid
    'TSH': 8000,
    'Free T3': 8000,
    'Free T4': 8000,
    'Thyroid Function': 20000,
    'TFT': 20000,
    'Thyroid Panel': 20000,

    # Serology
    'HIV': 3000,
    'HBsAg': 3000,
    'Hepatitis B Surface': 3000,
    'Hepatitis B Panel': 15000,
    'HBeAg': 8000,
    'Hepatitis B e-Antigen': 8000,
    'Hepatitis B Viral Load': 25000,
    'HBV DNA': 25000,
    'Hepatitis C': 5000,
    'HIV Viral Load': 25000,
    'VDRL': 3000,
    'RPR': 3000,
    'Syphilis': 3000,
    'TPHA': 5000,
    'Widal': 3000,
    'ASO': 5000,
    'Anti-Streptolysin': 5000,
    'CMV': 10000,
    'Rubella': 10000,
    'Toxoplasma': 10000,
    'HSV': 10000,
    'Chlamydia': 8000,
    'COVID': 5000,
    'Brucella': 5000,

    # Immunology
    'CD4': 10000,
    'Complement': 10000,
    'IgE': 8000,
    'ANA': 10000,
    'Antinuclear': 10000,
    'Rheumatoid Factor': 5000,
    'Anti-CCP': 10000,
    'Anti-dsDNA': 10000,
    'ANCA': 10000,

    # Urinalysis
    'Urinalysis': 2000,
    'Dipstick': 2000,
    'Urine Microscopy': 3000,
    'Urine Culture': 8000,
    'Urine M': 8000,
    '24-Hour Urine': 8000,
    'Urine Albumin': 8000,
    'ACR': 8000,
    'Pregnancy Test': 3000,
    'Urine Protein': 5000,
    'Urine Glucose': 3000,

    # Parasitology
    'Malaria': 3000,
    'mRDT': 3000,
    'RDT': 3000,
    'Stool': 3000,
    'Occult Blood': 3000,
    'Microfilaria': 5000,
    'Kala-azar': 5000,
    'Trypanosomiasis': 5000,
    'Sleeping Sickness': 5000,
    'Wet Smear': 3000,

    # Microbiology
    'Blood Culture': 10000,
    'Sputum Culture': 8000,
    'Stool Culture': 8000,
    'Wound Swab': 8000,
    'Throat Swab': 8000,
    'GeneXpert': 15000,
    'Gram Stain': 3000,
    'KOH': 3000,
    'AFB': 3000,
    'Ziehl-Neelsen': 3000,
    'Culture & Sensitivity': 8000,
    'C&S': 8000,
    'Eye Swab': 8000,

    # Ocular
    'Conjunctival Swab': 8000,
    'Corneal Scraping': 10000,
    'Lid Swab': 8000,
    'Lacrimal': 8000,
    'Aqueous': 25000,
    'Vitreous': 15000,
    'Ocular Fluid': 15000,

    # Histology
    'Histopathology': 15000,
    'Biopsy': 15000,
    'FNAC': 10000,
    'Fine Needle': 10000,
    'Cytology': 10000,
    'Pap Smear': 5000,
    'Impression Cytology': 10000,
    'Frozen Section': 20000,

    # Febrile
    'Febrile': 5000,
}

sp_lab_created = 0
sp_lab_updated = 0
unmatched = []

for t in LabTestType.objects.filter(is_deleted=False, is_active=True):
    matched_price = None
    # Try longest key first (more specific match)
    for key in sorted(LAB_PRICE_MAP.keys(), key=len, reverse=True):
        if key.lower().strip() in t.name.lower():
            matched_price = LAB_PRICE_MAP[key]
            break

    if matched_price is None:
        matched_price = 5000  # default fallback
        unmatched.append(t.name)

    price = Decimal(matched_price)
    sp, created = ServicePrice.objects.get_or_create(
        name=t.name,
        category=ServiceCategory.LABORATORY,
        defaults={'price': price, 'code': f'LAB-{t.code}'},
    )
    if created:
        sp_lab_created += 1
        print(f'  SP+LAB: {t.name:<50} {price:>8,} FCFA')
    elif sp.price != price:
        old = sp.price
        sp.price = price
        sp.save(update_fields=['price'])
        sp_lab_updated += 1
        print(f'  SP~LAB: {t.name:<50} {old} -> {price:>8,} FCFA')

print(f'\nServicePrice LAB: {sp_lab_created} created, {sp_lab_updated} updated.')
if unmatched:
    print(f'\nUsed default 5,000 FCFA for {len(unmatched)} tests:')
    for n in unmatched:
        print(f'  - {n}')

# Final summary
total_sp = ServicePrice.objects.filter(is_deleted=False).count()
inv_sp = ServicePrice.objects.filter(is_deleted=False, category=ServiceCategory.INVESTIGATION).count()
lab_sp = ServicePrice.objects.filter(is_deleted=False, category=ServiceCategory.LABORATORY).count()
print(f'\nTotal ServicePrice entries: {total_sp} (Investigations: {inv_sp}, Lab: {lab_sp})')
print('DONE.')
"""

sftp = ssh.open_sftp()
with sftp.open('/tmp/_set_prices.py', 'w') as f:
    f.write(remote_script)
sftp.close()

stdin, stdout, stderr = ssh.exec_command('cd /opt/ehr-africa && source venv/bin/activate && python3 /tmp/_set_prices.py')
out = stdout.read().decode('utf-8', errors='replace')
err = stderr.read().decode('utf-8', errors='replace')
print(out)
if err:
    for line in err.splitlines():
        if 'INFO' not in line and 'WARNING' not in line:
            print('ERR:', line)

ssh.close()
