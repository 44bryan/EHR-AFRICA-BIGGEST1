"""
Auto-sync signals: InventoryItem → optical catalogue
  - category='LENS'  → opticals.Lens
  - category='FRAME' → opticals.Frame

When the store keeper creates or updates a LENS or FRAME item in the general
inventory (with full GL account / cost center selection), the optical
catalogue is automatically kept in sync so the optical dispenser can
immediately see and use the item in orders.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver


def _guess_lens_type(name: str) -> str:
    n = name.upper()
    if 'PROG' in n or 'VARI' in n or 'PAL' in n:
        return 'PROGRESSIVE'
    if 'BIF' in n:
        return 'BIFOCAL'
    if 'OCC' in n or 'OFFICE' in n or 'OCCUP' in n:
        return 'OCCUPATIONAL'
    if 'CONTACT' in n or 'CL ' in n:
        return 'CONTACT'
    return 'SV'


def _parse_brand_model(name: str):
    parts = name.strip().split(' ', 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return name, name


@receiver(post_save, sender='inventory.InventoryItem')
def sync_lens_to_optical_catalogue(sender, instance, created, **kwargs):
    """Mirror LENS inventory items into opticals.Lens catalogue."""
    if instance.category != 'LENS' or instance.is_deleted:
        return
    try:
        from apps.opticals.models import Lens
        lens = Lens.objects.filter(inventory_item=instance).first()
        if not lens:
            lens = Lens.objects.filter(name__iexact=instance.name, is_deleted=False).first()
        if lens:
            update_fields = []
            if instance.unit_cost and lens.cost_price != instance.unit_cost:
                lens.cost_price = instance.unit_cost
                update_fields.append('cost_price')
            if lens.is_active != instance.is_active:
                lens.is_active = instance.is_active
                update_fields.append('is_active')
            if lens.inventory_item_id != instance.pk:
                lens.inventory_item = instance
                update_fields.append('inventory_item')
            if update_fields:
                update_fields.append('updated_at')
                lens.save(update_fields=update_fields)
        else:
            Lens.objects.create(
                name=instance.name,
                lens_type=_guess_lens_type(instance.name),
                cost_price=instance.unit_cost or 0,
                selling_price=0,
                is_active=instance.is_active,
                inventory_item=instance,
            )
    except Exception:
        pass


@receiver(post_save, sender='inventory.InventoryItem')
def sync_frame_to_optical_catalogue(sender, instance, created, **kwargs):
    """Mirror FRAME inventory items into opticals.Frame catalogue."""
    if instance.category != 'FRAME' or instance.is_deleted:
        return
    try:
        from apps.opticals.models import Frame
        frame = Frame.objects.filter(inventory_item=instance).first()
        if not frame:
            sku = instance.item_code or None
            if sku:
                frame = Frame.objects.filter(sku=sku, is_deleted=False).first()
            if not frame:
                brand, model = _parse_brand_model(instance.name)
                frame = Frame.objects.filter(
                    brand__iexact=brand, model__iexact=model, is_deleted=False
                ).first()
        if frame:
            update_fields = []
            if instance.unit_cost and frame.cost_price != instance.unit_cost:
                frame.cost_price = instance.unit_cost
                update_fields.append('cost_price')
            if frame.is_active != instance.is_active:
                frame.is_active = instance.is_active
                update_fields.append('is_active')
            if frame.quantity_in_stock != instance.current_stock:
                frame.quantity_in_stock = instance.current_stock
                update_fields.append('quantity_in_stock')
            if frame.inventory_item_id != instance.pk:
                frame.inventory_item = instance
                update_fields.append('inventory_item')
            if update_fields:
                update_fields.append('updated_at')
                frame.save(update_fields=update_fields)
        else:
            brand, model = _parse_brand_model(instance.name)
            Frame.objects.create(
                brand=brand, model=model,
                cost_price=instance.unit_cost or 0,
                selling_price=0,
                quantity_in_stock=instance.current_stock,
                sku=instance.item_code or None,
                is_active=instance.is_active,
                inventory_item=instance,
            )
    except Exception:
        pass
