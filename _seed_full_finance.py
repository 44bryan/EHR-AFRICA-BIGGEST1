"""
Seed comprehensive financial data across ALL major GL account classes
so the trial balance, auxiliary balance, and cost center P&L show meaningful data.
"""
import sys, os, django, random
from decimal import Decimal
from datetime import date, timedelta

sys.path.insert(0, "/opt/ehr-africa")
os.environ["DJANGO_SETTINGS_MODULE"] = "ehr_project.settings.base"
django.setup()

from apps.billing.models import (
    GLAccount, JournalEntry, JournalLine, JournalType, CostCenter, FiscalPeriod
)
from apps.accounts.models import User

admin = User.objects.filter(is_superuser=True).first()
print(f"Admin: {admin.username}")

# ── 1. Create Cost Centers ──────────────────────────────────────────
cost_centers_data = [
    ("OPD", "Outpatient Department"),
    ("OPT", "Optical Shop"),
    ("PHR", "Pharmacy"),
    ("IPD", "Inpatient Department"),
    ("SRG", "Surgery / Theatre"),
    ("LAB", "Laboratory"),
    ("RAD", "Radiology / Imaging"),
    ("ADM", "Administration"),
    ("FIN", "Finance & Accounts"),
    ("HRM", "Human Resources"),
    ("MNT", "Maintenance & Facilities"),
    ("OUT", "Outreach & Community"),
    ("LVS", "Low Vision Services"),
    ("ORT", "Orthoptics"),
    ("NUR", "Nursing Department"),
]

centers = {}
for code, name in cost_centers_data:
    cc, created = CostCenter.objects.get_or_create(
        code=code,
        defaults={"name": name, "created_by": admin}
    )
    centers[code] = cc
    if created:
        print(f"  Created CC: {code} - {name}")
    else:
        print(f"  Exists CC: {code}")

print(f"Cost Centers: {len(centers)} total")

# ── 2. Get or create fiscal period ──────────────────────────────────
fp_oct, _ = FiscalPeriod.objects.get_or_create(
    year=2026, month=10,
    defaults={"status": "OPEN", "created_by": admin}
)
fp_sep, _ = FiscalPeriod.objects.get_or_create(
    year=2026, month=9,
    defaults={"status": "OPEN", "created_by": admin}
)
print(f"Fiscal periods: Sep 2026, Oct 2026")

# ── 3. Get Journal Types ───────────────────────────────────────────
jt = {}
for j in JournalType.objects.filter(is_deleted=False):
    jt[j.code] = j
print(f"Journal types loaded: {list(jt.keys())}")

# ── 4. Helper: get GL account by code ──────────────────────────────
acct_cache = {}
def acct(code):
    if code not in acct_cache:
        a = GLAccount.objects.filter(code=code, is_deleted=False).first()
        if not a:
            # Try startswith for shorter codes
            a = GLAccount.objects.filter(code__startswith=code, is_deleted=False).order_by("code").first()
        if not a:
            print(f"  WARNING: Account {code} not found!")
        acct_cache[code] = a
    return acct_cache[code]

# ── 5. Helper: create balanced journal entry ───────────────────────
entry_counter = [0]
def post_entry(desc, lines, journal_type_code, cost_center_code=None, entry_date=None):
    """Create a posted journal entry with balanced lines.
    lines = [(acct_code, debit, credit), ...]
    """
    if entry_date is None:
        entry_date = date(2026, 10, 1) + timedelta(days=random.randint(0, 4))

    cc = centers.get(cost_center_code) if cost_center_code else None
    j_type = jt.get(journal_type_code)

    entry = JournalEntry.objects.create(
        entry_date=entry_date,
        reference=f"SEED-{entry_counter[0]:04d}",
        description=desc,
        is_posted=True,
        status="POSTED",
        source_type="MANUAL",
        journal_type=j_type,
        cost_center=cc,
        created_by=admin,
    )

    total_dr = Decimal("0")
    total_cr = Decimal("0")
    for acct_code, dr, cr in lines:
        account = acct(acct_code)
        if not account:
            continue
        JournalLine.objects.create(
            entry=entry,
            account=account,
            description=desc[:200],
            debit_amount=Decimal(str(dr)),
            credit_amount=Decimal(str(cr)),
        )
        total_dr += Decimal(str(dr))
        total_cr += Decimal(str(cr))

    entry_counter[0] += 1
    return entry

# ══════════════════════════════════════════════════════════════════════
# CLASS 1 — EQUITY & LONG-TERM LIABILITIES
# ══════════════════════════════════════════════════════════════════════

print("\n--- Class 1: Equity & Liabilities ---")

# Opening capital
post_entry("Opening capital contribution", [
    ("521100", 50000000, 0),      # Dr Bank
    ("101100", 0, 50000000),      # Cr Capital
], "AN", "FIN", date(2026, 1, 1))

# Investment subvention received
post_entry("Government health subvention Q3 2026", [
    ("521100", 15000000, 0),      # Dr Bank
    ("141100", 0, 15000000),      # Cr Etat subvention
], "OD", "FIN", date(2026, 9, 15))

# Statutory reserve allocation
post_entry("Annual reserve allocation", [
    ("131000", 2000000, 0),       # Dr Net Result Surplus
    ("112000", 0, 2000000),       # Cr Statutory Reserves
], "OD", "FIN", date(2026, 9, 30))

# Long-term loan from bank
post_entry("Equipment loan - Afriland First Bank", [
    ("521100", 25000000, 0),      # Dr Bank
    ("162000", 0, 25000000),      # Cr Allocated Funds
], "BQ", "FIN", date(2026, 3, 1))

print("  Class 1 entries posted")

# ══════════════════════════════════════════════════════════════════════
# CLASS 2 — FIXED ASSETS
# ══════════════════════════════════════════════════════════════════════

print("--- Class 2: Fixed Assets ---")

# Medical equipment purchase
post_entry("Slit lamp acquisition - Haag Streit", [
    ("241300", 12500000, 0),      # Dr Medical Equipment
    ("521100", 0, 12500000),      # Cr Bank
], "BQ", "OPD", date(2026, 2, 15))

# OCT machine
post_entry("OCT Heidelberg Spectralis acquisition", [
    ("241300", 45000000, 0),      # Dr Medical Equipment
    ("521100", 0, 45000000),      # Cr Bank
], "BQ", "OPD", date(2026, 3, 10))

# Office furniture
post_entry("Office furniture - reception area", [
    ("244100", 3500000, 0),       # Dr Office Equipment
    ("521100", 0, 3500000),       # Cr Bank
], "BQ", "ADM", date(2026, 4, 1))

# Computer equipment
post_entry("Server and workstations purchase", [
    ("244400", 8500000, 0),       # Dr IT Equipment
    ("521100", 0, 8500000),       # Cr Bank
], "BQ", "ADM", date(2026, 5, 1))

# Vehicle
post_entry("Outreach vehicle - Toyota Hilux", [
    ("245100", 22000000, 0),      # Dr Vehicles
    ("521100", 0, 22000000),      # Cr Bank
], "BQ", "OUT", date(2026, 6, 1))

# Depreciation entries (monthly)
for month in range(1, 11):
    d = date(2026, month, 28)
    post_entry(f"Monthly depreciation - {d.strftime('%B')} 2026", [
        ("681200", 1250000, 0),   # Dr Depreciation expense
        ("284130", 0, 1250000),   # Cr Accumulated depreciation (or 281)
    ], "OD", "ADM", d)

print("  Class 2 entries posted")

# ══════════════════════════════════════════════════════════════════════
# CLASS 3 — INVENTORIES
# ══════════════════════════════════════════════════════════════════════

print("--- Class 3: Inventories ---")

# Optical stock purchases
for i in range(8):
    amt = random.randint(500000, 3000000)
    d = date(2026, 9, 1) + timedelta(days=random.randint(0, 29))
    post_entry(f"Optical stock purchase #{i+1}", [
        ("311001", amt, 0),       # Dr Stock of Frames
        ("603100", 0, amt),       # Cr Cost of Sales Frames (variation)
    ], "ST", "OPT", d)

# Lens stock
for i in range(6):
    amt = random.randint(400000, 2500000)
    d = date(2026, 9, 1) + timedelta(days=random.randint(0, 29))
    post_entry(f"Lens stock purchase #{i+1}", [
        ("311002", amt, 0),       # Dr Stock of Lenses
        ("603101", 0, amt),       # Cr Cost of Sales Lenses
    ], "ST", "OPT", d)

# Pharmacy stock
for i in range(10):
    amt = random.randint(300000, 2000000)
    d = date(2026, 9, 1) + timedelta(days=random.randint(0, 29))
    post_entry(f"Pharmacy stock purchase #{i+1}", [
        ("321000", amt, 0),       # Dr Merchandise stock
        ("603109", 0, amt),       # Cr Cost of Sales Medication
    ], "ST", "PHR", d)

# Consumables stock
for i in range(5):
    amt = random.randint(200000, 800000)
    d = date(2026, 9, 1) + timedelta(days=random.randint(0, 29))
    post_entry(f"Medical consumables purchase #{i+1}", [
        ("321000", amt, 0),       # Dr Merchandise
        ("603110", 0, amt),       # Cr Cost of Sales Consumables
    ], "ST", "SRG", d)

# Stock exits (consumption)
for i in range(12):
    amt = random.randint(100000, 1500000)
    d = date(2026, 9, 1) + timedelta(days=random.randint(0, 29))
    cc = random.choice(["OPT", "PHR", "SRG", "OPD"])
    post_entry(f"Stock consumption - {cc}", [
        ("603100", amt, 0),       # Dr Variation de stocks
        ("311001", 0, amt),       # Cr Stock
    ], "ST", cc, d)

print("  Class 3 entries posted")

# ══════════════════════════════════════════════════════════════════════
# CLASS 4 — RECEIVABLES & PAYABLES
# ══════════════════════════════════════════════════════════════════════

print("--- Class 4: Receivables & Payables ---")

# Supplier invoices (purchases on credit)
suppliers = [
    ("401100", "Essilor Cameroun - lens order", 4500000),
    ("401100", "Marchon eyewear - frame order", 3200000),
    ("401100", "COPHAC - medication supply", 2800000),
    ("401100", "Ubipharm - pharmacy restock", 1900000),
    ("401100", "Laborex - surgical consumables", 3500000),
]
for acct_code, desc, amt in suppliers:
    d = date(2026, 9, random.randint(1, 28))
    post_entry(f"Supplier invoice: {desc}", [
        ("601100", amt, 0),       # Dr Purchases
        (acct_code, 0, amt),      # Cr Supplier
    ], "AC", "OPT", d)

# Supplier payments
for i in range(3):
    amt = random.randint(1500000, 4000000)
    d = date(2026, 9, random.randint(10, 28))
    post_entry(f"Supplier payment #{i+1}", [
        ("401100", amt, 0),       # Dr Supplier (reduce payable)
        ("521100", 0, amt),       # Cr Bank
    ], "BQ", "FIN", d)

# Patient receivables (insurance claims)
for i in range(15):
    amt = random.randint(50000, 500000)
    d = date(2026, 9, random.randint(1, 28))
    cc = random.choice(["OPD", "OPT", "PHR", "SRG", "LAB"])
    post_entry(f"Insurance claim - patient #{i+1}", [
        ("411000", amt, 0),       # Dr Members receivable
        ("706000", 0, amt),       # Cr Consultation revenue
    ], "VE", cc, d)

# Insurance payments received
for i in range(8):
    amt = random.randint(200000, 800000)
    d = date(2026, 9, random.randint(10, 28))
    post_entry(f"Insurance payment received #{i+1}", [
        ("521100", amt, 0),       # Dr Bank
        ("411000", 0, amt),       # Cr Members receivable
    ], "BQ", "FIN", d)

# Staff advances
for i in range(3):
    amt = random.randint(100000, 500000)
    d = date(2026, 9, random.randint(1, 20))
    post_entry(f"Staff advance #{i+1}", [
        ("421000", amt, 0),       # Dr Staff advance
        ("571000", 0, amt),       # Cr Cash
    ], "CA", "HRM", d)

# Tax payable (IRPP withholding)
post_entry("Monthly IRPP withholding - September", [
    ("664100", 1850000, 0),       # Dr Tax expense
    ("447100", 0, 1850000),       # Cr Tax payable
], "SA", "HRM", date(2026, 9, 30))

# CNPS contributions
post_entry("CNPS employer contribution - September", [
    ("664200", 2100000, 0),       # Dr Social charges
    ("431100", 0, 2100000),       # Cr CNPS payable
], "SA", "HRM", date(2026, 9, 30))

print("  Class 4 entries posted")

# ══════════════════════════════════════════════════════════════════════
# CLASS 5 — CASH & BANK
# ══════════════════════════════════════════════════════════════════════

print("--- Class 5: Cash & Bank ---")

# Daily cash receipts (OPD consultations)
for day in range(1, 26):
    d = date(2026, 9, day)
    amt = random.randint(150000, 800000)
    post_entry(f"Daily OPD cash receipts - Sep {day}", [
        ("571000", amt, 0),       # Dr Cash
        ("706000", 0, amt),       # Cr Consultation revenue
    ], "CA", "OPD", d)

# Cash deposits to bank
for i in range(4):
    amt = random.randint(2000000, 5000000)
    d = date(2026, 9, random.choice([7, 14, 21, 28]))
    post_entry(f"Cash deposit to bank #{i+1}", [
        ("521100", amt, 0),       # Dr Bank
        ("571000", 0, amt),       # Cr Cash
    ], "CA", "FIN", d)

# Bank charges
post_entry("Monthly bank charges - September", [
    ("631100", 45000, 0),         # Dr Bank charges
    ("521100", 0, 45000),         # Cr Bank
], "BQ", "FIN", date(2026, 9, 30))

# Petty cash replenishment
for i in range(2):
    amt = random.randint(200000, 500000)
    d = date(2026, 9, random.randint(1, 28))
    post_entry(f"Petty cash replenishment #{i+1}", [
        ("571000", amt, 0),       # Dr Cash
        ("521100", 0, amt),       # Cr Bank
    ], "CA", "ADM", d)

print("  Class 5 entries posted")

# ══════════════════════════════════════════════════════════════════════
# CLASS 6 — EXPENSES
# ══════════════════════════════════════════════════════════════════════

print("--- Class 6: Expenses ---")

# Salaries
post_entry("September salaries - medical staff", [
    ("661100", 8500000, 0),       # Dr Salaries
    ("521100", 0, 8500000),       # Cr Bank
], "SA", "OPD", date(2026, 9, 28))

post_entry("September salaries - admin & support", [
    ("661100", 4200000, 0),       # Dr Salaries
    ("521100", 0, 4200000),       # Cr Bank
], "SA", "ADM", date(2026, 9, 28))

post_entry("September salaries - nursing", [
    ("661100", 5800000, 0),       # Dr Salaries
    ("521100", 0, 5800000),       # Cr Bank
], "SA", "NUR", date(2026, 9, 28))

post_entry("September salaries - pharmacy", [
    ("661100", 2800000, 0),       # Dr Salaries
    ("521100", 0, 2800000),       # Cr Bank
], "SA", "PHR", date(2026, 9, 28))

post_entry("September salaries - lab techs", [
    ("661100", 1900000, 0),       # Dr Salaries
    ("521100", 0, 1900000),       # Cr Bank
], "SA", "LAB", date(2026, 9, 28))

# Rent
post_entry("Monthly rent - September 2026", [
    ("622100", 2500000, 0),       # Dr Rent expense
    ("521100", 0, 2500000),       # Cr Bank
], "OD", "ADM", date(2026, 9, 5))

# Utilities
post_entry("Electricity bill - September", [
    ("605200", 850000, 0),        # Dr Electricity
    ("521100", 0, 850000),        # Cr Bank
], "OD", "MNT", date(2026, 9, 15))

post_entry("Water bill - September", [
    ("605100", 180000, 0),        # Dr Water
    ("521100", 0, 180000),        # Cr Bank
], "OD", "MNT", date(2026, 9, 15))

# Internet & telecom
post_entry("Internet & telecom - September", [
    ("626100", 350000, 0),        # Dr Telecom
    ("521100", 0, 350000),        # Cr Bank
], "OD", "ADM", date(2026, 9, 10))

# Insurance premium
post_entry("Professional liability insurance Q3", [
    ("625100", 1500000, 0),       # Dr Insurance premium
    ("521100", 0, 1500000),       # Cr Bank
], "OD", "ADM", date(2026, 9, 1))

# Maintenance & repairs
for i in range(3):
    amt = random.randint(100000, 500000)
    d = date(2026, 9, random.randint(1, 28))
    post_entry(f"Equipment maintenance #{i+1}", [
        ("624100", amt, 0),       # Dr Maintenance expense
        ("571000", 0, amt),       # Cr Cash
    ], "CA", "MNT", d)

# Transport / outreach costs
for i in range(2):
    amt = random.randint(200000, 600000)
    d = date(2026, 9, random.randint(1, 28))
    post_entry(f"Outreach transport #{i+1}", [
        ("614100", amt, 0),       # Dr Transport expense
        ("571000", 0, amt),       # Cr Cash
    ], "CA", "OUT", d)

# Office supplies
post_entry("Office supplies - September", [
    ("604700", 250000, 0),        # Dr Office supplies
    ("571000", 0, 250000),        # Cr Cash
], "CA", "ADM", date(2026, 9, 8))

# Cleaning supplies
post_entry("Cleaning products - September", [
    ("604300", 150000, 0),        # Dr Cleaning
    ("571000", 0, 150000),        # Cr Cash
], "CA", "MNT", date(2026, 9, 12))

# Training / continuing education
post_entry("Staff training workshop - ophthalmology", [
    ("658000", 750000, 0),        # Dr Training expense
    ("521100", 0, 750000),        # Cr Bank
], "OD", "HRM", date(2026, 9, 20))

# Printing
post_entry("Patient folder printing", [
    ("604700", 320000, 0),        # Dr Office supplies
    ("571000", 0, 320000),        # Cr Cash
], "CA", "ADM", date(2026, 9, 18))

print("  Class 6 entries posted")

# ══════════════════════════════════════════════════════════════════════
# CLASS 7 — REVENUE
# ══════════════════════════════════════════════════════════════════════

print("--- Class 7: Revenue ---")

# Optical sales
for i in range(20):
    amt = random.randint(25000, 350000)
    d = date(2026, 9, random.randint(1, 28))
    post_entry(f"Optical sale #{i+1}", [
        ("571000", amt, 0),       # Dr Cash
        ("707000", 0, amt),       # Cr Optical revenue
    ], "VE", "OPT", d)

# Pharmacy sales
for i in range(25):
    amt = random.randint(5000, 150000)
    d = date(2026, 9, random.randint(1, 28))
    post_entry(f"Pharmacy sale #{i+1}", [
        ("571000", amt, 0),       # Dr Cash
        ("701000", 0, amt),       # Cr Pharmacy revenue
    ], "VE", "PHR", d)

# Surgery revenue
for i in range(6):
    amt = random.randint(200000, 1500000)
    d = date(2026, 9, random.randint(1, 28))
    post_entry(f"Surgical procedure #{i+1}", [
        ("571000", amt, 0),       # Dr Cash
        ("706000", 0, amt),       # Cr Consultation/procedure revenue
    ], "VE", "SRG", d)

# Lab investigation revenue
for i in range(15):
    amt = random.randint(10000, 80000)
    d = date(2026, 9, random.randint(1, 28))
    post_entry(f"Lab investigation #{i+1}", [
        ("571000", amt, 0),       # Dr Cash
        ("706000", 0, amt),       # Cr Revenue
    ], "VE", "LAB", d)

# IPD bed charges
for i in range(4):
    amt = random.randint(100000, 500000)
    d = date(2026, 9, random.randint(1, 28))
    post_entry(f"IPD bed charges #{i+1}", [
        ("571000", amt, 0),       # Dr Cash
        ("706000", 0, amt),       # Cr Revenue
    ], "VE", "IPD", d)

# Donation revenue received
post_entry("CBM grant - Q3 program funding", [
    ("521100", 8000000, 0),       # Dr Bank
    ("758200", 0, 8000000),       # Cr Donations received
], "OD", "OUT", date(2026, 9, 5))

post_entry("Sightsavers contribution - screening program", [
    ("521100", 5000000, 0),       # Dr Bank
    ("758200", 0, 5000000),       # Cr Donations received
], "OD", "OUT", date(2026, 9, 12))

# Interest income
post_entry("Bank interest income - September", [
    ("521100", 125000, 0),        # Dr Bank
    ("771000", 0, 125000),        # Cr Interest income
], "BQ", "FIN", date(2026, 9, 30))

print("  Class 7 entries posted")

# ══════════════════════════════════════════════════════════════════════
# CLASS 8 — (Special accounts - less common)
# ══════════════════════════════════════════════════════════════════════

print("--- Class 8: Special ---")

# Exceptional gain (insurance claim for damaged equipment)
post_entry("Insurance claim - damaged autoclave", [
    ("521100", 2500000, 0),       # Dr Bank
    ("841000", 0, 2500000),       # Cr Exceptional income
], "OD", "ADM", date(2026, 9, 25))

print("  Class 8 entries posted")

# ══════════════════════════════════════════════════════════════════════
# OCTOBER 2026 — Current month entries
# ══════════════════════════════════════════════════════════════════════

print("--- October 2026 (current month) ---")

# OPD cash for first 5 days of October
for day in range(1, 6):
    d = date(2026, 10, day)
    amt = random.randint(200000, 900000)
    post_entry(f"Daily OPD cash - Oct {day}", [
        ("571000", amt, 0),
        ("706000", 0, amt),
    ], "CA", "OPD", d)

# Optical sales October
for i in range(5):
    amt = random.randint(30000, 300000)
    d = date(2026, 10, random.randint(1, 5))
    post_entry(f"Optical sale Oct #{i+1}", [
        ("571000", amt, 0),
        ("707000", 0, amt),
    ], "VE", "OPT", d)

# Pharmacy sales October
for i in range(8):
    amt = random.randint(5000, 120000)
    d = date(2026, 10, random.randint(1, 5))
    post_entry(f"Pharmacy sale Oct #{i+1}", [
        ("571000", amt, 0),
        ("701000", 0, amt),
    ], "VE", "PHR", d)

print("  October entries posted")

# ══════════════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════════════

total_entries = JournalEntry.objects.filter(is_deleted=False, is_posted=True).count()
total_lines = JournalLine.objects.count()
from django.db.models import Sum
totals = JournalLine.objects.aggregate(
    total_dr=Sum("debit_amount"),
    total_cr=Sum("credit_amount"),
)

print(f"\n{'='*60}")
print(f"TOTAL posted entries: {total_entries}")
print(f"TOTAL journal lines:  {total_lines}")
print(f"TOTAL debits:  {totals['total_dr']:,.0f} FCFA")
print(f"TOTAL credits: {totals['total_cr']:,.0f} FCFA")
diff = (totals['total_dr'] or 0) - (totals['total_cr'] or 0)
print(f"DIFFERENCE:    {diff:,.0f} FCFA {'(BALANCED!)' if diff == 0 else '*** IMBALANCED ***'}")
print(f"{'='*60}")

# Show accounts with activity
print(f"\nAccounts with journal activity:")
active_accounts = JournalLine.objects.values("account__code", "account__name").annotate(
    dr=Sum("debit_amount"), cr=Sum("credit_amount")
).order_by("account__code")
for aa in active_accounts:
    print(f"  {aa['account__code']} | {aa['account__name'][:40]:40s} | Dr {aa['dr'] or 0:>15,.0f} | Cr {aa['cr'] or 0:>15,.0f}")

print(f"\nTotal accounts with activity: {active_accounts.count()}")
print("\nSeed complete!")
