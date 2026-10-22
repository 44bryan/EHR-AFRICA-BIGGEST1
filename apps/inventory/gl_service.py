"""
Inventory GL Service — Auto-posting for stock transactions.

Every financial inventory event auto-posts to the General Ledger following
OHADA SYCEBNL standards:
  - Stock received   → Dr Class 3 (Stock)       / Cr 603 (Variation in Stock)
  - Stock issued out → Dr 603 (Variation in Stock) / Cr Class 3 (Stock)
  - Stock disposal   → Dr 603 (Variation in Stock) / Cr Class 3 (Stock)
  - Stock adjustment → Dr or Cr accordingly
  - Stock count var  → Dr 603 or 658 / Cr Class 3 (or reverse)
  - Department return→ Dr Class 3 (Stock)       / Cr 603 (Variation in Stock)

4-Eyes Principle: GL posting happens ONLY when Finance Director validates.
"""
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)

# ── OHADA Account Code Map ───────────────────────────────────────────────────
# Stock accounts by InventoryItem category → OHADA Class 3 sub-accounts
STOCK_ACCOUNT_MAP = {
    'PHARMACEUTICAL': '32',     # Merchandise, raw materials
    'SURGICAL':       '33',     # Other supplies
    'MEDICAL_CONSUMABLE': '33', # Other supplies
    'DIAGNOSTIC':     '33',     # Other supplies
    'IMPLANT':        '32',     # Merchandise
    'LENS':           '32',     # Merchandise — Ophthalmic lenses
    'FRAME':          '32',     # Merchandise — Optical frames
    'OFFICE':         '33',     # Other supplies
    'CLEANING':       '33',     # Other supplies
    'IT':             '33',     # Other supplies
    'FURNITURE':      '33',     # Other supplies
    'LINEN':          '33',     # Other supplies
    'OTHER':          '33',     # Other supplies
}

# Variation in stock (expense-side)
VARIATION_IN_STOCK = '603'      # Variation des stocks de biens achetes

# Loss / shortage account (for unexplained variances)
STOCK_LOSS_ACCOUNT = '658'      # Other expenses (shortages)


def _get_account(code):
    """Fetch GLAccount by code prefix. Returns the most specific match."""
    from apps.billing.models import GLAccount
    try:
        # Try exact match first
        acct = GLAccount.objects.filter(code=code, is_active=True, is_deleted=False).first()
        if acct:
            return acct
        # Try prefix match (e.g. '603' matches '6031' etc.)
        acct = GLAccount.objects.filter(
            code__startswith=code, is_active=True, is_deleted=False
        ).order_by('code').first()
        if acct:
            return acct
        logger.warning(f"GL account {code} not found — GL not seeded. Skipping auto-post.")
        return None
    except Exception:
        logger.warning(f"GL account {code} lookup failed.")
        return None


def _op_for_code(op_code):
    """Look up BillingOperationCC by operation_code. Returns instance or None."""
    if not op_code:
        return None
    try:
        from apps.billing.models import BillingOperationCC
        return BillingOperationCC.objects.filter(
            operation_code=str(op_code), is_deleted=False
        ).first()
    except Exception:
        return None


def _create_entry(date, description, reference, source_type, source_id, lines,
                  user=None, cost_center=None, operation=None):
    """
    Create a balanced JournalEntry with the given lines.
    lines = list of (account_code, debit, credit, description)
    cost_center: CostCenter instance — auto-resolved from store location.
    operation: BillingOperationCC instance — TurboClinic operation code tag.
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
        logger.error(
            f"Unbalanced inventory journal entry for {source_type} {source_id}: "
            f"Dr={total_dr} Cr={total_cr}"
        )
        return None

    # OHADA analytical rule: cost center applies ONLY to Class 6 (Charges) and
    # Class 7 (Produits) lines. Class 3 (Stock), 4 (Créances/Dettes), 5 (Trésorerie)
    # must be left unassigned per SYSCOHADA.
    # The entry header also gets the cost center if any analytical line exists.
    has_analytical_line = any(str(acct.code)[:1] in ('6', '7') for acct, _, _, _ in resolved)
    entry_cc = cost_center if has_analytical_line else None

    entry = JournalEntry.objects.create(
        entry_date=date,
        description=description,
        reference=reference,
        source_type=source_type,
        source_id=str(source_id),
        is_posted=True,
        created_by=user,
        cost_center=entry_cc,
        operation=operation,
    )
    for seq, (acct, debit, credit, desc) in enumerate(resolved, 1):
        # Per-line cost center: only Class 6 and 7 accounts get the cost center tag
        line_cc = cost_center if (cost_center and str(acct.code)[:1] in ('6', '7')) else None
        JournalLine.objects.create(
            entry=entry,
            account=acct,
            debit_amount=debit,
            credit_amount=credit,
            description=desc,
            sequence=seq,
            cost_center=line_cc,
        )
    return entry


def _category_gl(item):
    """Return the ItemCategoryGL mapping for this item's category, or None."""
    try:
        from apps.inventory.models import ItemCategoryGL
        return ItemCategoryGL.objects.filter(category=item.category).select_related(
            'inventory_account', 'cogs_account', 'loss_account'
        ).first()
    except Exception:
        return None


def _stock_code_for_item(item):
    """
    Get the OHADA Class 3 stock account code for an inventory item.
    Priority:
      1. ItemCategoryGL.inventory_account (set by Finance Director — highest authority)
      2. StoreLocation.gl_account_code (store-level override)
      3. STOCK_ACCOUNT_MAP fallback (hardcoded defaults)
    """
    mapping = _category_gl(item)
    if mapping and mapping.inventory_account:
        return mapping.inventory_account.code
    if hasattr(item, 'store_location') and item.store_location and item.store_location.gl_account_code:
        return item.store_location.gl_account_code
    return STOCK_ACCOUNT_MAP.get(item.category, '33')


def _cogs_code_for_item(item):
    """
    Get the COGS / variation-in-stock account code for an item.
    Priority:
      1. ItemCategoryGL.cogs_account
      2. Default VARIATION_IN_STOCK (603)
    """
    mapping = _category_gl(item)
    if mapping and mapping.cogs_account:
        return mapping.cogs_account.code
    return VARIATION_IN_STOCK


def _loss_code_for_item(item):
    """
    Get the loss/write-off account code for an item (disposal, expiry, variance).
    Priority:
      1. ItemCategoryGL.loss_account
      2. Default STOCK_LOSS_ACCOUNT (658)
    """
    mapping = _category_gl(item)
    if mapping and mapping.loss_account:
        return mapping.loss_account.code
    return STOCK_LOSS_ACCOUNT


def _cost_center_for_item(item):
    """Return the CostCenter linked to this item's store location, or None."""
    try:
        if item and hasattr(item, 'store_location') and item.store_location:
            return item.store_location.cost_center
    except Exception:
        pass
    return None


def _cost_center_for_store(store):
    """Return the CostCenter linked to a StoreLocation instance, or None."""
    try:
        if store:
            return store.cost_center
    except Exception:
        pass
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API — Called by views after Finance Director validation
# ═══════════════════════════════════════════════════════════════════════════════

def post_stock_receipt(grn, user=None):
    """
    GL posting when stock is received (GRN accepted + validated by Finance Director).

    OHADA 3-way match — goods arrive before supplier invoice:
        Dr  Class 3 (Stock account)      →  asset in warehouse
        Cr  408100 (Supplier Awaiting Invoice)  →  accrued liability, invoice pending

    When the supplier invoice (APBill) is later matched to this GRN,
    post_ap_bill() clears 408100 and records the formal AP creditor:
        Dr  408100  →  clears the accrual
        Cr  401xxx  →  AP Vendors (formal payable)
    """
    try:
        from apps.inventory.models import GRNItem
        items = GRNItem.objects.filter(grn=grn).select_related('po_item__item')
        lines = []
        total = Decimal('0')

        for gi in items:
            qty = gi.quantity_accepted or 0
            if qty <= 0:
                continue
            unit_cost = gi.po_item.unit_price if gi.po_item else Decimal('0')
            amount = Decimal(str(qty)) * Decimal(str(unit_cost))
            if amount <= 0:
                continue
            total += amount
            stock_code = _stock_code_for_item(gi.po_item.item)
            lines.append((
                stock_code, amount, 0,
                f"Stock received: {gi.po_item.item.name} x{qty} @ {unit_cost}"
            ))

        if total <= 0 or not lines:
            return None

        # Credit 408100 (Supplier Awaiting Invoice) — accrued liability until
        # the supplier invoice arrives and is matched to this GRN.
        lines.append((
            '408100', 0, total,
            f"Supplier awaiting invoice — GRN {grn.grn_number} — PO {grn.purchase_order.po_number}"
        ))

        # Cost center: from the receiving store of the first item
        cost_center = None
        first_item = items.first()
        if first_item and first_item.po_item:
            cost_center = _cost_center_for_item(first_item.po_item.item)

        return _create_entry(
            date=grn.received_date,
            description=f"Stock receipt — GRN {grn.grn_number} — PO {grn.purchase_order.po_number}",
            reference=grn.grn_number,
            source_type='stock_receipt',
            source_id=grn.pk,
            lines=lines,
            user=user,
            cost_center=cost_center,
            operation=_op_for_code('141'),
        )
    except Exception as e:
        logger.exception(f"GL auto-post failed for GRN {grn.pk}: {e}")
        return None


def post_stock_issue(requisition, user=None):
    """
    GL posting when stock is issued to a department (requisition fulfilled).
        Dr  603 (Variation in Stock)
        Cr  Class 3 (Stock account)
    """
    try:
        from apps.inventory.models import RequisitionItem
        items = RequisitionItem.objects.filter(
            requisition=requisition
        ).select_related('item')
        lines = []
        total = Decimal('0')

        cost_center = None
        for ri in items:
            qty = ri.quantity_issued or 0
            if qty <= 0:
                continue
            unit_cost = ri.item.unit_cost or Decimal('0')
            amount = Decimal(str(qty)) * Decimal(str(unit_cost))
            if amount <= 0:
                continue
            total += amount
            stock_code = _stock_code_for_item(ri.item)
            if cost_center is None:
                cost_center = _cost_center_for_item(ri.item)
            lines.append((
                stock_code, 0, amount,
                f"Issued: {ri.item.name} x{qty} to {requisition.department}"
            ))

        if total <= 0 or not lines:
            return None

        # Use item-specific COGS code for first item; fall back to default 603
        first_item_obj = next((ri.item for ri in items if (ri.quantity_issued or 0) > 0), None)
        cogs_code = _cogs_code_for_item(first_item_obj) if first_item_obj else VARIATION_IN_STOCK
        lines.insert(0, (
            cogs_code, total, 0,
            f"Stock issued — REQ {requisition.req_number}"
        ))

        return _create_entry(
            date=requisition.issued_at.date() if hasattr(requisition.issued_at, 'date') else requisition.issued_at or requisition.updated_at.date(),
            description=f"Stock issued — REQ {requisition.req_number} — {requisition.department}",
            reference=requisition.req_number,
            source_type='stock_issue',
            source_id=requisition.pk,
            lines=lines,
            user=user,
            cost_center=cost_center,
            operation=_op_for_code('142'),
        )
    except Exception as e:
        logger.exception(f"GL auto-post failed for requisition {requisition.pk}: {e}")
        return None


def post_stock_disposal(disposal, user=None):
    """
    GL posting when stock is disposed of.
        Dr  603 (Variation in Stock)
        Cr  Class 3 (Stock account)
    """
    try:
        from apps.inventory.models import DisposalItem
        items = DisposalItem.objects.filter(disposal=disposal).select_related('item')
        lines = []
        total = Decimal('0')

        cost_center = None
        first_item_obj = None
        for di in items:
            amount = Decimal(str(di.quantity)) * Decimal(str(di.unit_cost or 0))
            if amount <= 0:
                continue
            total += amount
            stock_code = _stock_code_for_item(di.item)
            if cost_center is None:
                cost_center = _cost_center_for_item(di.item)
                first_item_obj = di.item
            lines.append((
                stock_code, 0, amount,
                f"Disposed: {di.item.name} x{di.quantity} ({disposal.get_reason_display()})"
            ))

        if total <= 0 or not lines:
            return None

        loss_code = _loss_code_for_item(first_item_obj) if first_item_obj else STOCK_LOSS_ACCOUNT
        lines.insert(0, (
            loss_code, total, 0,
            f"Stock disposal — {disposal.disposal_number}"
        ))

        return _create_entry(
            date=disposal.disposal_date or disposal.updated_at.date(),
            description=f"Stock disposal — {disposal.disposal_number} ({disposal.get_disposal_method_display()})",
            reference=disposal.disposal_number,
            source_type='stock_disposal',
            source_id=disposal.pk,
            lines=lines,
            user=user,
            cost_center=cost_center,
            operation=_op_for_code('144'),
        )
    except Exception as e:
        logger.exception(f"GL auto-post failed for disposal {disposal.pk}: {e}")
        return None


def post_stock_entry(entry_ref, items_data, entry_date, user=None, operation_type=None, cost_center=None):
    """
    GL posting for direct stock entry (walk-in delivery, donation, etc.).
    items_data = list of (item, quantity, unit_cost) tuples.

    If operation_type (StockOperationType) is provided, use its debit_account/credit_account
    instead of the default Class 3 / 603 mapping.
        Default:  Dr Class 3 (Stock) / Cr 603 (Variation in Stock)
        With op:  Dr operation_type.debit_account / Cr operation_type.credit_account
    """
    try:
        lines = []
        total = Decimal('0')

        # Determine GL accounts from operation type or fall back to defaults
        op_dr_code = None
        op_cr_code = None
        if operation_type and operation_type.debit_account and operation_type.credit_account:
            op_dr_code = operation_type.debit_account.code
            op_cr_code = operation_type.credit_account.code

        for item, qty, unit_cost in items_data:
            amount = Decimal(str(qty)) * Decimal(str(unit_cost or 0))
            if amount <= 0:
                continue
            total += amount
            dr_code = op_dr_code or _stock_code_for_item(item)
            lines.append((
                dr_code, amount, 0,
                f"Stock entry: {item.name} x{qty} @ {unit_cost}"
            ))

        if total <= 0 or not lines:
            return None

        cr_code = op_cr_code or VARIATION_IN_STOCK
        lines.append((
            cr_code, 0, total,
            f"Variation in stock — Entry {entry_ref}"
        ))

        # Auto-resolve cost_center from first item if not supplied
        if cost_center is None:
            first_item_obj = next((item for item, _, _ in items_data), None)
            if first_item_obj:
                cost_center = _cost_center_for_item(first_item_obj)

        op_billing = _op_for_code(operation_type.code) if operation_type else None
        return _create_entry(
            date=entry_date,
            description=f"Stock entry — {entry_ref}",
            reference=entry_ref,
            source_type='stock_entry',
            source_id=entry_ref,
            lines=lines,
            user=user,
            cost_center=cost_center,
            operation=op_billing,
        )
    except Exception as e:
        logger.exception(f"GL auto-post failed for stock entry {entry_ref}: {e}")
        return None


def post_stock_exit(exit_ref, items_data, exit_date, reason='', user=None, operation_type=None, cost_center=None):
    """
    GL posting for direct stock exit (patient use, maintenance, etc.).
    items_data = list of (item, quantity, unit_cost) tuples.

    If operation_type (StockOperationType) is provided, use its debit_account/credit_account
    instead of the default 603 / Class 3 mapping.
        Default:  Dr 603 (Variation in Stock) / Cr Class 3 (Stock)
        With op:  Dr operation_type.debit_account / Cr operation_type.credit_account
    """
    try:
        lines = []
        total = Decimal('0')

        # Determine GL accounts from operation type or fall back to defaults
        op_dr_code = None
        op_cr_code = None
        if operation_type and operation_type.debit_account and operation_type.credit_account:
            op_dr_code = operation_type.debit_account.code
            op_cr_code = operation_type.credit_account.code

        for item, qty, unit_cost in items_data:
            amount = Decimal(str(qty)) * Decimal(str(unit_cost or 0))
            if amount <= 0:
                continue
            total += amount
            cr_code = op_cr_code or _stock_code_for_item(item)
            lines.append((
                cr_code, 0, amount,
                f"Stock exit: {item.name} x{qty} ({reason})"
            ))

        if total <= 0 or not lines:
            return None

        dr_code = op_dr_code or VARIATION_IN_STOCK
        lines.insert(0, (
            dr_code, total, 0,
            f"Variation in stock — Exit {exit_ref}"
        ))

        # Auto-resolve cost_center from first item if not supplied
        if cost_center is None:
            first_item_obj = next((item for item, _, _ in items_data), None)
            if first_item_obj:
                cost_center = _cost_center_for_item(first_item_obj)

        op_billing = _op_for_code(operation_type.code) if operation_type else None
        return _create_entry(
            date=exit_date,
            description=f"Stock exit — {exit_ref} — {reason}",
            reference=exit_ref,
            source_type='stock_exit',
            source_id=exit_ref,
            lines=lines,
            user=user,
            cost_center=cost_center,
            operation=op_billing,
        )
    except Exception as e:
        logger.exception(f"GL auto-post failed for stock exit {exit_ref}: {e}")
        return None


def post_stock_adjustment(item, quantity, unit_cost, adj_date, reference, reason='', user=None):
    """
    GL posting for stock adjustment (manual correction).
    Positive quantity = stock increase (Dr Stock / Cr 603)
    Negative quantity = stock decrease (Dr 603 / Cr Stock)
    """
    try:
        amount = abs(Decimal(str(quantity))) * Decimal(str(unit_cost or 0))
        if amount <= 0:
            return None

        stock_code = _stock_code_for_item(item)

        if quantity > 0:
            lines = [
                (stock_code, amount, 0, f"Adjustment (+): {item.name} x{quantity}"),
                (VARIATION_IN_STOCK, 0, amount, f"Variation in stock — adjustment {reference}"),
            ]
        else:
            lines = [
                (VARIATION_IN_STOCK, amount, 0, f"Variation in stock — adjustment {reference}"),
                (stock_code, 0, amount, f"Adjustment (-): {item.name} x{abs(quantity)}"),
            ]

        adj_op_code = '133' if quantity > 0 else '142'
        return _create_entry(
            date=adj_date,
            description=f"Stock adjustment — {item.name} — {reason or reference}",
            reference=reference,
            source_type='stock_adjustment',
            source_id=reference,
            lines=lines,
            user=user,
            cost_center=_cost_center_for_item(item),
            operation=_op_for_code(adj_op_code),
        )
    except Exception as e:
        logger.exception(f"GL auto-post failed for stock adjustment {reference}: {e}")
        return None


def post_stock_count_variance(stock_count, user=None):
    """
    GL posting for stock count variances.
    For each item with variance:
      Positive variance (found more): Dr Stock / Cr 603
      Negative variance (shortage):   Dr 603 / Cr Stock
    """
    try:
        from apps.inventory.models import StockCountItem
        items = StockCountItem.objects.filter(
            stock_count=stock_count
        ).select_related('item')

        lines = []
        for sci in items:
            variance = sci.variance or 0
            if variance == 0:
                continue
            unit_cost = sci.item.unit_cost or Decimal('0')
            amount = abs(Decimal(str(variance))) * Decimal(str(unit_cost))
            if amount <= 0:
                continue
            stock_code = _stock_code_for_item(sci.item)

            if variance > 0:
                # Found more stock than expected
                lines.append((stock_code, amount, 0, f"Surplus: {sci.item.name} +{variance}"))
                lines.append((VARIATION_IN_STOCK, 0, amount, f"Stock count surplus — {sci.item.name}"))
            else:
                # Shortage
                lines.append((VARIATION_IN_STOCK, amount, 0, f"Shortage: {sci.item.name} {variance}"))
                lines.append((stock_code, 0, amount, f"Stock count shortage — {sci.item.name}"))

        if not lines:
            return None

        # Cost center from stock count's store location (if stock_count has one)
        store_cc = None
        if hasattr(stock_count, 'store_location') and stock_count.store_location:
            store_cc = _cost_center_for_store(stock_count.store_location)
        elif items.exists():
            store_cc = _cost_center_for_item(items.first().item)

        return _create_entry(
            date=stock_count.count_date,
            description=f"Stock count variance — {stock_count.count_number}",
            reference=stock_count.count_number,
            source_type='stock_count',
            source_id=stock_count.pk,
            lines=lines,
            user=user,
            cost_center=store_cc,
            operation=_op_for_code('144'),
        )
    except Exception as e:
        logger.exception(f"GL auto-post failed for stock count {stock_count.pk}: {e}")
        return None


def post_inter_store_transfer(transfer, user=None):
    """
    GL posting for inter-store transfers.
    No P&L impact — just balance sheet reclassification between Class 3 sub-accounts.
        Dr  destination store GL (stock in)
        Cr  source store GL      (stock out)
    """
    try:
        from apps.inventory.models import StoreTransferItem
        items = StoreTransferItem.objects.filter(transfer=transfer).select_related('item')
        lines = []
        total = Decimal('0')

        src_code = transfer.from_location.gl_account_code or '311000'
        dst_code = transfer.to_location.gl_account_code or '311000'

        if src_code == dst_code:
            # Same GL account — no journal entry needed
            return None

        for ti in items:
            qty = ti.quantity or 0
            if qty <= 0:
                continue
            unit_cost = ti.item.unit_cost or Decimal('0')
            amount = Decimal(str(qty)) * Decimal(str(unit_cost))
            if amount <= 0:
                continue
            total += amount

        if total <= 0:
            return None

        lines = [
            (dst_code, total, 0,
             f"Transfer in: {transfer.transfer_number} from {transfer.from_location.name}"),
            (src_code, 0, total,
             f"Transfer out: {transfer.transfer_number} to {transfer.to_location.name}"),
        ]

        return _create_entry(
            date=transfer.transfer_date,
            description=f"Inter-store transfer — {transfer.transfer_number} — "
                        f"{transfer.from_location.name} → {transfer.to_location.name}",
            reference=transfer.transfer_number,
            source_type='store_transfer',
            source_id=transfer.pk,
            lines=lines,
            user=user,
            cost_center=_cost_center_for_store(transfer.from_location),
            operation=_op_for_code('156'),
        )
    except Exception as e:
        logger.exception(f"GL auto-post failed for transfer {transfer.pk}: {e}")
        return None


def post_department_return(dept_return, user=None):
    """
    GL posting when good-condition items are returned to store.
        Dr  Class 3 (Stock account)
        Cr  603 (Variation in Stock)
    """
    try:
        from apps.inventory.models import DepartmentReturnItem
        items = DepartmentReturnItem.objects.filter(
            department_return=dept_return, condition='GOOD'
        ).select_related('item')
        lines = []
        total = Decimal('0')

        cost_center = None
        first_item_obj = None
        for dri in items:
            qty = dri.quantity or 0
            if qty <= 0:
                continue
            unit_cost = dri.item.unit_cost or Decimal('0')
            amount = Decimal(str(qty)) * Decimal(str(unit_cost))
            if amount <= 0:
                continue
            total += amount
            stock_code = _stock_code_for_item(dri.item)
            if cost_center is None:
                cost_center = _cost_center_for_item(dri.item)
                first_item_obj = dri.item
            lines.append((
                stock_code, amount, 0,
                f"Returned: {dri.item.name} x{qty} (good condition)"
            ))

        if total <= 0 or not lines:
            return None

        cogs_code = _cogs_code_for_item(first_item_obj) if first_item_obj else VARIATION_IN_STOCK
        lines.append((
            cogs_code, 0, total,
            f"Stock return — {dept_return.return_number}"
        ))

        return _create_entry(
            date=dept_return.updated_at.date(),
            description=f"Department return — {dept_return.return_number} — {dept_return.department}",
            reference=dept_return.return_number,
            source_type='dept_return',
            source_id=dept_return.pk,
            lines=lines,
            user=user,
            cost_center=cost_center,
            operation=_op_for_code('133'),
        )
    except Exception as e:
        logger.exception(f"GL auto-post failed for return {dept_return.pk}: {e}")
        return None
