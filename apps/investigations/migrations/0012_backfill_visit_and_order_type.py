"""
Data migration: backfill visit FK and order_type on existing InvestigationOrder rows.
- visit: set from consultation.visit_id when consultation exists
- order_type: set to CLINICAL_EXAM for REFRACTION/LOW_VISION/ORTHOPTICS categories
"""
from django.db import migrations


def backfill_visit_and_order_type(apps, schema_editor):
    InvestigationOrder = apps.get_model('investigations', 'InvestigationOrder')
    _CLINICAL_CATS = {'REFRACTION', 'LOW_VISION', 'ORTHOPTICS'}

    # Batch in chunks of 500
    qs = InvestigationOrder.objects.select_related(
        'consultation', 'investigation_type',
    ).filter(is_deleted=False)

    batch = []
    for order in qs.iterator(chunk_size=500):
        changed = False

        # Backfill visit from consultation
        if not order.visit_id and order.consultation_id:
            try:
                order.visit_id = order.consultation.visit_id
                changed = True
            except Exception:
                pass

        # Backfill order_type from investigation category
        try:
            cat = order.investigation_type.category
            expected = 'CLINICAL_EXAM' if cat in _CLINICAL_CATS else 'INVESTIGATION'
            if order.order_type != expected:
                order.order_type = expected
                changed = True
        except Exception:
            pass

        if changed:
            batch.append(order)

        if len(batch) >= 500:
            InvestigationOrder.objects.bulk_update(batch, ['visit_id', 'order_type'])
            batch = []

    if batch:
        InvestigationOrder.objects.bulk_update(batch, ['visit_id', 'order_type'])


def backfill_record_type(apps, schema_editor):
    """Backfill record_type on existing Consultation rows."""
    Consultation = apps.get_model('consultations', 'Consultation')
    _EXAM_DEPTS = {'REFRAC', 'PEDS_REFRAC', 'LOW_VIS', 'ORTHO'}

    batch = []
    qs = Consultation.objects.select_related('department').filter(is_deleted=False)
    for c in qs.iterator(chunk_size=500):
        try:
            code = c.department.code if c.department_id else ''
            expected = 'CLINICAL_EXAM' if code in _EXAM_DEPTS else 'CONSULTATION'
            if c.record_type != expected:
                c.record_type = expected
                batch.append(c)
        except Exception:
            pass

        if len(batch) >= 500:
            Consultation.objects.bulk_update(batch, ['record_type'])
            batch = []

    if batch:
        Consultation.objects.bulk_update(batch, ['record_type'])


class Migration(migrations.Migration):

    dependencies = [
        ('investigations', '0011_investigationorder_order_type_and_more'),
        ('consultations', '0012_consultation_record_type_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_visit_and_order_type, migrations.RunPython.noop),
        migrations.RunPython(backfill_record_type, migrations.RunPython.noop),
    ]
