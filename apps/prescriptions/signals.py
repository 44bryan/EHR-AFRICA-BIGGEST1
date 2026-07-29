"""
Auto-routing signals for Prescriptions.

Triggers:
  DrugPrescription.is_dispensed → True   → route patient back to doctor
  OpticalPrescription.is_dispensed → True → route patient back to doctor
"""
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger('ehr.auto_routing')


@receiver(post_save, sender='prescriptions.DrugPrescription')
def on_drug_dispensed(sender, instance, **kwargs):
    """When drugs are dispensed, route the patient back to their doctor."""
    if not instance.is_dispensed:
        return
    _auto_route_from_prescription(instance, expected_status='PHARMACY',
                                  reason='Drugs dispensed by pharmacy')


@receiver(post_save, sender='prescriptions.OpticalPrescription')
def on_optical_dispensed(sender, instance, **kwargs):
    """When glasses/optical are dispensed, route the patient back."""
    if not instance.is_dispensed:
        return
    _auto_route_from_prescription(instance, expected_status='OPTICAL',
                                  reason='Optical prescription dispensed')


def _auto_route_from_prescription(prescription, expected_status, reason):
    try:
        from apps.consultations.auto_routing import route_back_to_doctor

        consultation = prescription.consultation
        visit = getattr(consultation, 'visit', None)
        if not visit:
            return

        # Only route back when patient is currently at this service
        if visit.status != expected_status:
            return

        route_back_to_doctor(visit, reason=reason)
    except Exception:
        logger.exception(
            'prescriptions.signals: error for prescription %s',
            getattr(prescription, 'pk', '?'),
        )
