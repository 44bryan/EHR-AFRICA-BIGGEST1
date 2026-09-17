"""
Patient Tracker Board — data builder and broadcast utilities.

Used by both the HTTP view (initial render) and the WebSocket push.
"""
from django.utils import timezone


def build_tracker_rows():
    """
    Build a list of tracker row dicts for all active patients today.
    Returns (rows, token_count) where each row is a plain dict with
    serialisable values suitable for JSON or template rendering.
    """
    from apps.qms.models import QueueToken, TokenStatus
    from apps.patients.models import Visit, VisitStatus as VS

    today = timezone.localdate()
    now = timezone.now()

    # ── 1. QueueToken-based rows ──────────────────────────────────────────
    all_tokens = list(
        QueueToken.objects
        .filter(token_date=today)
        .exclude(status__in=[TokenStatus.CANCELLED, TokenStatus.NO_SHOW])
        .exclude(visit__isnull=True)
        .select_related(
            'patient', 'visit', 'visit__department',
            'visit__consultation_room',
            'visit__consultation_room__assigned_doctor',
            'visit__attending_doctor',
            'visit__referring_doctor',
            'counter', 'counter__staff_assigned',
            'assigned_doctor',
        )
        .order_by('-issued_at')
    )

    # Deduplicate: keep only the latest token per visit
    seen_visits = set()
    tokens = []
    for t in all_tokens:
        if t.visit_id not in seen_visits:
            seen_visits.add(t.visit_id)
            tokens.append(t)

    STATION_MAP = {
        'RECEPTIONIST': 'Reception',
        'CASHIER': 'Cashier',
        'PARAMETERS': 'Triage',
        'PARAMS_VIP': 'VIP Triage',
        'GENERAL': 'Gen Oph Consultation',
        'RETINA': 'Retina Clinic',
        'GLAUCOMA': 'Glaucoma Clinic',
        'CATARACT': 'Cataract / Surgical',
        'PEDIATRIC': 'Pediatric Oph',
        'CORNEA': 'Cornea Clinic',
        'OCULOPLASTY': 'Oculoplasty',
        'NEURO': 'Neuro-Ophthalmology',
        'UVEITIS': 'Uveitis Clinic',
        'LOW_VISION': 'Low Vision',
        'REFRACTION': 'Refraction',
        'VIP_CONSULT': 'VIP Consultation',
        'EXP_CONSULT': 'Express Consultation',
        'INSUR_CONSULT': 'Insurance Consultation',
        'INVESTIGATION': 'Investigation',
        'PHARMACY': 'Pharmacy',
        'OPTICAL': 'Optical Shop',
        'LAB': 'Laboratory',
        'GEN_PHYS': 'General Physician',
    }

    rows = []

    for t in tokens:
        patient = t.patient
        visit = t.visit
        if not patient or not visit:
            continue

        station = STATION_MAP.get(t.service_type, t.get_service_type_display())
        if t.counter:
            station += f' ({t.counter.name})'

        staff = (
            t.assigned_doctor
            or (t.counter.staff_assigned if t.counter else None)
            or (visit.consultation_room.assigned_doctor
                if visit.consultation_room else None)
            or visit.attending_doctor
        )

        ref_time = t.called_at or t.served_at or t.issued_at
        minutes = int((now - ref_time).total_seconds() / 60) if ref_time else 0

        room = None
        if visit.consultation_room:
            room = (visit.consultation_room.label
                    or f'Room {visit.consultation_room.room_number}')

        referring_doc = (visit.referring_doctor
                         if visit.referring_doctor_id else None)

        dept = ''
        if visit.department:
            dept = visit.department.name
        elif t.service_type:
            dept = STATION_MAP.get(t.service_type, t.service_type)

        rows.append({
            'patient': patient,
            'visit': visit,
            'token': t,
            'station': station,
            'room': room,
            'staff': staff,
            'referring_doctor': referring_doc,
            'status': t.get_status_display(),
            'status_key': t.status,
            'minutes': minutes,
            'hours': minutes // 60,
            'mins_remainder': minutes % 60,
            'tier': visit.service_tier,
            'department': dept,
            # Timeline data
            'arrived_at': visit.visit_date,
            'triage_at': t.served_at if t.service_type == 'PARAMETERS' else None,
            'issued_at': t.issued_at,
            'called_at': t.called_at,
            'served_at': t.served_at,
            'completed_at': t.completed_at,
        })

    # ── 2. Visits without tokens ──────────────────────────────────────────
    no_token_visits = (
        Visit.objects
        .filter(visit_date__date=today, is_deleted=False)
        .exclude(status=VS.DISCHARGED)
        .exclude(pk__in=seen_visits)
        .select_related(
            'patient', 'department', 'attending_doctor',
            'triage_nurse', 'consultation_room',
            'consultation_room__assigned_doctor',
            'referring_doctor',
        )
        .order_by('-visit_date')
    )

    for v in no_token_visits:
        station = v.get_status_display()
        staff = v.attending_doctor or v.triage_nurse
        room = None
        if v.consultation_room:
            room = (v.consultation_room.label
                    or f'Room {v.consultation_room.room_number}')
        minutes = int((now - v.visit_date).total_seconds() / 60)
        referring_doc = v.referring_doctor if v.referring_doctor_id else None

        dept = ''
        if v.department:
            dept = v.department.name

        rows.append({
            'patient': v.patient,
            'visit': v,
            'token': None,
            'station': station,
            'room': room,
            'staff': staff,
            'referring_doctor': referring_doc,
            'status': v.get_status_display(),
            'status_key': v.status,
            'minutes': minutes,
            'hours': minutes // 60,
            'mins_remainder': minutes % 60,
            'tier': v.service_tier,
            'department': dept,
            'arrived_at': v.visit_date,
            'triage_at': None,
            'issued_at': None,
            'called_at': None,
            'served_at': None,
            'completed_at': None,
        })

    return rows


def rows_to_json(rows):
    """Serialise tracker rows to JSON-safe dicts for WebSocket push."""
    def _ts(dt):
        return dt.strftime('%H:%M') if dt else None

    def _staff(u):
        if not u:
            return None
        return {
            'pk': str(u.pk),
            'name': u.get_full_name(),
            'role': u.get_role_display() if hasattr(u, 'get_role_display') else '',
        }

    out = []
    for r in rows:
        p = r['patient']
        out.append({
            'id': str(r['visit'].pk),
            'patient_name': p.get_full_name() if hasattr(p, 'get_full_name') else str(p),
            'patient_id': p.patient_id if hasattr(p, 'patient_id') else '',
            'station': r['station'],
            'room': r['room'] or '',
            'staff': _staff(r['staff']),
            'referring_doctor': _staff(r['referring_doctor']),
            'status': r['status'],
            'status_key': r['status_key'],
            'minutes': r['minutes'],
            'tier': r['tier'] or 'STANDARD',
            'department': r['department'],
            'token_number': r['token'].token_number if r['token'] else '',
            # Timeline
            'arrived_at': _ts(r['arrived_at']),
            'issued_at': _ts(r['issued_at']),
            'called_at': _ts(r['called_at']),
            'served_at': _ts(r['served_at']),
            'completed_at': _ts(r['completed_at']),
        })
    return out


def notify_tracker():
    """Broadcast a refresh signal to all tracker WebSocket clients."""
    from apps.core.ws_notify import notify_queue
    notify_queue('tracker')
