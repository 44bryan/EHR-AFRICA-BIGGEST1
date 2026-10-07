"""
Seed realistic Cameroon pharmaceutical suppliers.
Run via: manage.py shell < _seed_suppliers.py
"""
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.base')
import django; django.setup()

from apps.pharmacy.models import Supplier

SUPPLIERS = [
    {
        'name': 'CAPHARM (Centrale d\'Achat des Pharmacies)',
        'contact_person': 'Dr. Mbarga Pierre',
        'phone': '+237 222 20 50 60',
        'email': 'commandes@capharm.cm',
        'address': 'Douala, Rue de la Joie, Bonanjo',
        'registration_number': 'MINSANTE/DPM/2024-001',
    },
    {
        'name': 'LABOREX Cameroun',
        'contact_person': 'Mme. Nkwenti Grace',
        'phone': '+237 233 42 31 00',
        'email': 'orders@laborex.cm',
        'address': 'Douala, Zone Industrielle de Bonaberi',
        'registration_number': 'MINSANTE/DPM/2024-002',
    },
    {
        'name': 'CINPHARM (Cameroon International Pharmaceutical)',
        'contact_person': 'M. Fotso Emmanuel',
        'phone': '+237 233 39 22 10',
        'email': 'sales@cinpharm.cm',
        'address': 'Douala, Zone Industrielle de Bassa',
        'registration_number': 'MINSANTE/DPM/2024-003',
    },
    {
        'name': 'Alcon Laboratories (Eye Care)',
        'contact_person': 'Regional Rep - West Africa',
        'phone': '+237 699 88 77 66',
        'email': 'westafrica@alcon.com',
        'address': 'Douala Distribution Center',
        'registration_number': 'MINSANTE/DPM/2024-004',
    },
    {
        'name': 'Novartis Pharma Cameroun',
        'contact_person': 'Dr. Atanga Robert',
        'phone': '+237 699 55 44 33',
        'email': 'cameroon.orders@novartis.com',
        'address': 'Yaounde, Quartier Bastos',
        'registration_number': 'MINSANTE/DPM/2024-005',
    },
    {
        'name': 'Sanofi Cameroun',
        'contact_person': 'Mme. Nguemo Flore',
        'phone': '+237 222 23 01 50',
        'email': 'cameroun@sanofi.com',
        'address': 'Douala, Avenue Charles de Gaulle',
        'registration_number': 'MINSANTE/DPM/2024-006',
    },
    {
        'name': 'SOPHARMA Cameroun',
        'contact_person': 'M. Tchatchoua Jean',
        'phone': '+237 233 43 12 00',
        'email': 'commandes@sopharma.cm',
        'address': 'Douala, Deido',
        'registration_number': 'MINSANTE/DPM/2024-007',
    },
    {
        'name': 'UBIPHARM Cameroun',
        'contact_person': 'Dr. Kenne Paul',
        'phone': '+237 233 40 55 80',
        'email': 'orders@ubipharm.cm',
        'address': 'Douala, Zone Industrielle de Magzi',
        'registration_number': 'MINSANTE/DPM/2024-008',
    },
    {
        'name': 'Allergan (AbbVie) Eye Care',
        'contact_person': 'Regional Manager',
        'phone': '+237 699 22 11 00',
        'email': 'westafrica@allergan.com',
        'address': 'Distributor via LABOREX',
        'registration_number': 'MINSANTE/DPM/2024-009',
    },
    {
        'name': 'Bausch + Lomb (Ophthalmic)',
        'contact_person': 'Africa Desk',
        'phone': '+237 699 33 22 11',
        'email': 'africa@bausch.com',
        'address': 'Distributor via CAPHARM',
        'registration_number': 'MINSANTE/DPM/2024-010',
    },
]

created = 0
for s in SUPPLIERS:
    obj, was_created = Supplier.objects.get_or_create(
        name=s['name'],
        defaults=s,
    )
    if was_created:
        created += 1
        print(f'  + {s["name"]}')
    else:
        print(f'  = {s["name"]} (already exists)')

print(f'\nCreated {created} suppliers. Total: {Supplier.objects.filter(is_deleted=False).count()}')
