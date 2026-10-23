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
    'CASH_ACCOUNT':       '5710001',  # Main Safe — postable child of 571000 (Cash in Hand)
    'BANK_ACCOUNT':       '521000',   # Bank Account — Main (OHADA 521)
    'MOBILE_MONEY':       '5520001',  # MTN Mobile Money - MASTER (postable child of 552000)
    'AR_PATIENT':         '4120001',  # Clients-Patients (Direct Pay / Cash)
    'AR_INSURANCE':       '4120002',  # Clients-Patients (HMO / CNPS Insurance)
    'AR_CORPORATE':       '4120003',  # Clients-Patients (Corporate Accounts)
    'AP_VENDORS':         '4011001',  # D Boy Distribution Sarl.U (default vendor)
    'PATIENT_DEPOSITS':   '4192001',  # Clients-Advances Received (Proforma)
    'STAFF_ADVANCES':     '421100',   # Personnel Advance parent — staff-specific sub-accounts used per-posting
    'LOSS_ON_DISPOSAL':   '654000',   # Loss on disposal
    'GAIN_ON_DISPOSAL':   '754000',   # Gain on disposal
    'ACCUM_DEPRECIATION': '284401',   # Accumulated Depreciation - Equipment (main)
    'FIXED_ASSETS':       '240001',   # Equipment (main fixed asset account)
}

_REVENUE_DEFAULTS = {
    # Clinical services — Standard-tier sub-account as fallback (tier routing handled by get_tier_revenue_code)
    'CONSULT':   '7052001',  # Consultation - Standard
    'CLINICAL':  '7052141',  # Other Medical Services - Standard
    'INVEST':    '7052091',  # Investigations - Standard
    'LAB':       '7052111',  # Laboratory - Standard
    'SURGICAL':  '7052081',  # Other Surgery - Standard
    'ADMISSION': '7052121',  # Hospitalization - Standard
    'REG':       '7052151',  # Sundry Income - Standard
    # Product sales — not tier-differentiated in COA
    'PHARMACY':  '7051501',  # Sales of Medications-MICEI
    'OPTICAL':   '7051001',  # Sales of Frames - Standard
    'OTHER':     '758800',   # Other Miscellaneous Income
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
    'CASH':      '5710001',  # Main Safe
    'CARD':      '521000',   # Bank Account — Main
    'TRANSFER':  '521000',   # Bank Account — Main
    'MOBILE':    '5520001',  # MTN Mobile Money - MASTER
    'INSURANCE': '4120002',  # Clients-Patients (HMO / CNPS Insurance)
    'NHIS':      '4120002',  # Clients-Patients (HMO / CNPS Insurance)
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


# ── Cost center auto-tagging for billing operations ───────────────────────────

# ServiceCategory → CostCenter code (real AEF codes from TurboClinic)
_SERVICE_CAT_TO_CC = {
    'CONSULT':     '001',   # Ophthalmology
    'CLINICAL':    '001',   # Ophthalmology (clinical procedures)
    'INVEST':      '001',   # Ophthalmology investigations (refractometry, OCT, visual field, etc.)
    'LAB':         '004',   # General Laboratory (blood work, non-ophthalmic)
    'PHARMACY':    '008',   # Pharmacy
    'OPTICAL':     '009',   # Optical Shop
    'REFRACTION':  '001',   # Ophthalmology (refraction)
    'SURGICAL':    '001',   # Ophthalmology (surgery/theatre)
    'ADMISSION':   '006',   # Accommodation (IPD/Ward)
    'REG':         '007',   # Patient Affairs
    'OTHER':       '012',   # Finance & Administration (default)
}

# ExpenseCategory → CostCenter code
_EXPENSE_CAT_TO_CC = {
    'SUPPLIES':   '012',  # Finance & Administration
    'UTILITIES':  '016',  # General Admin Expenses
    'SALARY':     '012',  # Finance & Administration
    'RENT':       '016',  # General Admin Expenses
    'EQUIPMENT':  '013',  # Other Support Services (maintenance)
    'DRUGS':      '008',  # Pharmacy
    'TRANSPORT':  '012',  # Finance & Administration
    'ADMIN':      '012',  # Finance & Administration
    'MARKETING':  '014',  # Partnership, Marketing & Dev't
    'EXP_OTHER':  '012',  # Finance & Administration
}


def _billing_cc(cc_code):
    """Return active CostCenter for the given code, or None."""
    if not cc_code:
        return None
    try:
        from apps.billing.models import CostCenter
        return CostCenter.objects.filter(code=cc_code, is_active=True, is_deleted=False).first()
    except Exception:
        return None


def _cc_for_service_category(category_code):
    """
    Resolve CostCenter from a ServiceCategory code string.
    Checks the DB-backed BillingOperationCC table first so Finance Directors
    can reconfigure mappings via the UI without touching code.
    Falls back to the hardcoded dict if no DB row exists.
    """
    try:
        from apps.billing.models import BillingOperationCC
        row = BillingOperationCC.objects.filter(
            category_key=category_code, group='REVENUE', is_deleted=False,
        ).select_related('cost_center').first()
        if row and row.cost_center and row.cost_center.is_active:
            return row.cost_center
    except Exception:
        pass
    return _billing_cc(_SERVICE_CAT_TO_CC.get(category_code, '012'))


def _cc_for_expense_category(category_code):
    """
    Resolve CostCenter from an ExpenseCategory code string.
    DB-backed lookup with hardcoded-dict fallback.
    """
    try:
        from apps.billing.models import BillingOperationCC
        row = BillingOperationCC.objects.filter(
            category_key=category_code, group='EXPENSE', is_deleted=False,
        ).select_related('cost_center').first()
        if row and row.cost_center and row.cost_center.is_active:
            return row.cost_center
    except Exception:
        pass
    return _billing_cc(_EXPENSE_CAT_TO_CC.get(category_code, '012'))


# CashDesk.desk_type → cost-center code mapping (real AEF codes)
_DESK_TYPE_TO_CC = {
    'TIER':      '001',  # Ophthalmology (consultations)
    'PHARMACY':  '008',  # Pharmacy
    'OPTICAL':   '009',  # Optical Shop
    'INSURANCE': '007',  # Patient Affairs
}


def _cc_for_desk(cash_desk):
    """Return the CostCenter for a CashDesk based on its desk_type field."""
    if not cash_desk:
        return _billing_cc('012')  # Finance & Administration fallback
    return _billing_cc(_DESK_TYPE_TO_CC.get(getattr(cash_desk, 'desk_type', ''), '012'))


def _op_for_key(category_key, group=None):
    """
    Resolve a BillingOperationCC row from category_key (and optional group).
    Returns the model instance so it can be FK-stored on JournalEntry.operation.
    Used to stamp TurboClinic operation codes on every auto-generated GL entry.
    """
    try:
        from apps.billing.models import BillingOperationCC
        qs = BillingOperationCC.objects.filter(
            category_key=category_key, is_deleted=False,
        )
        if group:
            qs = qs.filter(group=group)
        return qs.first()
    except Exception:
        return None


def _dominant_category(items):
    """
    Return the ServiceCategory that accounts for the most revenue in a list of
    invoice items. Used to tag the journal entry with a single cost center.
    CONSULT always wins when present — it is the primary clinical service.
    """
    from decimal import Decimal as _D
    totals = {}
    for item in items:
        cat = getattr(item, 'category', 'OTHER') or 'OTHER'
        totals[cat] = totals.get(cat, _D('0')) + (getattr(item, 'line_total', None) or _D('0'))
    if not totals:
        return 'OTHER'
    # CONSULT is always the primary category when present
    if 'CONSULT' in totals:
        return 'CONSULT'
    return max(totals, key=totals.get)


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


# ── Tier-based revenue routing (Finance Director COA 2026-10-23) ──────────────
# Each clinical service has 7 sub-accounts — one per patient tier.
# Structure: 6-digit parent + 1-digit suffix  e.g. 705200 + 4 = 7052004 (VIP)
# Suffix:  1=Standard  2=Express/FT  3=Insured  4=VIP  5=Outreach  6=EVIP  7=Non-National

_TIER_TO_SUFFIX = {
    'STANDARD':     '1',
    'EXPRESS':      '2',
    'FAST_TRACK':   '2',
    'INSURED':      '3',
    'VIP':          '4',
    'OUTREACH':     '5',
    'EVIP':         '6',
    'NON_NATIONAL': '7',
}

# ServiceCategory → 6-digit revenue parent code
_CLINICAL_CAT_PARENT = {
    'CONSULT':   '705200',   # Ophthalmology Consultation
    'CLINICAL':  '705214',   # Other Medical Services
    'INVEST':    '705209',   # Investigation
    'LAB':       '705211',   # Laboratory
    'SURGICAL':  '705208',   # Other Surgery (generic; specific surgery ops use BillingOperationCC directly)
    'ADMISSION': '705212',   # Hospitalization
    'REG':       '705215',   # Sundry Income
    'OTHER':     '705215',   # Sundry Income
}


def get_tier_revenue_code(category_key, tier=None):
    """
    Return the 7-digit GL revenue account for a service category + patient tier.

    Clinical services (CONSULT, LAB, INVEST, etc.) have 7 COA sub-accounts — one
    per patient tier (Standard, Express, Insured, VIP, Outreach, EVIP, Non-National).
    This function resolves the correct one.

    Pharmacy / Optical product sales are NOT tier-differentiated in the COA —
    they fall back to get_revenue_code() which uses product-type sub-accounts.

    Falls back to get_revenue_code(category_key) if the tier account is not in DB.
    """
    if category_key in ('PHARMACY', 'OPTICAL'):
        return get_revenue_code(category_key)

    parent_code = _CLINICAL_CAT_PARENT.get(category_key)
    suffix = _TIER_TO_SUFFIX.get((tier or 'STANDARD').upper(), '1')

    if parent_code:
        candidate = parent_code + suffix   # e.g. '705200' + '1' = '7052001'
        try:
            from apps.billing.models import GLAccount
            if GLAccount.objects.filter(
                code=candidate, is_summary=False, is_active=True
            ).exists():
                return candidate
        except Exception:
            pass

    return get_revenue_code(category_key)


def get_expense_code(category_key):
    """Get GL code for an expense category."""
    return _get_mapping('EXPENSE', category_key, _EXPENSE_DEFAULTS.get(category_key, _EXPENSE_DEFAULTS['EXP_OTHER']))


def get_payment_account(method_key):
    """Get GL code for a payment method. Returns None for waivers."""
    code = _get_mapping('PAYMENT', method_key, _PAYMENT_DEFAULTS.get(method_key))
    return code


def get_system_account(key):
    """Get a system GL account code (AR, AP, Cash, etc.)."""
    # Allow aliases: CASH_SAFE → CASH_ACCOUNT fallback, BANK_LOCAL → BANK_ACCOUNT
    code = _get_mapping('SYSTEM', key, _SYSTEM_DEFAULTS.get(key))
    if not code:
        _alias = {'CASH_SAFE': 'CASH_ACCOUNT', 'BANK_LOCAL': 'BANK_ACCOUNT',
                  'AP_SUPPLIER': 'AP_VENDORS', 'STAFF_ADVANCES': 'STAFF_ADVANCES'}
        fallback_key = _alias.get(key, key)
        code = _SYSTEM_DEFAULTS.get(fallback_key)
    return code


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


def _create_entry(date, description, reference, source_type, source_id, lines,
                  user=None, cost_center=None, operation=None):
    """
    Create a balanced JournalEntry with the given lines.
    lines = list of (account_code, debit, credit, description)
    cost_center: billing.CostCenter instance — auto-tagged from store location.
    operation: BillingOperationCC instance — TurboClinic operation code.
    Returns the JournalEntry or None if accounts not found / not balanced.
    """
    from apps.billing.models import JournalEntry, JournalLine
    resolved = []
    for code, debit, credit, desc in lines:
        acct = _get_account(code)
        if acct is None:
            return None
        if acct.is_summary:
            logger.error(
                f"Cannot post to summary account {code} ({acct.name}) for {source_type} {source_id}. "
                f"Summary accounts aggregate children — post to a leaf account instead."
            )
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
        cost_center=cost_center,
        operation=operation,
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

        # Resolve patient tier from visit for tier-specific GL routing
        visit = getattr(invoice, 'visit', None)
        patient_tier = (getattr(visit, 'service_tier', None) or 'STANDARD').upper()

        # Debit: AR account — insured patients use AR_INSURANCE, others AR_PATIENT
        if patient_tier == 'INSURED':
            ar_code = get_system_account('AR_INSURANCE') or get_system_account('AR_PATIENT')
        else:
            ar_code = get_system_account('AR_PATIENT')
        lines.append((ar_code, amount, 0,
                       f"Invoice {invoice.invoice_number} — {invoice.patient.full_name}"))

        # Credit: Revenue split by service category + patient tier
        total_allocated = Decimal('0')
        item_list = list(items)
        for i, item in enumerate(item_list):
            # Prefer item-level GL → sub-category GL → tier-based category default
            rev_code = getattr(item, 'gl_account_code', '') or ''
            if not rev_code and hasattr(item, 'resolve_gl_code'):
                rev_code = item.resolve_gl_code()
            if not rev_code:
                rev_code = get_tier_revenue_code(item.category, patient_tier)
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

        dominant_cat = _dominant_category(item_list) if item_list else 'OTHER'
        return _create_entry(
            date=invoice.issue_date,
            description=f"Invoice issued — {invoice.invoice_number} — {invoice.patient.full_name}",
            reference=invoice.invoice_number,
            source_type='invoice',
            source_id=invoice.pk,
            lines=lines,
            user=user or getattr(invoice, 'created_by', None),
            cost_center=_cc_for_service_category(dominant_cat),
            operation=_op_for_key(dominant_cat, 'REVENUE'),
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

        ar_patient = get_system_account('AR_PATIENT')
        lines = [
            (debit_code,  amount, 0,
             f"Receipt {payment.receipt_number} — {payment.get_payment_method_display()}"),
            (ar_patient,  0,      amount,
             f"Settlement — Inv {invoice.invoice_number} — {invoice.patient.full_name}"),
        ]

        # Inherit cost center from invoice's dominant service category
        item_list = list(invoice.items.filter(is_deleted=False))
        dominant_cat = _dominant_category(item_list) if item_list else 'OTHER'
        _create_entry(
            date=payment.payment_date.date() if hasattr(payment.payment_date, 'date') else payment.payment_date,
            description=f"Patient payment — {invoice.invoice_number} — {invoice.patient.full_name}",
            reference=payment.receipt_number,
            source_type='payment',
            source_id=payment.pk,
            lines=lines,
            user=payment.received_by,
            cost_center=_cc_for_service_category(dominant_cat),
            operation=_op_for_key('PATIENT_RECEIPT', 'CASH'),
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
        credit_code = get_system_account('CASH_SAFE') if expense.payment_method == 'CASH' else get_system_account('BANK_LOCAL')
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
            cost_center=_cc_for_expense_category(expense.category),
            operation=_op_for_key(expense.category, 'EXPENSE'),
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
        credit_code = get_system_account('CASH_SAFE') if ap_payment.payment_method == 'CASH' else get_system_account('BANK_LOCAL')
        ap_vendors = get_system_account('AP_SUPPLIER') or get_system_account('AP_VENDORS') or AP_VENDORS

        lines = [
            (ap_vendors,   amount, 0,      f"Payment to {ap_payment.bill.vendor.name}"),
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
            cost_center=_billing_cc('012'),  # Finance & Administration
        )
    except Exception as e:
        logger.exception(f"GL auto-post failed for AP payment {ap_payment.pk}: {e}")


def post_ap_bill(bill):
    """
    Post a vendor bill to the GL — OHADA 3-way match compliant.

    A) Bill linked to a GRN (goods purchase) → clears 408100 accrual:
          Dr  408100 (Supplier Awaiting Invoice)   ← clears GRN accrual
          Cr  401xxx (AP Vendors)                  ← formal payable recorded

    B) Bill NOT linked to a GRN (services, utilities, consultancy) → direct expense:
          Dr  Expense Account (Class 6)
          Cr  401xxx (AP Vendors)
    """
    try:
        amount = Decimal(str(bill.amount_due))
        ap_vendors = get_system_account('AP_SUPPLIER') or get_system_account('AP_VENDORS') or AP_VENDORS

        if bill.grn_id:
            # Case A — GRN-linked: clear the 408100 accrual posted at stock receipt
            lines = [
                ('408100', amount, 0,
                 f"GRN match — {bill.grn.grn_number} — {bill.description}"),
                (ap_vendors, 0, amount,
                 f"Bill from {bill.vendor.name} — {bill.bill_number}"),
            ]
            description = (
                f"AP Bill (GRN match) — {bill.vendor.name} — {bill.bill_number} "
                f"— GRN {bill.grn.grn_number}"
            )
            # Inherit CC from the GRN's store location
            bill_cc = None
            bill_op = None
            try:
                bill_cc = getattr(bill.grn.store_location, 'cost_center', None)
                # Map store CC code → STOCK_IN category key
                _CC_TO_STOCK_IN = {
                    '0001': 'STOCK_IN_PHARMACY',
                    '0002': 'STOCK_IN_OT',
                    '0003': 'STOCK_IN_MAIN',
                    '0004': 'STOCK_IN_LAB',
                    '0005': 'STOCK_IN_OPTICAL',
                }
                if bill_cc:
                    bill_op = _op_for_key(
                        _CC_TO_STOCK_IN.get(bill_cc.code, 'STOCK_IN_GRN'), 'STOCK'
                    )
                else:
                    bill_op = _op_for_key('STOCK_IN_GRN', 'STOCK')
            except Exception:
                bill_op = _op_for_key('STOCK_IN_GRN', 'STOCK')
        else:
            # Case B — Direct service/expense: hit expense account immediately
            debit_code = get_expense_code(bill.category)
            if bill.gl_account:
                debit_code = bill.gl_account.code
            lines = [
                (debit_code, amount, 0,  bill.description),
                (ap_vendors, 0,      amount, f"Bill from {bill.vendor.name}"),
            ]
            description = f"AP Bill — {bill.vendor.name} — {bill.bill_number}"
            bill_cat = getattr(bill, 'category', 'EXP_OTHER') or 'EXP_OTHER'
            bill_cc = _cc_for_expense_category(bill_cat)
            bill_op = _op_for_key(bill_cat, 'EXPENSE')

        _create_entry(
            date=bill.bill_date,
            description=description,
            reference=bill.vendor_ref or bill.bill_number,
            source_type='ap_bill',
            source_id=bill.pk,
            lines=lines,
            user=bill.approved_by,
            cost_center=bill_cc,
            operation=bill_op,
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
                (get_system_account('CASH_SAFE'), 0, deposit.amount, "Cash withdrawn from safe"),
            ],
            user=user,
            cost_center=_billing_cc('012'),
            operation=_op_for_key('CASH_DEPOSIT', 'CASH'),
        )
    except Exception as e:
        logger.exception(f"GL auto-post failed for cash-to-bank {deposit.pk}: {e}")


def post_advance_disbursement(advance, user=None):
    """
    GL posting when a staff advance is disbursed.
    Dr  Staff Advance 421000  |  Cr  Cash/Bank
    """
    try:
        cash_safe = get_system_account('CASH_SAFE')
        cr_code = get_payment_account(advance.payment_method) or cash_safe
        if cr_code is None:
            cr_code = cash_safe
        staff_adv = get_system_account('STAFF_ADVANCES') or STAFF_ADVANCES
        amount = advance.amount_approved or advance.amount_requested
        return _create_entry(
            date=advance.disbursed_date,
            description=f"Staff advance to {advance.staff.get_full_name()} ({advance.get_advance_type_display()})",
            reference=advance.reference or f"ADV-{advance.pk}",
            source_type='advance_disburse',
            source_id=advance.pk,
            lines=[
                (staff_adv, amount, 0, f"Advance to {advance.staff.get_full_name()}"),
                (cr_code, 0, amount, "Cash/bank disbursement"),
            ],
            user=user,
            cost_center=_billing_cc('012'),
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
        staff_adv = get_system_account('STAFF_ADVANCES') or STAFF_ADVANCES
        return _create_entry(
            date=advance.settled_date,
            description=f"Advance settlement — {advance.staff.get_full_name()}",
            reference=f"ADVS-{advance.pk}",
            source_type='advance_settle',
            source_id=advance.pk,
            lines=[
                (get_system_account('CASH_SAFE'), amount, 0, "Cash received for advance settlement"),
                (staff_adv, 0, amount, f"Settlement of advance by {advance.staff.get_full_name()}"),
            ],
            user=user,
            cost_center=_billing_cc('012'),
        )
    except Exception as e:
        logger.exception(f"GL auto-post failed for advance settlement {advance.pk}: {e}")


def post_asset_addition(asset, user=None):
    """
    GL posting when a new fixed asset is registered.
    OHADA SYSCEBNL:
        Dr  2xxxxx  (Fixed Asset — e.g. 241000 Equipement)
        Cr  481000  (Supplier / Accounts Payable for assets)

    Asset category → GL debit account mapping:
        LAND          → 221000
        BUILDING      → 231000
        VEHICLE       → 245000
        EQUIPMENT     → 241000  (default)
        FURNITURE     → 244000
        IT_EQUIPMENT  → 242000
        MEDICAL       → 241000
        OTHER         → 249000
    """
    try:
        from decimal import Decimal as _D
        cost = _D(str(asset.purchase_cost or 0))
        if cost <= 0:
            return None

        # Map category to OHADA asset account — postable 7-digit children from new COA
        CAT_MAP = {
            'LAND':         '226100',   # Parkings (closest land improvement account)
            'BUILDING':     '2313001',  # Main Building
            'VEHICLE':      '2451001',  # Vehicles
            'EQUIPMENT':    '2411001',  # Electrical Equipment (general equipment)
            'FURNITURE':    '2441101',  # Hospital Furniture
            'IT_EQUIPMENT': '2122001',  # IT Licences / Software
            'MEDICAL':      '2413001',  # Ophthalmology Equipment
            'OTHER':        '2411001',  # Default to Electrical Equipment
        }
        asset_code = CAT_MAP.get(str(asset.category), '2411001')
        asset_acct = GLAccount.objects.filter(code=asset_code, is_deleted=False).first()
        if not asset_acct:
            asset_acct = GLAccount.objects.filter(code__startswith='241', is_deleted=False).first()

        # Cr Suppliers for assets payable
        ap_asset = GLAccount.objects.filter(code__startswith='481', is_deleted=False).first()
        if not ap_asset:
            ap_asset = GLAccount.objects.filter(code__startswith='401', is_deleted=False).first()

        if not asset_acct or not ap_asset:
            return None

        from django.utils import timezone as _tz
        return _create_entry(
            date=asset.purchase_date or _tz.localdate(),
            description=f"Asset acquisition — {asset.name} [{asset.asset_number}]",
            reference=asset.asset_number,
            source_type='asset_addition',
            source_id=asset.pk,
            lines=[
                (asset_code, cost, 0,
                 f"Fixed asset — {asset.name} ({asset.get_category_display()})"),
                (ap_asset.code, 0, cost,
                 f"Supplier payable — {asset.supplier or 'N/A'}"),
            ],
            user=user,
            cost_center=_billing_cc('013'),
        )
    except Exception as e:
        logger.exception(f"GL auto-post failed for asset addition {asset.pk}: {e}")
        return None


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

        _accum_dep_code  = get_system_account('ACCUM_DEPRECIATION') or ACCUM_DEPRECIATION
        _fixed_asset_code = get_system_account('FIXED_ASSETS') or FIXED_ASSETS
        _loss_code       = get_system_account('LOSS_ON_DISPOSAL') or LOSS_ON_DISPOSAL
        _gain_code       = get_system_account('GAIN_ON_DISPOSAL') or GAIN_ON_DISPOSAL

        lines = [
            (_accum_dep_code, accum_dep, 0, f"Accumulated depreciation on {asset.name}"),
            (_fixed_asset_code, 0, cost, f"Disposal of {asset.name} (cost)"),
        ]

        if proceeds > 0:
            lines.append(
                (get_system_account('CASH_SAFE'), proceeds, 0, f"Proceeds from disposal of {asset.name}")
            )

        diff = nbv - proceeds
        if diff > 0:
            lines.append(
                (_loss_code, diff, 0, f"Loss on disposal of {asset.name}")
            )
        elif diff < 0:
            lines.append(
                (_gain_code, 0, abs(diff), f"Gain on disposal of {asset.name}")
            )

        entry = _create_entry(
            date=disposal.disposal_date,
            description=f"Asset disposal: {asset.name} ({disposal.get_disposal_method_display()})",
            reference=f"DISP-{disposal.pk}",
            source_type='asset_disposal',
            source_id=disposal.pk,
            lines=lines,
            user=user,
            cost_center=_billing_cc('013'),
            operation=_op_for_key('ASSET_DISPOSAL', 'ASSET'),
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
        credit_code = get_payment_account(refund.payment_method) or get_system_account('CASH_SAFE')
        if credit_code is None:
            credit_code = get_system_account('CASH_SAFE')

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

        dominant_cat = _dominant_category(item_list) if item_list else 'OTHER'
        _create_entry(
            date=refund.refund_date.date() if hasattr(refund.refund_date, 'date') else refund.refund_date,
            description=f"Refund — {invoice.invoice_number} — {invoice.patient.full_name}",
            reference=refund.reference or f"REF-{refund.pk}",
            source_type='refund',
            source_id=refund.pk,
            lines=lines,
            user=user or refund.processed_by,
            cost_center=_cc_for_service_category(dominant_cat),
            operation=_op_for_key('PATIENT_REFUND', 'CASH'),
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
            cost_center=_cc_for_service_category('OTHER'),
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
            cost_center=_billing_cc('012'),  # Administration cost center
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

                # Derive cost center from invoice dominant category
                _inv_items = list(wallet_txn.invoice.items.filter(is_deleted=False))
                _inv_cc = _cc_for_service_category(_inv_items[0].category if _inv_items else 'OTHER')
                _create_entry(
                    date=wallet_txn.created_at.date(),
                    description=f"Wallet payment — {wallet_txn.wallet.patient.full_name} — Inv {wallet_txn.invoice.invoice_number}",
                    reference=f"WPAY-{wallet_txn.pk}",
                    source_type='wallet_deduction',
                    source_id=wallet_txn.pk,
                    lines=lines,
                    user=user,
                    cost_center=_inv_cc,
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
            cost_center=_billing_cc('012'),  # Administration fallback
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
            operation=_op_for_key(entry.category, 'EXPENSE') if entry.entry_type == 'DEBIT'
                      else _op_for_key('CASH_FLOAT', 'CASH'),
            cost_center=_cc_for_expense_category(entry.category) if entry.entry_type == 'DEBIT'
                        else _billing_cc('012'),
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
            cost_center=_billing_cc('012'),  # Administration cost center
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
            cost_center=_billing_cc('012'),
            user=user or transfer.confirmed_by,
            operation=_op_for_key('CASH_TRANSFER', 'CASH'),
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

        ar_patient   = get_system_account('AR_PATIENT')
        ar_insurance = get_system_account('AR_INSURANCE') or ar_patient

        # Debit: Patient AR for patient's copay share
        if patient_amount > 0:
            lines.append((ar_patient, patient_amount, 0,
                          f"Patient copay — Inv {invoice.invoice_number} — {invoice.patient.full_name}"))

        # Debit: Insurance AR for insurer's share
        if ins_amount > 0:
            lines.append((ar_insurance, ins_amount, 0,
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

        dominant_cat_ins = _dominant_category(item_list) if item_list else 'OTHER'
        return _create_entry(
            date=invoice.issue_date,
            description=f"Invoice issued (insurance split) — {invoice.invoice_number} — {invoice.patient.full_name}",
            reference=invoice.invoice_number,
            source_type='invoice',
            source_id=invoice.pk,
            lines=lines,
            user=user or getattr(invoice, 'created_by', None),
            cost_center=_cc_for_service_category(dominant_cat_ins),
            operation=_op_for_key(dominant_cat_ins, 'REVENUE'),
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
            cost_center=_billing_cc('007'),
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
            cost_center=_billing_cc('007'),
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
            cost_center=_billing_cc('007'),
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
            cost_center=_billing_cc('012'),
            operation=_op_for_key('ADJUSTMENT', 'YEAR_END'),
        )
    except Exception as e:
        logger.exception(f"GL auto-post failed for cash variance {variance.pk}: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# PHARMACY → ACCOUNTING GL POSTINGS
# ═══════════════════════════════════════════════════════════════════════════════

PHARMACY_STOCK   = '321000'   # OHADA Class 3 — Pharmacy Stock (Marchandises)
THEATRE_STOCK    = '323000'   # OHADA Class 3 — Theatre/OT Consumables Stock
COGS_PHARMACY    = '601000'   # OHADA Class 6 — Cost of Goods Sold (Achats de marchandises)
PHARMACY_REVENUE = '7051501'  # Sales of Medications-MICEI (postable child of 705150)
STOCK_LOSS       = '603000'   # OHADA Class 6 — Stock Losses (damage, expiry, pilferage)
STOCK_GAIN       = '321000'   # Surplus goes back to stock

# GL account by PharmacyLocation type
_PHARMA_LOC_GL = {
    'MAIN':       '321000',
    'SATELLITE':  '321000',
    'WARD':       '321000',
    'OUTPATIENT': '321000',
    'EMERGENCY':  '321000',
    'THEATRE':    '323000',
}


def post_pharmacy_cogs(dispensing_item, user=None):
    """
    COGS recognition when pharmacy dispenses drugs.
    Called from DispensingItem.save() after physical stock is deducted.

    OHADA standard: when goods leave stock, recognise cost:
        Dr  601000 (COGS — Achats de marchandises vendues)
        Cr  321000 (Pharmacy Stock — Marchandises)

    Uses the drug's cost_price (purchase cost) × quantity, NOT the selling price.
    Idempotent: silently skips if a COGS entry for this item already exists.
    """
    try:
        # Idempotency guard — never post COGS twice for the same dispensing item
        from apps.billing.models import JournalEntry
        if JournalEntry.objects.filter(
            source_type='pharmacy_cogs', source_id=str(dispensing_item.pk)
        ).exists():
            return None

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

        # Determine if dispensed from theatre location (OT) or regular pharmacy
        _loc_type = None
        try:
            _loc_type = dispensing_item.dispensing.location.location_type
        except Exception:
            pass
        _pharma_stock_op_key = 'STOCK_OUT_OT' if _loc_type == 'THEATRE' else 'STOCK_OUT_PHARMA'
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
            cost_center=_billing_cc('001') if _loc_type == 'THEATRE' else _billing_cc('008'),
            operation=_op_for_key(_pharma_stock_op_key, 'STOCK'),
        )
    except Exception as e:
        logger.exception(f"GL auto-post failed for pharmacy COGS {dispensing_item.pk}: {e}")
        return None


def post_pharmacy_transfer(transfer, user=None):
    """
    GL reclassification when pharmacy stock moves between locations.
    No P&L impact — just balance sheet sub-account reclass.
        Dr  destination location GL (e.g. 323000 Theatre or 321000 Pharmacy)
        Cr  source location GL      (e.g. 321000 Pharmacy)
    If both locations use the same GL account, no journal entry is posted.
    """
    try:
        from django.utils import timezone as _tz
        src_code = _PHARMA_LOC_GL.get(transfer.from_location.location_type, '321000')
        dst_code = _PHARMA_LOC_GL.get(transfer.to_location.location_type, '321000')
        if src_code == dst_code:
            return None  # Same sub-account — no reclass needed

        total = Decimal('0')
        items = transfer.items.select_related('drug', 'stock_batch').all()
        for item in items:
            qty = item.quantity_received or item.quantity or 0
            if qty <= 0:
                continue
            cost = Decimal('0')
            if item.stock_batch:
                cost = getattr(item.stock_batch, 'unit_cost', None) or \
                       getattr(item.stock_batch, 'purchase_price', None) or Decimal('0')
            if cost <= 0 and item.drug:
                cost = getattr(item.drug, 'cost_price', None) or \
                       getattr(item.drug, 'purchase_price', None) or Decimal('0')
            total += Decimal(str(cost)) * Decimal(str(qty))

        if total <= 0:
            return None

        ref = transfer.transfer_number
        return _create_entry(
            date=_tz.localdate(),
            description=f"Stock transfer: {transfer.from_location.name} → {transfer.to_location.name} [{ref}]",
            reference=ref,
            source_type='pharmacy_transfer',
            source_id=transfer.pk,
            lines=[
                (dst_code, total, 0,
                 f"Transfer IN from {transfer.from_location.name}"),
                (src_code, 0, total,
                 f"Transfer OUT to {transfer.to_location.name}"),
            ],
            user=user,
            cost_center=getattr(getattr(transfer, 'to_location', None), 'cost_center', None) or _billing_cc('008'),
            operation=_op_for_key('STOCK_TRANSFER', 'STOCK'),
        )
    except Exception as e:
        logger.exception(f"GL auto-post failed for pharmacy transfer {transfer.pk}: {e}")
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
            cost_center=_billing_cc('008'),
            operation=_op_for_key('PHARMACY', 'REVENUE'),
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
            cost_center=_billing_cc('008'),
            operation=_op_for_key('EXPIRED_STOCK', 'STOCK') if adjustment.quantity_change < 0
                      else _op_for_key('STOCK_IN_PHARMACY', 'STOCK'),
        )
    except Exception as e:
        logger.exception(f"GL auto-post failed for stock adjustment {adjustment.pk}: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# OPTICAL STORE — COGS & STOCK RECEIPT
# ═══════════════════════════════════════════════════════════════════════════════

# OHADA accounts for optical merchandise:
#   371000 — Optical stock (Marchandises — Optique)
#   607000 — COGS optical (Achats de marchandises optiques)
OPTICAL_STOCK = '371000'
OPTICAL_COGS  = '607000'


def post_optical_cogs(order, user=None):
    """
    COGS recognition when an optical order is DELIVERED.
    Records the cost of frames and lenses leaving inventory:

        Dr  607000 (COGS — Achats marchandises optiques)
        Cr  371000 (Optical Stock — Marchandises)

    Uses Frame.cost_price and Lens.cost_price (purchase cost).
    Silently skips if cost prices are zero (not yet set in catalogue).
    """
    try:
        from django.utils import timezone as _tz
        total_cost = Decimal('0')
        lines_debit = []
        lines_credit = []

        if order.frame and getattr(order.frame, 'cost_price', 0):
            fc = Decimal(str(order.frame.cost_price))
            if fc > 0:
                total_cost += fc
                lines_debit.append((OPTICAL_COGS, fc, 0,
                    f"COGS Frame — {order.frame.brand} {order.frame.model}"))
                lines_credit.append((OPTICAL_STOCK, 0, fc,
                    f"Stock out — Frame {order.frame.brand} {order.frame.model}"))

        if order.lens and getattr(order.lens, 'cost_price', 0):
            lc = Decimal(str(order.lens.cost_price))
            if lc > 0:
                total_cost += lc
                lines_debit.append((OPTICAL_COGS, lc, 0,
                    f"COGS Lens — {order.lens.lens_type} {order.lens.brand}"))
                lines_credit.append((OPTICAL_STOCK, 0, lc,
                    f"Stock out — Lens {order.lens.lens_type}"))

        if total_cost <= 0:
            return None   # No cost prices set — skip silently

        return _create_entry(
            date=order.delivered_date or _tz.localdate(),
            description=f"COGS Optical — {order.order_number} — {order.patient.full_name}",
            reference=order.order_number,
            source_type='optical_cogs',
            source_id=order.pk,
            lines=lines_debit + lines_credit,
            user=user,
            cost_center=_billing_cc('009'),
            operation=_op_for_key('STOCK_OUT_OPTICAL', 'STOCK'),
        )
    except Exception as e:
        logger.exception(f"GL auto-post failed for optical COGS order {order.pk}: {e}")
        return None


def post_optical_stock_receipt(frame, quantity, unit_cost, supplier_ref='', user=None):
    """
    GL posting when optical frame/lens stock is received from supplier.

        Dr  371000 (Optical Stock)   — inventory increases
        Cr  401100 (AP Vendors)      — payable to supplier

    Called from opticals.views.frame_receive_stock / lens_receive_stock
    when unit_cost is provided.
    """
    try:
        from django.utils import timezone as _tz
        if not unit_cost or unit_cost <= 0 or quantity <= 0:
            return None
        amount = Decimal(str(unit_cost)) * Decimal(str(quantity))
        ap_code = get_system_account('AP_VENDORS')
        return _create_entry(
            date=_tz.localdate(),
            description=f"Stock receipt — {frame} x{quantity} units",
            reference=supplier_ref or f"RCV-{str(frame.pk)[:8]}",
            source_type='optical_stock_receipt',
            source_id=frame.pk,
            lines=[
                (OPTICAL_STOCK, amount, 0,
                 f"Stock in — {frame} x{quantity} @ {unit_cost} FCFA"),
                (ap_code, 0, amount,
                 f"Payable to supplier — {supplier_ref or 'N/A'}"),
            ],
            user=user,
            cost_center=_billing_cc('009'),
            operation=_op_for_key('STOCK_IN_OPTICAL', 'STOCK'),
        )
    except Exception as e:
        logger.exception(f"GL auto-post failed for optical stock receipt {frame.pk}: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# CASH WITHDRAWAL & DESK SUPPLY GL POSTINGS
# ══════════════════════════════════════════════════════════════════════════════

def post_cash_withdrawal(withdrawal, user=None):
    """
    GL posting for Retrait Espèces / Retrait Multiple / Retrait Patient.

    Single-line:  Dr  gl_account (expense/advance)  |  Cr  Cash 572000
    Multi-line:   Dr  each line's gl_account         |  Cr  Cash 572000 (sum)
    Reversal:     Creates inverse entry (Cr expense / Dr Cash).
    """
    try:
        if withdrawal.is_reversed and not withdrawal.reversal_ref:
            # Skip — already reversed, avoid double-posting
            return None
        from apps.billing.models import JournalEntry
        if JournalEntry.objects.filter(
            source_type='cash_withdrawal', source_id=str(withdrawal.pk)
        ).exists():
            return None

        amount = Decimal(str(withdrawal.total_amount))
        if amount <= 0:
            return None

        cash_code = _PAYMENT_DEFAULTS['CASH']   # 572000
        exp_default = _EXPENSE_DEFAULTS['EXP_OTHER']  # 658000

        if withdrawal.is_multi_line:
            lines_qs = withdrawal.lines.all()
            dr_lines = []
            for line in lines_qs:
                acc = line.gl_account.code if line.gl_account else exp_default
                desc = line.libelle or line.auto_libelle or withdrawal.reason or 'Retrait Multiple'
                dr_lines.append((acc, Decimal(str(line.amount)), 0, desc))
            dr_lines.append((cash_code, 0, amount, f"Sortie caisse — {withdrawal.bordereau_number}"))
            lines = dr_lines
        else:
            dr_code = withdrawal.gl_account.code if withdrawal.gl_account else exp_default
            desc = withdrawal.reason or f"Retrait — {withdrawal.bordereau_number}"
            lines = [
                (dr_code, amount, 0, desc),
                (cash_code, 0, amount, f"Sortie caisse — {withdrawal.cash_desk}"),
            ]

        if withdrawal.is_reversed:
            # Extourne: swap Dr / Cr
            lines = [(acc, cr, dr, d) for (acc, dr, cr, d) in lines]

        return _create_entry(
            date=withdrawal.withdrawal_date,
            description=f"Retrait caisse {withdrawal.bordereau_number} — {withdrawal.reason or ''}",
            reference=withdrawal.bordereau_number,
            source_type='cash_withdrawal',
            source_id=withdrawal.pk,
            lines=lines,
            user=user,
            operation=_op_for_key('CASH_WITHDRAW', 'CASH'),
            cost_center=_cc_for_desk(getattr(withdrawal, 'cash_desk', None)),
        )
    except Exception as e:
        logger.exception(f"GL auto-post failed for cash withdrawal {withdrawal.pk}: {e}")
        return None


def post_depreciation_monthly(asset, period_year, period_month, user=None):
    """
    Monthly straight-line depreciation journal entry per OHADA SYSCOHADA.

    OHADA Op 160:
        Dr  681301  Dotations aux amortissements — immobilisations corporelles
        Cr  284400  Amortissements des équipements (or category-specific acc. dep. account)

    Idempotency: reference "DEP-{asset_number}-{YYYYMM}" prevents double-posting.
    """
    from decimal import Decimal as _D
    try:
        annual = _D(str(asset.annual_depreciation or 0))
        if annual <= 0:
            return None

        monthly_amount = (annual / 12).quantize(_D('0.01'))
        if monthly_amount <= 0:
            return None

        # Already posted for this period?
        period_ref = f"DEP-{asset.asset_number}-{period_year}{period_month:02d}"
        from apps.billing.models import JournalEntry
        if JournalEntry.objects.filter(reference=period_ref).exists():
            return None

        # Depreciation expense account (OHADA 681xxx)
        dep_exp_code = '681301'
        dep_exp = GLAccount.objects.filter(code=dep_exp_code, is_deleted=False).first()
        if not dep_exp:
            dep_exp = GLAccount.objects.filter(code__startswith='681', is_deleted=False).first()

        # Accumulated depreciation account — map by category
        ACCUM_MAP = {
            'BUILDING':     '281100',
            'VEHICLE':      '284500',
            'EQUIPMENT':    '284400',
            'IT_EQUIPMENT': '284200',
            'FURNITURE':    '284400',
            'MEDICAL':      '284400',
            'OTHER':        '284900',
        }
        accum_code = ACCUM_MAP.get(str(asset.category), '284400')
        accum_acc = GLAccount.objects.filter(code=accum_code, is_deleted=False).first()
        if not accum_acc:
            accum_acc = GLAccount.objects.filter(code__startswith='284', is_deleted=False).first()

        if not dep_exp or not accum_acc:
            logger.warning(f"Depreciation GL accounts not found for {asset.asset_number} — skipping.")
            return None

        import datetime
        period_date = datetime.date(period_year, period_month, 1)

        return _create_entry(
            date=period_date,
            description=f"Dotations aux amortissements — {asset.name} [{asset.asset_number}] {period_year}/{period_month:02d}",
            reference=period_ref,
            source_type='depreciation',
            source_id=asset.pk,
            lines=[
                (dep_exp_code, monthly_amount, 0,
                 f"Amort. {asset.name} — {period_year}/{period_month:02d}"),
                (accum_acc.code, 0, monthly_amount,
                 f"Amort. cumulé {asset.name} — {period_year}/{period_month:02d}"),
            ],
            user=user,
            cost_center=_billing_cc('013'),
            operation=_op_for_key('DEPRECIATION', 'ASSET'),
        )
    except Exception as e:
        logger.exception(f"GL depreciation post failed for {asset.asset_number}: {e}")
        return None


def post_desk_supply(supply, user=None):
    """
    GL posting for Approvisionnement Caisse (desk fund/drain).

    ENTREE (bank → desk):  Dr  Cash 572000  |  Cr  Bank 521100
    SORTIE (desk → bank):  Dr  Bank 521100  |  Cr  Cash 572000
    """
    try:
        from apps.billing.models import JournalEntry, CashDeskSupplyDirection
        if JournalEntry.objects.filter(
            source_type='desk_supply', source_id=str(supply.pk)
        ).exists():
            return None

        amount = Decimal(str(supply.amount))
        if amount <= 0:
            return None

        cash_code = _PAYMENT_DEFAULTS['CASH']   # 572000
        bank_code = supply.bank_account.gl_account.code if (
            supply.bank_account and supply.bank_account.gl_account
        ) else get_system_account('BANK_ACCOUNT')

        if supply.direction == CashDeskSupplyDirection.ENTREE:
            # Bank → Desk
            lines = [
                (cash_code, amount, 0, f"Approvisionnement caisse — {supply.cash_desk}"),
                (bank_code, 0, amount, f"Sortie banque — {supply.bank_account or 'Banque'}"),
            ]
        else:
            # Desk → Bank (SORTIE)
            lines = [
                (bank_code, amount, 0, f"Versement banque — {supply.bank_account or 'Banque'}"),
                (cash_code, 0, amount, f"Sortie caisse — {supply.cash_desk}"),
            ]

        return _create_entry(
            date=supply.supply_date,
            description=f"Approvisionnement caisse {supply.supply_number} — {supply.get_direction_display()}",
            reference=supply.supply_number,
            source_type='desk_supply',
            source_id=supply.pk,
            lines=lines,
            user=user,
            operation=_op_for_key('CASH_FLOAT', 'CASH'),
            cost_center=_cc_for_desk(getattr(supply, 'cash_desk', None)),
        )
    except Exception as e:
        logger.exception(f"GL auto-post failed for desk supply {supply.pk}: {e}")
        return None
