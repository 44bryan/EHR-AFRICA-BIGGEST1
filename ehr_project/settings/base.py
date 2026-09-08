"""
Base Django settings for EHR Africa - Ophthalmologist EHR System
"""
import os
from pathlib import Path
import environ

# Build paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Environment variables
env = environ.Env(
    DEBUG=(bool, False),
)
environ.Env.read_env(os.path.join(BASE_DIR, '.env'))

SECRET_KEY = env('SECRET_KEY')
DEBUG = env('DEBUG')
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['localhost', '127.0.0.1'])

# Application definition
DJANGO_APPS = [
    'daphne',          # must be before staticfiles (daphne.E001)
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
]

THIRD_PARTY_APPS = [
    'channels',
    'rest_framework',
    'crispy_forms',
    'crispy_bootstrap5',
    'widget_tweaks',
    'django_htmx',
    'axes',
    'import_export',
    'django_celery_results',
    'django_celery_beat',
    'phonenumber_field',
]

LOCAL_APPS = [
    'apps.core',
    'apps.accounts',
    'apps.departments',
    'apps.patients',
    'apps.appointments',
    'apps.consultations',
    'apps.prescriptions',
    'apps.investigations',
    'apps.laboratory',
    'apps.reports',
    'apps.ai_assistant',
    'apps.dashboard',
    'apps.api',
    # Phase 2 modules
    'apps.qms',
    'apps.pharmacy',
    'apps.inventory',
    'apps.opticals',
    'apps.ipd',
    'apps.cssd',
    'apps.hrms',
    'apps.leads',
    'apps.feedback',
    'apps.opd',
    'apps.leadership',
    'apps.billing',
    'apps.reception',
    'apps.notifications',
    'apps.outreach',
    'apps.patient_portal',
    # New enterprise modules
    'apps.hmo',
    'apps.blood_bank',
    'apps.infection_control',
    'apps.dietary',
    'apps.mortuary',
    'apps.telemedicine',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'apps.core.multi_session_middleware.MultiSessionMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django_htmx.middleware.HtmxMiddleware',
    'axes.middleware.AxesMiddleware',
    'apps.core.middleware.ContentSecurityPolicyMiddleware',
    'apps.core.middleware.PromptInjectionGuard',  # Must be before AuditMiddleware
    'apps.core.middleware.RateLimitMiddleware',
    'apps.core.middleware.AuditMiddleware',
]

ROOT_URLCONF = 'ehr_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.core.context_processors.hospital_settings',
                'apps.core.context_processors.hospital_modules',
                'apps.core.context_processors.user_notifications',
                'apps.core.context_processors.session_slot',
                'apps.core.context_processors.doctor_assigned_room',
                'apps.core.context_processors.route_config',
            ],
            'builtins': [
                'apps.core.templatetags.ehr_tags',
            ],
        },
    },
]

WSGI_APPLICATION = 'ehr_project.wsgi.application'
ASGI_APPLICATION = 'ehr_project.asgi.application'

# Database — defaults to SQLite for development
_db_url = env('DATABASE_URL', default='')
if _db_url:
    DATABASES = {'default': env.db('DATABASE_URL')}
    # Reuse DB connections: keep alive 5 min. At 300 users this avoids reconnect overhead.
    DATABASES['default']['CONN_MAX_AGE'] = 300
    # Auto-recover stale connections (network drop, DB restart) without 500 errors.
    DATABASES['default']['CONN_HEALTH_CHECKS'] = True
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Custom User Model
AUTH_USER_MODEL = 'accounts.User'

# Authentication
AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
    'django.contrib.auth.backends.ModelBackend',
]

LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'dashboard:home'
LOGOUT_REDIRECT_URL = 'accounts:login'

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
     'OPTIONS': {'min_length': 12}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Douala'

# Cameroon localisation
COUNTRY = 'Cameroon'
CURRENCY_CODE = 'XAF'
CURRENCY_SYMBOL = 'FCFA'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / env('MEDIA_ROOT', default='media')

# Default primary key
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Crispy Forms
CRISPY_ALLOWED_TEMPLATE_PACKS = 'bootstrap5'
CRISPY_TEMPLATE_PACK = 'bootstrap5'

# DRF
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 25,
}

# Celery
CELERY_BROKER_URL = env('REDIS_URL', default='redis://127.0.0.1:6379/0')
CELERY_RESULT_BACKEND = 'django-db'
CELERY_CACHE_BACKEND = 'django-cache'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'Africa/Douala'
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'

# Cache
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': env('REDIS_URL', default='redis://127.0.0.1:6379/1'),
    }
}

# Django Channels — always use db=2, isolated from Celery (db=0) and cache (db=1)
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': ['redis://127.0.0.1:6379/2'],
            'capacity': 1500,
            'expiry': 10,
        },
    },
}

# Axes (brute force protection)
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 1  # 1 hour
AXES_LOCKOUT_TEMPLATE = 'accounts/lockout.html'

# Phone number field
PHONENUMBER_DEFAULT_REGION = 'CM'

# AI — Hybrid LLM Architecture
# Demo:       Groq (Llama-3.3-70b) for fast reasoning + Claude for complex extraction
# Production: Ollama (Llama-3.3-70b local) replaces Groq; Claude optional
ANTHROPIC_API_KEY = env('ANTHROPIC_API_KEY', default='')
AI_MODEL = 'claude-sonnet-4-6'
AI_MAX_TOKENS = 4096

# Groq — DeepSeek-R1 distill for deep clinical reasoning
GROQ_API_KEY = env('GROQ_API_KEY', default='')
GROQ_MODEL = env('GROQ_MODEL', default='deepseek-r1-distill-llama-70b')  # Primary reasoning model (R1 chain-of-thought)
GROQ_FAST_MODEL = env('GROQ_FAST_MODEL', default='llama-3.1-8b-instant')  # Receptionist / simple Q&A

# Which engine to use for each feature
# Options: 'groq' | 'claude' | 'ollama'
AI_ENGINE_REASONING    = env('AI_ENGINE_REASONING',    default='groq')   # Diagnosis, analytics, receptionist
AI_ENGINE_EXTRACTION   = env('AI_ENGINE_EXTRACTION',   default='groq')   # Voice EMR clinical extraction
AI_ENGINE_PRODUCTION   = env('AI_ENGINE_PRODUCTION',   default='ollama') # On-premises target

# Ollama (production on-premises)
OLLAMA_BASE_URL = env('OLLAMA_BASE_URL', default='http://localhost:11434')
OLLAMA_MODEL    = env('OLLAMA_MODEL',    default='llama3.3:70b')

# Whisper model size: tiny|base|small|medium|large (base = good CPU demo)
WHISPER_MODEL_SIZE = env('WHISPER_MODEL_SIZE', default='base')

# Hospital Configuration
HOSPITAL_NAME = env('HOSPITAL_NAME', default='EyeCare Specialist Hospital')
HOSPITAL_COUNTRY = env('HOSPITAL_COUNTRY', default='Cameroon')
HOSPITAL_CITY = env('HOSPITAL_CITY', default='Yaoundé')
HOSPITAL_ADDRESS = env('HOSPITAL_ADDRESS', default='')
HOSPITAL_PHONE = env('HOSPITAL_PHONE', default='')
HOSPITAL_EMAIL = env('HOSPITAL_EMAIL', default='')
HOSPITAL_WEBSITE = env('HOSPITAL_WEBSITE', default='')
HOSPITAL_REG_NUMBER = env('HOSPITAL_REG_NUMBER', default='')

# Session — use Redis-backed cached_db for near-zero latency on every request
# (Redis = ~0.1ms lookup vs DB = ~5-10ms; DB is the write-through fallback)
SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db'
SESSION_CACHE_ALIAS = 'default'     # uses the Redis cache defined in CACHES
SESSION_COOKIE_AGE = 43200          # 12 hours — covers full shift including overtime
SESSION_EXPIRE_AT_BROWSER_CLOSE = False  # tablet-safe: session persists up to SESSION_COOKIE_AGE
SESSION_SAVE_EVERY_REQUEST = True   # reset the 12h clock on every page visit (inactivity-based expiry)
SESSION_COOKIE_HTTPONLY = True      # JS cannot read session cookie
SESSION_COOKIE_SAMESITE = 'Lax'     # CSRF protection
SESSION_COOKIE_SECURE = env.bool('SESSION_COOKIE_SECURE', default=(not DEBUG))

# CSRF cookie
CSRF_COOKIE_NAME = 'ehr_csrf'      # fresh name — invalidates old secure cookies
SESSION_COOKIE_NAME = 'ehr_session' # fresh name — invalidates old secure sessions
CSRF_COOKIE_HTTPONLY = False        # JS must read it for AJAX
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SECURE = env.bool('CSRF_COOKIE_SECURE', default=(not DEBUG))
# Trusted origins — required for Django 4+ on non-localhost LAN/production hosts.
# Set in .env as: CSRF_TRUSTED_ORIGINS=http://192.168.30.169,http://192.168.200.254
CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=['http://localhost', 'http://127.0.0.1'])

# Security headers (applied by SecurityMiddleware)
SECURE_BROWSER_XSS_FILTER = True        # X-XSS-Protection: 1; mode=block
SECURE_CONTENT_TYPE_NOSNIFF = True      # X-Content-Type-Options: nosniff
X_FRAME_OPTIONS = 'SAMEORIGIN'          # Allow same-origin iframes (receipt modal)

# HSTS — only activate in production (not dev, breaks HTTP)
SECURE_HSTS_SECONDS = 0 if DEBUG else 31536000   # 1 year in prod
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG

# Referrer policy
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'

# Content Security Policy — allow Bootstrap CDN, own static files, HTMX inline scripts
# Adjust in prod.py to tighten if all assets are served locally
CSP_DEFAULT_SRC = ("'self'",)
CSP_SCRIPT_SRC  = ("'self'", "'unsafe-inline'", "cdn.jsdelivr.net", "cdnjs.cloudflare.com")
CSP_STYLE_SRC   = ("'self'", "'unsafe-inline'", "cdn.jsdelivr.net", "cdnjs.cloudflare.com")
CSP_IMG_SRC     = ("'self'", "data:", "blob:")
CSP_FONT_SRC    = ("'self'", "cdn.jsdelivr.net", "cdnjs.cloudflare.com")
CSP_CONNECT_SRC = ("'self'",)
CSP_MEDIA_SRC   = ("'self'", "blob:")
CSP_FRAME_SRC   = ("'self'",)           # Allow same-origin iframes (receipt modal)
CSP_OBJECT_SRC  = ("'none'",)

# Twilio (SMS / WhatsApp)
TWILIO_ACCOUNT_SID   = env('TWILIO_ACCOUNT_SID',   default='')
TWILIO_AUTH_TOKEN    = env('TWILIO_AUTH_TOKEN',     default='')
TWILIO_FROM_NUMBER   = env('TWILIO_FROM_NUMBER',    default='')
TWILIO_WHATSAPP_FROM = env('TWILIO_WHATSAPP_FROM',  default='whatsapp:+14155238886')
SMS_ENABLED          = env.bool('SMS_ENABLED',      default=False)

# Backup settings
BACKUP_DIR           = env('BACKUP_DIR', default=str(BASE_DIR / 'backups'))
BACKUP_EXTERNAL_PATH = env('BACKUP_EXTERNAL_PATH', default='')  # e.g. /mnt/usb_drive/ehr_backups
BACKUP_KEEP          = env.int('BACKUP_KEEP', default=30)       # How many backups to retain

# Celery Beat schedule — daily backup at 02:00 Africa/Douala
from celery.schedules import crontab
CELERY_BEAT_SCHEDULE = {
    'daily-db-backup': {
        'task': 'core.daily_backup',
        'schedule': crontab(hour=2, minute=0),
    },
    'daily-appointment-reminders': {
        'task': 'notifications.send_appointment_reminders',
        'schedule': crontab(hour=7, minute=0),
    },
    'daily-inventory-alerts': {
        'task': 'notifications.daily_inventory_alerts',
        'schedule': crontab(hour=8, minute=0),
    },
    # 19:00 — mark any SCHEDULED/CONFIRMED appointments not yet checked in as NO_SHOW
    'daily-mark-no-shows': {
        'task': 'appointments.mark_no_shows',
        'schedule': crontab(hour=19, minute=0),
    },
    # 23:55 — auto-bill nightly bed charges for all admitted inpatients
    'nightly-bed-charges': {
        'task': 'ipd.auto_bill_bed_charges',
        'schedule': crontab(hour=23, minute=55),
    },
}

# DICOM Imaging Viewer
DICOM_VIEWER_BASE_URL   = env('DICOM_VIEWER_BASE_URL', default='')

# Patient Portal
PATIENT_PORTAL_BASE_URL = env('PATIENT_PORTAL_BASE_URL', default='')

# Email
EMAIL_BACKEND = env('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = env('EMAIL_HOST', default='')
EMAIL_PORT = env.int('EMAIL_PORT', default=587)
EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=True)
EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = f"{HOSPITAL_NAME} <{EMAIL_HOST_USER}>"

# Telemedicine — Jitsi Meet server (can be self-hosted)
JITSI_SERVER = env('JITSI_SERVER', default='https://meet.jit.si')

# File upload limits
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

# Logging
import os as _os
_os.makedirs(BASE_DIR / 'logs', exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
        'audit': {
            'format': '{asctime} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'ehr_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'ehr.log',
            'maxBytes': 10 * 1024 * 1024,  # 10MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
        # Clinical audit log — NEVER delete this file, it's a compliance record
        'audit_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'audit.log',
            'maxBytes': 50 * 1024 * 1024,  # 50MB per file
            'backupCount': 30,             # Keep 30 rotations (~1.5GB total)
            'formatter': 'audit',
        },
        # Security events (injection attempts, rate limits, failed logins)
        'security_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'security.log',
            'maxBytes': 20 * 1024 * 1024,
            'backupCount': 10,
            'formatter': 'audit',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'ehr_file'],
            'level': 'INFO',
            'propagate': False,
        },
        'apps': {
            'handlers': ['console', 'ehr_file'],
            'level': 'DEBUG',
            'propagate': False,
        },
        # Dedicated audit trail logger
        'ehr.audit': {
            'handlers': ['audit_file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
        # Security events
        'ehr.security': {
            'handlers': ['security_file', 'console'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}
