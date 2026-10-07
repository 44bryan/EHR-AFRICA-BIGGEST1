"""
Set realistic expiry dates and review selling prices for seeded drug stock.
Run via: manage.py shell < _fix_expiry_prices.py
"""
import os, random, datetime
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.base')
import django; django.setup()

from apps.pharmacy.models import Drug, DrugStock, DrugForm

today = datetime.date.today()

# ── 1. Realistic expiry dates based on drug form ────────────────────────────
# Typical shelf life by form (WHO guidelines):
#   Eye drops/ointments: 1-2 years (shorter after opening)
#   Injections: 2-3 years
#   Tablets/capsules: 3-5 years
#   Syrups: 2-3 years
#   Creams: 2-3 years

FORM_EXPIRY_RANGE = {
    'EYE_DROP':   (180, 540),     # 6-18 months from now
    'EYE_OINT':   (180, 540),
    'INJECTION':  (270, 730),     # 9-24 months
    'SYRUP':      (180, 640),     # 6-21 months
    'CREAM':      (270, 640),     # 9-21 months
    'NASAL':      (180, 540),     # 6-18 months
    'TABLET':     (365, 1095),    # 1-3 years
    'CAPSULE':    (365, 1095),
    'OTHER':      (270, 730),
}

batches = DrugStock.objects.filter(is_deleted=False).select_related('drug')
updated_expiry = 0
updated_price = 0

for batch in batches:
    form = batch.drug.form
    min_days, max_days = FORM_EXPIRY_RANGE.get(form, (270, 730))

    # Randomize expiry within the range
    exp_days = random.randint(min_days, max_days)
    new_expiry = today + datetime.timedelta(days=exp_days)

    # Some batches (10%) should be expiring soon (within 90 days) — realistic
    if random.random() < 0.10:
        new_expiry = today + datetime.timedelta(days=random.randint(15, 90))

    # A few (3%) already expired — realistic for alerts testing
    if random.random() < 0.03:
        new_expiry = today - datetime.timedelta(days=random.randint(1, 60))

    batch.expiry_date = new_expiry
    batch.save(update_fields=['expiry_date'])
    updated_expiry += 1

print(f'Updated {updated_expiry} batch expiry dates')

# ── 2. Fix selling prices — ensure all drugs have sensible markup ────────────
# Markup tiers based on cost price (Cameroon pharmacy standard):
#   < 500 FCFA:    50% markup (low-cost generics)
#   500-2000 FCFA: 40% markup
#   2000-10000:    35% markup
#   > 10000:       25% markup (expensive drugs, lower margin)

drugs = Drug.objects.filter(is_deleted=False)
for drug in drugs:
    cost = drug.cost_price
    if cost <= 0:
        continue
    if cost < 500:
        markup = Decimal('1.50')
    elif cost < 2000:
        markup = Decimal('1.40')
    elif cost < 10000:
        markup = Decimal('1.35')
    else:
        markup = Decimal('1.25')

    new_price = (cost * markup).quantize(Decimal('1'))  # Round to nearest FCFA
    if new_price != drug.selling_price:
        drug.selling_price = new_price
        drug.save(update_fields=['selling_price'])
        updated_price += 1

print(f'Updated {updated_price} drug selling prices')

# ── Summary ──────────────────────────────────────────────────────────────────
soon = DrugStock.objects.filter(
    is_deleted=False,
    expiry_date__lte=today + datetime.timedelta(days=90),
    expiry_date__gte=today
).count()
expired = DrugStock.objects.filter(is_deleted=False, expiry_date__lt=today).count()
print(f'\nExpiry status:')
print(f'  Expired: {expired} batches')
print(f'  Expiring within 90 days: {soon} batches')
print(f'  Total active batches: {DrugStock.objects.filter(is_deleted=False).count()}')
