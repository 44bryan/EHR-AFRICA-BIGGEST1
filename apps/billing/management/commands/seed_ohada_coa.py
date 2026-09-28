"""
Management command: seed_ohada_coa
Reads the OHADA SYCEBNL chart of accounts from the Excel file and seeds
GLAccount records with English translations.

Usage:
    python manage.py seed_ohada_coa                     # seed all 1,130 accounts
    python manage.py seed_ohada_coa --clear              # wipe existing then seed
    python manage.py seed_ohada_coa --class 5            # seed only class 5
"""
import os
from django.core.management.base import BaseCommand
from apps.billing.models import GLAccount, AccountType


# ═══════════════════════════════════════════════════════════════════════════════
# FRENCH → ENGLISH TRANSLATION MAP
# Covers all 77 principal (2-digit) accounts + common sub-account terms.
# ═══════════════════════════════════════════════════════════════════════════════

PRINCIPAL_EN = {
    '10': 'ENDOWMENT / CAPITAL',
    '11': 'RESERVES',
    '12': 'RETAINED EARNINGS',
    '13': 'NET RESULT FOR THE YEAR',
    '14': 'INVESTMENT SUBSIDIES / GRANTS',
    '15': 'REGULATED PROVISIONS AND SIMILAR FUNDS',
    '16': 'ALLOCATED FUNDS FROM DONATIONS OR BEQUESTS OF FIXED ASSETS',
    '17': 'DEFERRED FUNDS',
    '18': 'BORROWINGS AND SIMILAR DEBTS',
    '19': 'PROVISIONS FOR RISKS AND CHARGES',
    '20': 'ASSETS HELD FOR SALE FROM DONATIONS AND BEQUESTS',
    '21': 'INTANGIBLE ASSETS',
    '22': 'LAND',
    '23': 'BUILDINGS, TECHNICAL INSTALLATIONS AND FITTINGS',
    '24': 'EQUIPMENT, FURNITURE AND BIOLOGICAL ASSETS',
    '25': 'ADVANCES AND DEPOSITS ON FIXED ASSETS',
    '26': 'EQUITY INVESTMENTS',
    '27': 'OTHER FINANCIAL ASSETS',
    '28': 'ACCUMULATED DEPRECIATION',
    '29': 'IMPAIRMENT OF FIXED ASSETS',
    '31': 'GOODS RELATED TO ACTIVITY',
    '32': 'MERCHANDISE, RAW MATERIALS AND RELATED SUPPLIES',
    '33': 'OTHER SUPPLIES',
    '34': 'DONATIONS IN KIND',
    '35': 'WORK IN PROGRESS — PRODUCTS AND SERVICES',
    '36': 'FINISHED PRODUCTS, INTERMEDIARY AND RESIDUAL PRODUCTS',
    '37': 'GOODS IN TRANSIT, ON CONSIGNMENT OR DEPOSIT',
    '38': 'DONATIONS IN KIND (EXCEPTIONAL)',
    '39': 'IMPAIRMENT OF INVENTORIES AND WORK IN PROGRESS',
    '40': 'SUPPLIERS AND RELATED ACCOUNTS',
    '41': 'MEMBERS, CLIENTS-USERS AND RELATED ACCOUNTS',
    '42': 'PERSONNEL / STAFF',
    '43': 'SOCIAL SECURITY ORGANIZATIONS',
    '44': 'STATE AND PUBLIC AUTHORITIES',
    '45': 'FOUNDERS, CONTRIBUTORS AND CURRENT ACCOUNTS',
    '46': 'DONORS, ADMINISTRATION FUNDS',
    '47': 'MISCELLANEOUS DEBTORS AND CREDITORS',
    '48': 'RECEIVABLES AND DEBTS OUTSIDE ORDINARY ACTIVITIES',
    '49': 'IMPAIRMENT AND SHORT-TERM RISK PROVISIONS',
    '50': 'INVESTMENT SECURITIES',
    '51': 'VALUES FOR COLLECTION',
    '52': 'BANKS',
    '53': 'FINANCIAL INSTITUTIONS AND SIMILAR',
    '55': 'ELECTRONIC MONEY INSTRUMENTS',
    '56': 'BANKS — TREASURY CREDIT AND DISCOUNT',
    '57': 'CASH',
    '58': 'INTERNAL TRANSFERS',
    '59': 'IMPAIRMENT AND SHORT-TERM RISK PROVISIONS (TREASURY)',
    '60': 'PURCHASES AND INVENTORY CHANGES',
    '61': 'TRANSPORT',
    '62': 'EXTERNAL SERVICES',
    '63': 'OTHER EXTERNAL SERVICES',
    '64': 'TAXES AND DUTIES',
    '65': 'OTHER EXPENSES',
    '66': 'PERSONNEL EXPENSES',
    '67': 'FINANCIAL CHARGES AND SIMILAR',
    '68': 'DEPRECIATION CHARGES',
    '69': 'PROVISION AND IMPAIRMENT CHARGES',
    '70': 'REVENUE',
    '71': 'OPERATING SUBSIDIES / GRANTS',
    '72': 'CAPITALIZED PRODUCTION',
    '73': 'INVENTORY CHANGES — PRODUCED GOODS',
    '75': 'OTHER INCOME',
    '77': 'FINANCIAL INCOME AND SIMILAR',
    '78': 'TRANSFER OF CHARGES',
    '79': 'REVERSAL OF PROVISIONS AND IMPAIRMENTS',
    '81': 'BOOK VALUE OF DISPOSED ASSETS',
    '82': 'PROCEEDS FROM DISPOSAL OF ASSETS',
    '83': 'EXCEPTIONAL EXPENSES',
    '84': 'EXCEPTIONAL INCOME',
    '85': 'EXCEPTIONAL PROVISION CHARGES',
    '86': 'REVERSAL OF EXCEPTIONAL PROVISIONS AND IMPAIRMENTS',
    '87': 'INVENTORY CHANGES — DONATIONS IN KIND (EXCEPTIONAL)',
    '88': 'BALANCING SUBSIDIES',
    '90': 'USE OF VOLUNTARY IN-KIND CONTRIBUTIONS',
    '91': 'VOLUNTARY IN-KIND CONTRIBUTIONS',
    '92': 'REFLECTED ACCOUNTS',
    '93': 'RECLASSIFICATION ACCOUNTS',
    '94': 'COST ACCOUNTS',
    '95': 'INVENTORY ACCOUNTS (ANALYTICAL)',
    '96': 'VARIANCE ON STANDARD COSTS',
    '97': 'ACCOUNTING TREATMENT DIFFERENCES',
    '98': 'RESULT ACCOUNTS (ANALYTICAL)',
    '99': 'INTERNAL LIAISON ACCOUNTS',
}

# ═══════════════════════════════════════════════════════════════════════════════
# WORD-BY-WORD FRENCH → ENGLISH dictionary (comprehensive accounting terms)
# ═══════════════════════════════════════════════════════════════════════════════

_WORDS = {
    # Articles / connectors (remove or translate)
    'et': 'and', 'ou': 'or', 'de': 'of', 'des': 'of', 'du': 'of the',
    'au': 'to the', 'aux': 'to', 'le': 'the', 'la': 'the', 'les': 'the',
    'un': 'a', 'une': 'a', 'en': 'in', 'dans': 'in', 'sur': 'on',
    'par': 'by', 'pour': 'for', 'avec': 'with', 'sans': 'without',
    'non': 'non', 'ne': '', 'pas': 'not', 'plus': 'more',
    # Prepositions/links
    "d'": 'of', "l'": 'the',
    # Core accounting nouns
    'dotation': 'endowment', 'dotations': 'endowments',
    'reserves': 'reserves', 'reserve': 'reserve',
    'resultat': 'result', 'resultats': 'results',
    'excedent': 'surplus', 'excedents': 'surpluses',
    'deficit': 'deficit', 'deficits': 'deficits',
    'subventions': 'grants', 'subvention': 'grant',
    'provisions': 'provisions', 'provision': 'provision',
    'fonds': 'funds', 'fond': 'fund',
    'emprunts': 'borrowings', 'emprunt': 'borrowing',
    'dettes': 'debts', 'dette': 'debt',
    'immobilisations': 'fixed assets', 'immobilisation': 'fixed asset',
    'immoblisations': 'fixed assets',  # typo in source
    'amortissements': 'depreciation', 'amortissement': 'depreciation',
    'depreciations': 'impairments', 'depreciation': 'impairment',
    'stocks': 'inventories', 'stock': 'inventory',
    'fournisseurs': 'suppliers', 'fournisseur': 'supplier',
    'clients': 'clients', 'client': 'client',
    'adherents': 'members', 'adherent': 'member',
    'usagers': 'users', 'usager': 'user',
    'personnel': 'staff', 'personnels': 'staff',
    'charges': 'expenses', 'charge': 'expense',
    'produits': 'income', 'produit': 'income',
    'revenus': 'revenue', 'revenu': 'revenue',
    'caisse': 'cash', 'caisses': 'cash',
    'banque': 'bank', 'banques': 'banks',
    'terrains': 'land', 'terrain': 'land',
    'batiments': 'buildings', 'batiment': 'building',
    'materiel': 'equipment', 'materiels': 'equipment',
    'mobilier': 'furniture', 'mobiliers': 'furniture',
    'vehicules': 'vehicles', 'vehicule': 'vehicle',
    'impots': 'taxes', 'impot': 'tax',
    'taxes': 'duties', 'taxe': 'duty',
    'achats': 'purchases', 'achat': 'purchase',
    'ventes': 'sales', 'vente': 'sale',
    'transports': 'transport', 'transport': 'transport',
    'loyers': 'rent', 'loyer': 'rent',
    'assurances': 'insurance', 'assurance': 'insurance',
    'honoraires': 'professional fees',
    'interets': 'interest', 'interet': 'interest',
    'salaires': 'salaries', 'salaire': 'salary',
    'indemnites': 'allowances', 'indemnite': 'allowance',
    'cotisations': 'contributions', 'cotisation': 'contribution',
    'variations': 'changes', 'variation': 'change',
    'creances': 'receivables', 'creance': 'receivable',
    'titres': 'securities', 'titre': 'security',
    'acomptes': 'deposits on account', 'acompte': 'deposit on account',
    'avances': 'advances', 'avance': 'advance',
    'virements': 'transfers', 'virement': 'transfer',
    'cessions': 'disposals', 'cession': 'disposal',
    'reprises': 'reversals', 'reprise': 'reversal',
    'numeraire': 'cash', 'nature': 'kind',
    'incorporelles': 'intangible', 'incorporelle': 'intangible',
    'corporelles': 'tangible', 'corporelle': 'tangible',
    'financieres': 'financial', 'financiere': 'financial',
    'financiers': 'financial', 'financier': 'financial',
    'exploitation': 'operating',
    'ordinaires': 'ordinary', 'ordinaire': 'ordinary',
    'investissement': 'investment', 'investissements': 'investments',
    'tresorerie': 'treasury',
    'exercice': 'fiscal year',
    'etat': 'state', 'etats': 'states',
    'organismes': 'organizations', 'organisme': 'organization',
    'sociaux': 'social', 'social': 'social',
    'divers': 'miscellaneous', 'diverses': 'miscellaneous',
    'siege': 'head office',
    'succursales': 'branches', 'succursale': 'branch',
    'comptes': 'accounts', 'compte': 'account',
    'rattaches': 'related', 'rattache': 'related',
    'courants': 'current', 'courant': 'current',
    'debiteurs': 'debtors', 'debiteur': 'debtor',
    'crediteurs': 'creditors', 'crediteur': 'creditor',
    'medical': 'medical', 'medicaux': 'medical',
    'medicaments': 'medicines', 'medicament': 'medicine',
    'fournitures': 'supplies', 'fourniture': 'supply',
    'consommables': 'consumables', 'consommable': 'consumable',
    'marchandises': 'merchandise', 'marchandise': 'merchandise',
    'matieres': 'materials', 'matiere': 'material',
    'premieres': 'raw',
    'approvisionnements': 'provisions/supplies',
    'emballages': 'packaging', 'emballage': 'packaging',
    'entretien': 'maintenance', 'entretiens': 'maintenance',
    'reparations': 'repairs', 'reparation': 'repair',
    'publicite': 'advertising',
    'electricite': 'electricity',
    'eau': 'water', 'eaux': 'water',
    'telephone': 'telephone', 'telephoniques': 'telephone',
    'poste': 'postal',
    'missions': 'missions', 'mission': 'mission',
    'deplacements': 'travel', 'deplacement': 'travel',
    'formation': 'training', 'formations': 'training',
    'recherche': 'research',
    'brevets': 'patents', 'brevet': 'patent',
    'licences': 'licenses', 'licence': 'license',
    'logiciels': 'software', 'logiciel': 'software',
    'constructions': 'buildings', 'construction': 'building',
    'installations': 'installations', 'installation': 'installation',
    'agencements': 'fittings', 'agencement': 'fitting',
    'informatique': 'IT/computer',
    'outillage': 'tools',
    'biologique': 'biological', 'biologiques': 'biological',
    # More accounting/business terms
    'reglementees': 'regulated', 'reglementee': 'regulated',
    'assimilees': 'similar', 'assimilee': 'similar', 'assimiles': 'similar',
    'techniques': 'technical', 'technique': 'technical',
    'placement': 'investment', 'placements': 'investments',
    'participation': 'equity stake', 'participations': 'equity stakes',
    'encaisser': 'collect', 'encaissement': 'collection',
    'decaisser': 'disburse', 'decaissement': 'disbursement',
    'valeurs': 'values', 'valeur': 'value',
    'comptables': 'book', 'comptable': 'book',
    'immobilisees': 'capitalized', 'immobilisee': 'capitalized',
    'production': 'production',
    'intermediaires': 'intermediate',
    'residuels': 'residual', 'residuel': 'residual',
    'finis': 'finished', 'fini': 'finished',
    'consignation': 'consignment',
    'depot': 'deposit', 'depots': 'deposits',
    'route': 'transit',
    'cours': 'progress',
    'activites': 'activities', 'activite': 'activity',
    'propres': 'own',
    'transferts': 'transfers', 'transfert': 'transfer',
    'internes': 'internal', 'interne': 'internal',
    'externes': 'external', 'externe': 'external',
    'exterieurs': 'external',
    'services': 'services', 'service': 'service',
    'autres': 'other',
    'biens': 'goods', 'bien': 'goods',
    'lies': 'related', 'lie': 'related', 'liee': 'related', 'liees': 'related',
    'dons': 'donations', 'don': 'donation',
    'legs': 'bequests',
    'fondateurs': 'founders', 'fondateur': 'founder',
    'apporteurs': 'contributors', 'apporteur': 'contributor',
    'bailleurs': 'donors/funders', 'bailleur': 'donor/funder',
    'administration': 'administration',
    'projet': 'project', 'projets': 'projects',
    'developpement': 'development',
    'specifique': 'specific', 'specifiques': 'specific',
    'affectes': 'allocated', 'affecte': 'allocated',
    'affectation': 'allocation',
    'instance': 'pending',
    'net': 'net', 'nets': 'net',
    'brut': 'gross', 'bruts': 'gross',
    'directes': 'direct', 'directe': 'direct', 'directs': 'direct', 'direct': 'direct',
    'indirectes': 'indirect', 'indirecte': 'indirect',
    'versees': 'paid', 'versee': 'paid', 'verses': 'paid', 'verse': 'paid',
    'recus': 'received', 'recu': 'received', 'recues': 'received', 'recue': 'received',
    'national': 'national', 'nationaux': 'national',
    'etranger': 'foreign', 'etrangers': 'foreign', 'etrangere': 'foreign',
    'locales': 'local', 'locale': 'local', 'locaux': 'local',
    'remunerations': 'remuneration', 'remuneration': 'remuneration',
    'primes': 'bonuses', 'prime': 'bonus',
    'conges': 'leave', 'conge': 'leave',
    'gratifications': 'bonuses',
    'prestation': 'benefit', 'prestations': 'benefits',
    'retraite': 'retirement', 'retraites': 'retirement',
    'prevoyance': 'welfare',
    'accidents': 'accidents', 'accident': 'accident',
    'travail': 'work',
    'maladies': 'sickness', 'maladie': 'sickness',
    'professionnelles': 'professional', 'professionnel': 'professional',
    'familiales': 'family', 'familiale': 'family',
    'allocations': 'allowances', 'allocation': 'allowance',
    'statutaires': 'statutory', 'statutaire': 'statutory',
    'contractuelles': 'contractual', 'contractuelle': 'contractual',
    'obligatoires': 'mandatory', 'obligatoire': 'mandatory',
    'facultatives': 'voluntary', 'facultative': 'voluntary',
    'volontaires': 'voluntary', 'volontaire': 'voluntary',
    'temporaire': 'temporary', 'temporaires': 'temporary',
    'permanente': 'permanent', 'permanentes': 'permanent',
    'annuelles': 'annual', 'annuelle': 'annual', 'annuel': 'annual',
    'mensuelles': 'monthly', 'mensuelle': 'monthly',
    'reevaluation': 'revaluation',
    'ecarts': 'differences', 'ecart': 'difference',
    'consomptible': 'consumable',
    'droit': 'right',
    'droits': 'rights',
    'reprise': 'reclaim',
    'entree': 'entry',
    'risques': 'risks', 'risque': 'risk',
    'publiques': 'public', 'publique': 'public',
    'collectivites': 'authorities', 'collectivite': 'authority',
    'decentralisees': 'decentralized',
    'entites': 'entities', 'entite': 'entity',
    'prives': 'private', 'prive': 'private', 'privees': 'private',
    'mixtes': 'mixed', 'mixte': 'mixed',
    'internationaux': 'international', 'international': 'international',
    'speciales': 'special', 'speciale': 'special', 'speciaux': 'special',
    'gle': 'general',
    'g.le.': 'general',
    'long': 'long', 'moyen': 'medium', 'court': 'short',
    'terme': 'term',
    'regions': 'regions', 'region': 'region',
    'departements': 'departments', 'departement': 'department',
    'communes': 'municipalities', 'commune': 'municipality',
    'inscription': 'registration',
    'inscrite': 'recorded', 'inscrit': 'recorded',
    'effets': 'notes', 'effet': 'note',
    'payer': 'payable', 'recevoir': 'receivable',
    'commerciaux': 'commercial', 'commercial': 'commercial',
    'escomptes': 'discounts', 'escompte': 'discount',
    'rabais': 'rebates',
    'remises': 'discounts', 'remise': 'discount',
    'ristournes': 'rebates', 'ristourne': 'rebate',
    'obtenus': 'obtained', 'obtenu': 'obtained',
    'accordes': 'granted', 'accorde': 'granted',
    'retenues': 'withholdings', 'retenue': 'withholding',
    'fiscales': 'fiscal/tax', 'fiscale': 'fiscal/tax',
    'douanes': 'customs', 'douane': 'customs',
    'tva': 'VAT', 'iva': 'VAT',
    'recuperable': 'recoverable',
    'collectee': 'collected', 'collecte': 'collected',
    'facturee': 'invoiced', 'facture': 'invoiced',
    'decaissee': 'disbursed',
    'emise': 'issued', 'emis': 'issued',
    'echues': 'due/matured', 'echu': 'due/matured',
    'impayees': 'unpaid', 'impaye': 'unpaid',
    'douteuses': 'doubtful', 'douteuse': 'doubtful', 'douteux': 'doubtful',
    'litigieuses': 'disputed', 'litigieux': 'disputed',
    'contentieuses': 'contentious',
    'credit': 'credit', 'credits': 'credits',
    'debit': 'debit', 'debits': 'debits',
    'solde': 'balance', 'soldes': 'balances',
    'interimaire': 'interim',
    'prorata': 'pro-rata',
    'arrondi': 'rounding',
    'regularisation': 'adjustment', 'regularisations': 'adjustments',
    'disponibilites': 'cash/liquid assets',
    'electronique': 'electronic', 'electroniques': 'electronic',
    'monnaie': 'money',
    'instruments': 'instruments', 'instrument': 'instrument',
    'etablissements': 'institutions', 'etablissement': 'institution',
    'hao': 'exceptional',
    'h.a.o.': 'exceptional',
    'equilibre': 'balancing',
    'contributions': 'contributions', 'contribution': 'contribution',
    'emplois': 'uses', 'emploi': 'use',
    'reflechis': 'reflected',
    'reclassements': 'reclassification',
    'couts': 'costs', 'cout': 'cost',
    'preetablis': 'standard/preset',
    'differences': 'differences', 'difference': 'difference',
    'traitement': 'treatment',
    'liaisons': 'liaison',
    'analytique': 'analytical',
    'comptabilite': 'accounting',
    'amortissable': 'depreciable',
    'amor': 'depreciation',
    'frais': 'costs/fees',
    'preliminaires': 'preliminary',
    'constitutif': 'formation', 'constitution': 'formation',
    'augmentation': 'increase',
    'capital': 'capital',
    'inscription': 'registration',
    'bourse': 'stock exchange',
    'concessions': 'concessions', 'concession': 'concession',
    'marques': 'trademarks', 'marque': 'trademark',
    'modeles': 'models', 'modele': 'model',
    'fonds': 'goodwill',
    'commercial': 'commercial',
    'goodwill': 'goodwill',
    'mali': 'loss',
    'boni': 'gain',
    'fusion': 'merger',
    'scission': 'split',
    'apport': 'contribution',
    'partiel': 'partial', 'partiels': 'partial',
    'actif': 'asset', 'actifs': 'assets',
    'passif': 'liability', 'passifs': 'liabilities',
    'juridiques': 'legal', 'juridique': 'legal',
    'dommages': 'damages',
    'garanties': 'warranties', 'garantie': 'warranty',
    'donnees': 'given', 'donnee': 'given',
    'nantissement': 'pledge',
    'hypotheque': 'mortgage', 'hypotheques': 'mortgages',
    'cautionnement': 'deposit/bond',
    'prets': 'loans', 'pret': 'loan',
    'creances': 'receivables',
    'immobilisees': 'capitalized',
    'bureautique': 'office equipment',
    'medical': 'medical',
    'industriel': 'industrial',
    'agricole': 'agricultural',
    'roulant': 'rolling',
    'bureau': 'office',
    'cheptel': 'livestock',
    'plantation': 'plantation',
    'recuperables': 'recoverable',
    'consignes': 'deposits (returnable)',
    'deteriorations': 'deterioration',
    'non': 'non',
    'recuperes': 'recovered',
    'provisionnement': 'provisioning',
    'depots': 'deposits',
    'cautionnements': 'bonds/deposits',
}


def _normalize(text):
    """Strip accents and lowercase for matching."""
    import unicodedata
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c)).lower()


def translate_name(code, french_name):
    """Translate a French OHADA account name to English."""
    if code in PRINCIPAL_EN:
        return PRINCIPAL_EN[code]

    norm = _normalize(french_name)
    # Split into words, translate each
    import re
    tokens = re.split(r'([\s,;:\-–—/()\'\"\.]+)', norm)
    result = []
    for tok in tokens:
        stripped = tok.strip(" ,;:-–—/()'\".")
        if stripped in _WORDS:
            translated = _WORDS[stripped]
            if translated:  # skip empty replacements
                result.append(tok.replace(stripped, translated))
        else:
            result.append(tok)

    out = ''.join(result).strip()
    # Title case
    out = out.title()
    # Fix short words
    for w in ['And', 'Or', 'Of', 'The', 'In', 'On', 'For', 'To', 'By', 'A', 'An', 'At']:
        out = out.replace(f' {w} ', f' {w.lower()} ')
    # First char always upper
    if out:
        out = out[0].upper() + out[1:]
    return out


def class_to_account_type(class_num):
    """Map OHADA class number to AccountType."""
    mapping = {
        1: AccountType.EQUITY,
        2: AccountType.ASSET,
        3: AccountType.ASSET,
        4: AccountType.LIABILITY,   # Mixed, but default LIABILITY (AP, staff, tax)
        5: AccountType.ASSET,       # Cash & bank are assets
        6: AccountType.EXPENSE,
        7: AccountType.REVENUE,
        8: AccountType.EXPENSE,     # Mixed exceptional — default expense
        9: AccountType.EXPENSE,     # Cost accounting
    }
    return mapping.get(class_num, AccountType.EXPENSE)


# Class 4 exceptions: some 4x accounts are ASSET (receivables), not LIABILITY
CLASS4_ASSET_CODES = {'41', '411', '412', '413', '414', '415', '416', '417', '418'}


class Command(BaseCommand):
    help = 'Seed OHADA SYCEBNL Chart of Accounts from Excel file (English translations)'

    def add_arguments(self, parser):
        parser.add_argument('--clear', action='store_true',
                            help='Soft-delete all existing GL accounts before seeding')
        parser.add_argument('--class', dest='class_num', type=int, default=0,
                            help='Seed only a specific class (1-9)')

    def handle(self, *args, **options):
        import openpyxl

        excel_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            '..', '..', '..', '..', 'Plan_de_comptes_SYCEBNL_OHADA.xlsx'
        )
        # Normalize path
        excel_path = os.path.normpath(excel_path)
        if not os.path.exists(excel_path):
            self.stderr.write(self.style.ERROR(f'Excel file not found: {excel_path}'))
            return

        if options['clear']:
            count = GLAccount.objects.all().count()
            GLAccount.objects.all().update(is_deleted=True)
            self.stdout.write(self.style.WARNING(f'Soft-deleted {count} existing accounts'))

        wb = openpyxl.load_workbook(excel_path, read_only=True)
        ws = wb['Plan complet']

        created = 0
        updated = 0
        skipped = 0
        class_filter = options['class_num']

        # First pass: create/update all accounts (without parent links)
        accounts_data = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            class_num, code, name_fr, level, parent_code = row
            if not code or not name_fr:
                continue
            code = str(code).strip()
            if class_filter and class_num != class_filter:
                continue

            name_en = translate_name(code, name_fr)
            acct_type = class_to_account_type(class_num)

            # Class 4 exceptions: 41x = receivables (ASSET)
            if class_num == 4 and code[:2] == '41':
                acct_type = AccountType.ASSET
            # Class 8 revenue exceptions
            if class_num == 8 and code[:2] in ('82', '84', '86', '88'):
                acct_type = AccountType.REVENUE

            accounts_data.append({
                'code': code,
                'name': name_en,
                'name_fr': name_fr,
                'account_type': acct_type,
                'parent_code': str(parent_code).strip() if parent_code else None,
            })

        # Create/update accounts
        for data in accounts_data:
            try:
                obj, was_created = GLAccount.objects.update_or_create(
                    code=data['code'],
                    defaults={
                        'name': data['name'],
                        'account_type': data['account_type'],
                        'description': data['name_fr'],  # Keep French in description
                        'is_active': True,
                        'is_deleted': False,
                    }
                )
                if was_created:
                    created += 1
                else:
                    updated += 1
            except Exception as e:
                self.stderr.write(f"Error on {data['code']}: {e}")
                skipped += 1

        # Second pass: set parent links
        parent_set = 0
        for data in accounts_data:
            if data['parent_code']:
                try:
                    child = GLAccount.objects.get(code=data['code'])
                    parent = GLAccount.objects.filter(code=data['parent_code']).first()
                    if parent and child.parent_id != parent.pk:
                        child.parent = parent
                        child.save(update_fields=['parent'])
                        parent_set += 1
                except GLAccount.DoesNotExist:
                    pass

        self.stdout.write(self.style.SUCCESS(
            f'Done: {created} created, {updated} updated, {skipped} skipped, '
            f'{parent_set} parent links set'
        ))
        self.stdout.write(f'Total accounts: {GLAccount.objects.filter(is_deleted=False).count()}')
