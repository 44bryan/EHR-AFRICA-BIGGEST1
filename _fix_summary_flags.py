"""
Mark every GLAccount that has children pointing to it as is_summary=True.
This ensures Balance Generale shows rolled-up totals and Balance Auxiliaire
shows the detail leaf accounts — making the two modes visually distinct.
"""
import os, sys, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ehr_project.settings.base")
sys.path.insert(0, "/opt/ehr-africa")
django.setup()

from apps.billing.models import GLAccount

# Every account that has at least one child must be a summary account
parents = GLAccount.objects.filter(
    is_deleted=False,
    children__isnull=False,
    is_summary=False,
).distinct()

fixed = 0
for p in parents:
    p.is_summary = True
    p.save(update_fields=['is_summary'])
    fixed += 1
    print(f"  Summary: {p.code} — {p.name[:55]}")

print()
print(f"Newly marked as summary: {fixed}")

s  = GLAccount.objects.filter(is_deleted=False, is_summary=True).count()
le = GLAccount.objects.filter(is_deleted=False, is_summary=False).count()
wp = GLAccount.objects.filter(is_deleted=False, parent__isnull=False).count()
print(f"Total summary accounts : {s}")
print(f"Total leaf accounts    : {le}")
print(f"Accounts with parent FK: {wp}")
print()

# Show a sample of what Generale will look like
print("Sample Balance Generale accounts (first 10 summary):")
for a in GLAccount.objects.filter(is_deleted=False, is_summary=True).order_by('code')[:10]:
    child_count = a.children.filter(is_deleted=False).count()
    print(f"  {a.code}  {a.name[:50]:<50}  ({child_count} children)")
