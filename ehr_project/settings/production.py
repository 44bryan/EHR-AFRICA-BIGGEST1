from .base import *  # noqa
import os

DEBUG = False

# Render sets PORT env var — allow the render domain
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=[]) + [
    '.onrender.com',
    'localhost',
]

# Security
CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[
    'https://*.onrender.com',
])

# Static files — WhiteNoise serves them directly
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Cache — use database cache (no Redis needed on free tier)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'django_cache',
    }
}

# Celery — run tasks eagerly (no Redis on free tier)
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Email — console for now (no SMTP needed for demo)
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Axes — enabled in prod
AXES_ENABLED = True

# Logging
LOGGING['handlers']['console']['level'] = 'ERROR'  # noqa
