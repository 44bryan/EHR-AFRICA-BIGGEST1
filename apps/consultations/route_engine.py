"""
Smart Route Engine — reads consultation orders and returns hint data.

Returns which destinations to highlight and a one-line hint text.
Advisory only — never blocks or enforces. The doctor can ignore hints
and pick any destination manually.
"""
import logging

logger = logging.getLogger(__name__)


def suggest_hints(consultation):
    """
    Analyze a consultation's orders/prescriptions and return routing hints.

    Returns dict:
        {
            'highlight': ['PHARMACY', 'OPTICAL'],   # destination codes to glow
            'hint_text': 'Patient has: drug prescription, spectacle Rx',
            'reasons': {
                'PHARMACY': 'Drug prescription written',
                'OPTICAL': 'Spectacle prescription written',
            }
        }

    If consultation is None or has no orders, returns empty hints.
    """
    if not consultation:
        return {'highlight': [], 'hint_text': '', 'reasons': {}}

    highlight = []
    reasons = {}
    parts = []  # for hint_text

    try:
        # ── Drug prescriptions → Pharmacy ──
        has_drug_rx = consultation.drug_prescriptions.filter(
            is_dispensed=False, is_deleted=False
        ).exists()
        if has_drug_rx:
            highlight.append('PHARMACY')
            reasons['PHARMACY'] = 'Drug prescription'
            parts.append('drug prescription')
    except Exception:
        pass

    try:
        # ── Optical prescriptions → Optical Shop or Contact Lens ──
        optical_rxs = consultation.optical_prescriptions.filter(
            is_deleted=False
        )
        for rx in optical_rxs:
            if rx.prescription_type == 'CONTACT_LENS':
                if 'CONTACT_LENS' not in highlight:
                    highlight.append('CONTACT_LENS')
                    reasons['CONTACT_LENS'] = 'Contact lens Rx'
                    parts.append('contact lens Rx')
            else:
                if 'OPTICAL' not in highlight:
                    highlight.append('OPTICAL')
                    reasons['OPTICAL'] = 'Spectacle Rx'
                    parts.append('spectacle Rx')
    except Exception:
        pass

    try:
        # ── Investigation orders → Lab or Imaging ──
        pending_orders = consultation.investigation_orders.filter(
            status='ORDERED', is_deleted=False
        ).select_related('investigation_type')

        has_lab = False
        has_imaging = False
        for order in pending_orders:
            cat = getattr(order.investigation_type, 'category', '')
            # Lab-type categories (typically sent to external lab)
            if cat in ('EXTERNAL',):
                has_lab = True
            else:
                # All ophthalmic investigations go to the investigation room
                has_imaging = True

        if has_lab:
            highlight.append('LAB')
            reasons['LAB'] = 'Lab tests ordered'
            parts.append('lab tests')
        if has_imaging:
            highlight.append('IMAGING')
            reasons['IMAGING'] = 'Investigations ordered'
            parts.append('investigations')
    except Exception:
        pass

    # Build hint text
    hint_text = ''
    if parts:
        hint_text = 'Patient has: ' + ', '.join(parts)

    return {
        'highlight': highlight,
        'hint_text': hint_text,
        'reasons': reasons,
    }
