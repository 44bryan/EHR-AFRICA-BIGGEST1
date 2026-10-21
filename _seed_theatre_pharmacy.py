"""Seed Theatre, Ward and Emergency pharmacy locations."""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.base')
django.setup()

from apps.pharmacy.models import PharmacyLocation

locations_to_add = [
    ('Theatre Pharmacy', 'THEATRE', 'Drugs and consumables for operating theatre'),
    ('Ward Pharmacy', 'WARD', 'Ward drug trolley / floor stock'),
    ('Emergency Pharmacy', 'EMERGENCY', 'Emergency drugs — crash cart and acute care'),
]
for name, loc_type, addr in locations_to_add:
    obj, created = PharmacyLocation.objects.get_or_create(
        name=name,
        defaults={'location_type': loc_type, 'address': addr, 'is_active': True}
    )
    status = 'CREATED' if created else 'EXISTS'
    print(f"{status}: {obj.name} ({obj.location_type})")

print("Done.")
