"""
Data migration: merge FAST_TRACK tier into EXPRESS everywhere.
"""
from django.db import migrations


def merge_fast_track(apps, schema_editor):
    """Convert all FAST_TRACK records to EXPRESS."""
    Visit = apps.get_model('patients', 'Visit')
    updated = Visit.objects.filter(service_tier='FAST_TRACK').update(service_tier='EXPRESS')
    if updated:
        print(f'  Visits: {updated} FAST_TRACK → EXPRESS')

    VisitTierChange = apps.get_model('patients', 'VisitTierChange')
    VisitTierChange.objects.filter(old_tier='FAST_TRACK').update(old_tier='EXPRESS')
    VisitTierChange.objects.filter(new_tier='FAST_TRACK').update(new_tier='EXPRESS')

    User = apps.get_model('accounts', 'User')
    u1 = User.objects.filter(consultation_unit='FAST_TRACK').update(consultation_unit='EXPRESS')
    u2 = User.objects.filter(patient_tier='FAST_TRACK').update(patient_tier='EXPRESS')
    if u1 or u2:
        print(f'  Users: {u1} consultation_unit, {u2} patient_tier → EXPRESS')

    QueueToken = apps.get_model('qms', 'QueueToken')
    qt = QueueToken.objects.filter(service_tier='FAST_TRACK').update(service_tier='EXPRESS')
    if qt:
        print(f'  QueueTokens: {qt} FAST_TRACK → EXPRESS')

    TierZoneMapping = apps.get_model('qms', 'TierZoneMapping')
    TierZoneMapping.objects.filter(tier='FAST_TRACK').delete()

    Appointment = apps.get_model('appointments', 'Appointment')
    ap = Appointment.objects.filter(service_tier='FAST_TRACK').update(service_tier='EXPRESS')
    if ap:
        print(f'  Appointments: {ap} FAST_TRACK → EXPRESS')

    # ConsultationRoom
    try:
        ConsultationRoom = apps.get_model('departments', 'ConsultationRoom')
        cr = ConsultationRoom.objects.filter(room_tier='FAST_TRACK').update(room_tier='EXPRESS')
        if cr:
            print(f'  ConsultationRooms: {cr} FAST_TRACK → EXPRESS')
    except Exception:
        pass

    # ServiceCounter serves_tiers field (comma-separated)
    try:
        ServiceCounter = apps.get_model('qms', 'ServiceCounter')
        for sc in ServiceCounter.objects.filter(serves_tiers__contains='FAST_TRACK'):
            tiers = [t.strip() for t in sc.serves_tiers.split(',')]
            new_tiers = []
            for t in tiers:
                if t == 'FAST_TRACK':
                    if 'EXPRESS' not in new_tiers:
                        new_tiers.append('EXPRESS')
                else:
                    new_tiers.append(t)
            sc.serves_tiers = ','.join(new_tiers)
            sc.save(update_fields=['serves_tiers'])
    except Exception:
        pass


class Migration(migrations.Migration):
    dependencies = [
        ('patients', '0040_patient_phone_number_2'),
        ('accounts', '0038_remove_hospitalconfig_module_telemedicine_and_more'),
        ('qms', '0016_alter_queuetoken_origin_zone_alter_queuetoken_zone_and_more'),
        ('appointments', '0003_appointment_service_tier'),
        ('departments', '0009_visit_stop_and_paused_status'),
    ]

    operations = [
        migrations.RunPython(merge_fast_track, migrations.RunPython.noop),
    ]
