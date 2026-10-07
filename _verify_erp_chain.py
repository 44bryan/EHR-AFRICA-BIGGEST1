#!/usr/bin/env python
"""Comprehensive ERP Chain Verification — checks every link from Chart of Accounts to Financial Statements."""
import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.base')
django.setup()

from apps.billing.models import (
    GLAccount, GLMapping, ServiceSubCategory, ServicePrice,
    Invoice, InvoiceItem, Payment, JournalEntry, JournalLine,
    Expense, APBill, Budget,
)
from django.db.models import Sum, Count, Q, F, Case, When, Value, DecimalField
from decimal import Decimal

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"
results = []

def check(name, condition, detail=""):
    status = PASS if condition else FAIL
    results.append((status, name, detail))
    icon = "+" if condition else "X"
    print(f"  [{icon}] {name}" + (f" — {detail}" if detail else ""))

def warn(name, detail=""):
    results.append((WARN, name, detail))
    print(f"  [!] {name}" + (f" — {detail}" if detail else ""))

print("=" * 70)
print("  EHR AFRICA — FULL ERP CHAIN VERIFICATION")
print("=" * 70)

# ── 1. Chart of Accounts ──
print("\n1. CHART OF ACCOUNTS (OHADA SYSCEBNL)")
total = GLAccount.objects.filter(is_active=True).count()
check(f"GL Accounts loaded", total > 500, f"{total} active accounts")

for cls, label in [(1,"Equity/Capital"), (2,"Assets"), (3,"Inventory/Stock"),
                    (4,"Receivables/Payables"), (5,"Cash/Bank"),
                    (6,"Expenses"), (7,"Revenue"), (8,"Other Income/Expense")]:
    cnt = GLAccount.objects.filter(is_active=True, code__startswith=str(cls)).count()
    check(f"Class {cls} ({label})", cnt > 0, f"{cnt} accounts")

# ── 2. GL Mappings ──
print("\n2. GL MAPPING ENGINE")
for cat, label in [('REVENUE','Revenue mappings'), ('PAYMENT','Payment mappings'),
                    ('EXPENSE','Expense mappings'), ('SYSTEM','System mappings')]:
    cnt = GLMapping.objects.filter(category=cat).count()
    check(label, cnt > 0, f"{cnt} mappings")

# Check all mappings point to active accounts
orphan = GLMapping.objects.filter(gl_account__is_active=False).count()
check("All mappings → active accounts", orphan == 0,
      f"{orphan} orphaned" if orphan else "all valid")

# ── 3. Sub-Categories → Revenue GL ──
print("\n3. SERVICE SUB-CATEGORIES → GL ACCOUNTS")
subs = ServiceSubCategory.objects.filter(is_deleted=False)
total_subs = subs.count()
linked = subs.exclude(gl_account__isnull=True).count()
check(f"Sub-categories exist", total_subs > 0, f"{total_subs} families")
check(f"Sub-categories linked to GL", linked > 0, f"{linked}/{total_subs} linked")

# Verify linked accounts are revenue class
bad_class = subs.exclude(gl_account__isnull=True).exclude(gl_account__code__startswith='7').count()
check("All sub-cat GL accounts are Class 7 (Revenue)", bad_class == 0,
      f"{bad_class} non-revenue" if bad_class else "all revenue")

# ── 4. Service Prices ──
print("\n4. SERVICE PRICE CATALOG")
prices = ServicePrice.objects.filter(is_deleted=False)
total_prices = prices.count()
with_sub = prices.exclude(sub_category__isnull=True).count()
check("Service prices exist", total_prices > 0, f"{total_prices} items")
check("Prices linked to sub-categories", with_sub > 0, f"{with_sub}/{total_prices}")

# ── 5. Invoices & Items ──
print("\n5. INVOICES & LINE ITEMS")
inv_count = Invoice.objects.count()
item_count = InvoiceItem.objects.count()
check("Invoices exist", inv_count > 0, f"{inv_count} invoices")
check("Invoice items exist", item_count > 0, f"{item_count} line items")

inv_with_items = Invoice.objects.filter(items__isnull=False).distinct().count()
check("Invoices have items", inv_with_items > 0, f"{inv_with_items}/{inv_count} have items")

# ── 6. Payments ──
print("\n6. PAYMENTS")
pay_count = Payment.objects.count()
pay_total = Payment.objects.aggregate(s=Sum('amount'))['s'] or 0
check("Payments recorded", pay_count > 0, f"{pay_count} payments, total {pay_total:,.0f} FCFA")

# ── 7. Journal Entries ──
print("\n7. JOURNAL ENTRIES (Double-Entry)")
je_count = JournalEntry.objects.count()
jl_count = JournalLine.objects.count()
check("Journal entries exist", je_count > 0, f"{je_count} entries")
check("Journal lines exist", jl_count > 0, f"{jl_count} lines")

# Check all journal lines reference active GL accounts
jl_orphan = JournalLine.objects.filter(account__is_active=False).count()
check("All journal lines → active GL accounts", jl_orphan == 0,
      f"{jl_orphan} orphaned" if jl_orphan else "all valid")

# Double-entry balance check: every JE should have Dr == Cr
unbalanced = 0
for je in JournalEntry.objects.all():
    lines = je.lines.aggregate(
        dr=Sum('debit_amount', default=Decimal('0')),
        cr=Sum('credit_amount', default=Decimal('0'))
    )
    if abs(lines['dr'] - lines['cr']) > Decimal('0.01'):
        unbalanced += 1
check("All journal entries balanced (Dr=Cr)", unbalanced == 0,
      f"{unbalanced} unbalanced" if unbalanced else f"all {je_count} balanced")

# ── 8. General Ledger / Trial Balance ──
print("\n8. TRIAL BALANCE")
agg = JournalLine.objects.aggregate(
    total_dr=Sum('debit_amount', default=Decimal('0')),
    total_cr=Sum('credit_amount', default=Decimal('0'))
)
dr, cr = agg['total_dr'], agg['total_cr']
diff = abs(dr - cr)
check(f"Trial Balance balances", diff < Decimal('1'),
      f"Dr={dr:,.0f}  Cr={cr:,.0f}  diff={diff:,.2f}")

# ── 9. Balance Sheet Equation ──
print("\n9. BALANCE SHEET (Assets = Liabilities + Equity)")
# Assets: classes 2,3,4(41-49),5
# Liabilities: class 4(40x)
# Equity: class 1
asset_bal = Decimal('0')
liab_bal = Decimal('0')
equity_bal = Decimal('0')
revenue_bal = Decimal('0')
expense_bal = Decimal('0')

acct_balances = (
    JournalLine.objects
    .values('account__code', 'account__account_type')
    .annotate(
        dr=Sum('debit_amount', default=Decimal('0')),
        cr=Sum('credit_amount', default=Decimal('0'))
    )
)

for ab in acct_balances:
    code = ab['account__code']
    atype = ab['account__account_type']
    net_dr = ab['dr'] - ab['cr']

    if atype == 'ASSET':
        asset_bal += net_dr
    elif atype == 'LIABILITY':
        liab_bal += net_dr  # normally negative (cr > dr)
    elif atype == 'EQUITY':
        equity_bal += net_dr  # normally negative
    elif atype == 'REVENUE':
        revenue_bal += net_dr  # normally negative (cr side)
    elif atype == 'EXPENSE':
        expense_bal += net_dr  # normally positive (dr side)

net_income = -(revenue_bal) - expense_bal  # revenue is cr, expense is dr
bs_diff = abs(asset_bal - (-liab_bal + -equity_bal + net_income))

check(f"Assets", True, f"{asset_bal:,.0f} FCFA")
check(f"Liabilities", True, f"{-liab_bal:,.0f} FCFA")
check(f"Equity", True, f"{-equity_bal:,.0f} FCFA")
check(f"Net Income (Rev-Exp)", True, f"{net_income:,.0f} FCFA")
check(f"Balance Sheet equation", bs_diff < Decimal('100'),
      f"A - (L+E+NI) = {bs_diff:,.2f}")

# ── 10. P&L ──
print("\n10. PROFIT & LOSS")
check(f"Revenue (Class 7)", True, f"{-revenue_bal:,.0f} FCFA")
check(f"Expenses (Class 6)", True, f"{expense_bal:,.0f} FCFA")
check(f"Net Result", True, f"{net_income:,.0f} FCFA")

# ── 11. Expenses & AP ──
print("\n11. EXPENSES & ACCOUNTS PAYABLE")
exp_count = Expense.objects.count()
check("Expense records", exp_count > 0, f"{exp_count} records")
ap_count = APBill.objects.count()
check("AP Bills", ap_count > 0, f"{ap_count} bills")

# ── 12. Budgets ──
print("\n12. BUDGET MODULE")
bud_count = Budget.objects.count()
check("Budgets defined", bud_count > 0, f"{bud_count} budget lines")

# ── Summary ──
print("\n" + "=" * 70)
passes = sum(1 for s,_,_ in results if s == PASS)
fails = sum(1 for s,_,_ in results if s == FAIL)
warns = sum(1 for s,_,_ in results if s == WARN)
total = len(results)
print(f"  RESULTS: {passes}/{total} PASS | {fails} FAIL | {warns} WARN")
if fails == 0:
    print("  STATUS: ALL CHECKS PASSED — Full ERP chain verified!")
else:
    print(f"  STATUS: {fails} checks failed — review above")
print("=" * 70)
