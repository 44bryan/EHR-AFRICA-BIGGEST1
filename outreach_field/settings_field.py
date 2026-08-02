"""
EHR Africa — Outreach Field App Settings
Runs on a local laptop using SQLite (no internet required).
Only the outreach module is active.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'outreach-field-local-key-not-for-production-use'
DEBUG = True
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '0.0.0.0']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # EHR apps needed for the field module
    'apps.accounts',
    'apps.core',
    'apps.patients',
    'apps.outreach',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'outreach_field.urls_field'

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
                'apps.core.context_processors.hospital_config',
            ],
            'builtins': ['apps.core.templatetags.ehr_tags'],
        },
    },
]

# SQLite — works 100% offline
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'outreach_field' / 'field_data.sqlite3',
    }
}

AUTH_USER_MODEL = 'accounts.User'
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/outreach/'

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Douala'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'outreach_field' / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Field device identity — edit this before deploying to a specific laptop
FIELD_DEVICE_ID = os.environ.get('FIELD_DEVICE_ID', 'OUTREACH-LAPTOP-01')
FIELD_DEVICE_LABEL = os.environ.get('FIELD_DEVICE_LABEL', 'Outreach Laptop 1')

# Hospital server address for sync
HOSPITAL_SERVER_URL = os.environ.get('HOSPITAL_SERVER_URL', 'http://192.168.30.169')
OUTREACH_SYNC_TOKEN = os.environ.get('OUTREACH_SYNC_TOKEN', '')
