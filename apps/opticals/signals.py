"""
Auto-sync signal: InventoryItem(category='LENS') → opticals.Lens
When the store keeper creates or updates a LENS item in the general inventory,
the optical catalogue (opticals.Lens) is automatically kept in sync so the
optical dispenser can immediately see and use the item in orders.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver


def _guess_lens_type(name: str) -> str:
    """Infer LensType from item name keywords."""
    n = name.upper()
    if 'PROG' in n or 'VARI' in n or 'PAL' in n:
        return 'PROGRESSIVE'
    if 'BIF' in n:
        return 'BIFOCAL'
    if 'OCC' in n or 'OFFICE' in n or 'OCCUP' in n:
        return 'OCCUPATIONAL'
    if 'CONTACT' in n or 'CL ' in n:
        return 'CONTACT'
    return 'SV'  # Single Vision default


@receiver(post_save, sender='inventory.InventoryItem')
def sync_lens_to_optical_catalogue(sender, instance, created, **kwargs):
    """
    When a LENS InventoryItem is saved by the store keeper, mirror it into
    opticals.Lens so it appears in the optical dispenser's order form.
    """
    if instance.category != 'LENS':
        return
    if instance.is_deleted:
        return

    try:
        from apps.opticals.models import Lens

        # Try to find existing linked lens
        lens = Lens.objects.filter(inventory_item=instance).first()
        if not lens:
            # Try by name match (handles items uploaded before FK existed)
            lens = Lens.objects.filter(name__iexact=instance.name, is_deleted=False).first()

        if lens:
            # Update cost price if changed; keep selling price set by dispenser
            update_fields = []
            if instance.unit_cost and lens.cost_price != instance.unit_cost:
                lens.cost_price = instance.unit_cost
                update_fields.append('cost_price')
            if lens.is_active != instance.is_active:
                lens.is_active = instance.is_active
                update_fields.append('is_active')
            # Link the FK if not already linked
            if lens.inventory_item_id != instance.pk:
                lens.inventory_item = instance
                update_fields.append('inventory_item')
            if update_fields:
                update_fields.append('updated_at')
                lens.save(update_fields=update_fields)
        else:
            # Create new catalogue entry
            Lens.objects.create(
                name=instance.name,
                lens_type=_guess_lens_type(instance.name),
                cost_price=instance.unit_cost or 0,
                selling_price=0,
                is_active=instance.is_active,
                inventory_item=instance,
            )
    except Exception:
        pass  # Never block inventory saves due to catalogue sync errors
