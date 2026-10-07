"""
Seed comprehensive accounting data to verify the full ERP flow:
  Sales → Journal Entries → General Ledger → Trial Balance → Balance Sheet → P&L

Run: python manage.py shell < _seed_accounting.py
"""
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.base')
django.setup()

from decimal import Decimal
from datetime import date, timedelta
from django.utils import timezone
from apps.accounts.models import User, UserRole
from apps.patients.models import Patient
from apps.billing.models import (
    Invoice, InvoiceItem, Payment, Expense,
    ServiceCategory, PaymentMethod, InvoiceStatus, ExpenseCategory,
    APVendor, APBill, APPayment, APBillStatus,
    GLAccount,
)
from apps.billing import gl_service

print("=" * 60)
print("SEEDING COMPREHENSIVE ACCOUNTING DATA")
print("=" * 60)

# ── Get or create users ──────────────────────────────────────
admin = User.objects.filter(is_superuser=True).first()
cashier = User.objects.filter(role=UserRole.CASHIER).first() or admin
fin_dir = User.objects.filter(role=UserRole.FINANCE_DIRECTOR).first() or admin
sr_acct = User.objects.filter(role=UserRole.SENIOR_ACCOUNTANT).first() or admin

print(f"Admin: {admin}")
print(f"Cashier: {cashier}")
print(f"Finance Director: {fin_dir}")
print(f"Senior Accountant: {sr_acct}")

# ── Get patients ─────────────────────────────────────────────
patients = list(Patient.objects.filter(is_deleted=False)[:5])
if len(patients) < 3:
    print("ERROR: Need at least 3 patients. Please seed patients first.")
    exit()
print(f"Using {len(patients)} patients: {[p.full_name for p in patients]}")

today = date.today()
yesterday = today - timedelta(days=1)
last_week = today - timedelta(days=7)
two_weeks = today - timedelta(days=14)

created_invoices = []
created_payments = []
created_expenses = []
created_bills = []
created_bill_payments = []

# ═══════════════════════════════════════════════════════════════
# 1. SALES INVOICES — Different service categories
# ═══════════════════════════════════════════════════════════════
print("\n── Creating Sales Invoices ──")

invoice_data = [
    # (patient_idx, date, status, items: [(cat, desc, qty, price)], payments: [(method, amount)])
    (0, two_weeks, 'full_cash', [
        ('CONSULT', 'General Consultation', 1, 15000),
        ('INVEST', 'Visual Acuity Test', 1, 5000),
        ('PHARMACY', 'Timolol 0.5% Eye Drops', 2, 3500),
    ], [('CASH', 27000)]),  # Fully paid cash

    (1, last_week, 'full_card', [
        ('CONSULT', 'Specialist Ophthalmology Consultation', 1, 25000),
        ('INVEST', 'OCT Scan — Both Eyes', 1, 35000),
        ('LAB', 'Blood Sugar (FBS)', 1, 5000),
        ('PHARMACY', 'Latanoprost Eye Drops', 1, 12000),
    ], [('CARD', 77000)]),  # Fully paid by POS card

    (2, last_week, 'partial_payment', [
        ('SURGICAL', 'Cataract Surgery — Left Eye (Phaco+IOL)', 1, 350000),
        ('ADMISSION', 'Day Case Admission', 1, 25000),
        ('PHARMACY', 'Post-Op Medication Pack', 1, 15000),
    ], [('CASH', 200000), ('MOBILE', 100000)]),  # Partial: 300k of 390k → 90k AR

    (0, yesterday, 'mobile_money', [
        ('OPTICAL', 'Progressive Lenses — High Index', 2, 45000),
        ('OPTICAL', 'Titanium Frame — Designer', 1, 85000),
    ], [('MOBILE', 175000)]),  # Fully paid mobile money

    (3 if len(patients) > 3 else 0, yesterday, 'multi_method', [
        ('CONSULT', 'Pediatric Eye Exam', 1, 20000),
        ('INVEST', 'Refraction — Both Eyes', 1, 10000),
        ('PHARMACY', 'Artificial Tears', 3, 2500),
    ], [('CASH', 20000), ('CARD', 17500)]),  # Fully paid split cash+card

    (4 if len(patients) > 4 else 1, today, 'transfer_full', [
        ('CONSULT', 'Glaucoma Follow-Up', 1, 15000),
        ('INVEST', 'Visual Field Test (Humphrey)', 1, 25000),
        ('INVEST', 'IOP Measurement (Goldmann)', 1, 5000),
        ('PHARMACY', 'Brimonidine Eye Drops', 1, 8000),
        ('PHARMACY', 'Acetazolamide Tablets 250mg', 1, 4500),
    ], [('TRANSFER', 57500)]),  # Fully paid bank transfer

    (1, today, 'unpaid_invoice', [
        ('REG', 'Registration Fee', 1, 5000),
        ('CONSULT', 'Emergency Eye Consultation', 1, 30000),
        ('INVEST', 'B-Scan Ultrasound', 1, 20000),
    ], []),  # UNPAID — purely AR
]

for pat_idx, inv_date, label, items, payments in invoice_data:
    patient = patients[pat_idx]
    inv = Invoice(
        patient=patient,
        status=InvoiceStatus.DRAFT,
        issue_date=inv_date,
        created_by=admin,
    )
    inv.save()

    for cat, desc, qty, price in items:
        InvoiceItem.objects.create(
            invoice=inv,
            category=cat,
            description=desc,
            quantity=qty,
            unit_price=Decimal(str(price)),
        )

    # Issue the invoice → triggers GL auto-post (Dr AR / Cr Revenue)
    inv.status = InvoiceStatus.ISSUED
    inv.save()
    gl_service.post_invoice_issued(inv, user=cashier)
    print(f"  INV {inv.invoice_number}: {inv.total:,.0f} XAF — {label} — {patient.full_name}")
    created_invoices.append(inv)

    # Record payments
    total_paid = Decimal('0')
    for method, amount in payments:
        pmt = Payment(
            invoice=inv,
            payment_method=method,
            amount=Decimal(str(amount)),
            received_by=cashier,
            payment_date=timezone.make_aware(
                timezone.datetime.combine(inv_date, timezone.datetime.min.time().replace(hour=10))
            ),
        )
        pmt.save()
        gl_service.post_payment(pmt)
        total_paid += Decimal(str(amount))
        print(f"    PMT {pmt.receipt_number}: {amount:,.0f} XAF via {method}")
        created_payments.append(pmt)

print(f"\nInvoices created: {len(created_invoices)}")
print(f"Payments created: {len(created_payments)}")


# ═══════════════════════════════════════════════════════════════
# 2. EXPENSES — Operating costs
# ═══════════════════════════════════════════════════════════════
print("\n── Creating Expenses ──")

expense_data = [
    (two_weeks, 'UTILITIES', 'Electricity Bill — September 2026', 85000, 'TRANSFER', 'ENEO Cameroon', 'ENEO-SEP-2026'),
    (two_weeks, 'UTILITIES', 'Water Bill — September 2026', 25000, 'TRANSFER', 'CDE Cameroon', 'CDE-SEP-2026'),
    (last_week, 'SUPPLIES', 'Surgical Gloves (Box x100) — 5 boxes', 45000, 'CASH', 'MedSupply Douala', 'MS-2026-0891'),
    (last_week, 'SUPPLIES', 'Cotton Wool Rolls x20', 12000, 'CASH', 'MedSupply Douala', 'MS-2026-0892'),
    (last_week, 'DRUGS', 'Pharmacy Restock — Antibiotics', 180000, 'TRANSFER', 'CIMENCAM Pharma', 'CP-INV-4521'),
    (yesterday, 'EQUIPMENT', 'Slit Lamp Bulb Replacement', 35000, 'CASH', 'OptiTech Services', 'OTS-0034'),
    (yesterday, 'TRANSPORT', 'Staff Shuttle — Weekly Fuel', 40000, 'CASH', 'Total Energies', 'TE-2026-3322'),
    (today, 'ADMIN', 'Printer Toner Cartridges x3', 27000, 'CASH', 'IT Store Douala', 'ITS-0189'),
    (today, 'RENT', 'Monthly Clinic Lease — October 2026', 500000, 'TRANSFER', 'Landlord SARL', 'RENT-OCT-2026'),
]

for exp_date, cat, desc, amount, method, vendor, ref in expense_data:
    exp = Expense.objects.create(
        date=exp_date,
        category=cat,
        description=desc,
        amount=Decimal(str(amount)),
        payment_method=method,
        vendor=vendor,
        reference=ref,
        approved_by=fin_dir,
        created_by=admin,
    )
    gl_service.post_expense(exp)
    print(f"  EXP: {desc} — {amount:,.0f} XAF ({method})")
    created_expenses.append(exp)

print(f"\nExpenses created: {len(created_expenses)}")


# ═══════════════════════════════════════════════════════════════
# 3. VENDOR BILLS (AP) — Purchases on credit
# ═══════════════════════════════════════════════════════════════
print("\n── Creating AP Vendors & Bills ──")

# Create vendors
vendors_data = [
    ('Pharma Central SARL', 'V-001', 'Jean Mbarga', '+237677123456', 30),
    ('OptiLens International', 'V-002', 'Paul Nkeng', '+237699887766', 45),
    ('MedEquip Cameroun SA', 'V-003', 'Marie Fotso', '+237655443322', 60),
]

vendors = []
for name, code, contact, phone, terms in vendors_data:
    v, _ = APVendor.objects.update_or_create(
        vendor_code=code,
        defaults=dict(
            name=name, contact_name=contact, phone=phone,
            payment_terms_days=terms, is_active=True,
            created_by=admin,
        )
    )
    vendors.append(v)
    print(f"  Vendor: {v.name} ({v.vendor_code})")

# Create bills
bills_data = [
    (vendors[0], two_weeks, 'DRUGS', 'Monthly Drug Supply — Glaucoma Medications', 450000, 'PH-INV-2026-089'),
    (vendors[0], last_week, 'DRUGS', 'Emergency Restock — Post-Op Antibiotics', 120000, 'PH-INV-2026-095'),
    (vendors[1], last_week, 'SUPPLIES', 'Progressive Lenses — Batch Order (50 pairs)', 750000, 'OL-INV-2026-0341'),
    (vendors[1], yesterday, 'SUPPLIES', 'Contact Lens Trial Pack Assortment', 85000, 'OL-INV-2026-0355'),
    (vendors[2], two_weeks, 'EQUIPMENT', 'Autorefractor Annual Service Contract', 350000, 'ME-SVC-2026-012'),
]

for vendor, bill_date, cat, desc, amount, vendor_ref in bills_data:
    bill = APBill(
        vendor=vendor,
        vendor_ref=vendor_ref,
        category=cat,
        description=desc,
        amount_due=Decimal(str(amount)),
        bill_date=bill_date,
        due_date=bill_date + timedelta(days=vendor.payment_terms_days),
        status=APBillStatus.PENDING,
        approved_by=fin_dir,
        created_by=admin,
    )
    bill.save()
    gl_service.post_ap_bill(bill)
    print(f"  BILL {bill.bill_number}: {desc} — {amount:,.0f} XAF from {vendor.name}")
    created_bills.append(bill)


# ═══════════════════════════════════════════════════════════════
# 4. AP PAYMENTS — Pay some vendor bills
# ═══════════════════════════════════════════════════════════════
print("\n── Creating AP Payments ──")

ap_payments_data = [
    (0, yesterday, 450000, 'TRANSFER', 'TRF-AP-2026-001'),  # Full payment of bill 0
    (1, today, 120000, 'TRANSFER', 'TRF-AP-2026-002'),      # Full payment of bill 1
    (2, today, 400000, 'TRANSFER', 'TRF-AP-2026-003'),      # Partial payment of bill 2 (750k)
]

for bill_idx, pay_date, amount, method, ref in ap_payments_data:
    bill = created_bills[bill_idx]
    ap_pmt = APPayment(
        bill=bill,
        payment_date=pay_date,
        amount=Decimal(str(amount)),
        payment_method=method,
        reference=ref,
        paid_by=fin_dir,
        created_by=admin,
    )
    ap_pmt.save()
    gl_service.post_ap_payment(ap_pmt)
    bill.update_status()
    print(f"  AP-PMT: {amount:,.0f} XAF to {bill.vendor.name} — Bill {bill.bill_number} (Status: {bill.status})")
    created_bill_payments.append(ap_pmt)


# ═══════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("SEED COMPLETE — SUMMARY")
print("=" * 60)

total_revenue = sum(inv.total for inv in created_invoices)
total_collected = sum(p.amount for p in created_payments)
total_ar = total_revenue - total_collected
total_expenses = sum(e.amount for e in created_expenses)
total_ap_billed = sum(b.amount_due for b in created_bills)
total_ap_paid = sum(p.amount for p in created_bill_payments)
total_ap_outstanding = total_ap_billed - total_ap_paid

from apps.billing.models import JournalEntry
je_count = JournalEntry.objects.count()

print(f"""
REVENUE (Sales):
  Invoices created:     {len(created_invoices)}
  Total billed:         {total_revenue:>12,.0f} XAF
  Total collected:      {total_collected:>12,.0f} XAF
  Outstanding AR:       {total_ar:>12,.0f} XAF

EXPENSES:
  Expenses recorded:    {len(created_expenses)}
  Total expenses:       {total_expenses:>12,.0f} XAF

ACCOUNTS PAYABLE:
  Vendor bills:         {len(created_bills)}
  Total AP billed:      {total_ap_billed:>12,.0f} XAF
  Total AP paid:        {total_ap_paid:>12,.0f} XAF
  Outstanding AP:       {total_ap_outstanding:>12,.0f} XAF

JOURNAL ENTRIES:
  Total GL entries:     {je_count}

VERIFY IN BROWSER:
  Trial Balance:    /billing/trial-balance/
  Balance Sheet:    /billing/balance-sheet/
  P&L:              /billing/income-statement/
  General Ledger:   /billing/general-ledger/
  Journal Entries:  /billing/journal/
  GL Mappings:      /billing/gl/mappings/
""")

print("Done! Log in and check the financial reports.")
