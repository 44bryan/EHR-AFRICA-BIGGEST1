"""
Auto-routing signals for Laboratory.

Triggers:
  LabResult saved with is_verified=True → route patient back to doctor
  LabOrder.status → COMPLETED           → same (fallback)
"""
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger('ehr.auto_routing')


@receiver(post_save, sender='laboratory.LabResult')
def on_lab_result_verified(sender, instance, **kwargs):
    """When a lab result is verified, route the patient back to their doctor."""
    if not instance.is_verified:
        return
    order = instance.order_item.order
    _auto_route_from_lab_order(order, 'Lab result verified')


@receiver(post_save, sender='laboratory.LabOrder')
def on_lab_order_completed(sender, instance, **kwargs):
    """Fallback: when a lab order is marked COMPLETED, route back to doctor."""
    if instance.status != 'COMPLETED':
        return
    _auto_route_from_lab_order(instance, 'Lab order completed')


def _auto_route_from_lab_order(order, reason):
    try:
        from apps.consultations.auto_routing import route_back_to_doctor

        consultation = order.consultation
        visit = getattr(consultation, 'visit', None)
        if not visit:
            return

        # Only route back when patient is currently AT the laboratory
        if visit.status != 'LABORATORY':
            return

        # For result-based triggers: only route when ALL items in the order are verified
        if 'verified' in reason.lower():
            pending = order.items.filter(
                result__isnull=True
            ).count() + order.items.filter(
                result__is_verified=False
            ).count()
            if pending > 0:
                return  # Still waiting for other items

        route_back_to_doctor(
            visit,
            reason=reason,
        )
    except Exception:
        logger.exception('laboratory.signals: error for order %s', getattr(order, 'pk', '?'))
