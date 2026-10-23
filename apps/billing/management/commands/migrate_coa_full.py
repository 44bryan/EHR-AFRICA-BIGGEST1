"""
Management command: migrate_coa_full
Full Chart of Accounts migration — Finance Director's new COA replaces the old one.

Steps:
  1. Mark ALL 6-digit parent accounts in the new COA as is_summary=True
     (they are header/group accounts — posting goes to 7-digit children)
  2. Ensure all 7-digit child accounts have the correct parent FK
  3. Auto-remap BillingOperationCC and StockOperationType Dr/Cr to 7-digit accounts:
       - Parent has 1 child  → use that child
       - Parent has N children → use first child as default (flag for manual review)
       - Parent has 0 children → flag as unmappable (Finance Director must add children)

Usage:
    python manage.py migrate_coa_full [--dry-run]

Note: Run AFTER import_coa_excel (which creates/updates all accounts).
"""
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = 'Full COA migration: mark parents is_summary=True + auto-remap all operations'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Show what would change without writing')

    @transaction.atomic
    def handle(self, *args, **options):
        import openpyxl, os
        from django.conf import settings
        from apps.billing.models import (
            GLAccount, BillingOperationCC, StockOperationType
        )

        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — no changes written'))

        # ── Load Excel structure ─────────────────────────────────────────
        excel_path = os.path.join(settings.BASE_DIR, 'PlanComptable-21.10.20262222.xlsx')
        wb = openpyxl.load_workbook(excel_path, data_only=True)
        ws = wb.active
        raw_rows = [r for r in ws.iter_rows(min_row=2, values_only=True) if any(v for v in r)]

        # Build parent → children map from Excel
        children_by_parent = {}
        parent_names = {}
        current_parent = None
        for row in raw_rows:
            parent_code, child_code, name = row[0], row[1], row[2]
            name = (name or '').strip()
            if parent_code and not child_code:
                current_parent = str(int(parent_code))
                children_by_parent[current_parent] = []
                parent_names[current_parent] = name
            elif child_code and not parent_code and current_parent:
                children_by_parent[current_parent].append(str(int(child_code)))

        parent_codes = set(children_by_parent.keys())

        # ── Load all GL accounts from DB ─────────────────────────────────
        all_accounts = {a.code: a for a in GLAccount.objects.all()}

        # ═══════════════════════════════════════════════════════════════
        # STEP 1 — Mark ALL 6-digit parents as is_summary=True
        # ═══════════════════════════════════════════════════════════════
        self.stdout.write('\n' + '='*60)
        self.stdout.write('STEP 1 — Promote all COA parents to is_summary=True')
        self.stdout.write('='*60)

        promoted = 0
        already_summary = 0
        parent_not_in_db = []

        for code in sorted(parent_codes):
            acct = all_accounts.get(code)
            if acct is None:
                parent_not_in_db.append(code)
                continue
            if acct.is_summary:
                already_summary += 1
            else:
                promoted += 1
                if not dry_run:
                    acct.is_summary = True
                    acct.allow_manual_posting = False
                    acct.save(update_fields=['is_summary', 'allow_manual_posting'])
                child_count = len(children_by_parent.get(code, []))
                self.stdout.write(
                    f'  {"[DRY]" if dry_run else "  OK "} {code} — {acct.name}'
                    f' [{child_count} children]'
                )

        self.stdout.write(f'\n  Promoted: {promoted} | Already summary: {already_summary}'
                          f' | Not in DB: {len(parent_not_in_db)}')
        if parent_not_in_db:
            self.stdout.write(f'  WARNING — parents not in DB: {parent_not_in_db}')

        # ═══════════════════════════════════════════════════════════════
        # STEP 2 — Ensure child accounts have correct parent FK
        # ═══════════════════════════════════════════════════════════════
        self.stdout.write('\n' + '='*60)
        self.stdout.write('STEP 2 — Wire parent FK on all child accounts')
        self.stdout.write('='*60)

        fk_set = 0
        fk_already_ok = 0
        fk_child_missing = []

        for parent_code, child_codes in children_by_parent.items():
            parent_acct = all_accounts.get(parent_code)
            if parent_acct is None:
                continue
            for child_code in child_codes:
                child_acct = all_accounts.get(child_code)
                if child_acct is None:
                    fk_child_missing.append(child_code)
                    continue
                if child_acct.parent_id == parent_acct.pk:
                    fk_already_ok += 1
                else:
                    fk_set += 1
                    if not dry_run:
                        child_acct.parent = parent_acct
                        child_acct.save(update_fields=['parent'])

        self.stdout.write(f'  FK set: {fk_set} | Already correct: {fk_already_ok}'
                          f' | Child not in DB: {len(fk_child_missing)}')

        # ═══════════════════════════════════════════════════════════════
        # STEP 3 — Auto-remap BillingOperationCC Dr/Cr accounts
        # ═══════════════════════════════════════════════════════════════
        self.stdout.write('\n' + '='*60)
        self.stdout.write('STEP 3 — Remap BillingOperationCC to 7-digit accounts')
        self.stdout.write('='*60)

        def best_child(parent_code):
            """Return best child GLAccount for a 6-digit parent code, or None."""
            children = children_by_parent.get(parent_code, [])
            if not children:
                return None, 'NO_CHILDREN'
            acct = all_accounts.get(children[0])
            if acct is None:
                return None, 'CHILD_NOT_IN_DB'
            if len(children) > 1:
                return acct, 'MULTI_DEFAULT'
            return acct, 'SINGLE'

        billing_remapped = 0
        billing_ok = 0
        billing_unmappable = []
        billing_multi = []

        for op in BillingOperationCC.objects.select_related(
                'default_debit_account', 'default_credit_account'):
            dr_acct = op.default_debit_account
            cr_acct = op.default_credit_account
            changed = False

            new_dr = dr_acct
            new_cr = cr_acct

            if dr_acct and dr_acct.code in parent_codes:
                child_acct, reason = best_child(dr_acct.code)
                if child_acct:
                    new_dr = child_acct
                    changed = True
                    if reason == 'MULTI_DEFAULT':
                        billing_multi.append(
                            f'  BillingOp {op.operation_code} Dr: {dr_acct.code}'
                            f' → {child_acct.code} (MULTI — verify)'
                        )
                else:
                    billing_unmappable.append(
                        f'  BillingOp {op.operation_code} Dr={dr_acct.code} ({reason})'
                    )

            if cr_acct and cr_acct.code in parent_codes:
                child_acct, reason = best_child(cr_acct.code)
                if child_acct:
                    new_cr = child_acct
                    changed = True
                    if reason == 'MULTI_DEFAULT':
                        billing_multi.append(
                            f'  BillingOp {op.operation_code} Cr: {cr_acct.code}'
                            f' → {child_acct.code} (MULTI — verify)'
                        )
                else:
                    billing_unmappable.append(
                        f'  BillingOp {op.operation_code} Cr={cr_acct.code} ({reason})'
                    )

            if changed:
                billing_remapped += 1
                self.stdout.write(
                    f'  {"[DRY]" if dry_run else "  OK "} {op.operation_code}: '
                    f'Dr {dr_acct.code if dr_acct else "-"}→{new_dr.code if new_dr else "-"} | '
                    f'Cr {cr_acct.code if cr_acct else "-"}→{new_cr.code if new_cr else "-"}'
                )
                if not dry_run:
                    op.default_debit_account  = new_dr
                    op.default_credit_account = new_cr
                    op.save(update_fields=['default_debit_account', 'default_credit_account'])
            else:
                billing_ok += 1

        self.stdout.write(f'\n  Remapped: {billing_remapped} | No change needed: {billing_ok}')

        # ═══════════════════════════════════════════════════════════════
        # STEP 4 — Auto-remap StockOperationType Dr/Cr accounts
        # ═══════════════════════════════════════════════════════════════
        self.stdout.write('\n' + '='*60)
        self.stdout.write('STEP 4 — Remap StockOperationType to 7-digit accounts')
        self.stdout.write('='*60)

        stock_remapped = 0
        stock_ok = 0
        stock_unmappable = []
        stock_multi = []

        for sot in StockOperationType.objects.select_related('debit_account', 'credit_account'):
            dr_acct = sot.debit_account
            cr_acct = sot.credit_account
            changed = False

            new_dr = dr_acct
            new_cr = cr_acct

            if dr_acct and dr_acct.code in parent_codes:
                child_acct, reason = best_child(dr_acct.code)
                if child_acct:
                    new_dr = child_acct
                    changed = True
                    if reason == 'MULTI_DEFAULT':
                        stock_multi.append(
                            f'  StockOp {sot.code} Dr: {dr_acct.code}'
                            f' → {child_acct.code} (MULTI — verify)'
                        )
                else:
                    stock_unmappable.append(
                        f'  StockOp {sot.code} Dr={dr_acct.code} ({reason})'
                    )

            if cr_acct and cr_acct.code in parent_codes:
                child_acct, reason = best_child(cr_acct.code)
                if child_acct:
                    new_cr = child_acct
                    changed = True
                    if reason == 'MULTI_DEFAULT':
                        stock_multi.append(
                            f'  StockOp {sot.code} Cr: {cr_acct.code}'
                            f' → {child_acct.code} (MULTI — verify)'
                        )
                else:
                    stock_unmappable.append(
                        f'  StockOp {sot.code} Cr={cr_acct.code} ({reason})'
                    )

            if changed:
                stock_remapped += 1
                self.stdout.write(
                    f'  {"[DRY]" if dry_run else "  OK "} {sot.code}: '
                    f'Dr {dr_acct.code if dr_acct else "-"}→{new_dr.code if new_dr else "-"} | '
                    f'Cr {cr_acct.code if cr_acct else "-"}→{new_cr.code if new_cr else "-"}'
                )
                if not dry_run:
                    sot.debit_account  = new_dr
                    sot.credit_account = new_cr
                    sot.save(update_fields=['debit_account', 'credit_account'])
            else:
                stock_ok += 1

        self.stdout.write(f'\n  Remapped: {stock_remapped} | No change needed: {stock_ok}')

        # ═══════════════════════════════════════════════════════════════
        # FINAL SUMMARY
        # ═══════════════════════════════════════════════════════════════
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS(
            'MIGRATION COMPLETE' + (' (DRY RUN)' if dry_run else '')
        ))
        self.stdout.write('='*60)
        self.stdout.write(f'  Parents promoted to is_summary=True : {promoted}')
        self.stdout.write(f'  Child parent-FKs wired              : {fk_set}')
        self.stdout.write(f'  BillingOperationCC remapped         : {billing_remapped}')
        self.stdout.write(f'  StockOperationType remapped         : {stock_remapped}')

        if billing_multi or stock_multi:
            self.stdout.write('\n--- MULTI-CHILD auto-mapped (Finance Director should verify) ---')
            for line in billing_multi + stock_multi:
                self.stdout.write(line)

        if billing_unmappable or stock_unmappable:
            self.stdout.write('\n--- UNMAPPABLE (parent has no children — add sub-accounts) ---')
            for line in billing_unmappable + stock_unmappable:
                self.stdout.write(self.style.WARNING(line))

        self.stdout.write('\n  GL Config Hub: verify all remapped operations are correct.')
        self.stdout.write('  Accounts 412000/412001/412002/419200: no children — add them first.')
