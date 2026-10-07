#!/usr/bin/env python
"""Finance Director Walkthrough — show what's on every key page."""
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.base')
django.setup()

from apps.billing.models import (
    GLAccount, GLMapping, ServiceSubCategory, ServicePrice,
    Invoice, InvoiceItem, Payment, JournalEntry, JournalLine,
    Expense, APBill, APPayment, APVendor, Budget,
    CashierSession, CashierShift,
    BankAccount, CashToBank, BankReconciliation,
    ChequeBook, ChequeRegister, StaffAdvance,
    CashTransfer, SafeBalance, CashVarianceRegister,
    AssetRegister, AssetDisposal, PettyCashFund,
    FiscalPeriod, CostCenter,
    DiscountApproval, PatientWallet,
    CorporateAccount, InvoiceStatus,
)
from django.db.models import Sum, Count, Q
from decimal import Decimal

def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def row(label, value):
    print(f"  {label:<40} {value}")

# ── 1. WHAT THE FINANCE DIRECTOR DASHBOARD SHOWS ──
section("1. FINANCE DIRECTOR DASHBOARD (billing:finance_director_dashboard)")
from django.utils import timezone
today = timezone.localdate()
first_of_month = today.replace(day=1)
first_of_year = today.replace(month=1, day=1)

rev_today = Payment.objects.filter(is_deleted=False, payment_date__date=today).aggregate(t=Sum('amount'))['t'] or 0
rev_month = Payment.objects.filter(is_deleted=False, payment_date__date__gte=first_of_month).aggregate(t=Sum('amount'))['t'] or 0
rev_ytd = Payment.objects.filter(is_deleted=False, payment_date__date__gte=first_of_year).aggregate(t=Sum('amount'))['t'] or 0
exp_month = Expense.objects.filter(is_deleted=False, approved_by__isnull=False, date__gte=first_of_month).aggregate(t=Sum('amount'))['t'] or 0
exp_ytd = Expense.objects.filter(is_deleted=False, approved_by__isnull=False, date__gte=first_of_year).aggregate(t=Sum('amount'))['t'] or 0

row("Revenue Today", f"{rev_today:,.0f} FCFA")
row("Revenue This Month", f"{rev_month:,.0f} FCFA")
row("Revenue YTD", f"{rev_ytd:,.0f} FCFA")
row("Expenses This Month", f"{exp_month:,.0f} FCFA")
row("Expenses YTD", f"{exp_ytd:,.0f} FCFA")
row("Net This Month", f"{rev_month - exp_month:,.0f} FCFA")
row("Net YTD", f"{rev_ytd - exp_ytd:,.0f} FCFA")

# ── 2. CHART OF ACCOUNTS ──
section("2. CHART OF ACCOUNTS (billing:chart_of_accounts)")
for cls in range(1, 9):
    cnt = GLAccount.objects.filter(is_active=True, code__startswith=str(cls)).count()
    labels = {1:'Capital/Equity',2:'Fixed Assets',3:'Inventory',4:'Receivables/Payables',
              5:'Cash/Bank',6:'Expenses',7:'Revenue',8:'Other'}
    row(f"Class {cls} — {labels.get(cls,'')}", f"{cnt} accounts")
row("TOTAL", f"{GLAccount.objects.filter(is_active=True).count()} accounts")

# ── 3. JOURNAL ENTRIES ──
section("3. JOURNAL ENTRIES (billing:journal_entry_list)")
je_count = JournalEntry.objects.count()
jl_count = JournalLine.objects.count()
row("Total Journal Entries", je_count)
row("Total Journal Lines", jl_count)
print("\n  Last 10 Journal Entries:")
for je in JournalEntry.objects.order_by('-entry_date', '-created_at')[:10]:
    lines = je.lines.aggregate(dr=Sum('debit_amount'), cr=Sum('credit_amount'))
    print(f"    {je.entry_date} | {je.reference:<20} | Dr {lines['dr'] or 0:>12,.0f} | Cr {lines['cr'] or 0:>12,.0f} | {je.description[:50]}")

# ── 4. GENERAL LEDGER — WHY IT MAY LOOK EMPTY ──
section("4. GENERAL LEDGER (billing:general_ledger)")
# The GL page requires selecting an account. Show which accounts have activity.
active_accounts = (
    JournalLine.objects.values('account__code', 'account__name')
    .annotate(
        lines=Count('id'),
        total_dr=Sum('debit_amount'),
        total_cr=Sum('credit_amount'),
    )
    .order_by('account__code')
)
row("Accounts with journal activity", active_accounts.count())
print("\n  Accounts with GL Activity (select these to see ledger):")
for a in active_accounts:
    net = (a['total_dr'] or 0) - (a['total_cr'] or 0)
    print(f"    {a['account__code']} {a['account__name'][:35]:<35} | {a['lines']:>3} lines | Dr {a['total_dr'] or 0:>12,.0f} | Cr {a['total_cr'] or 0:>12,.0f} | Net {net:>12,.0f}")

# ── 5. TRIAL BALANCE ──
section("5. TRIAL BALANCE (billing:trial_balance)")
totals = JournalLine.objects.aggregate(dr=Sum('debit_amount'), cr=Sum('credit_amount'))
row("Total Debits", f"{totals['dr'] or 0:,.0f} FCFA")
row("Total Credits", f"{totals['cr'] or 0:,.0f} FCFA")
row("Difference", f"{(totals['dr'] or 0) - (totals['cr'] or 0):,.2f} FCFA")

# ── 6. BALANCE SHEET ──
section("6. BALANCE SHEET (billing:balance_sheet)")
asset_bal = Decimal('0')
liab_bal = Decimal('0')
equity_bal = Decimal('0')
revenue_bal = Decimal('0')
expense_bal = Decimal('0')
for a in active_accounts:
    code = a['account__code']
    net = (a['total_dr'] or Decimal('0')) - (a['total_cr'] or Decimal('0'))
    if code.startswith(('2','3','5')) or (code.startswith('4') and not code.startswith('40')):
        asset_bal += net
    elif code.startswith('40'):
        liab_bal += net
    elif code.startswith('1'):
        equity_bal += net
    elif code.startswith('7'):
        revenue_bal += net
    elif code.startswith('6'):
        expense_bal += net

net_income = -revenue_bal - expense_bal
row("Assets (Class 2+3+4x+5)", f"{asset_bal:,.0f} FCFA")
row("Liabilities (Class 40x)", f"{-liab_bal:,.0f} FCFA")
row("Equity (Class 1)", f"{-equity_bal:,.0f} FCFA")
row("Net Income (Rev - Exp)", f"{net_income:,.0f} FCFA")

# ── 7. P&L ──
section("7. PROFIT & LOSS (billing:report_pl)")
row("Revenue (Class 7)", f"{-revenue_bal:,.0f} FCFA")
row("Expenses (Class 6)", f"{expense_bal:,.0f} FCFA")
row("Net Result", f"{net_income:,.0f} FCFA")

# ── 8. INVOICES ──
section("8. INVOICES (billing:invoice_list)")
for status in ['ISSUED', 'PARTIALLY_PAID', 'PAID', 'CANCELLED', 'REFUNDED']:
    cnt = Invoice.objects.filter(status=status).count()
    if cnt > 0:
        row(f"Status: {status}", cnt)
row("TOTAL invoices", Invoice.objects.count())

# ── 9. SALES JOURNAL ──
section("9. SALES JOURNAL (billing:sales_journal)")
row("Total Payments", Payment.objects.count())
total_paid = Payment.objects.filter(is_deleted=False).aggregate(t=Sum('amount'))['t'] or 0
row("Total Amount Collected", f"{total_paid:,.0f} FCFA")
# By method
from django.db.models import Count as Cnt
methods = Payment.objects.filter(is_deleted=False).values('payment_method').annotate(c=Cnt('id'), t=Sum('amount')).order_by('-t')
for m in methods:
    row(f"  {m['payment_method']}", f"{m['c']} payments = {m['t']:,.0f} FCFA")

# ── 10. WHAT'S IN OTHER PAGES ──
section("10. OTHER FINANCIAL PAGES — DATA STATUS")
row("AP Vendors", APVendor.objects.count())
row("AP Bills", APBill.objects.count())
row("AP Payments", APPayment.objects.count())
row("Expenses", Expense.objects.count())
row("Petty Cash Funds", PettyCashFund.objects.filter(is_deleted=False).count())
row("Staff Advances", StaffAdvance.objects.filter(is_deleted=False).count())
row("Bank Accounts", BankAccount.objects.filter(is_deleted=False).count())
row("Bank Reconciliations", BankReconciliation.objects.filter(is_deleted=False).count())
row("Cash-to-Bank Deposits", CashToBank.objects.filter(is_deleted=False).count())
row("Cheque Books", ChequeBook.objects.filter(is_deleted=False).count())
row("Cash Transfers", CashTransfer.objects.filter(is_deleted=False).count())
row("Safe Balances", SafeBalance.objects.filter(is_deleted=False).count())
row("Cash Variances", CashVarianceRegister.objects.filter(is_deleted=False).count())
row("Fixed Assets", AssetRegister.objects.filter(is_deleted=False).count())
row("Asset Disposals", AssetDisposal.objects.filter(is_deleted=False).count())
row("Budgets", Budget.objects.count())
row("Cost Centers", CostCenter.objects.filter(is_deleted=False).count())
row("Fiscal Periods", FiscalPeriod.objects.filter(is_deleted=False).count())
row("Proforma Invoices", "N/A")
row("Discount Approvals", DiscountApproval.objects.count())
row("Patient Wallets", PatientWallet.objects.count())
row("Corporate Accounts", CorporateAccount.objects.filter(is_deleted=False).count())
row("GL Mappings", GLMapping.objects.count())
row("Billing Days", "N/A")
row("Cashier Sessions", CashierSession.objects.count())
row("Cashier Shifts", CashierShift.objects.count())

print("\n" + "="*60)
print("  SUMMARY")
print("="*60)
print("""
  The GENERAL LEDGER page requires you to SELECT an account
  from the dropdown. If you don't select one, it shows empty.

  To see GL activity:
  1. Go to General Ledger page
  2. Select an account from the dropdown (e.g. 571000 - Cash)
  3. Click "View" — all journal lines for that account appear

  Accounts with the most activity are listed above in section 4.
""")
