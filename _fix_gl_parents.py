# coding: utf-8
import django, os, sys
sys.path.insert(0, '/opt/ehr-africa')
os.environ["DJANGO_SETTINGS_MODULE"] = "ehr_project.settings.base"
django.setup()

from apps.billing.models import GLAccount, JournalLine
from django.db import transaction

def get_or_create_summary(code, name, account_type):
    obj, created = GLAccount.objects.get_or_create(
        code=code,
        defaults={
            "name": name,
            "account_type": account_type,
            "is_summary": True,
            "is_active": True,
            "allow_manual_posting": False,
        }
    )
    if not obj.is_summary:
        obj.is_summary = True
        obj.save(update_fields=["is_summary"])
    status = "CREATED" if created else "EXISTS"
    print(f"  [{status}] {code} -- {name}")
    return obj

def link(child_code, parent):
    try:
        child = GLAccount.objects.get(code=child_code, is_deleted=False)
        child.parent = parent
        child.save(update_fields=["parent"])
        print(f"  linked: {child_code} ({child.name}) --> {parent.code}")
    except GLAccount.DoesNotExist:
        print(f"  MISSING: {child_code}")

with transaction.atomic():

    # ---- Class 3: Stocks ---------------------------------------------------
    print("\nClass 3 -- Stocks:")
    p311 = GLAccount.objects.get(code="311000")
    link("321000", p311)   # Marchandises A
    link("33",     p311)   # Other Supplies

    # ---- Class 4: Receivables ----------------------------------------------
    print("\nClass 4 -- Receivables:")
    a41 = get_or_create_summary("41", "Clients et creances diverses", "ASSET")
    link("411000", a41)    # Members Receivable
    link("412000", a41)    # Clients-user_Patients

    # ---- Class 5: Cash & Bank ----------------------------------------------
    print("\nClass 5 -- Tresorerie:")
    a57 = get_or_create_summary("57", "Tresorerie", "ASSET")
    link("571000", a57)    # Cash in Hand
    link("572000", a57)    # Cash in Foreign Currency

    # ---- Class 6: link existing summaries that have no parent  -------------
    # (no orphaned posted leaf accounts in Class 6, but tidy up 603 group)
    print("\nClass 6 -- Expenses (tidy up):")
    for code in ["601100","601200","603","603100","603110","603400",
                 "622000","624000","626000","627000","628000",
                 "631000","632000","634300","637000","638000",
                 "659000","661000","662000","668000","681300","691100"]:
        try:
            a = GLAccount.objects.get(code=code, is_deleted=False)
            if not a.parent_id:
                # no change needed -- just report
                print(f"  (no parent): {code} {a.name}")
        except GLAccount.DoesNotExist:
            pass

    # ---- Class 7: Revenue --------------------------------------------------
    print("\nClass 7 -- Revenue:")
    a70 = get_or_create_summary("70", "Produits des activites", "REVENUE")
    for code in ["701000","702000","703000","706000","707000",
                 "705100","705110","705120","705130","705160","705190","705200",
                 "718000","791000"]:
        try:
            a = GLAccount.objects.get(code=code, is_deleted=False)
            if not a.parent_id:
                a.parent = a70
                a.save(update_fields=["parent"])
                print(f"  linked: {code} --> 70")
        except GLAccount.DoesNotExist:
            pass

# ---- Verification ----------------------------------------------------------
print("\n=== VERIFICATION ===")
posted_ids = set(JournalLine.objects.values_list("account_id", flat=True).distinct())
orphans = GLAccount.objects.filter(
    is_deleted=False, is_active=True,
    is_summary=False, parent__isnull=True,
    id__in=posted_ids
)
print(f"Orphaned accounts WITH transactions remaining: {orphans.count()}")
for a in orphans:
    print(f"  {a.code}  {a.name}")

print("\nSummary accounts and their child counts:")
for s in GLAccount.objects.filter(is_deleted=False, is_active=True, is_summary=True).order_by("code"):
    n = GLAccount.objects.filter(is_deleted=False, parent=s).count()
    posted = GLAccount.objects.filter(is_deleted=False, parent=s, id__in=posted_ids).count()
    if posted > 0:
        print(f"  {s.code:<12} {s.name:<50} [{n} children, {posted} with transactions]")

print("\nDone.")
