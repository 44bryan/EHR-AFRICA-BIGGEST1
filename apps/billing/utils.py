"""
Auto-billing utilities.
Called by pharmacy, investigations, laboratory, and opticals to create
invoice line items automatically when services are rendered.
"""
import logging
from django.utils import timezone

logger = logging.getLogger('apps.billing')


def get_or_create_today_invoice(patient, consultation=None, created_by=None):
    """
    Return the patient's open (DRAFT or ISSUED) invoice for today.
    Creates one if none exists.
    """
    from .models import Invoice, InvoiceStatus
    today = timezone.localdate()

    invoice = Invoice.objects.filter(
        patient=patient,
        status__in=[InvoiceStatus.DRAFT, InvoiceStatus.ISSUED],
        issue_date=today,
        is_deleted=False,
    ).first()

    if not invoice:
        invoice = Invoice.objects.create(
            patient=patient,
            consultation=consultation,
            status=InvoiceStatus.ISSUED,
            issue_date=today,
            created_by=created_by,
        )
        logger.info('Auto-created invoice %s for %s', invoice.invoice_number, patient.full_name)

    return invoice


def add_billing_item(patient, description, category, unit_price, quantity=1,
                     consultation=None, created_by=None):
    """
    Add a line item to the patient's current open invoice.
    Returns the created InvoiceItem.
    """
    from .models import InvoiceItem
    invoice = get_or_create_today_invoice(patient, consultation=consultation, created_by=created_by)
    item = InvoiceItem.objects.create(
        invoice=invoice,
        description=description,
        category=category,
        quantity=quantity,
        unit_price=unit_price,
        created_by=created_by,
    )
    logger.info('Auto-billing: added %s (x%s) @ %s to invoice %s',
                description, quantity, unit_price, invoice.invoice_number)
    return item


def bill_consultation(consultation, fee=None, created_by=None):
    """Add a consultation fee billing item."""
    from .models import ServiceCategory
    price = fee or _get_default_fee('consultation')
    return add_billing_item(
        patient=consultation.patient,
        description=f'Consultation — {consultation.department.name}',
        category=ServiceCategory.CONSULTATION,
        unit_price=price,
        consultation=consultation,
        created_by=created_by or consultation.consulting_doctor,
    )


def bill_investigation(order, created_by=None):
    """Add an investigation order billing item."""
    from .models import ServiceCategory
    inv_type = order.investigation_type
    price = getattr(inv_type, 'price', None) or _get_default_fee('investigation')
    return add_billing_item(
        patient=order.patient,
        description=f'Investigation — {inv_type.name}',
        category=ServiceCategory.INVESTIGATION,
        unit_price=price,
        consultation=order.consultation,
        created_by=created_by or order.ordered_by,
    )


def bill_lab_order(order, created_by=None):
    """Add a lab order billing item (one item per test)."""
    from .models import ServiceCategory
    items_created = []
    for item in order.items.all():
        test = item.test_type
        price = getattr(test, 'price', None) or _get_default_fee('lab')
        billing_item = add_billing_item(
            patient=order.patient,
            description=f'Laboratory — {test.name}',
            category=ServiceCategory.LABORATORY,
            unit_price=price,
            consultation=order.consultation,
            created_by=created_by or order.ordered_by,
        )
        items_created.append(billing_item)
    return items_created


def bill_dispensing(dispensing, created_by=None):
    """Add pharmacy dispensing billing items."""
    from .models import ServiceCategory
    items_created = []
    for item in dispensing.items.all():
        drug = item.drug
        strength = getattr(drug, 'strength', '') or ''
        unit_price = item.unit_price or getattr(drug, 'selling_price', None) or _get_default_fee('pharmacy')
        billing_item = add_billing_item(
            patient=dispensing.patient,
            description=f'Pharmacy — {item.display_name} {strength}'.strip(),
            category=ServiceCategory.PHARMACY,
            quantity=item.quantity_dispensed,
            unit_price=unit_price,
            created_by=created_by or dispensing.dispensed_by,
        )
        items_created.append(billing_item)
    return items_created


def bill_optical_order(order, created_by=None):
    """Add optical order billing item."""
    from .models import ServiceCategory
    price = getattr(order, 'total_price', None) or _get_default_fee('optical')
    return add_billing_item(
        patient=order.patient,
        description=f'Opticals — {order}',
        category=ServiceCategory.OPTICAL,
        unit_price=price,
        created_by=created_by,
    )


# Default fees when no price is configured (FCFA — Central African CFA Franc)
_DEFAULT_FEES = {
    'consultation': 5000,
    'investigation': 3000,
    'lab': 2000,
    'pharmacy': 500,
    'optical': 15000,
    'admission': 20000,
}


def _get_default_fee(category):
    return _DEFAULT_FEES.get(category, 1000)
