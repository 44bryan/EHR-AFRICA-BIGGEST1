import os, sys, django, traceback
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ehr_project.settings.base")
sys.path.insert(0, "/opt/ehr-africa")
django.setup()

import apps.billing.gl_service as gs
from apps.billing.models import GLAccount, Invoice, Payment, JournalEntry
from decimal import Decimal

# Monkey-patch _create_entry so we can see every lookup
original_create = gs._create_entry

def patched_create(date, description, reference, source_type, source_id, lines, user=None):
    print(f"  _create_entry: {source_type} / {reference}")
    resolved = []
    for code, debit, credit, desc in lines:
        acct = GLAccount.objects.filter(code=code, is_active=True).first()
        status = ("FOUND: " + acct.name[:35]) if acct else "*** MISSING ***"
        print(f"    {code}  Dr={debit}  Cr={credit}  -> {status}")
        if acct is None:
            print(f"    !! Returning None — account {code} not found in DB")
            return None
        resolved.append((acct, Decimal(str(debit)), Decimal(str(credit)), desc))
    total_dr = sum(d for _, d, _, _ in resolved)
    total_cr = sum(c for _, _, c, _ in resolved)
    diff = abs(total_dr - total_cr)
    print(f"    Totals: Dr={total_dr}  Cr={total_cr}  diff={diff}")
    if diff > Decimal("0.01"):
        print(f"    !! Returning None — unbalanced entry")
        return None
    return original_create(date, description, reference, source_type, source_id, lines, user)

gs._create_entry = patched_create

# Also show what AR_PATIENT and CASH_ACCOUNT resolve to
print("=== MODULE-LEVEL CONSTANTS ===")
print(f"  AR_PATIENT    = {gs.AR_PATIENT}")
print(f"  CASH_ACCOUNT  = {gs.CASH_ACCOUNT}")
print(f"  BANK_ACCOUNT  = {gs.BANK_ACCOUNT}")
print(f"  get_payment_account('CASH') = {gs.get_payment_account('CASH')}")
print(f"  get_revenue_code('CONSULT') = {gs.get_revenue_code('CONSULT')}")
print(f"  get_revenue_code('INVEST')  = {gs.get_revenue_code('INVEST')}")
print()

for inv_num in ["INV-2026-00494", "INV-2026-00495"]:
    inv = Invoice.objects.filter(invoice_number=inv_num).first()
    if not inv:
        print(f"{inv_num}: NOT FOUND")
        continue

    inv_je = JournalEntry.objects.filter(source_type="invoice", source_id=str(inv.pk)).first()
    print(f"\n=== {inv_num}  total={inv.total}  insurance_amount={getattr(inv,'insurance_amount','N/A')}  existing_GL={'YES' if inv_je else 'NO'} ===")

    # Show items
    for item in inv.items.filter(is_deleted=False):
        rev_code = getattr(item, "gl_account_code", "") or ""
        if not rev_code and hasattr(item, "resolve_gl_code"):
            rev_code = item.resolve_gl_code()
        if not rev_code:
            rev_code = gs.get_revenue_code(item.category)
        a = GLAccount.objects.filter(code=rev_code, is_active=True).first()
        print(f"  Item: {item.description[:40]}  cat={item.category}  gl={rev_code}  -> {'FOUND: '+a.name[:30] if a else 'MISSING'}")

    # Try posting (skip if already exists)
    if not inv_je:
        print("  > Calling post_invoice_issued...")
        try:
            result = gs.post_invoice_issued(inv)
            print(f"  > Result: {result}")
        except Exception:
            traceback.print_exc()

    # Payment
    pay = inv.payments.filter(is_deleted=False).first()
    if pay:
        pje = JournalEntry.objects.filter(source_type="payment", source_id=str(pay.pk)).first()
        print(f"\n  Payment {pay.receipt_number}  method={pay.payment_method}  amount={pay.amount}  existing_GL={'YES' if pje else 'NO'}")
        if not pje:
            print("  > Calling post_payment...")
            try:
                result = gs.post_payment(pay)
                print(f"  > Result: {result}")
            except Exception:
                traceback.print_exc()

print("\nDone.")
