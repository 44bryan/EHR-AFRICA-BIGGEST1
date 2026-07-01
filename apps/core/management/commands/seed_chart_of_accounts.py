"""
Management command: seed_chart_of_accounts
Seeds the OHADA/SYSCOHADA Chart of Accounts for Cameroon.
Safe to run multiple times — uses get_or_create.
"""
from django.core.management.base import BaseCommand
from apps.billing.models import GLAccount, AccountType


# OHADA SYSCOHADA Chart of Accounts
# Format: (code, name, type, parent_code_or_None)
OHADA_ACCOUNTS = [
    # ── CLASS 1: CAPITAL & RESERVES ──────────────────────────────────────────
    ('100000', 'Capital & Reserves',            AccountType.EQUITY,    None),
    ('101000', 'Share Capital',                 AccountType.EQUITY,    '100000'),
    ('102000', 'Share Premium',                 AccountType.EQUITY,    '100000'),
    ('106000', 'Statutory Reserves',            AccountType.EQUITY,    '100000'),
    ('110000', 'Retained Earnings',             AccountType.EQUITY,    '100000'),
    ('120000', 'Net Income for the Year',       AccountType.EQUITY,    '100000'),
    ('130000', 'Investment Grants',             AccountType.EQUITY,    '100000'),

    # ── CLASS 2: FIXED ASSETS ─────────────────────────────────────────────────
    ('200000', 'Fixed Assets',                  AccountType.ASSET,     None),
    ('211000', 'Land',                          AccountType.ASSET,     '200000'),
    ('212000', 'Buildings',                     AccountType.ASSET,     '200000'),
    ('221000', 'Medical Equipment',             AccountType.ASSET,     '200000'),
    ('222000', 'Office Equipment & Furniture',  AccountType.ASSET,     '200000'),
    ('223000', 'Computer & IT Equipment',       AccountType.ASSET,     '200000'),
    ('224000', 'Vehicles',                      AccountType.ASSET,     '200000'),
    ('281000', 'Acc. Depr. — Buildings',        AccountType.ASSET,     '200000'),
    ('282000', 'Acc. Depr. — Equipment',        AccountType.ASSET,     '200000'),

    # ── CLASS 3: INVENTORIES ──────────────────────────────────────────────────
    ('300000', 'Inventories',                   AccountType.ASSET,     None),
    ('310000', 'Pharmaceutical Stock',          AccountType.ASSET,     '300000'),
    ('320000', 'Medical Consumables',           AccountType.ASSET,     '300000'),
    ('330000', 'Optical Inventory (Frames)',    AccountType.ASSET,     '300000'),
    ('331000', 'Optical Inventory (Lenses)',    AccountType.ASSET,     '300000'),
    ('340000', 'Stationery & Office Supplies',  AccountType.ASSET,     '300000'),

    # ── CLASS 4: RECEIVABLES & PAYABLES ──────────────────────────────────────
    ('400000', 'Receivables & Payables',        AccountType.ASSET,     None),
    ('411000', 'Patients Receivable',           AccountType.ASSET,     '400000'),
    ('412000', 'Insurance Receivable',          AccountType.ASSET,     '400000'),
    ('413000', 'Corporate Accounts Receivable', AccountType.ASSET,     '400000'),
    ('419000', 'Provision for Bad Debts',       AccountType.ASSET,     '400000'),
    ('220000', 'Accounts Payable — Vendors',    AccountType.LIABILITY, None),
    ('401000', 'Trade Creditors',               AccountType.LIABILITY, '220000'),
    ('402000', 'Accrued Expenses',              AccountType.LIABILITY, '220000'),
    ('431000', 'Social Security Payable',       AccountType.LIABILITY, None),
    ('441000', 'VAT Payable',                   AccountType.LIABILITY, None),
    ('442000', 'Income Tax Payable',            AccountType.LIABILITY, None),
    ('451000', 'Staff Loans / Advances',        AccountType.ASSET,     None),
    ('461000', 'Prepaid Expenses',              AccountType.ASSET,     None),

    # ── CLASS 5: FINANCIAL ACCOUNTS ───────────────────────────────────────────
    ('500000', 'Financial Accounts',            AccountType.ASSET,     None),
    ('521000', 'Bank Account — Main',           AccountType.ASSET,     '500000'),
    ('522000', 'Bank Account — Operations',     AccountType.ASSET,     '500000'),
    ('523000', 'Mobile Money Account',          AccountType.ASSET,     '500000'),
    ('571000', 'Petty Cash — Main',             AccountType.ASSET,     '500000'),
    ('572000', 'Cash in Hand — Cashier',        AccountType.ASSET,     '500000'),

    # ── CLASS 6: EXPENSES ────────────────────────────────────────────────────
    ('600000', 'Operating Expenses',            AccountType.EXPENSE,   None),
    ('601000', 'Pharmaceutical Purchases',      AccountType.EXPENSE,   '600000'),
    ('602000', 'Medical Consumables Purchases', AccountType.EXPENSE,   '600000'),
    ('603000', 'Optical Purchases',             AccountType.EXPENSE,   '600000'),
    ('611000', 'Rent — Premises',               AccountType.EXPENSE,   '600000'),
    ('612000', 'Electricity & Water',           AccountType.EXPENSE,   '600000'),
    ('613000', 'Telecommunications',            AccountType.EXPENSE,   '600000'),
    ('614000', 'Maintenance & Repairs',         AccountType.EXPENSE,   '600000'),
    ('615000', 'Security Services',             AccountType.EXPENSE,   '600000'),
    ('621000', 'Salaries & Wages',              AccountType.EXPENSE,   '600000'),
    ('622000', 'Social Charges (CNPS)',         AccountType.EXPENSE,   '600000'),
    ('623000', 'Medical Staff Benefits',        AccountType.EXPENSE,   '600000'),
    ('631000', 'Bank Charges & Fees',           AccountType.EXPENSE,   '600000'),
    ('632000', 'Interest on Loans',             AccountType.EXPENSE,   '600000'),
    ('641000', 'Depreciation — Equipment',      AccountType.EXPENSE,   '600000'),
    ('642000', 'Depreciation — Buildings',      AccountType.EXPENSE,   '600000'),
    ('651000', 'Training & Staff Development',  AccountType.EXPENSE,   '600000'),
    ('652000', 'Marketing & Advertising',       AccountType.EXPENSE,   '600000'),
    ('653000', 'Professional Fees',             AccountType.EXPENSE,   '600000'),
    ('654000', 'Stationery & Printing',         AccountType.EXPENSE,   '600000'),
    ('655000', 'Travel & Transport',            AccountType.EXPENSE,   '600000'),
    ('656000', 'Insurance Premiums',            AccountType.EXPENSE,   '600000'),
    ('657000', 'Sundry Expenses',               AccountType.EXPENSE,   '600000'),
    ('681000', 'Petty Cash Disbursements',      AccountType.EXPENSE,   '600000'),

    # ── CLASS 7: REVENUES ────────────────────────────────────────────────────
    ('700000', 'Operating Revenue',             AccountType.REVENUE,   None),
    ('701000', 'Consultation Revenue',          AccountType.REVENUE,   '700000'),
    ('702000', 'Surgical Procedures Revenue',   AccountType.REVENUE,   '700000'),
    ('703000', 'Laboratory Revenue',            AccountType.REVENUE,   '700000'),
    ('704000', 'Radiology / Imaging Revenue',   AccountType.REVENUE,   '700000'),
    ('705000', 'Pharmacy Revenue',              AccountType.REVENUE,   '700000'),
    ('706000', 'Optical Dispensing Revenue',    AccountType.REVENUE,   '700000'),
    ('707000', 'IPD / Nursing Revenue',         AccountType.REVENUE,   '700000'),
    ('708000', 'CSSD Revenue',                  AccountType.REVENUE,   '700000'),
    ('709000', 'Other Clinical Revenue',        AccountType.REVENUE,   '700000'),
    ('711000', 'Insurance Reimbursements',      AccountType.REVENUE,   '700000'),
    ('720000', 'Other Operating Income',        AccountType.REVENUE,   '700000'),
    ('731000', 'Interest Income',               AccountType.REVENUE,   '700000'),
]


class Command(BaseCommand):
    help = 'Seeds the OHADA/SYSCOHADA Chart of Accounts for Cameroon'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset', action='store_true',
            help='Delete all existing GL accounts before seeding (CAUTION: destroys journal lines)'
        )

    def handle(self, *args, **options):
        if options['reset']:
            count = GLAccount.objects.count()
            GLAccount.objects.all().delete()
            self.stdout.write(self.style.WARNING(f'Deleted {count} existing GL accounts.'))

        created_count = 0
        updated_count = 0
        parent_cache = {}

        # Pass 1 — create all root accounts (no parent)
        for code, name, acct_type, parent_code in OHADA_ACCOUNTS:
            if parent_code is None:
                obj, created = GLAccount.objects.get_or_create(
                    code=code,
                    defaults={'name': name, 'account_type': acct_type, 'is_active': True}
                )
                if not created:
                    obj.name = name
                    obj.account_type = acct_type
                    obj.save()
                    updated_count += 1
                else:
                    created_count += 1
                parent_cache[code] = obj

        # Pass 2 — create child accounts
        for code, name, acct_type, parent_code in OHADA_ACCOUNTS:
            if parent_code is not None:
                parent = parent_cache.get(parent_code)
                if parent is None:
                    try:
                        parent = GLAccount.objects.get(code=parent_code)
                        parent_cache[parent_code] = parent
                    except GLAccount.DoesNotExist:
                        self.stdout.write(
                            self.style.WARNING(f'  Parent {parent_code} not found for {code} — skipping')
                        )
                        continue

                obj, created = GLAccount.objects.get_or_create(
                    code=code,
                    defaults={
                        'name': name,
                        'account_type': acct_type,
                        'parent': parent,
                        'is_active': True
                    }
                )
                if not created:
                    obj.name = name
                    obj.account_type = acct_type
                    obj.parent = parent
                    obj.save()
                    updated_count += 1
                else:
                    created_count += 1
                parent_cache[code] = obj

        total = GLAccount.objects.count()
        self.stdout.write(self.style.SUCCESS(
            f'\nOHADA Chart of Accounts seeded successfully!'
            f'\n  Created : {created_count}'
            f'\n  Updated : {updated_count}'
            f'\n  Total   : {total} accounts'
            f'\n\nNext steps:'
            f'\n  1. Go to Billing > GL > Chart of Accounts to review'
            f'\n  2. Adjust account names/codes as needed for your hospital'
            f'\n  3. Run migrations if not already done: python manage.py migrate billing'
        ))
