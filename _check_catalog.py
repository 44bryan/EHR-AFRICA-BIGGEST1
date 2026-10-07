import django, os
os.environ['DJANGO_SETTINGS_MODULE'] = 'ehr_project.settings.base'
django.setup()
from apps.billing.models import ServicePrice, ServiceCategory
from django.db.models import Count

total = ServicePrice.objects.filter(is_deleted=False).count()
active = ServicePrice.objects.filter(is_deleted=False, is_active=True).count()
inactive = total - active
print(f'Total services: {total}, Active: {active}, Inactive: {inactive}')
print()

# Count by category
for cat_val, cat_label in ServiceCategory.choices:
    c = ServicePrice.objects.filter(is_deleted=False, is_active=True, category=cat_val).count()
    if c > 0:
        print(f'  {cat_label} ({cat_val}): {c} services')
print()

# Tier distribution
tiers = ServicePrice.objects.filter(is_deleted=False, is_active=True).values('tier').annotate(n=Count('id')).order_by('tier')
for t in tiers:
    label = t['tier'] or 'ALL (no tier)'
    print(f'  Tier {label}: {t["n"]} services')
print()

# Show all services grouped by category
for cat_val, cat_label in ServiceCategory.choices:
    svcs = ServicePrice.objects.filter(is_deleted=False, is_active=True, category=cat_val).order_by('tier', 'name')
    if svcs.exists():
        print(f'\n--- {cat_label} ({cat_val}) ---')
        for s in svcs:
            gl = s.get_gl_code() if hasattr(s, 'get_gl_code') else '-'
            tier = s.tier or 'ALL'
            print(f'  [{tier}] {s.name} -- {int(s.price):,} FCFA  (GL: {gl})')

# Check POS category tabs vs DB categories
pos_tabs = {'REG', 'CONSULT', 'CLINICAL', 'INVEST', 'LAB', 'PHARMACY', 'OPTICAL', 'SURGICAL', 'OTHER', 'ADMISSION'}
db_cats = set(ServicePrice.objects.filter(is_deleted=False, is_active=True).values_list('category', flat=True).distinct())
missing_tabs = db_cats - pos_tabs
if missing_tabs:
    print(f'\nWARNING: DB has categories not in POS tabs: {missing_tabs}')
    for m in missing_tabs:
        count = ServicePrice.objects.filter(is_deleted=False, is_active=True, category=m).count()
        print(f'  {m}: {count} services HIDDEN from POS!')
else:
    print('\nAll DB categories are covered by POS tabs.')
