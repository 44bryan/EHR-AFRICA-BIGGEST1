"""
Split drugs between FT Pharmacy and General Pharmacy based on category.
Run via: manage.py shell < _split_locations.py
"""
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.base')
import django; django.setup()

from apps.pharmacy.models import Drug, PharmacyLocation

ft = PharmacyLocation.objects.filter(name='FT Pharmacy').first()
gen = PharmacyLocation.objects.filter(name='General Pharmacy').first()

if not ft or not gen:
    print('ERROR: Pharmacy locations not found. Run seed_pharmacy_stock.py first.')
    exit()

# Ophthalmic categories go to FT Pharmacy
OPHTHALMIC_CATEGORIES = {'GLAUCOMA', 'MYDRIATIC', 'LUBRICANT', 'ANAESTHETIC'}
# Eye drops and eye ointments go to FT Pharmacy regardless of category
OPHTHALMIC_FORMS = {'EYE_DROP', 'EYE_OINT'}

drugs = Drug.objects.filter(is_deleted=False, is_active=True)
moved = 0
for drug in drugs:
    if drug.category in OPHTHALMIC_CATEGORIES or drug.form in OPHTHALMIC_FORMS:
        if drug.location != ft:
            drug.location = ft
            drug.save(update_fields=['location'])
            moved += 1
    else:
        if drug.location != gen:
            drug.location = gen
            drug.save(update_fields=['location'])

ft_count = Drug.objects.filter(is_deleted=False, location=ft).count()
gen_count = Drug.objects.filter(is_deleted=False, location=gen).count()
print(f'Moved {moved} ophthalmic drugs to FT Pharmacy')
print(f'FT Pharmacy: {ft_count} drugs')
print(f'General Pharmacy: {gen_count} drugs')
