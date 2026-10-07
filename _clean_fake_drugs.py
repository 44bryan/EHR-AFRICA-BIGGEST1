"""Soft-delete fake/test drugs that don't have PH0 barcodes."""
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.base')
import django
django.setup()

from django.db import connection
from apps.pharmacy.models import Drug, DrugStock

real = Drug.objects.filter(is_deleted=False, barcode__startswith='PH0')
fake = Drug.objects.filter(is_deleted=False).exclude(barcode__startswith='PH0')

print(f'Total drugs: {Drug.objects.filter(is_deleted=False).count()}')
print(f'Real (PH0 barcode): {real.count()}')
print(f'Fake/old to remove: {fake.count()}')

fake_ids = list(fake.values_list('id', flat=True))

if not fake_ids:
    print('Nothing to clean!')
else:
    with connection.cursor() as cur:
        # Soft-delete stock batches for fake drugs
        cur.execute(
            "UPDATE pharmacy_drugstock SET is_deleted = TRUE WHERE drug_id = ANY(%s) AND is_deleted = FALSE",
            [fake_ids]
        )
        print(f'Soft-deleted {cur.rowcount} fake stock batches')

        # Soft-delete the fake drugs themselves
        cur.execute(
            "UPDATE pharmacy_drug SET is_deleted = TRUE WHERE id = ANY(%s)",
            [fake_ids]
        )
        print(f'Soft-deleted {cur.rowcount} fake drugs')

    print(f'\nRemaining active drugs: {Drug.objects.filter(is_deleted=False).count()}')
    print(f'Remaining active stock: {DrugStock.objects.filter(is_deleted=False).count()}')
