"""
Management command: seed_cost_centers
======================================
Sets up:
  1. CostCenter records (CC-001 … CC-012) with OHADA-style numbering
  2. ItemCategoryGL mappings — Finance Director configured once, used forever
  3. Links each existing StoreLocation to its cost center

Run:
    python manage.py seed_cost_centers
    python manage.py seed_cost_centers --force   # re-apply even if already exists
"""
from django.core.management.base import BaseCommand
from django.db import transaction


COST_CENTERS = [
    # (code,         name,                     description)
    ('CC-001', 'Pharmacy',        'Pharmacy / Drug dispensary operations'),
    ('CC-002', 'Theatre',         'Operating theatre, surgical consumables'),
    ('CC-003', 'OPD',             'Outpatient department consultations'),
    ('CC-004', 'Laboratory',      'Lab investigations and reagents'),
    ('CC-005', 'Optical',         'Optical dispensary — frames, lenses'),
    ('CC-006', 'IPD / Ward',      'Inpatient wards and nursing floor'),
    ('CC-007', 'Radiology',       'Imaging and radiology unit'),
    ('CC-008', 'Administration',  'Administrative and management overhead'),
    ('CC-009', 'Finance',         'Finance department operations'),
    ('CC-010', 'CSSD',            'Central Sterile Services Department'),
    ('CC-011', 'Nutrition',       'Dietary and nutrition unit'),
    ('CC-012', 'Maintenance',     'Maintenance, engineering and facilities'),
]

# ItemCategory → (inventory_code, cogs_code, loss_code)
# OHADA SYSCEBNL accounts:
#   Class 3 = Stock; 601/603 = Cost of goods sold / Variation in stock; 658 = Other losses
CATEGORY_GL = {
    'PHARMACEUTICAL':     ('321000', '601000', '6581'),   # Drugs
    'SURGICAL':           ('323000', '603000', '6581'),   # Theatre/Surgical
    'MEDICAL_CONSUMABLE': ('331000', '603000', '6581'),   # Consumables
    'DIAGNOSTIC':         ('331000', '603000', '6581'),   # Diagnostic kits
    'IMPLANT':            ('323000', '601000', '6581'),   # Implants/prostheses
    'LENS':               ('322000', '601000', '6581'),   # Optical lenses
    'OFFICE':             ('331000', '603000', '658000'), # Office supplies → Autres approvisionnements
    'CLEANING':           ('331000', '603000', '658000'), # Cleaning supplies
    'IT':                 ('331000', '603000', '658000'), # IT consumables
    'FURNITURE':          ('331000', '603000', '658000'), # Furniture/fixtures
    'LINEN':              ('331000', '603000', '658000'), # Linen
    'OTHER':              ('331000', '603000', '658000'), # Other
}

# StoreLocation.store_type → cost_center code
STORE_TO_CC = {
    'PHARMACY':   'CC-001',
    'THEATRE':    'CC-002',
    'GENERAL':    'CC-003',
    'CENTRAL':    'CC-003',
    'SUB':        'CC-003',
    'OPTICAL':    'CC-005',
    'SHOWROOM':   'CC-005',
    'WARD':       'CC-006',
    'EMERGENCY':  'CC-006',
    'FRONT_DESK': 'CC-003',
    'NON_MEDICAL':'CC-008',
    'OUTREACH':   'CC-003',
    'OTN':        'CC-003',
}


class Command(BaseCommand):
    help = 'Seed cost centers, ItemCategoryGL mappings, and wire StoreLocations'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force', action='store_true',
            help='Update existing records (default: skip if already exists)'
        )

    @transaction.atomic
    def handle(self, *args, **options):
        force = options['force']
        self._seed_cost_centers(force)
        self._seed_item_category_gl(force)
        self._wire_store_locations(force)
        self.stdout.write(self.style.SUCCESS('Done — cost centers seeded successfully.'))

    # ──────────────────────────────────────────────────────────────────────────
    def _seed_cost_centers(self, force):
        from apps.billing.models import CostCenter
        created = updated = skipped = 0
        for code, name, desc in COST_CENTERS:
            cc, was_created = CostCenter.objects.get_or_create(
                code=code,
                defaults={'name': name, 'description': desc, 'is_active': True},
            )
            if was_created:
                created += 1
            elif force:
                cc.name = name
                cc.description = desc
                cc.is_active = True
                cc.save()
                updated += 1
            else:
                skipped += 1
        self.stdout.write(
            f'  Cost Centers — created: {created}, updated: {updated}, skipped: {skipped}'
        )

    # ──────────────────────────────────────────────────────────────────────────
    def _seed_item_category_gl(self, force):
        from apps.billing.models import GLAccount
        from apps.inventory.models import ItemCategoryGL

        def _acct(code):
            """Find the best GL account for the given code (exact or prefix)."""
            a = GLAccount.objects.filter(code=code, is_active=True, is_deleted=False).first()
            if not a:
                a = GLAccount.objects.filter(
                    code__startswith=code, is_active=True, is_deleted=False
                ).order_by('code').first()
            return a

        created = updated = skipped = 0
        for cat, (inv_code, cogs_code, loss_code) in CATEGORY_GL.items():
            inv_acct  = _acct(inv_code)
            cogs_acct = _acct(cogs_code)
            loss_acct = _acct(loss_code)

            if not inv_acct:
                self.stdout.write(
                    self.style.WARNING(
                        f'  SKIP {cat}: GL account {inv_code} not found — run seed_ohada_coa first'
                    )
                )
                skipped += 1
                continue

            obj, was_created = ItemCategoryGL.objects.get_or_create(
                category=cat,
                defaults={
                    'inventory_account': inv_acct,
                    'cogs_account': cogs_acct,
                    'loss_account': loss_acct,
                },
            )
            if was_created:
                created += 1
            elif force:
                obj.inventory_account = inv_acct
                obj.cogs_account = cogs_acct
                obj.loss_account = loss_acct
                obj.save()
                updated += 1
            else:
                skipped += 1

        self.stdout.write(
            f'  ItemCategoryGL — created: {created}, updated: {updated}, skipped: {skipped}'
        )

    # ──────────────────────────────────────────────────────────────────────────
    def _wire_store_locations(self, force):
        from apps.billing.models import CostCenter
        from apps.inventory.models import StoreLocation

        cc_map = {cc.code: cc for cc in CostCenter.objects.all()}
        wired = already = no_match = 0

        for store in StoreLocation.objects.filter(is_active=True):
            cc_code = STORE_TO_CC.get(store.location_type)
            if not cc_code:
                no_match += 1
                continue
            cc = cc_map.get(cc_code)
            if not cc:
                no_match += 1
                continue
            if store.cost_center_id == cc.pk and not force:
                already += 1
                continue
            store.cost_center = cc
            store.save(update_fields=['cost_center'])
            wired += 1

        self.stdout.write(
            f'  StoreLocations — wired: {wired}, already set: {already}, no match: {no_match}'
        )
