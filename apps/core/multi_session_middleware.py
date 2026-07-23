"""
Multi-Session Middleware
========================
Allows up to 9 simultaneous logins in the same browser by isolating each
browser tab into its own session slot via the ``?s=N`` URL parameter (N = 1-9).

Slot 1 (default) = standard ``sessionid`` cookie.
Slots 2-9        = ``sessionid_2`` … ``sessionid_9`` cookies.

The CSRF cookie (``csrftoken``) is ALSO isolated per slot:
  Slot 1: ``csrftoken``   (standard)
  Slots 2-9: ``csrftoken_2`` … ``csrftoken_9``

This prevents cross-slot CSRF token rotation (Django calls rotate_token() on
login) from invalidating forms open in other tabs — which would cause silent
403 errors inside HTMX boost, making pages appear frozen.

Place BEFORE ``django.contrib.sessions.middleware.SessionMiddleware`` in MIDDLEWARE.

Slot resolution order (first match wins):
  1. ``?s=N``              — URL query string
  2. ``X-Session-Slot: N`` — AJAX header (sent by HTMX via htmx:configRequest)
  3. POST body ``s=N``     — hidden input in non-AJAX forms
  4. ``?next=…?s=N``       — slot embedded in login redirect next param
  5. Default: slot 1

How it works
------------
Request phase:
  - Saves the current ``sessionid`` value (slot-1's session).
  - Replaces ``sessionid`` in ``request.COOKIES`` with ``sessionid_N`` so
    Django's SessionMiddleware loads the correct session transparently.

Response phase:
  - Copies the new/updated ``sessionid`` value to ``sessionid_N``.
  - Explicitly re-sets ``sessionid`` to the ORIGINAL slot-1 value so the
    browser never loses Tab 1's session (even if the middleware team removes
    the cookie incorrectly in some Django/browser combination).
  - For logout (cookie deletion), deletes only ``sessionid_N``.
  - Appends ``?s=N`` to any redirect Location so navigation stays in the slot.
"""

from django.conf import settings
from urllib.parse import urlparse, urlencode, parse_qs, urlunparse

VALID_SLOTS = frozenset(str(i) for i in range(1, 10))
REDIRECT_STATUSES = frozenset((301, 302, 303, 307, 308))


def _slot_cookie(slot):
    base = settings.SESSION_COOKIE_NAME   # default: 'sessionid'
    return base if slot == '1' else f'{base}_{slot}'


def _csrf_slot_cookie(slot):
    base = getattr(settings, 'CSRF_COOKIE_NAME', 'csrftoken')
    return base if slot == '1' else f'{base}_{slot}'


def _add_slot_to_url(url, slot):
    """Append ``?s=<slot>`` to a relative URL. External/absolute URLs unchanged."""
    if not url or slot == '1':
        return url
    try:
        parts = list(urlparse(url))
        if parts[0] or parts[1]:   # has scheme or netloc → skip
            return url
        qs = parse_qs(parts[4], keep_blank_values=True)
        qs['s'] = [slot]
        parts[4] = urlencode(qs, doseq=True)
        return urlunparse(parts)
    except Exception:
        return url


def _resolve_slot(request):
    """Return the session slot string '1'-'9' for this request."""
    # 1. URL query string
    slot = request.GET.get('s', '').strip()
    if slot in VALID_SLOTS:
        return slot

    # 2. AJAX header (sent by htmx:configRequest JS handler)
    slot = request.META.get('HTTP_X_SESSION_SLOT', '').strip()
    if slot in VALID_SLOTS:
        return slot

    # 3. POST body hidden input
    if request.method == 'POST':
        try:
            slot = request.POST.get('s', '').strip()
            if slot in VALID_SLOTS:
                return slot
        except Exception:
            pass

    # 4. Slot embedded in the login ?next= redirect param
    next_url = request.GET.get('next', '')
    if next_url and 's=' in next_url:
        try:
            candidate = parse_qs(urlparse(next_url).query).get('s', [''])[0]
            if candidate in VALID_SLOTS:
                return candidate
        except Exception:
            pass

    return '1'


def _parse_max_age(raw):
    """Convert a morsel max-age string to int or None. Returns 0 for deletion."""
    if not raw:
        return None
    try:
        return int(raw)
    except (ValueError, TypeError):
        return None


class MultiSessionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        slot = _resolve_slot(request)
        request.session_slot = slot

        base        = settings.SESSION_COOKIE_NAME
        slot_cookie = _slot_cookie(slot)
        csrf_base   = getattr(settings, 'CSRF_COOKIE_NAME', 'csrftoken')
        csrf_slot   = _csrf_slot_cookie(slot)

        # ── REQUEST PHASE ────────────────────────────────────────────────────
        # Remember slot-1 values so we can restore them in the response.
        original_slot1_value = None
        original_slot1_csrf  = None

        if slot != '1':
            original_slot1_value = request.COOKIES.get(base)
            original_slot1_csrf  = request.COOKIES.get(csrf_base)

            slot_val      = request.COOKIES.get(slot_cookie)
            slot_csrf_val = request.COOKIES.get(csrf_slot)

            # Use a fresh copy so we don't mutate a shared dict
            new_cookies = dict(request.COOKIES)

            # Swap session cookie: slot-N's sessionid → base sessionid
            if slot_val:
                new_cookies[base] = slot_val
            else:
                new_cookies.pop(base, None)

            # Swap CSRF cookie: slot-N's csrftoken_N → csrftoken
            # If slot-N has its own CSRF cookie, use it; otherwise leave
            # the shared csrftoken in place (first-visit bootstrap).
            if slot_csrf_val:
                new_cookies[csrf_base] = slot_csrf_val

            request.COOKIES = new_cookies

        response = self.get_response(request)

        # ── RESPONSE PHASE: session cookie ───────────────────────────────────
        if slot != '1' and base in response.cookies:
            morsel      = response.cookies[base]
            max_age     = _parse_max_age(morsel['max-age'])
            is_deletion = (max_age == 0 or morsel.value == '')

            ck = dict(
                path     = morsel['path']     or settings.SESSION_COOKIE_PATH,
                domain   = morsel['domain']   or settings.SESSION_COOKIE_DOMAIN,
                secure   = bool(morsel['secure']),
                httponly = bool(morsel['httponly']),
                samesite = morsel['samesite'] or getattr(settings, 'SESSION_COOKIE_SAMESITE', 'Lax'),
            )

            if is_deletion:
                # Slot-N user logged out: delete only the slot-N cookie.
                response.set_cookie(slot_cookie, '', max_age=0, **ck)
                del response.cookies[base]
            else:
                # Slot-N user logged in or session refreshed.
                response.set_cookie(slot_cookie, morsel.value, max_age=max_age, **ck)
                if original_slot1_value:
                    response.set_cookie(base, original_slot1_value, max_age=max_age, **ck)
                else:
                    del response.cookies[base]

        # ── RESPONSE PHASE: CSRF cookie isolation ─────────────────────────────
        # Django's CsrfViewMiddleware may set/rotate the csrftoken cookie.
        # Isolate it per slot so that slot-1 login (which calls rotate_token)
        # cannot invalidate CSRF tokens that are open in other slot tabs.
        if slot != '1' and csrf_base in response.cookies:
            csrf_morsel  = response.cookies[csrf_base]
            csrf_max_age = _parse_max_age(csrf_morsel['max-age'])
            csrf_is_del  = (csrf_max_age == 0 or csrf_morsel.value == '')

            csrf_ck = dict(
                path     = csrf_morsel['path']   or getattr(settings, 'CSRF_COOKIE_PATH', '/'),
                domain   = csrf_morsel['domain'] or getattr(settings, 'CSRF_COOKIE_DOMAIN', None),
                secure   = bool(csrf_morsel['secure']),
                httponly = bool(csrf_morsel['httponly']),
                samesite = csrf_morsel['samesite'] or getattr(settings, 'CSRF_COOKIE_SAMESITE', 'Lax'),
            )

            if csrf_is_del:
                # CSRF token deleted for slot-N (e.g. logout): delete slot-N cookie.
                response.set_cookie(csrf_slot, '', max_age=0, **csrf_ck)
                del response.cookies[csrf_base]
            else:
                # Write new/rotated CSRF value to slot-N specific cookie.
                response.set_cookie(csrf_slot, csrf_morsel.value, max_age=csrf_max_age, **csrf_ck)
                # Restore slot-1's csrftoken so Tab 1 is never affected.
                if original_slot1_csrf:
                    response.set_cookie(csrf_base, original_slot1_csrf, max_age=csrf_max_age, **csrf_ck)
                else:
                    del response.cookies[csrf_base]

        # ── REDIRECT: keep slot in Location header ───────────────────────────
        if slot != '1' and response.status_code in REDIRECT_STATUSES:
            location = response.get('Location', '')
            if location:
                response['Location'] = _add_slot_to_url(location, slot)

        return response
