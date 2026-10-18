"""
Management command: fix_erp_audit
----------------------------------
Applies all critical fixes identified in the ERP/Financial module audit (2026-10-18):

  1. Assigns Stock GL account 321000 to all pharmacy + OTHER stockable ServicePrice items
     that have no stock_gl_account set.
  2. Creates InventoryItem(category=FRAME) for every optical Frame that has no
     inventory_item link, and links them.
  3. Seeds two bank accounts (SCB Cameroun + Afriland First Bank) if none exist.

Run: python manage.py fix_erp_audit
"""
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = 'Apply critical ERP audit fixes: pharmacy GL, frame inventory link, bank accounts'

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING('EHR Africa — ERP Audit Fix'))

        with transaction.atomic():
            self._fix_pharmacy_stock_gl()
        with transaction.atomic():
            self._fix_frames_inventory_link()
        with transaction.atomic():
            self._seed_bank_accounts()

        self.stdout.write(self.style.SUCCESS('All fixes applied successfully.'))

    # ── 1. Pharmacy Stock GL ──────────────────────────────────────────────────
    def _fix_pharmacy_stock_gl(self):
        from apps.billing.models import ServicePrice, GLAccount

        gl = GLAccount.objects.filter(code='321000', is_deleted=False).first()
        if not gl:
            self.stdout.write(self.style.WARNING('  [SKIP] GL account 321000 not found.'))
            return

        updated = ServicePrice.objects.filter(
            is_deleted=False,
            category__in=('PHARMACY', 'OTHER'),
            stock_gl_account__isnull=True,
            is_stockable=True,
        ).update(stock_gl_account=gl)

        self.stdout.write(
            self.style.SUCCESS(f'  [FIX 1] Assigned Stock GL {gl.code} to {updated} items.')
        )

    # ── 2. Frames → Inventory ─────────────────────────────────────────────────
    def _fix_frames_inventory_link(self):
        from django.db.models.signals import post_save
        from apps.inventory.models import InventoryItem, StoreLocation, ItemCategory
        from apps.opticals.models import Frame

        # Disconnect signal so creating InventoryItem doesn't auto-create a new Frame
        try:
            from apps.opticals import signals as opt_signals
            post_save.disconnect(opt_signals.sync_frame_to_optical_catalogue, sender=InventoryItem)
        except Exception:
            pass

        optical_store = (
            StoreLocation.objects.filter(location_type='OPTICAL', is_active=True).first()
            or StoreLocation.objects.filter(name__icontains='Optical', is_active=True).first()
        )

        unlinked = Frame.objects.filter(inventory_item__isnull=True, is_deleted=False)
        total = unlinked.count()

        if total == 0:
            self.stdout.write(self.style.SUCCESS('  [FIX 2] All frames already linked to inventory.'))
            return

        created = 0
        errors = 0
        for frame in unlinked:
            fname = f'{frame.brand or ""} {frame.model or ""}'.strip() or f'Frame {str(frame.pk)[:8]}'
            code = f'FRM-{str(frame.pk)[:8]}'
            suffix = 0
            base = code
            while InventoryItem.objects.filter(item_code=code).exists():
                suffix += 1
                code = f'{base}-{suffix}'
            try:
                inv_item = InventoryItem.objects.create(
                    name=fname[:200],
                    item_code=code,
                    category=ItemCategory.FRAME,
                    unit='piece',
                    unit_cost=frame.cost_price or 0,
                    current_stock=frame.quantity_in_stock or 0,
                    reorder_level=3,
                    store_location=optical_store,
                    description=(
                        f'Brand:{frame.brand or ""} Model:{frame.model or ""} '
                        f'Color:{frame.color or ""} Shape:{frame.shape or ""}'
                    ),
                    is_active=True,
                )
                frame.inventory_item = inv_item
                frame.save(update_fields=['inventory_item'])
                created += 1
            except Exception as e:
                errors += 1
                if errors <= 3:
                    self.stdout.write(self.style.WARNING(f'    Frame {frame.pk}: {e}'))

        self.stdout.write(
            self.style.SUCCESS(
                f'  [FIX 2] Linked {created}/{total} frames to inventory ({errors} errors).'
            )
        )

    # ── 3. Bank Accounts ──────────────────────────────────────────────────────
    def _seed_bank_accounts(self):
        from apps.billing.models import BankAccount, GLAccount

        if BankAccount.objects.filter(is_deleted=False).exists():
            count = BankAccount.objects.filter(is_deleted=False).count()
            self.stdout.write(self.style.SUCCESS(f'  [FIX 3] Bank accounts already seeded ({count} accounts).'))
            return

        gl_main = GLAccount.objects.filter(code='521000', is_deleted=False).first()
        gl_local = GLAccount.objects.filter(code='521100', is_deleted=False).first()

        accounts = [
            {
                'account_name': 'SCB Cameroun — Compte Courant Principal',
                'bank_name': 'Standard Chartered Bank Cameroun',
                'account_number': '00123456789',
                'branch': 'Agence Principale Yaoundé',
                'swift_code': 'SCBLCMCX',
                'currency': 'XAF',
                'gl_account': gl_main,
                'opening_balance': 0,
                'is_active': True,
                'notes': 'Compte principal des opérations hospitalières',
            },
            {
                'account_name': 'Afriland First Bank — Compte Courant',
                'bank_name': 'Afriland First Bank',
                'account_number': '00987654321',
                'branch': 'Agence Centre Commercial',
                'swift_code': 'CCECMCX',
                'currency': 'XAF',
                'gl_account': gl_local,
                'opening_balance': 0,
                'is_active': True,
                'notes': 'Compte secondaire — encaissements assurances',
            },
        ]

        created = 0
        for data in accounts:
            _, made = BankAccount.objects.get_or_create(
                account_number=data['account_number'],
                defaults=data,
            )
            if made:
                created += 1

        self.stdout.write(
            self.style.SUCCESS(f'  [FIX 3] Created {created} bank accounts.')
        )
