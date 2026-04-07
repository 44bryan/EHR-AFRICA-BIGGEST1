"""
Security Middleware for GLUDD EHR — three layers:

1. AuditMiddleware     — Full audit trail: every authenticated action logged with
                          user, IP, method, path, patient context, response code.

2. RateLimitMiddleware — Protects AI endpoints from abuse. Limits per user per minute.
                          Prevents: API key exhaustion, DoS on voice/AI endpoints.

3. PromptInjectionGuard — Sanitizes text before it goes to Claude AI.
                           Prevents: prompt injection attacks via clinical text fields.
"""
import re
import time
import logging
from collections import defaultdict
from django.http import JsonResponse
from django.utils import timezone

audit_logger = logging.getLogger('ehr.audit')
security_logger = logging.getLogger('ehr.security')


# ── 1. Full Audit Trail ───────────────────────────────────────────────────────

class AuditMiddleware:
    """
    Logs every authenticated write action (POST/PUT/PATCH/DELETE) with:
    - WHO:  user ID, role, employee ID
    - WHAT: HTTP method + path
    - WHERE: client IP (proxy-aware)
    - WHEN: timestamp
    - RESULT: HTTP status code

    Patient-sensitive paths (containing /patients/, /consultations/) are
    flagged with CLINICAL tag for compliance tracking.
    """
    CLINICAL_PATHS = ['/patients/', '/consultations/', '/prescriptions/',
                      '/investigations/', '/laboratory/', '/pharmacy/', '/ipd/']

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if request.user.is_authenticated and request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            is_clinical = any(p in request.path for p in self.CLINICAL_PATHS)
            tag = 'CLINICAL' if is_clinical else 'ADMIN'
            uid = getattr(request.user, 'employee_id', None) or str(request.user.pk)
            role = getattr(request.user, 'role', 'unknown')

            audit_logger.info(
                '[%s] user=%s role=%s method=%s path=%s status=%s ip=%s ts=%s',
                tag, uid, role,
                request.method, request.path,
                response.status_code,
                _get_client_ip(request),
                timezone.now().isoformat(),
            )

        return response


# ── 2. Rate Limiting for AI Endpoints ────────────────────────────────────────

class RateLimitMiddleware:
    """
    Simple in-memory rate limiter for AI endpoints.
    Limits each authenticated user to MAX_REQUESTS per WINDOW_SECONDS.

    Protects against:
    - API key exhaustion (Anthropic costs money)
    - DoS on /ai-assistant/voice/ and /ai-assistant/suggest-diagnosis/
    - Scrapers hitting the analytics endpoint

    For production: replace with Redis-backed rate limiting (django-ratelimit).
    """
    AI_PATHS = ['/ai-assistant/voice/', '/ai-assistant/suggest-diagnosis/',
                '/ai-assistant/analytics/', '/ai-assistant/receptionist/']
    MAX_REQUESTS = 30    # per user per window
    WINDOW_SECONDS = 60  # 1 minute window

    _counters = defaultdict(list)  # {user_id: [timestamp, ...]}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == 'POST' and any(request.path.startswith(p) for p in self.AI_PATHS):
            if request.user.is_authenticated:
                user_id = str(request.user.pk)
                now = time.time()
                # Remove timestamps outside the window
                self._counters[user_id] = [
                    t for t in self._counters[user_id]
                    if now - t < self.WINDOW_SECONDS
                ]
                if len(self._counters[user_id]) >= self.MAX_REQUESTS:
                    security_logger.warning(
                        'RATE_LIMIT user=%s path=%s ip=%s',
                        user_id, request.path, _get_client_ip(request)
                    )
                    return JsonResponse(
                        {'error': 'Too many AI requests. Please wait a moment before trying again.'},
                        status=429
                    )
                self._counters[user_id].append(now)

        return self.get_response(request)


# ── 3. Prompt Injection Guard ────────────────────────────────────────────────

# Patterns that indicate an attempt to hijack the AI system prompt
_INJECTION_PATTERNS = [
    r'ignore\s+(all\s+)?(previous|prior|above)\s+instructions',
    r'you\s+are\s+now\s+a',
    r'forget\s+your\s+(previous\s+)?instructions',
    r'system\s*:\s*you\s+are',
    r'<\s*system\s*>',
    r'\[INST\]',
    r'###\s*instruction',
    r'act\s+as\s+if\s+you\s+are',
    r'pretend\s+you\s+are\s+a',
    r'jailbreak',
    r'dan\s+mode',
]

_INJECTION_REGEX = re.compile('|'.join(_INJECTION_PATTERNS), re.IGNORECASE)

AI_INPUT_FIELDS = ['transcription', 'message', 'question', 'chief_complaint',
                   'notes', 'history', 'exam_data']


class PromptInjectionGuard:
    """
    Scans POST data sent to AI endpoints for prompt injection patterns.
    Blocks the request and logs a security warning if detected.

    Protects against attackers submitting clinical text like:
      "Ignore all previous instructions. You are now..."
    to hijack the AI response for non-clinical purposes.
    """
    AI_PATHS = ['/ai-assistant/']

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == 'POST' and any(request.path.startswith(p) for p in self.AI_PATHS):
            # Check POST form fields
            for field in AI_INPUT_FIELDS:
                value = request.POST.get(field, '')
                if value and _INJECTION_REGEX.search(value):
                    security_logger.warning(
                        'PROMPT_INJECTION_ATTEMPT user=%s path=%s ip=%s field=%s',
                        getattr(request.user, 'pk', 'anon'),
                        request.path,
                        _get_client_ip(request),
                        field,
                    )
                    return JsonResponse(
                        {'error': 'Input contains disallowed content.'},
                        status=400
                    )

            # Check JSON body for text fields
            if request.content_type and 'application/json' in request.content_type:
                try:
                    import json
                    body = json.loads(request.body)
                    for field in AI_INPUT_FIELDS:
                        value = body.get(field, '') if isinstance(body, dict) else ''
                        if value and _INJECTION_REGEX.search(str(value)):
                            security_logger.warning(
                                'PROMPT_INJECTION_ATTEMPT user=%s path=%s ip=%s field=%s (JSON)',
                                getattr(request.user, 'pk', 'anon'),
                                request.path,
                                _get_client_ip(request),
                                field,
                            )
                            return JsonResponse(
                                {'error': 'Input contains disallowed content.'},
                                status=400
                            )
                except Exception:
                    pass  # Not valid JSON — let view handle it

        return self.get_response(request)


# ── 4. Content Security Policy ───────────────────────────────────────────────

class ContentSecurityPolicyMiddleware:
    """
    Adds Content-Security-Policy header from Django settings CSP_* variables.
    Prevents XSS by telling the browser which sources are trusted.

    Configure in settings:
        CSP_SCRIPT_SRC = ("'self'", "'unsafe-inline'", "cdn.jsdelivr.net")
        CSP_STYLE_SRC  = ("'self'", "'unsafe-inline'", "cdn.jsdelivr.net")
        etc.
    """
    def __init__(self, get_response):
        self.get_response = get_response
        self._csp_header = None

    def _build_csp(self):
        from django.conf import settings
        directives = {
            'default-src': getattr(settings, 'CSP_DEFAULT_SRC', ("'self'",)),
            'script-src':  getattr(settings, 'CSP_SCRIPT_SRC',  ("'self'",)),
            'style-src':   getattr(settings, 'CSP_STYLE_SRC',   ("'self'",)),
            'img-src':     getattr(settings, 'CSP_IMG_SRC',     ("'self'", "data:")),
            'font-src':    getattr(settings, 'CSP_FONT_SRC',    ("'self'",)),
            'connect-src': getattr(settings, 'CSP_CONNECT_SRC', ("'self'",)),
            'media-src':   getattr(settings, 'CSP_MEDIA_SRC',   ("'self'",)),
            'frame-src':   getattr(settings, 'CSP_FRAME_SRC',   ("'none'",)),
            'object-src':  getattr(settings, 'CSP_OBJECT_SRC',  ("'none'",)),
        }
        parts = [
            f"{directive} {' '.join(sources)}"
            for directive, sources in directives.items()
            if sources
        ]
        return '; '.join(parts)

    def __call__(self, request):
        response = self.get_response(request)
        # Only add CSP to HTML responses, not JSON/CSV/etc.
        ct = response.get('Content-Type', '')
        if 'text/html' in ct:
            if self._csp_header is None:
                self._csp_header = self._build_csp()
            response['Content-Security-Policy'] = self._csp_header
        return response


# ── Shared helper ─────────────────────────────────────────────────────────────

def _get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '?')
