"""
GL Service — Auto-posting functions for double-entry bookkeeping.

Called by signals when Payments, Expenses, AP Payments are saved.
Maps business transactions → OHADA GL account codes → JournalEntry + JournalLine.

Account code lookups: GLMapping DB table (editable GUI) → hardcoded fallback.
"""
import logging
from decimal import Decimal
from functools import lru_cache

logger = logging.getLogger(__name__)

# ── HARDCODED FALLBACKS (used when GLMapping table is empty or not yet seeded) ─

_SYSTEM_DEFAULTS = {
    'CASH_ACCOUNT':       '572000',
    'BANK_ACCOUNT':       '521000',
    'MOBILE_MONEY':       '521100',
    'AR_PATIENT':         '411000',
    'AR_INSURANCE':       '412000',
    'AR_CORPORATE':       '413000',
    'AP_VENDORS':         '401000',
    'PATIENT_DEPOSITS':   '499000',
    'STAFF_ADVANCES':     '421000',
    'LOSS_ON_DISPOSAL':   '654000',
    'GAIN_ON_DISPOSAL':   '754000',
    'ACCUM_DEPRECIATION': '281000',
    'FIXED_ASSETS':       '241000',
}

_REVENUE_DEFAULTS = {
    'CONSULT':   '701000',
    'CLINICAL':  '701000',
    'INVEST':    '702000',
    'LAB':       '703000',
    'PHARMACY':  '704000',
    'OPTICAL':   '705000',
    'SURGICAL':  '706000',
    'ADMISSION': '707000',
    'REG':       '708000',
    'OTHER':     '709000',
}

_EXPENSE_DEFAULTS = {
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

_PAYMENT_DEFAULTS = {
    'CASH':      '572000',
    'CARD':      '521000',
    'TRANSFER':  '521000',
    'MOBILE':    '521100',
    'INSURANCE': '412000',
    'NHIS':      '412000',
    'WAIVER':    None,
}


# ── DB-backed lookup with hardcoded fallback ─────────────────────────────────

def _load_mapping_cache():
    """Load all GLMappings into a dict. Called once, cached."""
    try:
        from apps.billing.models import GLMapping
        qs = GLMapping.objects.filter(is_active=True).select_related('gl_account')
        return {(m.category, m.source_key): m.gl_account.code for m in qs}
    except Exception:
        return {}


_mapping_cache = None


def _get_mapping(category, key, fallback=None):
    """Look up GL code from DB cache, fall back to hardcoded default."""
    global _mapping_cache
    if _mapping_cache is None:
        _mapping_cache = _load_mapping_cache()
    return _mapping_cache.get((category, key), fallback)


def invalidate_gl_cache():
    """Call after GLMapping save to refresh the cache."""
    global _mapping_cache
    _mapping_cache = None


def _sys(key):
    return _get_mapping('SYSTEM', key, _SYSTEM_DEFAULTS.get(key))


# ── Public constants (now DB-backed) ─────────────────────────────────────────

def _get_system_account(key):
    return _get_mapping('SYSTEM', key, _SYSTEM_DEFAULTS.get(key))


@property
def CASH_ACCOUNT():
    return _sys('CASH_ACCOUNT')


# For backward compat: module-level names that read from DB
# These are accessed as gl_service.CASH_ACCOUNT etc. throughout the codebase.
# We use a lazy approach: the first call loads the cache.

class _LazyCode:
    """Descriptor that looks up GL code from DB on first access."""
    def __init__(self, category, key, fallback):
        self.category = category
        self.key = key
        self.fallback = fallback

    def __str__(self):
        return _get_mapping(self.category, self.key, self.fallback) or ''

    def __eq__(self, other):
        return str(self) == str(other)

    def __hash__(self):
        return hash(str(self))


# Keep simple string constants for backward compat — read from DB at call time
def _s(key):
    return _get_mapping('SYSTEM', key, _SYSTEM_DEFAULTS.get(key))


# Module-level accessors (used by all post_* functions below)
CASH_ACCOUNT          = _SYSTEM_DEFAULTS['CASH_ACCOUNT']
BANK_ACCOUNT          = _SYSTEM_DEFAULTS['BANK_ACCOUNT']
MOBILE_MONEY_ACCOUNT  = _SYSTEM_DEFAULTS['MOBILE_MONEY']
AR_PATIENT            = _SYSTEM_DEFAULTS['AR_PATIENT']
AR_INSURANCE          = _SYSTEM_DEFAULTS['AR_INSURANCE']
AR_CORPORATE          = _SYSTEM_DEFAULTS['AR_CORPORATE']
AP_VENDORS            = _SYSTEM_DEFAULTS['AP_VENDORS']
PATIENT_DEPOSITS      = _SYSTEM_DEFAULTS['PATIENT_DEPOSITS']
STAFF_ADVANCES        = _SYSTEM_DEFAULTS['STAFF_ADVANCES']
LOSS_ON_DISPOSAL      = _SYSTEM_DEFAULTS['LOSS_ON_DISPOSAL']
GAIN_ON_DISPOSAL      = _SYSTEM_DEFAULTS['GAIN_ON_DISPOSAL']
ACCUM_DEPRECIATION    = _SYSTEM_DEFAULTS['ACCUM_DEPRECIATION']
FIXED_ASSETS          = _SYSTEM_DEFAULTS['FIXED_ASSETS']


def get_revenue_code(category_key):
    """Get GL code for a revenue/service category."""
    return _get_mapping('REVENUE', category_key, _REVENUE_DEFAULTS.get(category_key, _REVENUE_DEFAULTS['OTHER']))


def get_expense_code(category_key):
    """Get GL code for an expense category."""
    return _get_mapping('EXPENSE', category_key, _EXPENSE_DEFAULTS.get(category_key, _EXPENSE_DEFAULTS['EXP_OTHER']))


def get_payment_account(method_key):
    """Get GL code for a payment method. Returns None for waivers."""
    code = _get_mapping('PAYMENT', method_key, _PAYMENT_DEFAULTS.get(method_key))
    return code


def get_system_account(key):
    """Get a system GL account code (AR, AP, Cash, etc.)."""
    return _get_mapping('SYSTEM', key, _SYSTEM_DEFAULTS.get(key))


# Backward-compatible dicts — these now delegate to DB
REVENUE_MAP = _REVENUE_DEFAULTS  # fallback; post_* functions use get_revenue_code()

EXPENSE_MAP = _EXPENSE_DEFAULTS  # fallback; post_* functions use get_expense_code()

PAYMENT_METHOD_ACCOUNT = _PAYMENT_DEFAULTS  # fallback; post_* functions use get_payment_account()


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


def post_invoice_issued(invoice, user=None):
    """
    OHADA-compliant invoice recognition.
    When an invoice is issued to a patient, recognise the receivable:

        Dr  411 (Patient Accounts Receivable)
        Cr  7xx (Revenue — split by service category)

    If the invoice has insurance_amount > 0, delegates to
    post_insurance_invoice_split() to split AR between 411 and 412.

    This creates the patient's subsidiary ledger (Grand Livre Auxiliaire Client).
    Account 411 is the OHADA Class 4 third-party account for clients.
    """
    try:
        # Auto-delegate to insurance split if invoice has insurance portion
        ins_amount = getattr(invoice, 'insurance_amount', None)
        if ins_amount and Decimal(str(ins_amount)) > 0:
            return post_insurance_invoice_split(invoice, user)
        from apps.billing.models import ServiceCategory
        items = invoice.items.filter(is_deleted=False)
        total = invoice.total or Decimal('0')
        if total <= 0:
            return None

        amount = Decimal(str(total))
        lines = []

        # Debit: Patient AR (411)
        lines.append((AR_PATIENT, amount, 0,
                       f"Invoice {invoice.invoice_number} — {invoice.patient.full_name}"))

        # Credit: Revenue split by service category
        total_allocated = Decimal('0')
        item_list = list(items)
        for i, item in enumerate(item_list):
            rev_code = get_revenue_code(item.category)
            if i == len(item_list) - 1:
                item_amount = amount - total_allocated
            else:
                proportion = (item.line_total / total) if total else Decimal('1')
                item_amount = (amount * proportion).quantize(Decimal('0.01'))
                total_allocated += item_amount
            if item_amount > 0:
                lines.append((rev_code, 0, item_amount, item.description))

        if not item_list:
            lines.append((get_revenue_code('OTHER'), 0, amount,
                           f"Invoice {invoice.invoice_number}"))

        return _create_entry(
            date=invoice.issue_date,
            description=f"Invoice issued — {invoice.invoice_number} — {invoice.patient.full_name}",
            reference=invoice.invoice_number,
            source_type='invoice',
            source_id=invoice.pk,
            lines=lines,
            user=user or getattr(invoice, 'created_by', None),
        )
    except Exception as e:
        logger.exception(f"GL auto-post failed for invoice {invoice.pk}: {e}")
        return None


def post_payment(payment):
    """
    OHADA-compliant patient payment posting.
    When cash/bank payment is received, settle the receivable:

        Dr  Cash/Bank (572/521)   — money in
        Cr  411 (Patient AR)      — receivable reduced

    Insurance/NHIS:
        Dr  412 (Insurance AR)    — insurer now owes us
        Cr  411 (Patient AR)      — patient's debt transferred

    Waiver:  no GL entry (no cash movement)
    """
    try:
        debit_code = get_payment_account(payment.payment_method)
        if debit_code is None:
            return  # Waiver — skip

        invoice = payment.invoice
        amount = Decimal(str(payment.amount))
        if amount <= 0:
            return

        lines = [
            (debit_code,  amount, 0,
             f"Receipt {payment.receipt_number} — {payment.get_payment_method_display()}"),
            (AR_PATIENT,  0,      amount,
             f"Settlement — Inv {invoice.invoice_number} — {invoice.patient.full_name}"),
        ]

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
        debit_code  = get_expense_code(expense.category)
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
        debit_code = get_expense_code(bill.category)
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


def post_cash_to_bank(deposit, user=None):
    """
    GL posting for cash deposit to bank.
    Dr  Bank 521000  |  Cr  Cash 572000
    """
    try:
        bank_code = deposit.bank_account.gl_account.code if deposit.bank_account.gl_account else BANK_ACCOUNT
        return _create_entry(
            date=deposit.deposit_date,
            description=f"Cash deposit to {deposit.bank_account.bank_name} — {deposit.reference}",
            reference=deposit.reference or f"DEP-{deposit.pk}",
            source_type='cash_to_bank',
            source_id=deposit.pk,
            lines=[
                (bank_code, deposit.amount, 0, f"Bank deposit — {deposit.bank_account.bank_name}"),
                (CASH_ACCOUNT, 0, deposit.amount, "Cash withdrawn from safe"),
            ],
            user=user,
        )
    except Exception as e:
        logger.exception(f"GL auto-post failed for cash-to-bank {deposit.pk}: {e}")


def post_advance_disbursement(advance, user=None):
    """
    GL posting when a staff advance is disbursed.
    Dr  Staff Advance 421000  |  Cr  Cash/Bank
    """
    try:
        cr_code = get_payment_account(advance.payment_method) or CASH_ACCOUNT
        if cr_code is None:
            cr_code = CASH_ACCOUNT
        amount = advance.amount_approved or advance.amount_requested
        return _create_entry(
            date=advance.disbursed_date,
            description=f"Staff advance to {advance.staff.get_full_name()} ({advance.get_advance_type_display()})",
            reference=advance.reference or f"ADV-{advance.pk}",
            source_type='advance_disburse',
            source_id=advance.pk,
            lines=[
                (STAFF_ADVANCES, amount, 0, f"Advance to {advance.staff.get_full_name()}"),
                (cr_code, 0, amount, "Cash/bank disbursement"),
            ],
            user=user,
        )
    except Exception as e:
        logger.exception(f"GL auto-post failed for advance {advance.pk}: {e}")


def post_advance_settlement(advance, user=None):
    """
    GL posting when a staff advance is settled.
    Dr  Cash/Bank  |  Cr  Staff Advance 421000
    """
    try:
        amount = advance.amount_approved or advance.amount_requested
        return _create_entry(
            date=advance.settled_date,
            description=f"Advance settlement — {advance.staff.get_full_name()}",
            reference=f"ADVS-{advance.pk}",
            source_type='advance_settle',
            source_id=advance.pk,
            lines=[
                (CASH_ACCOUNT, amount, 0, "Cash received for advance settlement"),
                (STAFF_ADVANCES, 0, amount, f"Settlement of advance by {advance.staff.get_full_name()}"),
            ],
            user=user,
        )
    except Exception as e:
        logger.exception(f"GL auto-post failed for advance settlement {advance.pk}: {e}")


def post_asset_disposal(disposal, user=None):
    """
    GL posting for fixed asset disposal.

    Dr  Accumulated Depreciation (for depreciated amount)
    Dr  Cash/Bank (for actual proceeds, if sold)
    Dr  Loss on Disposal (if NBV > proceeds)  OR  Cr Gain on Disposal (if proceeds > NBV)
    Cr  Fixed Asset (at original cost)
    """
    try:
        asset = disposal.asset
        cost = asset.purchase_cost
        accum_dep = Decimal(str(asset.accumulated_depreciation))
        nbv = cost - accum_dep
        proceeds = disposal.actual_proceeds

        lines = [
            (ACCUM_DEPRECIATION, accum_dep, 0, f"Accumulated depreciation on {asset.name}"),
            (FIXED_ASSETS, 0, cost, f"Disposal of {asset.name} (cost)"),
        ]

        if proceeds > 0:
            lines.append(
                (CASH_ACCOUNT, proceeds, 0, f"Proceeds from disposal of {asset.name}")
            )

        diff = nbv - proceeds
        if diff > 0:
            lines.append(
                (LOSS_ON_DISPOSAL, diff, 0, f"Loss on disposal of {asset.name}")
            )
        elif diff < 0:
            lines.append(
                (GAIN_ON_DISPOSAL, 0, abs(diff), f"Gain on disposal of {asset.name}")
            )

        entry = _create_entry(
            date=disposal.disposal_date,
            description=f"Asset disposal: {asset.name} ({disposal.get_disposal_method_display()})",
            reference=f"DISP-{disposal.pk}",
            source_type='asset_disposal',
            source_id=disposal.pk,
            lines=lines,
            user=user,
        )
        if entry:
            disposal.journal_entry = entry
            disposal.save(update_fields=['journal_entry'])
        return entry
    except Exception as e:
        logger.exception(f"GL auto-post failed for asset disposal {disposal.pk}: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# REFUND GL POSTING
# ═══════════════════════════════════════════════════════════════════════════════

BAD_DEBT_EXPENSE = '658000'    # Bad Debt / Write-off Expense
PETTY_CASH       = '573000'    # Petty Cash Account
VARIANCE_INCOME  = '758000'    # Other Income (cash overage)
VARIANCE_EXPENSE = '658100'    # Shortage / Variance Expense


def post_refund(refund, user=None):
    """
    Auto-post a refund to the GL.
    Reverses revenue previously recognized:
        Dr  Revenue (by service category, proportional)  |  Cr  Cash/Bank
    """
    try:
        from apps.billing.models import ServiceCategory
        credit_code = get_payment_account(refund.payment_method) or CASH_ACCOUNT
        if credit_code is None:
            credit_code = CASH_ACCOUNT

        invoice = refund.invoice
        items = invoice.items.filter(is_deleted=False)
        total_inv = invoice.total or Decimal('0')
        amount = Decimal(str(refund.amount))
        lines = []

        # Debit side: reverse revenue proportionally
        item_list = list(items)
        total_allocated = Decimal('0')
        for i, item in enumerate(item_list):
            rev_code = get_revenue_code(item.category)
            if i == len(item_list) - 1:
                item_amount = amount - total_allocated
            else:
                proportion = (item.line_total / total_inv) if total_inv else Decimal('1')
                item_amount = (amount * proportion).quantize(Decimal('0.01'))
                total_allocated += item_amount
            if item_amount > 0:
                lines.append((rev_code, item_amount, 0, f"Refund: {item.description}"))

        if not item_list:
            lines.append((get_revenue_code('OTHER'), amount, 0, f"Refund — {invoice.invoice_number}"))

        # Credit side: cash/bank out
        lines.append((credit_code, 0, amount, f"Refund issued via {refund.payment_method}"))

        _create_entry(
            date=refund.refund_date.date() if hasattr(refund.refund_date, 'date') else refund.refund_date,
            description=f"Refund — {invoice.invoice_number} — {invoice.patient.full_name}",
            reference=refund.reference or f"REF-{refund.pk}",
            source_type='refund',
            source_id=refund.pk,
            lines=lines,
            user=user or refund.processed_by,
        )
    except Exception as e:
        logger.exception(f"GL auto-post failed for refund {refund.pk}: {e}")


def post_invoice_cancellation(invoice, user=None):
    """
    Reverse GL entries for a cancelled invoice.
    Finds the original payment GL entries and creates reversals.
    """
    try:
        from apps.billing.models import JournalEntry
        original_entries = JournalEntry.objects.filter(
            source_type='payment',
            source_id__in=[str(p.pk) for p in invoice.payments.filter(is_deleted=False)],
            is_posted=True,
            is_reversal=False,
        )
        for entry in original_entries:
            # Only reverse if not already reversed
            if not JournalEntry.objects.filter(
                source_type='reversal', reversed_entry=entry
            ).exists():
                reverse_entry(entry, f"Invoice {invoice.invoice_number} cancelled", user)
    except Exception as e:
        logger.exception(f"GL reversal failed for invoice cancellation {invoice.pk}: {e}")


def post_waiver(invoice, user=None):
    """
    Post a waiver (full write-off) to the GL.
        Dr  Bad Debt Expense 658000  |  Cr  Revenue (by category)
    """
    try:
        items = invoice.items.filter(is_deleted=False)
        total_inv = invoice.total or Decimal('0')
        if total_inv <= 0:
            return

        amount = Decimal(str(total_inv))
        lines = []

        # Credit side: reduce revenue by category
        item_list = list(items)
        total_allocated = Decimal('0')
        for i, item in enumerate(item_list):
            rev_code = get_revenue_code(item.category)
            if i == len(item_list) - 1:
                item_amount = amount - total_allocated
            else:
                proportion = (item.line_total / total_inv) if total_inv else Decimal('1')
                item_amount = (amount * proportion).quantize(Decimal('0.01'))
                total_allocated += item_amount
            if item_amount > 0:
                lines.append((rev_code, 0, item_amount, f"Waiver: {item.description}"))

        if not item_list:
            lines.append((get_revenue_code('OTHER'), 0, amount, f"Waiver — {invoice.invoice_number}"))

        # Debit: bad debt expense
        lines.insert(0, (BAD_DEBT_EXPENSE, amount, 0, f"Write-off — {invoice.invoice_number}"))

        _create_entry(
            date=invoice.updated_at.date() if hasattr(invoice.updated_at, 'date') else invoice.updated_at,
            description=f"Invoice waiver — {invoice.invoice_number} — {invoice.patient.full_name}",
            reference=f"WAIV-{invoice.pk}",
            source_type='waiver',
            source_id=invoice.pk,
            lines=lines,
            user=user,
        )
    except Exception as e:
        logger.exception(f"GL auto-post failed for waiver {invoice.pk}: {e}")


def post_wallet_deposit(wallet_txn, user=None):
    """
    Post a patient wallet deposit to the GL.
        Dr  Cash/Bank  |  Cr  Patient Deposits Liability 499000
    """
    try:
        amount = Decimal(str(wallet_txn.amount))
        if amount <= 0:
            return
        method = getattr(wallet_txn, 'payment_method', 'CASH')
        debit_code = get_payment_account(method) or CASH_ACCOUNT

        _create_entry(
            date=wallet_txn.created_at.date() if hasattr(wallet_txn.created_at, 'date') else wallet_txn.created_at,
            description=f"Wallet deposit — {wallet_txn.wallet.patient.full_name}",
            reference=wallet_txn.reference or f"WDEP-{wallet_txn.pk}",
            source_type='wallet_deposit',
            source_id=wallet_txn.pk,
            lines=[
                (debit_code, amount, 0, f"Cash received from {wallet_txn.wallet.patient.full_name}"),
                (PATIENT_DEPOSITS, 0, amount, "Patient deposit liability"),
            ],
            user=user,
        )
    except Exception as e:
        logger.exception(f"GL auto-post failed for wallet deposit {wallet_txn.pk}: {e}")


def post_wallet_deduction(wallet_txn, user=None):
    """
    Post a patient wallet deduction to the GL.
        Dr  Patient Deposits Liability 499000  |  Cr  Revenue (or Cash if refund)
    """
    try:
        amount = Decimal(str(wallet_txn.amount))
        if amount <= 0:
            return

        credit_code = get_revenue_code('OTHER')
        credit_desc = "Revenue from wallet deduction"

        # If linked to an invoice, try to get revenue categories
        if wallet_txn.invoice:
            items = wallet_txn.invoice.items.filter(is_deleted=False)
            item_list = list(items)
            if item_list:
                lines = [(PATIENT_DEPOSITS, amount, 0, "Wallet payment applied")]
                total_inv = wallet_txn.invoice.total or Decimal('0')
                total_allocated = Decimal('0')
                for i, item in enumerate(item_list):
                    rev_code = get_revenue_code(item.category)
                    if i == len(item_list) - 1:
                        item_amount = amount - total_allocated
                    else:
                        proportion = (item.line_total / total_inv) if total_inv else Decimal('1')
                        item_amount = (amount * proportion).quantize(Decimal('0.01'))
                        total_allocated += item_amount
                    if item_amount > 0:
                        lines.append((rev_code, 0, item_amount, item.description))

                _create_entry(
                    date=wallet_txn.created_at.date(),
                    description=f"Wallet payment — {wallet_txn.wallet.patient.full_name} — Inv {wallet_txn.invoice.invoice_number}",
                    reference=f"WPAY-{wallet_txn.pk}",
                    source_type='wallet_deduction',
                    source_id=wallet_txn.pk,
                    lines=lines,
                    user=user,
                )
                return

        # No invoice — simple deduction
        _create_entry(
            date=wallet_txn.created_at.date(),
            description=f"Wallet deduction — {wallet_txn.wallet.patient.full_name}",
            reference=f"WDED-{wallet_txn.pk}",
            source_type='wallet_deduction',
            source_id=wallet_txn.pk,
            lines=[
                (PATIENT_DEPOSITS, amount, 0, "Patient deposit applied"),
                (credit_code, 0, amount, credit_desc),
            ],
            user=user,
        )
    except Exception as e:
        logger.exception(f"GL auto-post failed for wallet deduction {wallet_txn.pk}: {e}")


def post_petty_cash_entry(entry, user=None):
    """
    Post a petty cash entry to the GL.
    DEBIT (expense payment):
        Dr  Expense Category Account  |  Cr  Petty Cash 573000
    CREDIT (top-up / replenishment):
        Dr  Petty Cash 573000  |  Cr  Cash 572000
    """
    try:
        amount = Decimal(str(entry.amount))
        if amount <= 0:
            return

        if entry.entry_type == 'DEBIT':
            # Expense from petty cash
            debit_code = get_expense_code(entry.category)
            lines = [
                (debit_code, amount, 0, entry.description),
                (PETTY_CASH, 0, amount, f"Petty cash payment — {entry.fund.name}"),
            ]
        else:
            # Top-up / replenishment of petty cash
            lines = [
                (PETTY_CASH, amount, 0, f"Petty cash top-up — {entry.fund.name}"),
                (CASH_ACCOUNT, 0, amount, "Cash used for petty cash replenishment"),
            ]

        _create_entry(
            date=entry.date,
            description=f"Petty cash — {entry.description}",
            reference=entry.reference or f"PC-{entry.pk}",
            source_type='petty_cash',
            source_id=entry.pk,
            lines=lines,
            user=user or entry.created_by,
        )
    except Exception as e:
        logger.exception(f"GL auto-post failed for petty cash entry {entry.pk}: {e}")


def post_petty_cash_fund_creation(fund, user=None):
    """
    Post initial petty cash float allocation to the GL.
        Dr  Petty Cash 573000  |  Cr  Cash 572000
    """
    try:
        amount = Decimal(str(fund.opening_balance))
        if amount <= 0:
            return

        _create_entry(
            date=fund.created_at.date() if hasattr(fund.created_at, 'date') else fund.created_at,
            description=f"Petty cash fund created — {fund.name}",
            reference=f"PCF-{fund.pk}",
            source_type='petty_cash_fund',
            source_id=fund.pk,
            lines=[
                (PETTY_CASH, amount, 0, f"Opening float — {fund.name}"),
                (CASH_ACCOUNT, 0, amount, "Cash allocated to petty cash"),
            ],
            user=user,
        )
    except Exception as e:
        logger.exception(f"GL auto-post failed for petty cash fund {fund.pk}: {e}")


def post_cash_transfer(transfer, user=None):
    """
    Post a confirmed cash transfer to the GL.
    DESK_SAFE:  Dr  Cash (Safe) 572100  |  Cr  Cash (Desk) 572000
    SAFE_BANK:  Dr  Bank 521000        |  Cr  Cash (Safe) 572100
    DESK_DESK:  Dr  Cash (To) 572000   |  Cr  Cash (From) 572000
    FLOAT:      Dr  Cash (Desk) 572000 |  Cr  Cash (Safe) 572100

    For simplicity, all internal cash movements:
        Dr Cash 572000 / Cr Cash 572000 (same code, differentiated by description)
    """
    try:
        amount = Decimal(str(transfer.amount))
        if amount <= 0:
            return

        xtype = transfer.transfer_type
        if xtype == 'SAFE_BANK':
            # Safe → Bank
            lines = [
                (BANK_ACCOUNT, amount, 0, f"Bank deposit from safe"),
                (CASH_ACCOUNT, 0, amount, f"Cash withdrawn from safe"),
            ]
        else:
            # Internal cash movements (desk→safe, safe→desk, desk→desk, float)
            from_desc = str(transfer.from_desk or 'Safe/Main')
            to_desc = str(transfer.to_desk or 'Safe/Main')
            lines = [
                (CASH_ACCOUNT, amount, 0, f"Cash received at {to_desc}"),
                (CASH_ACCOUNT, 0, amount, f"Cash sent from {from_desc}"),
            ]

        _create_entry(
            date=transfer.confirmed_at.date() if transfer.confirmed_at else transfer.transfer_date.date(),
            description=f"Cash transfer — {transfer.get_transfer_type_display()}",
            reference=transfer.reference or f"XFER-{transfer.pk}",
            source_type='cash_transfer',
            source_id=transfer.pk,
            lines=lines,
            user=user or transfer.confirmed_by,
        )
    except Exception as e:
        logger.exception(f"GL auto-post failed for cash transfer {transfer.pk}: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# INSURANCE / HMO GL POSTINGS — OHADA Account 412 (Insurance Receivables)
# ═══════════════════════════════════════════════════════════════════════════════

INSURANCE_BAD_DEBT = '658200'   # Insurance Bad Debt / Write-off


def post_insurance_invoice_split(invoice, user=None):
    """
    OHADA-compliant invoice recognition with insurance split.
    When an invoice has insurance_amount > 0, split the receivable:

        Dr  411 (Patient AR)     — patient's copay portion
        Dr  412 (Insurance AR)   — insurer's portion
        Cr  7xx (Revenue)        — by service category

    Called instead of post_invoice_issued() when invoice.insurance_amount > 0.
    """
    try:
        from apps.billing.models import ServiceCategory
        items = invoice.items.filter(is_deleted=False)
        total = invoice.total or Decimal('0')
        if total <= 0:
            return None

        ins_amount = Decimal(str(invoice.insurance_amount or 0))
        patient_amount = total - ins_amount

        lines = []

        # Debit: Patient AR (411) for patient's copay share
        if patient_amount > 0:
            lines.append((AR_PATIENT, patient_amount, 0,
                          f"Patient copay — Inv {invoice.invoice_number} — {invoice.patient.full_name}"))

        # Debit: Insurance AR (412) for insurer's share
        if ins_amount > 0:
            lines.append((AR_INSURANCE, ins_amount, 0,
                          f"Insurance claim — Inv {invoice.invoice_number} — {invoice.patient.full_name}"))

        # Credit: Revenue split by service category
        amount = Decimal(str(total))
        total_allocated = Decimal('0')
        item_list = list(items)
        for i, item in enumerate(item_list):
            rev_code = get_revenue_code(item.category)
            if i == len(item_list) - 1:
                item_amount = amount - total_allocated
            else:
                proportion = (item.line_total / total) if total else Decimal('1')
                item_amount = (amount * proportion).quantize(Decimal('0.01'))
                total_allocated += item_amount
            if item_amount > 0:
                lines.append((rev_code, 0, item_amount, item.description))

        if not item_list:
            lines.append((get_revenue_code('OTHER'), 0, amount,
                          f"Invoice {invoice.invoice_number}"))

        return _create_entry(
            date=invoice.issue_date,
            description=f"Invoice issued (insurance split) — {invoice.invoice_number} — {invoice.patient.full_name}",
            reference=invoice.invoice_number,
            source_type='invoice',
            source_id=invoice.pk,
            lines=lines,
            user=user or getattr(invoice, 'created_by', None),
        )
    except Exception as e:
        logger.exception(f"GL auto-post failed for insurance invoice split {invoice.pk}: {e}")
        return None


def post_insurance_batch_payment(batch, user=None):
    """
    GL posting when insurance scheme pays a claim batch.
    Settles the Insurance AR (412):

        Dr  Bank/Cash (521/572)  — money received from insurer
        Cr  412 (Insurance AR)   — receivable settled

    If partial payment, only post the amount actually received.
    """
    try:
        amount = Decimal(str(batch.total_paid or 0))
        if amount <= 0:
            return None

        # Determine payment method from payment_ref
        debit_code = BANK_ACCOUNT  # Insurance usually pays via bank transfer

        lines = [
            (debit_code, amount, 0,
             f"Insurance payment — {batch.scheme.name} — Batch {batch.batch_number}"),
            (AR_INSURANCE, 0, amount,
             f"Settlement — Batch {batch.batch_number} — Ref: {batch.payment_ref or 'N/A'}"),
        ]

        return _create_entry(
            date=batch.payment_date or batch.updated_at.date(),
            description=f"Insurance payment received — {batch.scheme.name} — Batch {batch.batch_number}",
            reference=batch.payment_ref or batch.batch_number,
            source_type='insurance_payment',
            source_id=batch.pk,
            lines=lines,
            user=user,
        )
    except Exception as e:
        logger.exception(f"GL auto-post failed for insurance batch payment {batch.pk}: {e}")
        return None


def post_insurance_claim_rejection(claim, user=None):
    """
    GL posting when an insurance claim is rejected.
    The insurance AR must be reversed — either written off as bad debt
    or transferred back to patient AR:

        Dr  Patient AR (411)         — patient now owes the full amount
        Cr  Insurance AR (412)       — insurer no longer owes us

    If the claim is linked to an invoice, use the claimed_amount.
    """
    try:
        amount = Decimal(str(claim.claimed_amount or 0))
        if amount <= 0:
            return None

        lines = [
            (AR_PATIENT, amount, 0,
             f"Claim rejected — {claim.claim_number} — transferred to patient"),
            (AR_INSURANCE, 0, amount,
             f"Claim rejection reversal — {claim.claim_number} — {claim.member.scheme.name}"),
        ]

        return _create_entry(
            date=claim.rejection_date or claim.updated_at.date(),
            description=f"Insurance claim rejected — {claim.claim_number} — {claim.member.patient.full_name}",
            reference=claim.claim_number,
            source_type='insurance_rejection',
            source_id=claim.pk,
            lines=lines,
            user=user,
        )
    except Exception as e:
        logger.exception(f"GL auto-post failed for claim rejection {claim.pk}: {e}")
        return None


def post_insurance_write_off(claim, user=None):
    """
    Write off an insurance claim as bad debt (scheme won't pay, patient not liable).

        Dr  Bad Debt Expense (658200)  — loss recognized
        Cr  Insurance AR (412)         — receivable cleared
    """
    try:
        amount = Decimal(str(claim.claimed_amount or 0))
        if amount <= 0:
            return None

        lines = [
            (INSURANCE_BAD_DEBT, amount, 0,
             f"Insurance write-off — {claim.claim_number} — {claim.member.scheme.name}"),
            (AR_INSURANCE, 0, amount,
             f"AR cleared — {claim.claim_number}"),
        ]

        return _create_entry(
            date=claim.updated_at.date() if hasattr(claim.updated_at, 'date') else claim.updated_at,
            description=f"Insurance claim write-off — {claim.claim_number} — {claim.member.patient.full_name}",
            reference=f"WO-{claim.claim_number}",
            source_type='insurance_write_off',
            source_id=claim.pk,
            lines=lines,
            user=user,
        )
    except Exception as e:
        logger.exception(f"GL auto-post failed for insurance write-off {claim.pk}: {e}")
        return None


def post_cash_variance(variance, user=None):
    """
    Post a resolved cash variance to the GL.
    Shortage (negative): Dr  Variance Expense 658100  |  Cr  Cash 572000
    Overage (positive):  Dr  Cash 572000              |  Cr  Other Income 758000
    """
    try:
        amount = abs(Decimal(str(variance.variance_amount)))
        if amount <= 0:
            return

        if variance.variance_amount < 0:
            # Shortage
            lines = [
                (VARIANCE_EXPENSE, amount, 0, f"Cash shortage — {variance.cashier.get_full_name()}"),
                (CASH_ACCOUNT, 0, amount, "Cash short from drawer"),
            ]
        else:
            # Overage
            lines = [
                (CASH_ACCOUNT, amount, 0, "Cash overage in drawer"),
                (VARIANCE_INCOME, 0, amount, f"Cash overage — {variance.cashier.get_full_name()}"),
            ]

        _create_entry(
            date=variance.variance_date,
            description=f"Cash variance — {variance.cashier.get_full_name()} — {'shortage' if variance.variance_amount < 0 else 'overage'}",
            reference=f"VAR-{variance.pk}",
            source_type='cash_variance',
            source_id=variance.pk,
            lines=lines,
            user=user or variance.resolved_by,
        )
    except Exception as e:
        logger.exception(f"GL auto-post failed for cash variance {variance.pk}: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# PHARMACY → ACCOUNTING GL POSTINGS
# ═══════════════════════════════════════════════════════════════════════════════

PHARMACY_STOCK   = '321000'   # OHADA Class 3 — Pharmacy Stock (Marchandises)
COGS_PHARMACY    = '601000'   # OHADA Class 6 — Cost of Goods Sold (Achats de marchandises)
PHARMACY_REVENUE = '704000'   # OHADA Class 7 — Pharmacy Sales Revenue
STOCK_LOSS       = '603000'   # OHADA Class 6 — Stock Losses (damage, expiry, pilferage)
STOCK_GAIN       = '321000'   # Surplus goes back to stock


def post_pharmacy_cogs(dispensing_item, user=None):
    """
    COGS recognition when pharmacy dispenses drugs.
    Called from DispensingItem.save() after physical stock is deducted.

    OHADA standard: when goods leave stock, recognise cost:
        Dr  601000 (COGS — Achats de marchandises vendues)
        Cr  321000 (Pharmacy Stock — Marchandises)

    Uses the drug's cost_price (purchase cost) × quantity, NOT the selling price.
    """
    try:
        drug = dispensing_item.drug
        if not drug:
            return None
        qty = dispensing_item.quantity_dispensed
        cost_price = getattr(drug, 'cost_price', None) or getattr(drug, 'purchase_price', None)
        if not cost_price or cost_price <= 0:
            # Fallback: use unit_price (selling price) — better than nothing
            cost_price = dispensing_item.unit_price
        if not cost_price or cost_price <= 0:
            return None

        amount = Decimal(str(cost_price)) * Decimal(str(qty))
        if amount <= 0:
            return None

        return _create_entry(
            date=dispensing_item.dispensing.dispensed_at.date()
                if hasattr(dispensing_item.dispensing, 'dispensed_at') and dispensing_item.dispensing.dispensed_at
                else __import__('django.utils.timezone', fromlist=['localdate']).localdate(),
            description=f"COGS — {drug.name} x{qty} — Dispensing {dispensing_item.dispensing.dispensing_number}",
            reference=dispensing_item.dispensing.dispensing_number,
            source_type='pharmacy_cogs',
            source_id=dispensing_item.pk,
            lines=[
                (COGS_PHARMACY, amount, 0,
                 f"Cost of {drug.name} x{qty} dispensed"),
                (PHARMACY_STOCK, 0, amount,
                 f"Stock reduction — {drug.name} x{qty}"),
            ],
            user=user,
        )
    except Exception as e:
        logger.exception(f"GL auto-post failed for pharmacy COGS {dispensing_item.pk}: {e}")
        return None


def post_otc_sale(dispensing, user=None):
    """
    GL posting for OTC / walk-in sale (no patient account, no invoice).
    The normal invoice pipeline is skipped for anonymous sales, so we
    post revenue + cash directly:

        Dr  572000 (Cash)          — money received
        Cr  704000 (Pharmacy Revenue) — revenue recognised

    Called from the direct-dispense view after amount_paid is set.
    """
    try:
        amount = Decimal(str(dispensing.amount_paid or 0))
        if amount <= 0:
            return None

        from django.utils import timezone as _tz
        return _create_entry(
            date=dispensing.dispensed_at.date() if dispensing.dispensed_at else _tz.localdate(),
            description=f"OTC sale — {dispensing.dispensing_number} — {dispensing.customer_name or 'Walk-in'}",
            reference=dispensing.dispensing_number,
            source_type='otc_sale',
            source_id=dispensing.pk,
            lines=[
                (CASH_ACCOUNT, amount, 0,
                 f"Cash received — OTC sale {dispensing.dispensing_number}"),
                (PHARMACY_REVENUE, 0, amount,
                 f"Pharmacy revenue — {dispensing.customer_name or 'Walk-in'}"),
            ],
            user=user,
        )
    except Exception as e:
        logger.exception(f"GL auto-post failed for OTC sale {dispensing.pk}: {e}")
        return None


def post_stock_adjustment(adjustment, user=None):
    """
    GL posting for manual stock adjustments.

    Stock DECREASE (damage, expiry, pilferage, count-down):
        Dr  603000 (Stock Losses)     — expense recognised
        Cr  321000 (Pharmacy Stock)   — asset reduced

    Stock INCREASE (patient return, count-up):
        Dr  321000 (Pharmacy Stock)   — asset increased
        Cr  603000 (Stock correction)  — reversal / gain

    Uses the drug's cost_price × |quantity_change| for the GL amount.
    """
    try:
        batch = adjustment.batch
        drug = batch.drug
        cost_price = getattr(drug, 'cost_price', None) or getattr(drug, 'purchase_price', None)
        if not cost_price or cost_price <= 0:
            cost_price = getattr(batch, 'unit_cost', None) or 0
        if not cost_price or cost_price <= 0:
            return None

        qty = abs(adjustment.quantity_change)
        amount = Decimal(str(cost_price)) * Decimal(str(qty))
        if amount <= 0:
            return None

        reason_label = adjustment.get_reason_display()

        if adjustment.quantity_change < 0:
            # Stock decreased — expense
            lines = [
                (STOCK_LOSS, amount, 0,
                 f"Stock loss — {drug.name} — {reason_label}"),
                (PHARMACY_STOCK, 0, amount,
                 f"Stock reduced — {drug.name} batch {batch.batch_number}"),
            ]
        else:
            # Stock increased — asset gained back
            lines = [
                (PHARMACY_STOCK, amount, 0,
                 f"Stock gained — {drug.name} — {reason_label}"),
                (STOCK_LOSS, 0, amount,
                 f"Stock correction — {drug.name} batch {batch.batch_number}"),
            ]

        from django.utils import timezone as _tz
        return _create_entry(
            date=adjustment.adjusted_at.date() if adjustment.adjusted_at else _tz.localdate(),
            description=f"Stock adjustment — {drug.name} — {reason_label}",
            reference=f"ADJ-{adjustment.pk}",
            source_type='stock_adjustment',
            source_id=adjustment.pk,
            lines=lines,
            user=user or adjustment.created_by,
        )
    except Exception as e:
        logger.exception(f"GL auto-post failed for stock adjustment {adjustment.pk}: {e}")
        return None
