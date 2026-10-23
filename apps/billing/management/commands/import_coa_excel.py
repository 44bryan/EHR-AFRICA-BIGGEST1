"""
Management command: import_coa_excel
Imports the Finance Director's updated Chart of Accounts from Excel.

Usage:
    python manage.py import_coa_excel --file PlanComptable-21.10.20262222.xlsx [--dry-run]

Excel format (3 columns):
  A: Parent Code  (6-digit, filled only for parent/summary accounts)
  B: Account number (7-digit, filled only for child/postable accounts)
  C: Intitulé (account name)

Rules:
  - Rows where A is filled, B is blank  → parent/summary account (is_summary=True)
  - Rows where B is filled, A is blank  → child/postable account (is_summary=False)
  - Parent-child relationship: sequential — each child belongs to the parent defined
    by the most recent parent row above it.

Strategy:
  - CREATE new accounts that don't exist yet
  - UPDATE name/is_summary for accounts that already exist (code match)
  - NEVER delete accounts (they may be referenced by journal entries)
  - Mark old 6-digit accounts that are now parents as is_summary=True
  - Leave remaining old accounts active (Finance Director remaps via GL Config Hub)
"""
import os
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


ACCOUNT_TYPE_MAP = {
    '1': 'EQUITY',
    '2': 'ASSET',
    '3': 'ASSET',
    '4': 'LIABILITY',   # refined below
    '5': 'ASSET',
    '6': 'EXPENSE',
    '7': 'REVENUE',
    '8': 'EXPENSE',     # Special charges (OHADA cl.8)
    '9': 'EXPENSE',     # Analytical (OHADA cl.9)
}

RECEIVABLE_PREFIXES = ('41', '46', '48', '49')   # Class 4 accounts that are assets/receivables


def _account_type(code: str) -> str:
    first = code[0] if code else '1'
    if first == '4':
        for pfx in RECEIVABLE_PREFIXES:
            if code.startswith(pfx):
                return 'ASSET'
        return 'LIABILITY'
    return ACCOUNT_TYPE_MAP.get(first, 'ASSET')


class Command(BaseCommand):
    help = 'Import Chart of Accounts from Finance Director Excel file'

    def add_arguments(self, parser):
        parser.add_argument('--file', default='PlanComptable-21.10.20262222.xlsx',
                            help='Path to Excel file (relative to BASE_DIR or absolute)')
        parser.add_argument('--dry-run', action='store_true',
                            help='Show what would change without writing to DB')

    @transaction.atomic
    def handle(self, *args, **options):
        from django.conf import settings

        try:
            import openpyxl
        except ImportError:
            raise CommandError('openpyxl not installed. Run: pip install openpyxl')

        from apps.billing.models import GLAccount

        filepath = options['file']
        if not os.path.isabs(filepath):
            filepath = os.path.join(settings.BASE_DIR, filepath)

        if not os.path.exists(filepath):
            raise CommandError(f'File not found: {filepath}')

        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — no changes will be written'))

        # ── Read Excel ──────────────────────────────────────────────────
        wb = openpyxl.load_workbook(filepath, data_only=True)
        ws = wb.active
        raw_rows = [r for r in ws.iter_rows(min_row=2, values_only=True) if any(v for v in r)]

        # Build parent-child structure
        parents = {}     # code_str -> name
        children = {}    # code_str -> (name, parent_code_str)
        current_parent = None
        for row in raw_rows:
            parent_code, child_code, name = row[0], row[1], row[2]
            name = (name or '').strip()
            if parent_code and not child_code:
                current_parent = str(int(parent_code))
                parents[current_parent] = name
            elif child_code and not parent_code and current_parent:
                child_str = str(int(child_code))
                children[child_str] = (name, current_parent)

        self.stdout.write(f'Excel contains {len(parents)} parent accounts + {len(children)} child accounts')

        # ── Load existing DB accounts ────────────────────────────────────
        existing = {a.code: a for a in GLAccount.objects.all()}

        stats = {'parents_created': 0, 'parents_updated': 0,
                 'children_created': 0, 'children_updated': 0,
                 'skipped': 0}

        parent_objs = {}  # code -> GLAccount instance

        # ── Step 1: Process parent accounts ─────────────────────────────
        # Strategy:
        #   NEW accounts (not in DB) → create with is_summary=True (safe — nothing posts to them)
        #   EXISTING accounts → update name only, DO NOT change is_summary
        #   (Changing is_summary on existing accounts would break GL postings that
        #    reference them; Finance Director remaps operations via GL Config Hub)
        self.stdout.write('\n--- Step 1: Parent (summary) accounts ---')
        for code, name in parents.items():
            acct_type = _account_type(code)
            if code in existing:
                acct = existing[code]
                changed = []
                if acct.name != name:
                    changed.append(f'name updated')
                if acct.account_type != acct_type:
                    changed.append(f'type: {acct.account_type} → {acct_type}')
                if changed:
                    stats['parents_updated'] += 1
                    if not dry_run:
                        acct.name = name
                        acct.account_type = acct_type
                        acct.save(update_fields=['name', 'account_type'])
                    self.stdout.write(f'  UPDATE existing {code} ({", ".join(changed)}) — is_summary unchanged')
                else:
                    stats['skipped'] += 1
                parent_objs[code] = acct
            else:
                stats['parents_created'] += 1
                if not dry_run:
                    acct = GLAccount.objects.create(
                        code=code, name=name,
                        account_type=acct_type,
                        is_summary=True,
                        allow_manual_posting=False,
                        is_active=True,
                    )
                    parent_objs[code] = acct
                    existing[code] = acct
                self.stdout.write(f'  CREATE parent {code} — {name} [is_summary=True]')

        # ── Step 2: Process child accounts ──────────────────────────────
        self.stdout.write('\n--- Step 2: Child (postable) accounts ---')
        for code, (name, parent_code) in children.items():
            acct_type = _account_type(code)
            parent_obj = parent_objs.get(parent_code) or existing.get(parent_code)

            if code in existing:
                acct = existing[code]
                changed = []
                if acct.name != name:
                    changed.append(f'name')
                if acct.is_summary:
                    changed.append('is_summary: True → False')
                if acct.account_type != acct_type:
                    changed.append(f'type: {acct.account_type} → {acct_type}')
                if parent_obj and acct.parent_id != parent_obj.pk:
                    changed.append(f'parent → {parent_code}')
                if changed:
                    stats['children_updated'] += 1
                    if not dry_run:
                        acct.name = name
                        acct.is_summary = False
                        acct.account_type = acct_type
                        if parent_obj:
                            acct.parent = parent_obj
                        acct.save(update_fields=['name', 'is_summary', 'account_type', 'parent'])
                else:
                    stats['skipped'] += 1
            else:
                stats['children_created'] += 1
                if not dry_run:
                    acct = GLAccount.objects.create(
                        code=code, name=name,
                        account_type=acct_type,
                        is_summary=False,
                        is_active=True,
                        parent=parent_obj,
                    )
                    existing[code] = acct

        # ── Summary ──────────────────────────────────────────────────────
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS('IMPORT COMPLETE' if not dry_run else 'DRY-RUN COMPLETE'))
        self.stdout.write(f'  Parents created : {stats["parents_created"]}')
        self.stdout.write(f'  Parents updated : {stats["parents_updated"]}')
        self.stdout.write(f'  Children created: {stats["children_created"]}')
        self.stdout.write(f'  Children updated: {stats["children_updated"]}')
        self.stdout.write(f'  Already correct : {stats["skipped"]}')
        self.stdout.write(f'  Total after import: {GLAccount.objects.count()}')

        # ── Remapping report ──────────────────────────────────────────────
        self.stdout.write('\n--- Operations referencing 6-digit parent accounts ---')
        self.stdout.write('  NOTE: These accounts remain POSTABLE (is_summary unchanged).')
        self.stdout.write('  Finance Director can remap to 7-digit sub-accounts in GL Config Hub:')
        from apps.billing.models import BillingOperationCC, StockOperationType
        summary_codes = set(parents.keys())
        needs_remap = []
        for op in BillingOperationCC.objects.select_related('default_debit_account', 'default_credit_account'):
            dr = op.default_debit_account
            cr = op.default_credit_account
            if (dr and dr.code in summary_codes) or (cr and cr.code in summary_codes):
                needs_remap.append(f'  BillingOp {op.operation_code}: Dr={dr.code if dr else "-"} Cr={cr.code if cr else "-"}')
        for sot in StockOperationType.objects.select_related('debit_account', 'credit_account'):
            dr = sot.debit_account
            cr = sot.credit_account
            if (dr and dr.code in summary_codes) or (cr and cr.code in summary_codes):
                needs_remap.append(f'  StockOp  {sot.code}: Dr={dr.code if dr else "-"} Cr={cr.code if cr else "-"}')
        if needs_remap:
            for line in needs_remap[:20]:
                self.stdout.write(line)
            if len(needs_remap) > 20:
                self.stdout.write(f'  ... and {len(needs_remap) - 20} more')
            self.stdout.write(f'  Total operations needing remap: {len(needs_remap)}')
        else:
            self.stdout.write('  None — all operations point to non-summary accounts.')
