import django, os, sys
sys.path.insert(0, '/opt/ehr-africa')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.base')
django.setup()

from apps.inventory.models import StoreLocation

stores = [
    ('FD01',   'Front Desk Store',               'FRONT_DESK',  'Front Desk / Reception'),
    ('NM01',   'Non-Medical Stock',              'NON_MEDICAL', 'Non-Medical Consumables Store'),
    ('OP01',   'Optical Showroom',               'SHOWROOM',    'Optical Department - Showroom'),
    ('OP02',   'Optical Store',                  'OPTICAL',     'Optical Department - Main Store'),
    ('PH02',   'Pharmacy Store',                 'PHARMACY',    'Central Pharmacy Store'),
    ('PH-CU',  'Transfert Chariots Urgence',     'EMERGENCY',   'Emergency Chariots / Chariots Urgence'),
    ('PH-OR',  'Medical Consumables Main Store', 'CENTRAL',     'Main Medical Consumables Store'),
    ('PH-OT',  'OT Store',                       'THEATRE',     'Operating Theatre Store'),
    ('PH-TOR', 'Transfert Outreach Store',       'OUTREACH',    'Outreach Programme Store'),
    ('PH-TOT', 'Transfert OT Store',             'OTN',         'OT Transfer Store'),
]

created = updated = 0
for code, name, loc_type, address in stores:
    obj, is_new = StoreLocation.objects.update_or_create(
        store_code=code,
        defaults={
            'name': name,
            'location_type': loc_type,
            'address': address,
            'is_active': True,
            'is_deleted': False,
        }
    )
    tag = 'CREATED' if is_new else 'UPDATED'
    print(f'  {tag}: {obj.store_code} - {obj.name}')
    if is_new:
        created += 1
    else:
        updated += 1

print(f'Done: {created} created, {updated} updated.')
