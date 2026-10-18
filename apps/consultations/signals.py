"""
Consultation post-save signals.

1. Auto-creates a follow-up appointment when the doctor sets follow_up_date.
2. (ipd) Auto-schedules standard post-op follow-up series when a SurgicalBooking
   is marked COMPLETED.
"""
import datetime
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger('apps.consultations')


# ── Post-op follow-up protocols by procedure type ─────────────────────────────
# Keys match SurgeryType values from apps.ipd.models
# Values: list of (days_after_surgery, label) tuples
POSTOP_PROTOCOLS = {
    'PHACO':          [(1, 'Day 1 Post-op'), (7, 'Week 1 Post-op'), (30, 'Month 1 Post-op'), (90, 'Month 3 Post-op')],
    'ECCE':           [(1, 'Day 1 Post-op'), (7, 'Week 1 Post-op'), (30, 'Month 1 Post-op'), (90, 'Month 3 Post-op')],
    'ICCE':           [(1, 'Day 1 Post-op'), (7, 'Week 1 Post-op'), (30, 'Month 1 Post-op'), (90, 'Month 3 Post-op')],
    'SICS':           [(1, 'Day 1 Post-op'), (7, 'Week 1 Post-op'), (30, 'Month 1 Post-op'), (90, 'Month 3 Post-op')],
    'IOL_EXCHANGE':   [(1, 'Day 1 Post-op'), (14, 'Week 2 Post-op'), (30, 'Month 1 Post-op')],
    'TRABECULECTOMY': [(1, 'Day 1 Post-op'), (3, 'Day 3 Post-op'), (7, 'Week 1 Post-op'), (14, 'Week 2'), (30, 'Month 1'), (90, 'Month 3 — IOP check')],
    'TUBE_SHUNT':     [(1, 'Day 1 Post-op'), (7, 'Week 1'), (30, 'Month 1'), (90, 'Month 3 — tube check')],
    'CYCLOPHOTOCOAG': [(1, 'Day 1'), (7, 'Week 1 — IOP check'), (30, 'Month 1 — IOP check')],
    'VITRECTOMY':     [(1, 'Day 1 Post-op'), (7, 'Week 1'), (30, 'Month 1'), (90, 'Month 3 — fundus check')],
    'BUCKLE':         [(1, 'Day 1'), (7, 'Week 1'), (30, 'Month 1 — fundus check')],
    'ANTI_VEGF':      [(7, 'Week 1 — Vision check'), (28, 'Month 1 — re-assessment for next injection')],
    'PKP':            [(1, 'Day 1'), (7, 'Week 1'), (30, 'Month 1'), (90, 'Month 3'), (180, 'Month 6 — suture check')],
    'DSAEK':          [(1, 'Day 1'), (7, 'Week 1'), (30, 'Month 1'), (90, 'Month 3 — endothelial count')],
    'PTERYGIUM_EXC':  [(1, 'Day 1'), (7, 'Week 1'), (30, 'Month 1')],
    'KERATOCONUS':    [(7, 'Week 1 — CXL check'), (30, 'Month 1'), (90, 'Month 3 — topo repeat')],
    'PTOSIS_REPAIR':  [(1, 'Day 1'), (7, 'Week 1'), (30, 'Month 1')],
    'DCR':            [(1, 'Day 1'), (7, 'Week 1 — syringe'), (30, 'Month 1 — syringe')],
    'ENUCLEATION':    [(1, 'Day 1'), (7, 'Week 1'), (30, 'Month 1 — socket check')],
    'STRABISMUS':     [(1, 'Day 1'), (7, 'Week 1'), (30, 'Month 1 — motility'), (90, 'Month 3 — alignment')],
    'CHALAZION_EXC':  [(7, 'Week 1')],
    'OTHER':          [(1, 'Day 1 Post-op'), (7, 'Week 1 Post-op'), (30, 'Month 1 Post-op')],
}
DEFAULT_PROTOCOL = [(1, 'Day 1 Post-op'), (7, 'Week 1 Post-op'), (30, 'Month 1 Post-op')]


@receiver(post_save, sender='consultations.Consultation')
def auto_create_follow_up_appointment(sender, instance, created, **kwargs):
    """
    When a Consultation is saved with a follow_up_date, create (or update)
    a FOLLOW_UP Appointment record automatically.
    """
    if not instance.follow_up_date:
        return

    try:
        from apps.appointments.models import Appointment

        reason = instance.follow_up_instructions or 'Follow-up consultation'

        existing = Appointment.objects.filter(
            patient=instance.patient,
            appointment_type=Appointment.AppointmentType.FOLLOW_UP,
            doctor=instance.consulting_doctor,
            department=instance.department,
            notes__contains=str(instance.pk),
        ).first()

        if existing:
            if existing.appointment_date != instance.follow_up_date:
                existing.appointment_date = instance.follow_up_date
                existing.reason = reason
                existing.save(update_fields=['appointment_date', 'reason'])
        else:
            service_tier = 'STANDARD'
            try:
                service_tier = instance.visit.service_tier or 'STANDARD'
            except Exception:
                pass

            Appointment.objects.create(
                patient=instance.patient,
                department=instance.department,
                doctor=instance.consulting_doctor,
                appointment_date=instance.follow_up_date,
                appointment_time=datetime.time(8, 0),
                appointment_type=Appointment.AppointmentType.FOLLOW_UP,
                service_tier=service_tier,
                reason=reason,
                booked_by=instance.consulting_doctor,
                notes=f'Auto-created from consultation {instance.pk}',
            )

    except Exception as e:
        logger.warning('auto_create_follow_up_appointment failed: %s', e)


@receiver(post_save, sender='ipd.SurgicalBooking')
def auto_schedule_postop_followups(sender, instance, **kwargs):
    """
    When a SurgicalBooking is marked COMPLETED, auto-schedule the standard
    post-operative follow-up series based on the procedure type.
    Only runs once — checks for existing post-op appointments first.
    """
    if instance.status != 'COMPLETED':
        return
    if not instance.surgery_date:
        return

    try:
        from apps.appointments.models import Appointment

        surgery_dt = instance.surgery_date
        surgery_day = surgery_dt.date() if hasattr(surgery_dt, 'date') else surgery_dt

        # Check if post-op appointments already exist for this booking
        marker = f'postop-{instance.id}'
        if Appointment.objects.filter(notes__contains=marker).exists():
            return

        protocol = POSTOP_PROTOCOLS.get(instance.procedure, DEFAULT_PROTOCOL)

        # Get the department from the linked consultation
        department = None
        try:
            if instance.consultation:
                department = instance.consultation.department
        except Exception:
            pass

        service_tier = 'STANDARD'
        try:
            if instance.consultation and instance.consultation.visit:
                service_tier = instance.consultation.visit.service_tier or 'STANDARD'
        except Exception:
            pass

        for days_after, label in protocol:
            appt_date = surgery_day + datetime.timedelta(days=days_after)
            Appointment.objects.create(
                patient=instance.patient,
                department=department,
                doctor=instance.surgeon,
                appointment_date=appt_date,
                appointment_time=datetime.time(8, 0),
                appointment_type=Appointment.AppointmentType.REVIEW,
                service_tier=service_tier,
                reason=f'{label} — {instance.get_procedure_display()}',
                booked_by=instance.surgeon or instance.admission_officer,
                notes=f'Auto post-op: {marker}',
            )

        logger.info('Post-op follow-ups scheduled for booking %s (%d appointments)', instance.booking_number, len(protocol))

    except Exception as e:
        logger.warning('auto_schedule_postop_followups failed: %s', e)


@receiver(post_save, sender='consultations.SurgicalRequest')
def create_counselling_qms_token(sender, instance, created, **kwargs):
    """
    When a SurgicalRequest is created (or set to SENT_FOR_COUNSELING),
    auto-issue a QMS token for the COUNSEL queue so the counselling nurse
    sees the patient in the QMS system.
    """
    SC = instance.StatusChoice.SENT_FOR_COUNSELING
    if instance.status != SC:
        return

    try:
        from apps.qms.models import QueueToken, ServiceType

        # Avoid duplicate tokens for the same request
        existing = QueueToken.objects.filter(
            patient=instance.patient,
            service_type=ServiceType.COUNSEL,
            status__in=['WAITING', 'CALLING'],
        ).filter(notes__icontains=str(instance.pk)).first()

        if existing:
            return

        QueueToken.objects.create(
            patient=instance.patient,
            service_type=ServiceType.COUNSEL,
            service_tier=getattr(instance, '_service_tier', 'STANDARD'),
            notes=f'Surgical counselling required — request {instance.pk}',
        )
        logger.info('Counselling QMS token created for SurgicalRequest %s', instance.pk)
    except Exception as e:
        logger.warning('create_counselling_qms_token failed: %s', e)
