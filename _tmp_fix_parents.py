import django, os, sys
sys.path.insert(0, '/opt/ehr-africa')
os.environ["DJANGO_SETTINGS_MODULE"] = "ehr_project.settings.base"
django.setup()

from apps.billing.models import GLAccount, AccountType
from django.db import transaction

with transaction.atomic():
    def get_or_create_summary(code, name, account_type):
        obj, created = GLAccount.objects.get_or_create(
            code=code,
            defaults={
                "name": name, "account_type": account_type,
                "is_summary": True, "is_active": True, "allow_manual_posting": False,
            }
        )
        if not obj.is_summary:
            obj.is_summary = True
            obj.save(update_fields=["is_summary"])
        print(f"  {"created" if created else "exists"}: {code} — {name}")
        return obj

    def link(child_code, parent):
        try:
            child = GLAccount.objects.get(code=child_code, is_deleted=False)
            child.parent = parent
            child.save(update_fields=["parent"])
            print(f"  linked: {child_code} -> {parent.code}")
        except GLAccount.DoesNotExist:
            print(f"  MISSING: {child_code}")

    print("Class 3:")
    p311 = GLAccount.objects.get(code="311000")
    link("321000", p311)
    link("33", p311)

    print("Class 4:")
    a41 = get_or_create_summary("41", "Clients et creances diverses", "ASSET")
    for c in ["411000","412000"]:
        link(c, a41)

    print("Class 5:")
    a57 = get_or_create_summary("57", "Tresorerie", "ASSET")
    link("571000", a57)
    link("572000", a57)

    print("Class 7:")
    a70 = get_or_create_summary("70", "Produits des activites", "REVENUE")
    for c in ["701000","702000","703000","706000","707000","718000","705100","705110","705120","705130","705160","705190","705200","791000"]:
        try:
            a = GLAccount.objects.get(code=c, is_deleted=False)
            if not a.parent_id:
                a.parent = a70
                a.save(update_fields=["parent"])
                print(f"  linked: {c} -> 70")
        except GLAccount.DoesNotExist:
            pass

print()
from apps.billing.models import JournalLine
posted_ids = set(JournalLine.objects.values_list("account_id", flat=True).distinct())
orphans = GLAccount.objects.filter(is_deleted=False,is_active=True,is_summary=False,parent__isnull=True,id__in=posted_ids)
print(f"Orphaned posted accounts remaining: {orphans.count()}")
for a in orphans: print(f"  {a.code}  {a.name}")
