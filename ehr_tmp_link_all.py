import django, os
os.environ["DJANGO_SETTINGS_MODULE"] = "ehr_project.settings.production"
django.setup()

from apps.billing.models import StockOperationType, BillingOperationCC

# Map: StockOperationType.code -> BillingOperationCC.operation_code
links = {
    # Remaining receipt types
    "136":  "136",   # Stock Receipt Theatre/OT  -> Entrees OT CC:005
    "137":  "137",   # Stock Receipt Lab          -> Entrees Lab CC:004
    "141":  "141",   # Stock Entry GRN Reception  -> Entree Reception GRN CC:013
    "163":  "148",   # Ward/Emergency Receipt     -> Sorties OPD CC:001 (closest general)
    "300":  "300",   # Non-Medical Store duplicate -> Entrees Non-Medical CC:013
    # Inter-store receive types
    "135":  "156",   # Inter-Store Transfer Receive -> Transfert Inter-magasin CC:013
    "139":  "156",   # Auto Receive Optical        -> Transfert CC:013
    "140":  "156",   # Auto Receive                -> Transfert CC:013
    # Stock Count / Inventory types
    "150":  "150",   # Stock Count Pharmacy        -> Inventaire Pharmacie CC:008
    "151":  "151",   # Stock Count Theatre/OT      -> Inventaire OT CC:005
    "152":  "152",   # Stock Count Optical         -> Inventaire Optique CC:009
    "153":  "153",   # Stock Count Reception       -> Inventaire Reception CC:007
    "154":  "154",   # Stock Count Medical Consumables -> Inventaire Consommables CC:001
    "155":  "155",   # Periodic Journal Entry      -> Ecriture Periodique CC:012
    "156":  "155",   # Stock Count Non-Medical     -> Ecriture Periodique CC:012
    # Donation / Grant types -> Expense CC
    "160":  "144",   # Donation Lab                -> Sorties Perimees CC:016
    "170":  "144",   # Donation Optical            -> Sorties Perimees CC:016
    "172":  "144",   # Donation Surgical           -> Sorties Perimees CC:016
    "175":  "144",   # Donation General Store      -> Sorties Perimees CC:016
    # Internal transfer IN types
    "158":  "156",   # Return from Wards Lab       -> Transfert CC:013
    "159":  "156",   # Internal Transfer In Lab    -> Transfert CC:013
    "164":  "156",   # Internal Transfer In Ward   -> Transfert CC:013
    "171":  "156",   # Return from Surgery OT      -> Transfert CC:013
    "176":  "156",   # Internal Transfer In General -> Transfert CC:013
    "179":  "133",   # Outreach Store Receipt      -> Entrees Magasin Principal CC:013
}

linked = 0
skipped = []
for sot_code, op_code in links.items():
    try:
        sot = StockOperationType.objects.get(code=sot_code, is_deleted=False)
        if sot.billing_operation is not None:
            continue  # already linked, skip
        op = BillingOperationCC.objects.get(operation_code=op_code, is_deleted=False)
        sot.billing_operation = op
        sot.save(update_fields=["billing_operation"])
        cc = op.cost_center.code if op.cost_center else "-"
        print("LINKED: %s %s -> Op %s CC:%s" % (sot_code, sot.name[:32], op_code, cc))
        linked += 1
    except StockOperationType.DoesNotExist:
        skipped.append("sot %s not found" % sot_code)
    except BillingOperationCC.DoesNotExist:
        skipped.append("op %s not found" % op_code)

print("\nDone. %d linked." % linked)
if skipped:
    print("Skipped: " + ", ".join(skipped))

print("\nFinal entry type summary:")
all_types = StockOperationType.objects.filter(is_deleted=False).order_by("category", "code")
entry = [t for t in all_types if t.category == "ENTRY"]
print("ENTRY (%d):" % len(entry))
for t in entry:
    op_code = t.billing_operation.operation_code if t.billing_operation else "UNLINKED"
    cc_code = t.billing_operation.cost_center.code if t.billing_operation and t.billing_operation.cost_center else "-"
    print("  %s | %s | %s | op:%s cc:%s" % (t.code, t.name[:35], t.location_types or "All", op_code, cc_code))
