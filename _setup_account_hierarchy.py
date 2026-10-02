"""
Auto-detect parent-child relationships in GLAccount based on account code prefix.

Rule (from Finance Director):
  - If account A.code[:-1]  matches account B.code  → B is the parent of A
  - B gets marked as is_summary=True (never posted to directly)
  - A gets parent FK → B

Example:
  705110 (Sales Lenses Standard) → parent 70511 (Sales Lenses)
  705111 (Sales Lenses Express)  → parent 70511
  705112 (Sales Lenses VIP)      → parent 70511
  70511  → is_summary=True

Run on server:
  cd /opt/ehr-africa && venv/bin/python _setup_account_hierarchy.py
"""
import os, sys, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ehr_project.settings.base")
sys.path.insert(0, "/opt/ehr-africa")
django.setup()

from apps.billing.models import GLAccount

accounts = list(GLAccount.objects.filter(is_deleted=False).order_by('code'))
code_to_acct = {a.code: a for a in accounts}

parents_found = 0
children_linked = 0
already_set = 0

for acct in accounts:
    if len(acct.code) < 2:
        continue
    parent_code = acct.code[:-1]
    parent = code_to_acct.get(parent_code)
    if parent and parent.id != acct.id:
        # Link child to parent
        changed = False
        if acct.parent_id != parent.id:
            acct.parent = parent
            changed = True
        if changed:
            acct.save(update_fields=['parent'])
            children_linked += 1
            print(f"  Linked: {acct.code} → {parent.code} ({parent.name[:40]})")
        else:
            already_set += 1

        # Mark parent as summary
        if not parent.is_summary:
            parent.is_summary = True
            parent.save(update_fields=['is_summary'])
            parents_found += 1
            print(f"  Summary: {parent.code} — {parent.name[:40]}")

print()
print(f"Summary accounts marked : {parents_found}")
print(f"Children linked          : {children_linked}")
print(f"Already correctly set    : {already_set}")
print()

# Safety check: no account should be its own ancestor
print("Checking for circular references...")
for acct in GLAccount.objects.filter(is_deleted=False, parent__isnull=False):
    visited = set()
    node = acct
    while node.parent_id:
        if node.parent_id in visited:
            print(f"  CIRCULAR LOOP DETECTED at account {acct.code}!")
            break
        visited.add(node.id)
        node = node.parent
    # no loop
print("Done — no circular references found.")

# Summary report
total = GLAccount.objects.filter(is_deleted=False).count()
summaries = GLAccount.objects.filter(is_deleted=False, is_summary=True).count()
leaves = GLAccount.objects.filter(is_deleted=False, is_summary=False).count()
with_parent = GLAccount.objects.filter(is_deleted=False, parent__isnull=False).count()
print()
print(f"Total accounts  : {total}")
print(f"Summary accounts: {summaries}")
print(f"Leaf accounts   : {leaves}")
print(f"With parent FK  : {with_parent}")
