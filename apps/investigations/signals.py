"""
Auto-routing signals for Investigations.

Triggers:
  InvestigationResult saved with is_verified=True  → route patient back to doctor
  InvestigationOrder.status → COMPLETED            → same (fallback when no verify step)
"""
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger('ehr.auto_routing')


@receiver(post_save, sender='investigations.InvestigationResult')
def on_result_verified(sender, instance, **kwargs):
    """When a result is verified, route the patient back to their doctor."""
    if not instance.is_verified:
        return
    _auto_route_from_order(instance.order, 'Investigation result verified')


@receiver(post_save, sender='investigations.InvestigationOrder')
def on_order_completed(sender, instance, **kwargs):
    """Fallback: when an order is marked COMPLETED, route back to doctor."""
    if instance.status != 'COMPLETED':
        return
    _auto_route_from_order(instance, 'Investigation completed')


def _auto_route_from_order(order, reason):
    try:
        from apps.consultations.auto_routing import route_back_to_doctor

        consultation = order.consultation
        visit = getattr(consultation, 'visit', None)
        if not visit:
            return

        # Only route back when patient is currently AT investigations
        if visit.status != 'INVESTIGATION':
            return

        route_back_to_doctor(
            visit,
            reason=f'{reason}: {order.investigation_type.name}',
        )
    except Exception:
        logger.exception('investigations.signals: error for order %s', getattr(order, 'pk', '?'))
