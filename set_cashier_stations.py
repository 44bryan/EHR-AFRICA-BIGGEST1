"""
One-time script: set cashier_station='ALL' on all cashier accounts
that have a blank or null cashier_station value.

Run from the project root:
    python manage.py shell < set_cashier_stations.py
  OR
    python set_cashier_stations.py  (if DJANGO_SETTINGS_MODULE is already set)
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.local')
django.setup()

from apps.accounts.models import User

updated = User.objects.filter(
    role='CASHIER',
    cashier_station__in=['', None],
).update(cashier_station='ALL')

total_cashiers = User.objects.filter(role='CASHIER').count()

print(f"Done. Updated {updated} cashier account(s) to station=ALL.")
print(f"Total cashier accounts: {total_cashiers}")
print()

# Print summary of all cashier stations after update
from django.db.models import Count
breakdown = (
    User.objects.filter(role='CASHIER')
    .values('cashier_station')
    .annotate(count=Count('id'))
    .order_by('cashier_station')
)
print("Cashier station breakdown:")
for row in breakdown:
    station = row['cashier_station'] or '(blank)'
    print(f"  {station}: {row['count']} account(s)")
