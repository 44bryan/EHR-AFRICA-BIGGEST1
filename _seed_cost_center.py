import sys, os, django
sys.path.insert(0, "/opt/ehr-africa")
os.environ["DJANGO_SETTINGS_MODULE"] = "ehr_project.settings.base"
django.setup()

from apps.billing.models import JournalType, StockOperationType, GLAccount
from apps.accounts.models import User

admin = User.objects.filter(is_superuser=True).first()

# Seed Journal Types
journal_types = [
    ("AC", "Journal des Achats", "Purchase journal - all supplier invoices and procurement entries"),
    ("VE", "Journal des Ventes", "Sales journal - all patient invoices, optical sales, pharmacy sales"),
    ("CA", "Journal de Caisse", "Cash journal - all cash receipts and disbursements"),
    ("BQ", "Journal de Banque", "Bank journal - all bank receipts, transfers, and payments"),
    ("ST", "Journal des Stocks", "Stock journal - all inventory entries and exits"),
    ("SA", "Journal des Salaires", "Payroll journal - salary, CNPS contributions, withholdings"),
    ("OD", "Journal des Operations Diverses", "Miscellaneous operations - adjustments, provisions, accruals"),
    ("AN", "Journal des A-Nouveau", "Opening balances journal - year-start carried-forward entries"),
]

created_jt = 0
for code, name, desc in journal_types:
    obj, created = JournalType.objects.get_or_create(
        code=code,
        defaults={"name": name, "description": desc, "created_by": admin}
    )
    if created:
        created_jt += 1
        print(f"  Created JT: {code} - {name}")
    else:
        print(f"  Exists JT: {code}")

print(f"Journal Types: {created_jt} created")
print()

# Seed Stock Operation Types
def get_acct(code_prefix):
    acct = GLAccount.objects.filter(code__startswith=code_prefix, is_deleted=False).first()
    if acct:
        return acct
    print(f"  WARNING: No GL account with code starting {code_prefix}")
    return None

acct_311 = get_acct("311")   # Stock of Frames
acct_321 = get_acct("321")   # Stock of Merchandise (Pharmacy)
acct_603 = get_acct("603")   # Variation de stocks
acct_758 = get_acct("758")   # Donations received
acct_658 = get_acct("658")   # Donations given
acct_659 = get_acct("659")   # Losses

stock_acct = acct_311 or acct_321
variation_acct = acct_603

if not stock_acct or not variation_acct:
    print("CRITICAL: Missing stock (31x) or variation (603) accounts.")
    for a in GLAccount.objects.filter(is_deleted=False, code__startswith="3").order_by("code")[:10]:
        print(f"  Found 3xx: {a.code} - {a.name}")
    for a in GLAccount.objects.filter(is_deleted=False, code__startswith="6").order_by("code")[:10]:
        print(f"  Found 6xx: {a.code} - {a.name}")
else:
    op_types = [
        ("EN-ACH", "Purchase Entry", "ENTRY", stock_acct, variation_acct,
         "Stock entry from purchase - Dr Stock 31x / Cr Variation 603"),
        ("EN-TRF", "Transfer In", "ENTRY", stock_acct, stock_acct,
         "Inter-store transfer received - Dr Stock dest / Cr Stock source"),
        ("EN-RET", "Return to Stock", "ENTRY", stock_acct, variation_acct,
         "Returned goods back to stock - Dr Stock 31x / Cr Variation 603"),
        ("EN-DON", "Donation Received", "ENTRY", stock_acct, acct_758 or variation_acct,
         "Donated goods received - Dr Stock 31x / Cr Donations 758"),
        ("EX-CON", "Consumption", "EXIT", variation_acct, stock_acct,
         "Internal consumption - Dr Variation 603 / Cr Stock 31x"),
        ("EX-VTE", "Sale Exit", "EXIT", variation_acct, stock_acct,
         "Stock exit for sale - Dr Variation 603 / Cr Stock 31x"),
        ("EX-DIS", "Disposal", "EXIT", acct_659 or variation_acct, stock_acct,
         "Disposal of expired/damaged stock - Dr Losses 659 / Cr Stock 31x"),
        ("EX-DON", "Donation Given", "EXIT", acct_658 or variation_acct, stock_acct,
         "Donated goods given out - Dr Charges 658 / Cr Stock 31x"),
        ("EX-PER", "Loss / Pilferage", "EXIT", acct_659 or variation_acct, stock_acct,
         "Lost or stolen stock - Dr Losses 659 / Cr Stock 31x"),
        ("EX-AJU", "Adjustment Shortage", "EXIT", acct_658 or variation_acct, stock_acct,
         "Stocktake shortage adjustment - Dr Charges 658 / Cr Stock 31x"),
    ]

    created_sot = 0
    for code, name, cat, dr_acct, cr_acct, desc in op_types:
        obj, created = StockOperationType.objects.get_or_create(
            code=code,
            defaults={
                "name": name, "category": cat,
                "debit_account": dr_acct, "credit_account": cr_acct,
                "description": desc, "created_by": admin,
            }
        )
        if created:
            created_sot += 1
            print(f"  Created SOT: {code} - {name} (Dr {dr_acct.code} / Cr {cr_acct.code})")
        else:
            print(f"  Exists SOT: {code}")

    print(f"Stock Operation Types: {created_sot} created")

print()
print("Seed complete!")
