"""Remove all SEED- journal entries and their lines."""
import sys, os, django
sys.path.insert(0, "/opt/ehr-africa")
os.environ["DJANGO_SETTINGS_MODULE"] = "ehr_project.settings.base"
django.setup()

from apps.billing.models import JournalEntry, JournalLine

# Find all SEED entries
seed_entries = JournalEntry.objects.filter(reference__startswith="SEED-")
count = seed_entries.count()

# Delete lines first, then entries
lines_deleted = JournalLine.objects.filter(entry__reference__startswith="SEED-").delete()[0]
entries_deleted = seed_entries.delete()[0]

print(f"Deleted {lines_deleted} journal lines")
print(f"Deleted {entries_deleted} journal entries")

# Verify remaining
remaining = JournalEntry.objects.filter(is_deleted=False).count()
remaining_lines = JournalLine.objects.count()
print(f"\nRemaining entries: {remaining}")
print(f"Remaining lines: {remaining_lines}")
print("Done!")
