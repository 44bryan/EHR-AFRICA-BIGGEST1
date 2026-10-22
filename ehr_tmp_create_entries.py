import django, os
os.environ["DJANGO_SETTINGS_MODULE"] = "ehr_project.settings.production"
django.setup()

from apps.billing.models import StockOperationType, BillingOperationCC, GLAccount

dr = GLAccount.objects.filter(code__startswith="311", is_deleted=False).first()
cr = GLAccount.objects.filter(code__startswith="401", is_deleted=False).first()
op1 = BillingOperationCC.objects.filter(operation_code="141", is_deleted=False).first()
op2 = BillingOperationCC.objects.filter(operation_code="300", is_deleted=False).first()

print("dr=%s cr=%s op1=%s op2=%s" % (dr, cr, op1, op2))

if not StockOperationType.objects.filter(code="135R").exists():
    t = StockOperationType.objects.create(
        code="135R", name="Stock Receipt - Reception / GRN", category="ENTRY",
        debit_account=dr, credit_account=cr, billing_operation=op1,
        location_types="FRONT_DESK,CENTRAL,GENERAL", is_active=True,
    )
    print("CREATED 135R: " + t.name)
else:
    print("SKIP 135R already exists")

if not StockOperationType.objects.filter(code="136NM").exists():
    t = StockOperationType.objects.create(
        code="136NM", name="Stock Receipt - Non-Medical Store", category="ENTRY",
        debit_account=dr, credit_account=cr, billing_operation=op2,
        location_types="NON_MEDICAL,FRONT_DESK", is_active=True,
    )
    print("CREATED 136NM: " + t.name)
else:
    print("SKIP 136NM already exists")

print("\nAll entry types now:")
for t in StockOperationType.objects.filter(category="ENTRY", is_deleted=False).order_by("code"):
    op_code = t.billing_operation.operation_code if t.billing_operation else "None"
    cc_code = t.billing_operation.cost_center.code if t.billing_operation and t.billing_operation.cost_center else "Unassigned"
    stores = t.location_types or "All"
    print("  %s | %s | stores:%s | op:%s cc:%s" % (t.code, t.name, stores, op_code, cc_code))
