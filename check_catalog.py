import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.production')
sys.path.insert(0, '/opt/ehr-africa')
django.setup()

from apps.billing.models import ServicePrice
svcs = ServicePrice.objects.filter(is_active=True, is_deleted=False).order_by('category', 'name')
print(f"Total active services: {svcs.count()}")
zero_price = svcs.filter(price=0)
print(f"Services with price=0: {zero_price.count()}")
print()
print("Sample services with price:")
for s in svcs.exclude(price=0)[:10]:
    print(f"  [{s.category}] {s.name} = {s.price} FCFA")
print()
print("Zero price services:")
for s in zero_price[:10]:
    print(f"  [{s.category}] {s.name}")
