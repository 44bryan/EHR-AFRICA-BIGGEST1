import sys
sys.path.insert(0, "/opt/ehr-africa")
import django, os
os.environ["DJANGO_SETTINGS_MODULE"] = "ehr_project.settings.production"
django.setup()
from apps.patients.models import RouteDestination

# Fix Optical Shop: should be terminal (not intermediate)
r = RouteDestination.objects.get(code="OPTICAL")
print(f"Before: code={r.code} group={r.group} intermediate={r.is_intermediate}")
r.is_intermediate = False
r.group = "FINISH"
r.save(update_fields=["is_intermediate", "group", "updated_at"])
print(f"After:  code={r.code} group={r.group} intermediate={r.is_intermediate}")

# Clear cache so the change takes effect immediately
from django.core.cache import cache
cache.delete("intermediate_dest_codes")
print("Cache cleared")

# Print all destinations for review
print("\nAll active destinations:")
for rd in RouteDestination.objects.filter(is_active=True).order_by("group", "code"):
    print(f"  {rd.code:20s} grp={rd.group:12s} intermediate={str(rd.is_intermediate):5s}  {rd.label}")
