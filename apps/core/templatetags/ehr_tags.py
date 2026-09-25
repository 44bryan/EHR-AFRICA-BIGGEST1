from django import template

register = template.Library()


@register.filter
def user_display(user, fallback='Unknown'):
    """
    Safe display name for a User FK that may be None.
    Usage: {{ obj.some_user_fk|user_display }}
           {{ obj.some_user_fk|user_display:"Unassigned" }}
    """
    if user is None:
        return fallback
    try:
        name = user.get_full_name()
        if name and name.strip():
            return name.strip()
    except Exception:
        pass
    try:
        return user.username or fallback
    except Exception:
        return fallback


@register.filter
def split(value, sep=','):
    """Split a string by a separator. Usage: "a,b,c"|split:"," """
    if value is None:
        return []
    return str(value).split(sep)


@register.filter
def get_item(dictionary, key):
    """Look up a key in a dict. Usage: mydict|get_item:"some_key" """
    if not isinstance(dictionary, dict):
        return ''
    return dictionary.get(str(key), '')


@register.filter
def dict_first(dictionary, keys):
    """Return first truthy value for comma-separated keys.
    Usage: {{ rd|dict_first:"sub_sph_dist_od,sph_od"|default:"—" }}
    Safe alternative to {% firstof %} which crashes on missing dict keys."""
    if not isinstance(dictionary, dict):
        return None
    for key in keys.split(','):
        val = dictionary.get(key.strip())
        if val:
            return val
    return None


@register.filter
def merge_dict(d1, d2):
    """
    Merge two dicts safely, d1 values have priority over d2.
    Usage: rd|merge_dict:d  → rd's keys override d's keys.
    Safe filter argument — never raises VariableDoesNotExist.
    """
    if not isinstance(d1, dict):
        d1 = {}
    if not isinstance(d2, dict):
        d2 = {}
    return {**d2, **d1}


@register.filter
def getattribute(obj, attr):
    """Get an attribute from an object by name. Usage: object|getattribute:"field_name" """
    return getattr(obj, str(attr), 'NT')


@register.filter
def absval(value):
    """Return absolute value. Usage: {{ negative_number|absval }}"""
    try:
        v = float(value)
        return int(v) if v >= 0 else int(-v)
    except (ValueError, TypeError):
        return value


@register.filter
def mul(value, arg):
    """Multiply. Usage: {{ qty|mul:unit_cost }}"""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def dictfirst(dictionary, keys_str):
    """
    Return the first non-empty value from a dict for any of the comma-separated keys.
    Safe to use as a filter argument — never raises VariableDoesNotExist.
    Usage: dd|dictfirst:"key1,key2,key3"
    """
    if not isinstance(dictionary, dict):
        return ''
    for key in keys_str.split(','):
        val = dictionary.get(key.strip())
        if val is not None and val != '':
            return val
    return ''


# ── Abnormal vital-sign highlighting ──────────────────────────────────────────
# Returns CSS class string for abnormal vitals.
# Usage: {{ value|vital_css:"iop" }}  → "text-danger fw-bold" when IOP > 21

_VITAL_RANGES = {
    # (low_warn, high_warn)  — values outside this range get highlighted
    'iop':         (10, 21),
    'bp_sys':      (90, 140),
    'bp_dia':      (60, 90),
    'pulse':       (60, 100),
    'temperature': (35.0, 38.0),
    'spo2':        (90, 100),
    'rr':          (12, 20),
}


@register.filter
def vital_css(value, vital_type):
    """
    Return danger/warning CSS classes when a vital sign is outside normal range.
    Usage: {{ iop_value|vital_css:"iop" }}
    Returns: "text-danger fw-bold" for abnormal, "" for normal/unparseable.
    """
    if value is None or value == '' or value == 'N/R':
        return ''
    try:
        num = float(value)
    except (ValueError, TypeError):
        return ''
    bounds = _VITAL_RANGES.get(vital_type)
    if not bounds:
        return ''
    lo, hi = bounds
    if num < lo or num > hi:
        return 'text-danger fw-bold'
    return ''


@register.filter
def bp_css(value):
    """
    Colour-code a blood pressure string like "140/90".
    Returns "text-danger fw-bold" if systolic ≥ 140, diastolic ≥ 90,
    systolic < 90, or diastolic < 60.
    """
    if not value or '/' not in str(value):
        return ''
    try:
        parts = str(value).split('/')
        sys_val = float(parts[0])
        dia_val = float(parts[1])
    except (ValueError, IndexError):
        return ''
    if sys_val >= 140 or sys_val < 90 or dia_val >= 90 or dia_val < 60:
        return 'text-danger fw-bold'
    return ''


# ── Drug administration time slots (hospital practice: base hour 06:00) ───────
_FREQ_TIME_SLOTS = {
    'OD':           '06:00',
    'BD':           '06:00, 18:00',
    'TDS':          '06:00, 12:00, 18:00',
    'QID':          '06:00, 12:00, 18:00, 00:00',
    '5x daily':     '06:00, 10:00, 14:00, 18:00, 22:00',
    'Q2H':          '06:00, 08:00, 10:00, 12:00, 14:00, 16:00, 18:00, 20:00',
    'Q3H':          '06:00, 09:00, 12:00, 15:00, 18:00, 21:00',
    'Q4H':          '06:00, 10:00, 14:00, 18:00, 22:00, 02:00',
    'Q6H':          '06:00, 12:00, 18:00, 00:00',
    'Q8H':          '06:00, 14:00, 22:00',
    'Q12H':         '06:00, 18:00',
    'Nocte':        '22:00 (bedtime)',
    'Mane':         '06:00 (morning)',
    'STAT':         'Immediately (once)',
    'PRN':          'As needed',
    'Weekly':       'Same day each week',
    'Twice weekly': 'e.g. Mon & Thu',
    'Monthly':      'Same date each month',
    'As directed':  'Per doctor instructions',
}


@register.filter
def time_slots(frequency):
    """
    Return standard administration time slots for a drug frequency code.
    Usage: {{ rx_item.frequency|time_slots }}
    """
    if not frequency:
        return ''
    return _FREQ_TIME_SLOTS.get(str(frequency).strip(), '')


@register.filter
def va_css(value):
    """
    Colour-code a Snellen visual acuity like "6/18" or "6/60".
    Returns "text-danger fw-bold" if worse than 6/18 (i.e. denominator > 18),
    or for non-numeric values like CF, HM, LP, NLP.
    Handles common clinical variants: "CF 2m", "HM+", "NPL", "6/60p", etc.
    """
    import re as _re
    if not value or value == 'N/R':
        return ''
    s = str(value).strip().upper()
    # Non-numeric acuities — always abnormal
    # Match exact or with suffixes: "CF", "CF 2M", "CF AT 1M", "HM+", "NPL", etc.
    if _re.match(r'^(CF|HM|LP|NLP|NPL|PL|NO\s*PL)\b', s):
        return 'text-danger fw-bold'
    if '/' not in s:
        return ''
    try:
        parts = s.split('/')
        # Strip non-numeric suffixes from denominator: "60p" → "60", "18-2" → "18"
        denom_str = _re.match(r'(\d+(?:\.\d+)?)', parts[1].strip())
        if not denom_str:
            return ''
        denom = float(denom_str.group(1))
    except (ValueError, IndexError):
        return ''
    if denom > 18:
        return 'text-danger fw-bold'
    return ''


@register.filter
def time_ampm(value):
    """
    Convert a 24-hour time string like "14:30" to "2:30 PM".
    Accepts HH:MM or HH:MM:SS strings. Returns the original value if unparseable.
    """
    if not value:
        return value
    s = str(value).strip()
    try:
        parts = s.split(':')
        h, m = int(parts[0]), int(parts[1])
        suffix = 'AM' if h < 12 else 'PM'
        h12 = h % 12 or 12
        return f'{h12}:{m:02d} {suffix}'
    except (ValueError, IndexError):
        return s
