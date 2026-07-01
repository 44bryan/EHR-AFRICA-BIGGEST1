"""
GL Service — Auto-posting functions for double-entry bookkeeping.

Called by signals when Payments, Expenses, AP Payments are saved.
Maps business transactions → OHADA GL account codes → JournalEntry + JournalLine.
"""
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)

# ── OHADA Account Code Map ─────────────────────────────────────────────────────
# These codes must exist in the GLAccount table (seeded by seed_coa command).

CASH_ACCOUNT          = '572000'   # Main Cash Drawer
BANK_ACCOUNT          = '521000'   # Bank Account
MOBILE_MONEY_ACCOUNT  = '521100'   # Mobile Money (treated as bank)
AR_PATIENT            = '411000'   # Patient Accounts Receivable
AR_INSURANCE          = '412000'   # Insurance Receivables
AR_CORPORATE          = '413000'   # Corporate Receivables
AP_VENDORS            = '401000'   # Accounts Payable (Suppliers)
PATIENT_DEPOSITS      = '499000'   # Patient Wallet / Deposits Liability

# Revenue accounts by ServiceCategory
REVENUE_MAP = {
    'CONSULT':   '701000',
    'INVEST':    '702000',
    'LAB':       '703000',
    'PHARMACY':  '704000',
    'OPTICAL':   '705000',
    'SURGICAL':  '706000',
    'ADMISSION': '707000',
    'REG':       '708000',
    'OTHER':     '709000',
}

# Expense accounts by ExpenseCategory
EXPENSE_MAP = {
    'SUPPLIES':   '602000',
    'UTILITIES':  '642000',
    'SALARY':     '621000',
    'RENT':       '641000',
    'EQUIPMENT':  '643000',
    'DRUGS':      '601000',
    'TRANSPORT':  '653000',
    'ADMIN':      '651000',
    'MARKETING':  '652000',
    'EXP_OTHER':  '658000',
}

# Payment method → GL debit account
PAYMENT_METHOD_ACCOUNT = {
    'CASH':      CASH_ACCOUNT,
    'CARD':      BANK_ACCOUNT,
    'TRANSFER':  BANK_ACCOUNT,
    'MOBILE':    MOBILE_MONEY_ACCOUNT,
    'INSURANCE': AR_INSURANCE,
    'NHIS':      AR_INSURANCE,
    'WAIVER':    None,  # No GL posting for waivers
}


def _get_account(code):
    """Fetch a GLAccount by code. Returns None if not found (GL not seeded yet)."""
    from apps.billing.models import GLAccount
    try:
        return GLAccount.objects.get(code=code, is_active=True)
    except GLAccount.DoesNotExist:
        logger.warning(f"GL account {code} not found — GL not seeded. Skipping auto-post.")
        return None


def _create_entry(date, description, reference, source_type, source_id, lines, user=None):
    """
    Create a balanced JournalEntry with the given lines.
    lines = list of (account_code, debit, credit, description)
    Returns the JournalEntry or None if accounts not found / not balanced.
    """
    from apps.billing.models import JournalEntry, JournalLine
    resolved = []
    for code, debit, credit, desc in lines:
        acct = _get_account(code)
        if acct is None:
            return None
        resolved.append((acct, Decimal(str(debit)), Decimal(str(credit)), desc))

    total_dr = sum(d for _, d, _, _ in resolved)
    total_cr = sum(c for _, _, c, _ in resolved)
    if abs(total_dr - total_cr) > Decimal('0.01'):
        logger.error(f"Unbalanced journal entry for {source_type} {source_id}: Dr={total_dr} Cr={total_cr}")
        return None

    entry = JournalEntry.objects.create(
        entry_date=date,
        description=description,
        reference=reference,
        source_type=source_type,
        source_id=str(source_id),
        is_posted=True,
        created_by=user,
    )
    for seq, (acct, debit, credit, desc) in enumerate(resolved, 1):
        JournalLine.objects.create(
            entry=entry,
            account=acct,
            debit_amount=debit,
            credit_amount=credit,
            description=desc,
            sequence=seq,
        )
    return entry


def post_payment(payment):
    """
    Auto-post a patient payment to the GL.

    Cash/Card/Transfer/Mobile:
        Dr  Cash/Bank  |  Cr  Revenue (by service category)

    Insurance/NHIS:
        Dr  AR Insurance  |  Cr  Revenue

    Waiver:  no GL entry (no cash movement)
    """
    try:
        from apps.billing.models import ServiceCategory
        debit_code = PAYMENT_METHOD_ACCOUNT.get(payment.payment_method)
        if debit_code is None:
            return  # Waiver — skip

        # Determine revenue breakdown from invoice items
        invoice = payment.invoice
        items = invoice.items.filter(is_deleted=False)
        total_inv = invoice.total or Decimal('0')
        if total_inv == 0:
            return

        amount = Decimal(str(payment.amount))
        lines = []

        # Debit side: one line for the cash/bank/AR account
        lines.append((debit_code, amount, 0, f"Receipt {payment.receipt_number}"))

        # Credit side: split by service category proportionally
        total_allocated = Decimal('0')
        item_list = list(items)
        for i, item in enumerate(item_list):
            rev_code = REVENUE_MAP.get(item.category, REVENUE_MAP['OTHER'])
            # Proportional share of this payment
            if i == len(item_list) - 1:
                item_amount = amount - total_allocated  # remainder to last item
            else:
                proportion = (item.line_total / total_inv) if total_inv else Decimal('1')
                item_amount = (amount * proportion).quantize(Decimal('0.01'))
                total_allocated += item_amount
            if item_amount > 0:
                lines.append((rev_code, 0, item_amount, item.description))

        if not item_list:
            # No items — credit generic revenue
            lines.append((REVENUE_MAP['OTHER'], 0, amount, f"Invoice {invoice.invoice_number}"))

        _create_entry(
            date=payment.payment_date.date() if hasattr(payment.payment_date, 'date') else payment.payment_date,
            description=f"Patient payment — {invoice.invoice_number} — {invoice.patient.full_name}",
            reference=payment.receipt_number,
            source_type='payment',
            source_id=payment.pk,
            lines=lines,
            user=payment.received_by,
        )
    except Exception as e:
        logger.exception(f"GL auto-post failed for payment {payment.pk}: {e}")


def post_expense(expense):
    """
    Auto-post an approved expense to the GL.
        Dr  Expense Account  |  Cr  Cash / Bank
    """
    try:
        debit_code  = EXPENSE_MAP.get(expense.category, EXPENSE_MAP['EXP_OTHER'])
        credit_code = CASH_ACCOUNT if expense.payment_method == 'CASH' else BANK_ACCOUNT
        amount = Decimal(str(expense.amount))

        lines = [
            (debit_code,  amount, 0,      expense.description),
            (credit_code, 0,      amount, f"Expense payment — {expense.vendor or 'N/A'}"),
        ]
        _create_entry(
            date=expense.date,
            description=f"Expense — {expense.description}",
            reference=expense.reference or str(expense.pk)[:8],
            source_type='expense',
            source_id=expense.pk,
            lines=lines,
            user=expense.approved_by,
        )
    except Exception as e:
        logger.exception(f"GL auto-post failed for expense {expense.pk}: {e}")


def post_ap_payment(ap_payment):
    """
    Post an AP vendor payment to the GL.
        Dr  AP Vendors (401000)  |  Cr  Bank (521000)
    """
    try:
        amount = Decimal(str(ap_payment.amount))
        credit_code = CASH_ACCOUNT if ap_payment.payment_method == 'CASH' else BANK_ACCOUNT

        lines = [
            (AP_VENDORS,   amount, 0,      f"Payment to {ap_payment.bill.vendor.name}"),
            (credit_code,  0,      amount, f"AP Bill {ap_payment.bill.bill_number}"),
        ]
        _create_entry(
            date=ap_payment.payment_date,
            description=f"AP Payment — {ap_payment.bill.vendor.name} — {ap_payment.bill.bill_number}",
            reference=ap_payment.reference or str(ap_payment.pk)[:8],
            source_type='ap_payment',
            source_id=ap_payment.pk,
            lines=lines,
            user=ap_payment.paid_by,
        )
    except Exception as e:
        logger.exception(f"GL auto-post failed for AP payment {ap_payment.pk}: {e}")


def post_ap_bill(bill):
    """
    Post a vendor bill receipt to the GL.
        Dr  Expense Account  |  Cr  AP Vendors (401000)
    """
    try:
        debit_code = EXPENSE_MAP.get(bill.category, EXPENSE_MAP['EXP_OTHER'])
        if bill.gl_account:
            debit_code = bill.gl_account.code
        amount = Decimal(str(bill.amount_due))

        lines = [
            (debit_code, amount, 0,      bill.description),
            (AP_VENDORS, 0,      amount, f"Bill from {bill.vendor.name}"),
        ]
        _create_entry(
            date=bill.bill_date,
            description=f"AP Bill received — {bill.vendor.name} — {bill.bill_number}",
            reference=bill.vendor_ref or bill.bill_number,
            source_type='ap_bill',
            source_id=bill.pk,
            lines=lines,
            user=bill.approved_by,
        )
    except Exception as e:
        logger.exception(f"GL auto-post failed for AP bill {bill.pk}: {e}")


def reverse_entry(original_entry, reason, user=None):
    """
    Create a reversal journal entry (swap debits and credits).
    Used for refunds, cancellations, corrections.
    """
    from apps.billing.models import JournalEntry, JournalLine
    try:
        rev = JournalEntry.objects.create(
            entry_date=original_entry.entry_date,
            description=f"REVERSAL of {original_entry.entry_number}: {reason}",
            reference=original_entry.reference,
            source_type='reversal',
            source_id=str(original_entry.pk),
            is_posted=True,
            is_reversal=True,
            reversed_entry=original_entry,
            created_by=user,
        )
        for seq, line in enumerate(original_entry.lines.all(), 1):
            JournalLine.objects.create(
                entry=rev,
                account=line.account,
                debit_amount=line.credit_amount,   # swap
                credit_amount=line.debit_amount,   # swap
                description=f"Reversal: {line.description}",
                sequence=seq,
            )
        return rev
    except Exception as e:
        logger.exception(f"GL reversal failed for entry {original_entry.pk}: {e}")
        return None
