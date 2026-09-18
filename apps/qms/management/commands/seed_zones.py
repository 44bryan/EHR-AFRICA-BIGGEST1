"""
Management command: seed_zones

Creates the 4 hospital zones + tier→zone mappings and auto-assigns existing
ServiceCounters to the correct zone based on their serves_tiers field.

Usage:
    python manage.py seed_zones
    python manage.py seed_zones --reset   (wipe and recreate all mappings)
"""
from django.core.management.base import BaseCommand
from django.db import transaction


ZONE_DEFS = [
    {
        'code': 'STANDARD',
        'name': 'Standard Zone',
        'description': 'Main outpatient area. Serves Standard-tier patients. '
                       'Has its own reception, triage, cashier, and consultation rooms.',
        'color': 'secondary',
    },
    {
        'code': 'FT_EXPRESS',
        'name': 'Fast Track / Express Zone',
        'description': 'Side-entrance section shared by Fast Track and Express patients. '
                       'Has dedicated cashier, triage, and consultation rooms.',
        'color': 'info',
    },
    {
        'code': 'VIP',
        'name': 'VIP Zone',
        'description': 'Back-entrance VIP area. Fully isolated — VIP patients never appear '
                       'in any other zone\'s queues, screens, or lists.',
        'color': 'warning',
    },
    {
        'code': 'SHARED',
        'name': 'Shared Services Zone',
        'description': 'Lab, Pharmacy, Investigations, and Optical — serves ALL tiers. '
                       'Queue is ordered by tier priority with anti-starvation protection '
                       'so lower-tier patients are not indefinitely delayed.',
        'color': 'primary',
    },
]

TIER_ZONE_MAP = {
    'STANDARD':   'STANDARD',
    'EXPRESS':    'FT_EXPRESS',
    'VIP':        'VIP',
}

# ServiceTypes that always route to SHARED zone regardless of patient tier
SHARED_SERVICE_TYPES = {
    'LAB', 'PHARMACY', 'INVEST', 'OPTICAL', 'COUNSEL',
    'BILLING', 'PRE_OP', 'ADMISSION',
}

# Map serves_tiers → zone code for existing counters
TIER_TO_ZONE_CODE = {
    'STANDARD':   'STANDARD',
    'EXPRESS':    'FT_EXPRESS',
    'VIP':        'VIP',
}


class Command(BaseCommand):
    help = 'Seed hospital zones and tier→zone mappings, and auto-assign existing counters to zones.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset', action='store_true',
            help='Delete existing zones and mappings before re-seeding.'
        )

    def handle(self, *args, **options):
        from apps.qms.models import Zone, TierZoneMapping, ServiceCounter

        if options['reset']:
            self.stdout.write(self.style.WARNING('Resetting zone data…'))
            TierZoneMapping.objects.all().delete()
            Zone.objects.all().delete()

        with transaction.atomic():
            # 1. Create / update zones
            zones = {}
            for z in ZONE_DEFS:
                obj, created = Zone.objects.update_or_create(
                    code=z['code'],
                    defaults={
                        'name': z['name'],
                        'description': z['description'],
                        'color': z['color'],
                        'is_active': True,
                    }
                )
                zones[z['code']] = obj
                verb = 'Created' if created else 'Updated'
                self.stdout.write(f'  {verb} zone: {obj.name}')

            # 2. Create / update tier → zone mappings
            for tier, zone_code in TIER_ZONE_MAP.items():
                mapping, created = TierZoneMapping.objects.update_or_create(
                    tier=tier,
                    defaults={'zone': zones[zone_code]},
                )
                verb = 'Created' if created else 'Updated'
                self.stdout.write(f'  {verb} mapping: {tier} → {zones[zone_code].name}')

            # 3. Auto-assign existing ServiceCounters to zones
            counters = ServiceCounter.objects.all()
            updated = 0
            for counter in counters:
                # Shared service types always go to SHARED zone
                if counter.service_type in SHARED_SERVICE_TYPES:
                    target_zone = zones.get('SHARED')
                elif counter.serves_tiers:
                    # Use the first listed tier to determine zone
                    tier_list = [t.strip() for t in counter.serves_tiers.split(',')]
                    # VIP takes priority, then FT_EXPRESS, then STANDARD
                    if 'VIP' in tier_list:
                        zone_code = 'VIP'
                    elif 'EXPRESS' in tier_list:
                        zone_code = 'FT_EXPRESS'
                    else:
                        zone_code = 'STANDARD'
                    target_zone = zones.get(zone_code)
                else:
                    # No tier restriction = serves all → Standard zone (catch-all)
                    target_zone = zones.get('STANDARD')

                if counter.zone != target_zone:
                    counter.zone = target_zone
                    counter.save(update_fields=['zone', 'updated_at'])
                    updated += 1

            self.stdout.write(
                self.style.SUCCESS(
                    f'\nDone. 4 zones seeded, 4 tier mappings created, '
                    f'{updated} counters auto-assigned to zones.'
                )
            )
            self.stdout.write('\nZone summary:')
            for z in zones.values():
                tiers = ', '.join(z.tier_list) or '(none mapped)'
                stations = z.station_count
                self.stdout.write(f'  {z.name:30s} | Tiers: {tiers:30s} | Active stations: {stations}')
