from .base import *  # noqa

DEBUG = True

try:
    import debug_toolbar  # noqa
    INSTALLED_APPS += ['debug_toolbar']  # noqa
    MIDDLEWARE += ['debug_toolbar.middleware.DebugToolbarMiddleware']  # noqa
    INTERNAL_IPS = ['127.0.0.1']
except ImportError:
    pass

# Use file-based cache in dev — no Redis required
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
        'LOCATION': BASE_DIR / '.cache',  # noqa
    }
}

# Force DB-only sessions in dev — no Redis, no cached_db
SESSION_ENGINE = 'django.contrib.sessions.backends.db'

# Celery — run tasks eagerly in dev (no Redis needed)
CELERY_BROKER_URL = 'memory://'
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Emails to console in dev
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Relax axes in dev
AXES_ENABLED = False

# Disable CSRF in dev — re-enable before going live
MIDDLEWARE = [m for m in MIDDLEWARE if 'CsrfViewMiddleware' not in m]  # noqa
