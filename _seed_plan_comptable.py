"""
Seed the hospital's real Plan Comptable (OHADA SYSCEBNL) from PlanComptable.xlsx.
Replaces ALL existing GLAccount records, rebuilds GL mappings, and reconnects sub-categories.

Run: python manage.py shell < _seed_plan_comptable.py
"""
import django, os, sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.base')
django.setup()

import openpyxl
from apps.billing.models import (
    GLAccount, AccountType, GLMapping, GLMappingCategory,
    ServiceSubCategory, ServicePrice, JournalLine,
)

print("=" * 70)
print("IMPORTING PLAN COMPTABLE FROM PlanComptable.xlsx")
print("=" * 70)

# ── French-to-English translation map for common patterns ─────────────
FR_EN = {
    "Achats de biens et services liés à l'activité hors Région": "Purchases of Goods & Services Outside Region",
    "Frais sur achats  de biens et services liés à l'activité": "Freight on Activity-Related Purchases",
    "Rabais. Remises et Ristournes obtenus (non ventilés)": "Discounts & Rebates Obtained (Unallocated)",
    "Achats de marchandises et matières premières dans l'Etat partie": "Purchase of Goods & Raw Materials (Domestic)",
    "Achats de marchandises et matières premières dans la Région": "Purchase of Goods & Raw Materials (Regional)",
    "Achats de marchandises et matières premières hors Région": "Purchase of Goods & Raw Materials (Foreign)",
    "frais sur achats de marchandises et matières": "Freight on Goods & Raw Materials",
    "Rabais, Remises et Ristournes obtenus (non ventilés)": "Discounts & Rebates Obtained (Unallocated)",
    "Variations des stocks de marchandises": "Stock Variations - Goods",
    "Variations des stocks de matières premières et fournitures liées": "Stock Variations - Raw Materials & Supplies",
    "Variations de stocks de dons en nature à distribuer": "Stock Variations - Donations in Kind",
    "Matières combustibles": "Fuel & Combustibles",
    "Produits d'entretien": "Cleaning Products",
    "Frais sur achats matières et fournitures consommables": "Freight on Consumable Supplies",
    "Fournitures de magasin": "Store Supplies",
    "Fournitures de bureau": "Office Supplies",
    "Fournitures non stockables -Eau": "Non-Stockable Supplies - Water",
    "Fournitures non stockables - Électricité": "Non-Stockable Supplies - Electricity",
    "Fournitures non stockables - Autres énergies": "Non-Stockable Supplies - Other Energy",
    "Cotisations des adhérents": "Member Subscriptions",
    "Quote-part de fonds d'administration transférés": "Share of Administration Funds Transferred",
    "Quote-part de dotation consomptible transférée": "Share of Consumable Endowment Transferred",
    "Dons": "Donations Received",
    "Legs": "Bequests",
    "Deniers du culte": "Religious Offerings",
    "Zakat, Dime, quête et assimilées": "Tithes, Offerings & Similar",
    "Célébrations": "Celebration Revenue",
    "Mécénats": "Sponsorship Revenue",
    "Parrainage": "Patronage Revenue",
    "Autres revenus liés à la générosité": "Other Generosity Revenue",
    "Services vendus": "Services Sold",
    "Ventes de produits finis": "Sales of Finished Products",
    "Ventes de produits intermédiaires": "Sales of Intermediate Products",
    "Ventes de produits résiduels": "Sales of Residual Products",
    "Revenus des manifestations": "Event Revenue",
    "Ventes de dons en nature": "Sales of Donated Goods",
    "Revenus d'usufruit": "Usufruct Revenue",
    "Production immobilisée, immobilisations incorporelles": "Capitalized Production - Intangible Assets",
    "Production immobilisée, immobilisations corporelles": "Capitalized Production - Tangible Assets",
    "Production autoconsommée": "Self-Consumed Production",
    "Production immobilisée, immobilisations financières": "Capitalized Production - Financial Assets",
    "Variations des stocks de produits finis et services en cours": "Stock Variations - Finished Goods & WIP",
    "Variations des stocks de produits finis, produits intermédiaires et résiduels": "Stock Variations - Finished, Intermediate & Residual",
    "Profits sur créances Adhérents, clients-usagers, et autres débiteurs": "Profit on Member & Customer Receivables",
    "Contribution du fondateur": "Founder Contribution",
    "Dons en nature courants reçus à distribuer": "Current In-Kind Donations for Distribution",
    "Indemnités d'assurances reçues": "Insurance Indemnities Received",
    "Abandons de frais par les bénévoles": "Volunteer Expense Waivers",
    "Autres produits divers": "Other Miscellaneous Income",
    "Reprises provisions sur risques à court terme": "Provision Reversal - Short-Term Risks",
    "Reprises de charges pour dépréciations sur stocks": "Depreciation Reversal - Stocks",
    "Reprises de charges pour dépréciations sur créances": "Depreciation Reversal - Receivables",
    "Intérêts de prêts": "Interest on Loans",
    "Intérêts sur créances diverses": "Interest on Miscellaneous Receivables",
    "Revenus des titres de participation": "Income from Equity Investments",
    "Revenus autres titres immobilisés": "Income from Other Fixed Securities",
    "Escomptes obtenus": "Discounts Obtained",
    "Revenus des obligations": "Bond Income",
    "Revenus des titres de placement": "Investment Securities Income",
    "Revenus des dépôts à terme et opérations assimilées": "Term Deposit Income",
    "Autres revenus de placement": "Other Investment Income",
    "Gains de change financiers": "Financial Foreign Exchange Gains",
    "Gains sur cessions de titres de placement": "Gains on Sale of Investment Securities",
    "Gains sur rentes viagères": "Gains on Life Annuities",
    "En Numéraire": "Cash Contributions (Capital)",
    "En Nature": "In-Kind Contributions (Capital)",
    "Droit d'Entrée": "Entrance Fee (Capital)",
    "Dotation Consomptible": "Consumable Endowment",
    "Dotation Consomptible Inscrite au Compte de Résultat": "Consumable Endowment - P&L",
    "Réserves Statutaires ou Contractuelles": "Statutory or Contractual Reserves",
    "Autres Réserves": "Other Reserves",
    "Résultat net en Instance d'affectation": "Net Result Pending Allocation",
    "Adhérents": "Members (Receivable)",
    "Provisions pour Litiges": "Provisions for Litigation",
    "Virements de fonds": "Fund Transfers",
    "Dépôts": "Security Deposits Received",
    "Cautionnements ": "Guarantees Received",
    "Emprunts Obligataires": "Bond Loans",
    "Emprunts et Dettes auprès des Etablissements de Crédit": "Bank Loans & Credit Institution Debts",
    "Avances reçues de l'Etat": "Advances Received from State",
    "Dettes de location-Acquistion/Crédit -Bail Immobilier": "Finance Lease Debt - Real Estate",
    "Dettes de location-Acquistion/Crédit -Bail Mobilier": "Finance Lease Debt - Equipment",
    "Dettes de location-Acquistion/Location-Vente": "Hire Purchase Debt",
    "Intérêts  Courus": "Accrued Interest",
    "Chèques à encaisser": "Cheques to Deposit",
    "Chèques à l'encaissement": "Cheques Being Cleared",
    "Cartes de crédit à encaisser": "Credit Card Receipts to Deposit",
    "Chèques de voyage": "Travellers Cheques",
    "Coupons échus": "Matured Coupons",
    "Intérêts échus des obligations": "Matured Bond Interest",
    "Banques en devises": "Foreign Currency Bank Accounts",
    "Banques autres États Région": "Banks in Other Regional States",
    "Banques autres États zone monétaire": "Banks in Monetary Zone States",
    "Banques postales": "Postal Bank Accounts",
    "Trésor": "Treasury",
    "Crédits de trésorerie": "Short-Term Credit Facilities",
    "Escompte de crédits ordinaires": "Discount on Regular Credits",
    "Monnaie électronique - carte péage": "Electronic Money - Toll Card",
    "Porte-monnaie électronique": "Electronic Wallet",
}

# ── Generic pattern translations ──────────────────────────────────────
GENERIC_FR_EN = [
    ("Ecarts de Réévaluation sur des biens sans droit de Reprise-Immobilisation Corporelles", "Revaluation Surplus - Tangible Assets (No Clawback)"),
    ("Ecarts de Réévaluation sur des biens sans droit de Reprise-Immobilisation Financières", "Revaluation Surplus - Financial Assets (No Clawback)"),
    ("Ecarts de Réévaluation sur des biens avec droit de Reprise-Immobilisation Corporelles", "Revaluation Surplus - Tangible Assets (With Clawback)"),
    ("Ecarts de Réévaluation sur des biens avec droit de Reprise-Immobilisation Financières", "Revaluation Surplus - Financial Assets (With Clawback)"),
    ("Provisions Spéciales de Réévaluation", "Special Revaluation Provisions"),
    ("Autres Provisions Réglementées et Fonds Assimilés", "Other Regulated Provisions & Similar Funds"),
    ("Fournisseurs, réserve de propriété", "Suppliers - Retention of Title"),
    ("Fournisseurs, retenues de garantie", "Suppliers - Retention Guarantees"),
    ("Fournisseurs sous-traitants, effets à payer", "Subcontractor Notes Payable"),
    ("Fournisseurs sous-traitants", "Subcontractors (Invoice Pending)"),
    ("Fournisseurs, intérêts courus", "Suppliers - Accrued Interest"),
    ("Fournisseurs, rabais, remises, ristournes et autres avoirs à obtenir", "Suppliers - Discounts & Credits Due"),
    ("Adhérents, chèques impayés", "Members - Bounced Cheques"),
    ("Clients-usagers, chèques impayés", "Patients - Bounced Cheques"),
    ("Adhérents, Autres valeurs impayées", "Members - Other Unpaid Items"),
    ("Clients-usagers, autres valeurs impayées", "Patients - Other Unpaid Items"),
    ("Adhérents cotisations litigieuses ou douteuses", "Members - Disputed Subscriptions"),
    ("Créances litigieuses ou douteuses", "Disputed or Doubtful Receivables"),
    ("Sociétés de gestion et d'intermédiation (S.G.I.)", "Securities & Intermediation Companies"),
    ("Établissements financiers, intérêts courus charges à payer", "Financial Institutions - Accrued Interest Payable"),
    ("Établissements financiers, intérêts courus produits à recevoir", "Financial Institutions - Accrued Interest Receivable"),
    ("Autres organismes financiers", "Other Financial Institutions"),
    ("Banque, intérêts courus charges à payer", "Bank - Accrued Interest Payable"),
    ("Banque, intérêts courus produits à recevoir", "Bank - Accrued Interest Receivable"),
    ("Banques, crédits de trésorerie, intérêts courus", "Banks - Treasury Credit Accrued Interest"),
    ("Dépréciations des titres de placement", "Impairment - Investment Securities"),
    ("Dépréciations des titres et valeurs à encaisser", "Impairment - Securities to Collect"),
    ("Dépréciations des comptes banques", "Impairment - Bank Accounts"),
    ("Dépréciations des comptes établissements financiers et assimilés", "Impairment - Financial Institution Accounts"),
    ("Dépréciations des comptes d'instruments de monnaie électronique", "Impairment - E-Money Instruments"),
]


def translate_name(name):
    """Translate French account name to English."""
    name = str(name).strip()
    # Direct lookup
    if name in FR_EN:
        return FR_EN[name]
    # Generic pattern lookup
    for fr, en in GENERIC_FR_EN:
        if name == fr:
            return en
    # Common prefix translations
    prefixes = [
        ("Reprises de provisions", "Provision Reversals"),
        ("Reprises de charges pour dépréciations", "Depreciation Charge Reversals"),
        ("Reprises de fonds affectés", "Allocated Fund Reversals"),
        ("Reprises de fonds reportés", "Deferred Fund Reversals"),
        ("Reprises des dépréciations", "Impairment Reversals"),
        ("Reprises d'amortissements", "Amortization Reversals"),
        ("Fonds affectés", "Allocated Funds"),
        ("Fonds Projet de Développement", "Development Project Funds"),
        ("Titres du Trésor", "Treasury Securities"),
        ("Titres d'organismes financiers", "Financial Institution Securities"),
        ("Bons de caisse", "Cash Vouchers"),
        ("Bons de souscription", "Subscription Warrants"),
        ("Titres négociables hors Région", "Negotiable Securities Outside Region"),
        ("Autres titres de placement", "Other Investment Securities"),
    ]
    for fr_prefix, en_prefix in prefixes:
        if name.startswith(fr_prefix):
            rest = name[len(fr_prefix):].strip()
            if rest:
                return f"{en_prefix} - {rest}"
            return en_prefix

    # If still French (has accented chars), do basic cleanup
    has_french_chars = any(c in name for c in 'éèêëàâäùûüîïôöçÉÈÊËÀÂÄÙÛÜÎÏÔÖÇ')
    if has_french_chars or "d'" in name or "l'" in name:
        # Basic character replacements for readability
        replacements = {
            'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
            'à': 'a', 'â': 'a', 'ä': 'a',
            'ù': 'u', 'û': 'u', 'ü': 'u',
            'î': 'i', 'ï': 'i',
            'ô': 'o', 'ö': 'o',
            'ç': 'c',
            'É': 'E', 'È': 'E', 'Ê': 'E', 'Ë': 'E',
            'À': 'A', 'Â': 'A', 'Ä': 'A',
            'Ù': 'U', 'Û': 'U', 'Ü': 'U',
            'Î': 'I', 'Ï': 'I',
            'Ô': 'O', 'Ö': 'O',
            'Ç': 'C',
        }
        for fr_c, en_c in replacements.items():
            name = name.replace(fr_c, en_c)
    return name


def get_account_type(code_str):
    """Determine account type from OHADA class (first digit)."""
    c = code_str[0]
    if c == '1':
        return AccountType.EQUITY
    elif c == '2':
        return AccountType.ASSET      # Fixed assets
    elif c == '3':
        return AccountType.ASSET      # Inventory (current asset)
    elif c == '4':
        # 40x = AP (liability), 41x-49x = AR (asset)
        if code_str.startswith('40'):
            return AccountType.LIABILITY
        return AccountType.ASSET
    elif c == '5':
        # Cash & bank = asset; 56x credit = liability
        if code_str.startswith('56'):
            return AccountType.LIABILITY
        elif code_str.startswith('59'):
            return AccountType.ASSET  # Impairment contra
        return AccountType.ASSET
    elif c == '6':
        return AccountType.EXPENSE
    elif c == '7':
        return AccountType.REVENUE
    elif c == '8':
        # 81/87 = transfers, treat as revenue/expense context
        if code_str.startswith('81') or code_str.startswith('83') or code_str.startswith('85'):
            return AccountType.EXPENSE
        return AccountType.REVENUE
    elif c == '9':
        return AccountType.EXPENSE  # Cost accounting
    return AccountType.ASSET


# ── Read the Excel ────────────────────────────────────────────────────
wb = openpyxl.load_workbook('PlanComptable.xlsx', data_only=True)
ws = wb.active

accounts_data = []
for r in range(2, ws.max_row + 1):
    code_raw = ws.cell(r, 2).value
    name_raw = ws.cell(r, 3).value
    if not code_raw or not name_raw:
        continue
    code = str(int(code_raw) if isinstance(code_raw, float) else code_raw).strip()
    name = translate_name(name_raw)
    acct_type = get_account_type(code)
    accounts_data.append((code, name, acct_type))

print(f"\nRead {len(accounts_data)} accounts from Excel")


# ── Step 1: Build old→new code mapping for journal lines ──────────────
# Get existing accounts before deletion
old_accounts = {a.code: a.id for a in GLAccount.objects.all()}
print(f"Existing GL accounts in DB: {len(old_accounts)}")

# Check which old codes exist in the new plan
new_codes = {code for code, _, _ in accounts_data}
preserved = set(old_accounts.keys()) & new_codes
lost = set(old_accounts.keys()) - new_codes
print(f"Codes preserved (same in both): {len(preserved)}")
print(f"Codes only in old DB (will be remapped): {len(lost)}")
if lost:
    print(f"  Lost codes: {sorted(lost)[:20]}{'...' if len(lost) > 20 else ''}")

# ── Step 2: Import all accounts ───────────────────────────────────────
print("\nImporting accounts...")

# Delete accounts that DON'T have journal lines referencing them
# For accounts WITH journal lines, we'll update them in place
accounts_with_lines = set(
    JournalLine.objects.values_list('account__code', flat=True).distinct()
)
print(f"Accounts with journal entries: {len(accounts_with_lines)}")

# Strategy:
# 1. For codes in PlanComptable.xlsx → update_or_create with new name/type
# 2. For old codes NOT in Excel but WITH journal lines → keep (don't delete data)
# 3. For old codes NOT in Excel and NO journal lines → delete

created = 0
updated = 0
kept = 0

# First, import all from Excel
for code, name, acct_type in accounts_data:
    obj, was_created = GLAccount.objects.update_or_create(
        code=code,
        defaults={
            'name': name,
            'account_type': acct_type,
            'is_active': True,
            'is_deleted': False,
        }
    )
    if was_created:
        created += 1
    else:
        updated += 1

# Delete old GL mappings that reference accounts not in the new plan
# (we'll rebuild ALL mappings later anyway)
old_mapping_count = GLMapping.objects.all().count()
GLMapping.objects.all().delete()
print(f"Deleted {old_mapping_count} old GL mappings (will rebuild)")

# Also clear sub-category and service price GL links (we'll rebuild them too)
ServiceSubCategory.objects.filter(is_deleted=False).update(gl_account=None)
ServicePrice.objects.filter(gl_account__isnull=False).update(gl_account=None)

# Delete old accounts not in new plan and without journal lines
old_only = GLAccount.objects.exclude(code__in=new_codes)
old_with_lines = old_only.filter(code__in=accounts_with_lines)
old_without_lines = old_only.exclude(code__in=accounts_with_lines)

kept_count = old_with_lines.count()
if kept_count > 0:
    print(f"Keeping {kept_count} old accounts (have journal entries):")
    for a in old_with_lines:
        print(f"  {a.code} - {a.name}")

deleted_count = old_without_lines.count()
if deleted_count > 0:
    old_without_lines.delete()

print(f"\nImport complete:")
print(f"  Created: {created}")
print(f"  Updated: {updated}")
print(f"  Kept (have journal lines): {kept_count}")
print(f"  Deleted (obsolete, no data): {deleted_count}")
print(f"  Total now: {GLAccount.objects.count()}")


# ── Step 3: Set parent accounts ───────────────────────────────────────
print("\nSetting parent account hierarchy...")
all_accounts = {a.code: a for a in GLAccount.objects.all()}
parent_set = 0
for code, acct in all_accounts.items():
    # Find parent: try removing last digit/digits
    if len(code) > 3:
        # Try parent as shorter code
        for parent_len in [len(code)-1, len(code)-2, len(code)-3]:
            if parent_len >= 3:
                parent_code = code[:parent_len]
                # Pad with zeros if needed
                while len(parent_code) < 6 and parent_code + '0' * (6 - len(parent_code)) in all_accounts:
                    parent_code = parent_code + '0' * (6 - len(parent_code))
                if parent_code in all_accounts and parent_code != code:
                    acct.parent = all_accounts[parent_code]
                    acct.save(update_fields=['parent'])
                    parent_set += 1
                    break
print(f"Parent relationships set: {parent_set}")


# ── Step 4: Rebuild GL Mappings ───────────────────────────────────────
print("\n── Rebuilding GL Mappings ──")

# Delete all old mappings
GLMapping.objects.all().delete()
print("Old mappings deleted.")

# Revenue mappings (ServiceCategory → GL Account)
revenue_mappings = [
    ('REVENUE', 'CONSULT',    'Consultation Revenue',            '7052000'),
    ('REVENUE', 'INVEST',     'Investigation Revenue',           '7052080'),
    ('REVENUE', 'LAB',        'Laboratory Revenue',              '7052101'),
    ('REVENUE', 'PHARMACY',   'Medication Sales',                '705160'),
    ('REVENUE', 'OPTICAL',    'Optical Product Sales',           '705100'),
    ('REVENUE', 'SURGICAL',   'Surgical Revenue',                '7052021'),
    ('REVENUE', 'ADMISSION',  'Hospitalization Revenue',         '7052111'),
    ('REVENUE', 'REG',        'Registration Revenue',            '7052141'),
    ('REVENUE', 'PROCEDURE',  'Procedure Revenue',               '7052071'),
    ('REVENUE', 'OTHER',      'Other Revenue',                   '707000'),
    ('REVENUE', 'LASER',      'Laser Treatment Revenue',         '7052090'),
    ('REVENUE', 'ORTHOPTIC',  'Orthoptic Revenue',               '7052121'),
]

# Payment method → GL Account
payment_mappings = [
    ('PAYMENT', 'CASH',     'Cash in Hand',              '571000'),
    ('PAYMENT', 'CARD',     'Credit Card Receipts',      '515000'),
    ('PAYMENT', 'MOBILE',   'Mobile Money (MTN)',        '552000'),
    ('PAYMENT', 'TRANSFER', 'Local Bank',                '521100'),
    ('PAYMENT', 'CHEQUE',   'Cheques to Deposit',        '513000'),
    ('PAYMENT', 'WALLET',   'Patient Wallet Deduction',  '412000'),
]

# Expense category → GL Account
expense_mappings = [
    ('EXPENSE', 'DRUGS',      'Drug & Medication Purchases',     '601101'),
    ('EXPENSE', 'SUPPLIES',   'Material & Consumable Supplies',  '604100'),
    ('EXPENSE', 'UTILITIES',  'Non-Stockable Supplies - Electricity', '605200'),
    ('EXPENSE', 'EQUIPMENT',  'Material for R&M',               '605005'),
    ('EXPENSE', 'TRANSPORT',  'Vehicle Fuel',                    '605004'),
    ('EXPENSE', 'ADMIN',      'Office Supplies',                 '604700'),
    ('EXPENSE', 'RENT',       'Other Purchases',                 '605001'),
    ('EXPENSE', 'SALARY',     'Staff Salary',                    '661000') if '661000' in all_accounts else ('EXPENSE', 'SALARY', 'Staff Salary', '662100'),
]

# System accounts
system_mappings = [
    ('SYSTEM', 'AR_PATIENT',      'Patient Receivables',           '412000'),
    ('SYSTEM', 'AR_MEMBER',       'Member Receivables',            '411000'),
    ('SYSTEM', 'AP_SUPPLIER',     'Local Suppliers',               '401100'),
    ('SYSTEM', 'AP_FOREIGN',      'Foreign Suppliers',             '401101'),
    ('SYSTEM', 'CASH_SAFE',       'Cash in Hand',                  '571000'),
    ('SYSTEM', 'BANK_LOCAL',      'Local Bank',                    '521100'),
    ('SYSTEM', 'BANK_FOREIGN',    'Foreign Bank',                  '524000'),
    ('SYSTEM', 'MTN_MOMO',        'MTN Mobile Money',              '552000'),
    ('SYSTEM', 'FUND_TRANSFER',   'Internal Fund Transfer',        '588000'),
    ('SYSTEM', 'RETAINED_EARNINGS', 'Retained Earnings (Gain)',    '121000'),
]

all_mapping_data = revenue_mappings + payment_mappings + expense_mappings + system_mappings

mapping_created = 0
mapping_skipped = 0
for cat, key, label, code in all_mapping_data:
    acct = all_accounts.get(code)
    if not acct:
        print(f"  WARNING: Account {code} not found for mapping {cat}/{key} — skipping")
        mapping_skipped += 1
        continue
    GLMapping.objects.create(
        category=cat, source_key=key, label=label,
        gl_account=acct, is_active=True,
    )
    mapping_created += 1

print(f"GL Mappings created: {mapping_created}, skipped: {mapping_skipped}")


# ── Step 5: Update ServiceSubCategory GL links ───────────────────────
print("\n── Updating Sub-Category GL Links ──")

# Map sub-category names to their correct GL accounts from the Plan Comptable
sub_gl_map = {
    # Optical product families
    'Eyeglass Frames':      '705100',   # Sales of Frames
    'Ophthalmic Lenses':    '705110',   # Sales of Lenses
    'Reading Glasses':      '705120',   # Sales of Reading Glasses
    'Sun Glasses':          '705130',   # Sales of Sun Glasses
    'Lens Cleaner':         '705140',   # Sales of Lens Cleaner
    'Optical Accessories':  '705150',   # Sales of Accessories
    'Medications':          '705160',   # Sales of Medications
    'Optical Cases':        '705170',   # Sales of Cases
    'Medical Consumables':  '705180',   # Sales of Consumables
    'Low Vision Devices':   '705190',   # Sales of Low Vision Devices
    'Orthoptic Cards':      '705191',   # Sales of Orthoptic Cards
    'Patient Folders':      '705192',   # Sales of Patient Folders
    # Service families
    'General Consultation': '7052000',  # Consultation
    'Specialist Consultation': '7052000',
    'Anesthesia Services':  '7052011',  # Anesthesia Standard
    'Cataract Surgery':     '7052021',  # Cataract Surgeries Standard
    'Cornea Surgery':       '7052031',  # Cornea Surgeries Standard
    'Glaucoma Surgery':     '7052041',  # Glaucoma Surgeries Standard
    'Vitreoretinal Surgery':'7052051',  # Vitreoretinal Surgeries Standard
    'Oculoplasty Surgery':  '7052061',  # Oculoplasty Surgeries Standard
    'Other Surgery':        '7052071',  # Other Surgeries Standard
    'Refractive Surgery':   '7052151',  # Refractive Surgeries Standard
    'Eye Investigations':   '7052080',  # Investigation
    'Laser Treatment':      '7052090',  # Laser Treatment
    'Laboratory Tests':     '7052101',  # Laboratory Standard
    'Hospitalization':      '7052111',  # Hospitalization Standard
    'Orthoptic Services':   '7052121',  # Orthoptic Standard
    'Other Medical Services':'7052131', # Other Medical Services Standard
    'Registration':         '7052141',  # Sundry Income
    'Contact Lenses':       '705150',   # Accessories (closest match)
    'Branded Lenses':       '705110',   # Sales of Lenses
}

sub_updated = 0
for sc in ServiceSubCategory.objects.filter(is_deleted=False):
    gl_code = sub_gl_map.get(sc.name)
    if gl_code and gl_code in all_accounts:
        sc.gl_account = all_accounts[gl_code]
        sc.save(update_fields=['gl_account', 'updated_at'])
        sub_updated += 1
        print(f"  {sc.name} → {gl_code}")
    else:
        # Try to find by category mapping
        rev_map = {m.source_key: m.gl_account for m in GLMapping.objects.filter(category='REVENUE')}
        if sc.category in rev_map:
            sc.gl_account = rev_map[sc.category]
            sc.save(update_fields=['gl_account', 'updated_at'])
            sub_updated += 1
            print(f"  {sc.name} → {sc.gl_account.code} (from category default)")

print(f"Sub-categories updated: {sub_updated}")


# ── Step 6: Invalidate GL cache ───────────────────────────────────────
try:
    from apps.billing.gl_service import invalidate_gl_cache
    invalidate_gl_cache()
    print("\nGL cache invalidated.")
except Exception:
    pass


# ── Summary ───────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("PLAN COMPTABLE IMPORT COMPLETE")
print("=" * 70)

final_counts = {}
for acct in GLAccount.objects.filter(is_active=True):
    c = acct.code[0] if acct.code else '?'
    final_counts[c] = final_counts.get(c, 0) + 1

print(f"\nFinal Chart of Accounts: {GLAccount.objects.filter(is_active=True).count()} accounts")
for c in sorted(final_counts):
    labels = {
        '1': 'Equity / Capital',
        '2': 'Fixed Assets',
        '3': 'Inventory / Stock',
        '4': 'Third Parties (AR/AP)',
        '5': 'Cash & Bank',
        '6': 'Expenses',
        '7': 'Revenue',
        '8': 'Other Income/Expense',
        '9': 'Cost Accounting',
    }
    print(f"  Class {c} ({labels.get(c, '?')}): {final_counts[c]} accounts")

print(f"\nGL Mappings: {GLMapping.objects.count()}")
print(f"Sub-categories linked: {ServiceSubCategory.objects.filter(is_deleted=False, gl_account__isnull=False).count()}")
print("\nDone! Check /billing/gl/accounts/ in the browser.")
