"""Fix imbalanced entries caused by missing GL accounts during seeding."""
import sys, os, django
sys.path.insert(0, "/opt/ehr-africa")
os.environ["DJANGO_SETTINGS_MODULE"] = "ehr_project.settings.base"
django.setup()

from django.db.models import Sum
from apps.billing.models import JournalEntry, JournalLine

# Find all SEED entries that are imbalanced (one-sided lines)
seed_entries = JournalEntry.objects.filter(
    reference__startswith="SEED-", is_deleted=False, is_posted=True
)

fixed = 0
deleted = 0
for entry in seed_entries:
    lines = entry.lines.all()
    total_dr = sum(l.debit_amount for l in lines)
    total_cr = sum(l.credit_amount for l in lines)

    if total_dr != total_cr:
        # This entry is imbalanced — has only 1 line (the other account was missing)
        if lines.count() == 1:
            # Delete the single line and the entry
            lines.delete()
            entry.is_deleted = True
            entry.save(update_fields=["is_deleted"])
            deleted += 1
        else:
            # Multiple lines but still imbalanced — investigate
            print(f"  WARNING: {entry.reference} has {lines.count()} lines but imbalanced: DR={total_dr} CR={total_cr}")
            # If difference is from one missing side, delete entry
            entry.is_deleted = True
            entry.lines.all().delete()
            entry.save(update_fields=["is_deleted"])
            deleted += 1

print(f"Deleted {deleted} imbalanced entries")

# Verify overall balance
totals = JournalLine.objects.filter(
    entry__is_deleted=False, entry__is_posted=True
).aggregate(
    total_dr=Sum("debit_amount"),
    total_cr=Sum("credit_amount"),
)

diff = (totals['total_dr'] or 0) - (totals['total_cr'] or 0)
print(f"\nAfter fix:")
print(f"  Total debits:  {totals['total_dr']:,.0f} FCFA")
print(f"  Total credits: {totals['total_cr']:,.0f} FCFA")
print(f"  Difference:    {diff:,.0f} FCFA {'(BALANCED!)' if diff == 0 else '*** STILL IMBALANCED ***'}")

if diff != 0:
    # Find remaining imbalanced entries
    print("\nRemaining imbalanced entries:")
    for entry in JournalEntry.objects.filter(is_deleted=False, is_posted=True):
        lines = entry.lines.all()
        dr = sum(l.debit_amount for l in lines)
        cr = sum(l.credit_amount for l in lines)
        if dr != cr:
            print(f"  {entry.reference}: {entry.description[:50]} DR={dr} CR={cr} diff={dr-cr}")
