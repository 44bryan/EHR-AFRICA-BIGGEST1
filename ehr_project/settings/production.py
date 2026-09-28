"""
Production settings for EHR Africa — Enterprise self-hosted deployment.

Usage:
    DJANGO_SETTINGS_MODULE=ehr_project.settings.production

Required extra .env keys (on top of base):
    ALLOWED_HOSTS          comma-separated: ehr.myhospital.cm,www.ehr.myhospital.cm
    CSRF_TRUSTED_ORIGINS   comma-separated: https://ehr.myhospital.cm
    DATABASE_URL           postgres://user:pass@host:5432/ehrdb
    REDIS_URL              redis://:password@host:6379/0
    EMAIL_BACKEND          django.core.mail.backends.smtp.EmailBackend
    EMAIL_HOST             smtp.yourdomain.cm
    EMAIL_HOST_USER        noreply@myhospital.cm
    EMAIL_HOST_PASSWORD    smtp-password
"""
from .base import *  # noqa

# ── Core ──────────────────────────────────────────────────────────────────────
DEBUG = False

# ── Template caching — parse each template once, store in memory ───────────
# In production, APP_DIRS is replaced with the CachedLoader so templates are
# loaded from disk only once per process restart, not on every request.
TEMPLATES[0]['APP_DIRS'] = False  # noqa: F405
TEMPLATES[0]['OPTIONS']['loaders'] = [  # noqa: F405
    ('django.template.loaders.cached.Loader', [
        'django.template.loaders.filesystem.Loader',
        'django.template.loaders.app_directories.Loader',
    ])
]

ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=[])

CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[])

# ── Database ──────────────────────────────────────────────────────────────────
# DATABASE_URL must be set in .env — no SQLite fallback in production
DATABASES = {
    'default': env.db('DATABASE_URL')
}
DATABASES['default']['CONN_MAX_AGE'] = 60          # persistent connections
# PostgreSQL-specific connection options — skip for SQLite
if 'postgresql' in DATABASES['default'].get('ENGINE', ''):
    DATABASES['default']['OPTIONS'] = {
        'connect_timeout': 10,
        'options': '-c statement_timeout=30000',    # 30-second query timeout
    }

# ── Cache — Redis ─────────────────────────────────────────────────────────────
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': env('REDIS_URL', default='redis://127.0.0.1:6379/1'),
        'OPTIONS': {
            'socket_connect_timeout': 5,
            'socket_timeout': 5,
        },
        'KEY_PREFIX': 'ehr',
        'TIMEOUT': 300,    # 5-minute default TTL
    }
}

# ── Session — cached_db = Redis speed + DB persistence (survives Redis restart)
SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db'
SESSION_CACHE_ALIAS = 'default'

# ── Static files — WhiteNoise with compression + long-lived caching ───────────
STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'

# ── Email — SMTP ─────────────────────────────────────────────────────────────
EMAIL_BACKEND = env(
    'EMAIL_BACKEND',
    default='django.core.mail.backends.smtp.EmailBackend'
)
EMAIL_HOST          = env('EMAIL_HOST',          default='')
EMAIL_PORT          = env.int('EMAIL_PORT',      default=587)
EMAIL_USE_TLS       = env.bool('EMAIL_USE_TLS',  default=True)
EMAIL_USE_SSL       = env.bool('EMAIL_USE_SSL',  default=False)
EMAIL_HOST_USER     = env('EMAIL_HOST_USER',     default='')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
EMAIL_TIMEOUT       = 10   # seconds — don't hang on a broken SMTP server

# ── Celery — Redis broker (full async task queue) ─────────────────────────────
CELERY_BROKER_URL            = env('REDIS_URL', default='redis://127.0.0.1:6379/0')
CELERY_RESULT_BACKEND        = 'redis'
CELERY_REDIS_MAX_CONNECTIONS = 10
CELERY_TASK_ALWAYS_EAGER     = False
CELERY_TASK_EAGER_PROPAGATES = False
CELERY_WORKER_CONCURRENCY    = env.int('CELERY_CONCURRENCY', default=4)

# ── Security ──────────────────────────────────────────────────────────────────
# LAN deployment uses HTTP — SSL settings controlled via env vars
SECURE_SSL_REDIRECT            = env.bool('SECURE_SSL_REDIRECT', default=False)
SECURE_HSTS_SECONDS            = env.int('SECURE_HSTS_SECONDS', default=0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=False)
SECURE_HSTS_PRELOAD            = env.bool('SECURE_HSTS_PRELOAD', default=False)
SECURE_PROXY_SSL_HEADER        = ('HTTP_X_FORWARDED_PROTO', 'https')  # behind Nginx

SESSION_COOKIE_SECURE   = env.bool('SESSION_COOKIE_SECURE', default=False)
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SECURE      = env.bool('CSRF_COOKIE_SECURE', default=False)

# ── Axes (brute-force login protection) ──────────────────────────────────────
AXES_ENABLED          = env.bool('AXES_ENABLED', default=False)
AXES_FAILURE_LIMIT    = env.int('AXES_FAILURE_LIMIT', default=999)
AXES_COOLOFF_TIME     = 1
AXES_LOCKOUT_TEMPLATE = 'accounts/lockout.html'
AXES_RESET_ON_SUCCESS = True

# ── Logging — files only; console only on ERROR ───────────────────────────────
LOGGING['handlers']['console']['level'] = 'ERROR'  # noqa: F405
LOGGING['loggers']['django']['level']   = 'WARNING'  # noqa: F405
LOGGING['loggers']['apps']['level']     = 'INFO'     # noqa: F405

# ── CSP — include Google Fonts for Inter typeface ────────────────────────────
CSP_FONT_SRC   = ("'self'", "fonts.gstatic.com", "cdn.jsdelivr.net")
CSP_STYLE_SRC  = ("'self'", "'unsafe-inline'", "cdn.jsdelivr.net", "fonts.googleapis.com")
CSP_SCRIPT_SRC = ("'self'", "'unsafe-inline'", "cdn.jsdelivr.net", "cdnjs.cloudflare.com")

# ── Admin URL hardening — set ADMIN_URL in .env to something non-obvious ──────
ADMIN_URL = env('ADMIN_URL', default='django-admin/')
