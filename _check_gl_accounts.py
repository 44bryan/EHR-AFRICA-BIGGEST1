import sys, os, django
sys.path.insert(0, "/opt/ehr-africa")
os.environ["DJANGO_SETTINGS_MODULE"] = "ehr_project.settings.base"
django.setup()

from apps.billing.models import GLAccount, JournalEntry, JournalLine, JournalType, CostCenter, FiscalPeriod
from apps.accounts.models import User

print(f"Existing journal entries: {JournalEntry.objects.filter(is_deleted=False).count()}")
print(f"  Posted: {JournalEntry.objects.filter(is_deleted=False, is_posted=True).count()}")
print(f"Existing journal lines: {JournalLine.objects.count()}")
print()

print("=== ALL GL ACCOUNTS ===")
for a in GLAccount.objects.filter(is_deleted=False, is_active=True).order_by("code"):
    print(f"  {a.code} | {a.name} | type={a.account_type}")

print()
print("=== COST CENTERS ===")
for cc in CostCenter.objects.filter(is_deleted=False).order_by("code"):
    print(f"  {cc.code} | {cc.name}")

print()
print("=== FISCAL PERIODS ===")
for fp in FiscalPeriod.objects.filter(is_deleted=False).order_by("-start_date")[:5]:
    print(f"  {fp.name} | {fp.start_date} to {fp.end_date} | status={fp.status}")

print()
print("=== JOURNAL TYPES ===")
for jt in JournalType.objects.filter(is_deleted=False).order_by("code"):
    print(f"  {jt.code} | {jt.name}")

admin = User.objects.filter(is_superuser=True).first()
print(f"\nAdmin: {admin.username} (id={admin.id})")
