"""
Django settings for the LaunchPad project.

Configuration comes from the environment. Copy .env.example to .env and fill it
in for local development; .env is git-ignored and must never be committed.

For the deployment checklist, see
https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.core.management.utils import get_random_secret_key
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env if it exists. Real environment variables always win, so a deployed
# environment can set them directly without a file being present.
load_dotenv(BASE_DIR / ".env", override=False)


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    raw = os.environ.get(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def env_int(name, default=0):
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ImproperlyConfigured(f"{name} must be an integer, got {value!r}") from exc


# ---------------------------------------------------------------------------
# Core security
# ---------------------------------------------------------------------------

# Defaults to False so that a missing or incomplete environment fails closed.
DEBUG = env_bool("DJANGO_DEBUG", default=False)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "").strip()

if not SECRET_KEY:
    if DEBUG:
        # Ephemeral, regenerated on every start. Sessions will not survive a
        # restart, which is a deliberate nudge to set DJANGO_SECRET_KEY in .env.
        SECRET_KEY = get_random_secret_key()
    else:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY is not set. Copy .env.example to .env and set a "
            "unique value, or export it in the deployment environment."
        )

# Localhost is included by default so that DEBUG=False still works locally.
# Production domains are supplied through the environment; none are hardcoded.
ALLOWED_HOSTS = env_list(
    "DJANGO_ALLOWED_HOSTS",
    default="localhost,127.0.0.1,[::1]",
)

CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")


# ---------------------------------------------------------------------------
# Application definition
# ---------------------------------------------------------------------------

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'core'
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

ROOT_URLCONF = 'config.urls'

LOGIN_URL = '/login/'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'core' / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.launchpad_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# ---------------------------------------------------------------------------
# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases
# ---------------------------------------------------------------------------
#
# Non-secret values keep working defaults so a fresh checkout points at the
# usual local database. The password has no default on purpose: it must come
# from the environment.

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME', 'launchpad_final_test'),
        'USER': os.environ.get('DB_USER', 'postgres'),
        'PASSWORD': os.environ.get('DB_PASSWORD', ''),
        'HOST': os.environ.get('DB_HOST', 'localhost'),
        'PORT': os.environ.get('DB_PORT', '5432'),
    }
}


# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# ---------------------------------------------------------------------------
# Default primary key field type
# ---------------------------------------------------------------------------
#
# Every existing migration declares BigAutoField and every core_* table in
# PostgreSQL already has a bigint primary key. Without this setting Django
# resolves the models to AutoField, so makemigrations wants to generate an
# AlterField shrinking all 22 primary keys to 32-bit integers. Declaring it
# here makes the model state agree with the migrations and the database.

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ---------------------------------------------------------------------------
# Static and media files
# ---------------------------------------------------------------------------

STATIC_URL = '/static/'

# collectstatic gathers everything here for a web server to serve. It is a
# build artifact, not source, so it is git-ignored.
STATIC_ROOT = Path(os.environ.get('DJANGO_STATIC_ROOT', BASE_DIR / 'staticfiles'))

MEDIA_URL = '/media/'
MEDIA_ROOT = Path(os.environ.get('DJANGO_MEDIA_ROOT', BASE_DIR / 'media'))


# ---------------------------------------------------------------------------
# Uploads
# ---------------------------------------------------------------------------

# Ceiling for a single uploaded file and for a whole request body. Keeps a
# stray large upload from exhausting memory or disk.
FILE_UPLOAD_MAX_MEMORY_SIZE = env_int('DJANGO_FILE_UPLOAD_MAX_BYTES', 10 * 1024 * 1024)
DATA_UPLOAD_MAX_MEMORY_SIZE = env_int('DJANGO_DATA_UPLOAD_MAX_BYTES', 20 * 1024 * 1024)


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

EMAIL_BACKEND = os.environ.get(
    'DJANGO_EMAIL_BACKEND',
    'django.core.mail.backends.console.EmailBackend',
)
DEFAULT_FROM_EMAIL = os.environ.get('DJANGO_DEFAULT_FROM_EMAIL', 'noreply@launchpad.local')


# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------
#
# These are safe over plain HTTP and are always on.

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'

# Everything below depends on the site actually being served over HTTPS.
# SECURE_MODE follows DEBUG by default but can be overridden, which matters for
# a staging box that runs DEBUG=False over plain HTTP - turning secure cookies
# on there would make login impossible.
SECURE_MODE = env_bool('DJANGO_SECURE_MODE', default=not DEBUG)

SESSION_COOKIE_SECURE = SECURE_MODE
CSRF_COOKIE_SECURE = SECURE_MODE
SECURE_SSL_REDIRECT = SECURE_MODE

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'

# HSTS tells browsers to refuse plain HTTP for this domain for the given
# duration, and it CANNOT be undone before it expires. It stays off (0) unless
# DJANGO_HSTS_SECONDS is set explicitly, and is ignored entirely outside secure
# mode.
#
# Production rollout: confirm HTTPS works on every subdomain first, then ramp
# DJANGO_HSTS_SECONDS up (e.g. 3600, then 86400, then 31536000). Only set
# DJANGO_HSTS_INCLUDE_SUBDOMAINS once every subdomain is HTTPS-only, and only
# set DJANGO_HSTS_PRELOAD when you intend to submit to the browser preload list.
SECURE_HSTS_SECONDS = env_int('DJANGO_HSTS_SECONDS', 0) if SECURE_MODE else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0 and env_bool(
    'DJANGO_HSTS_INCLUDE_SUBDOMAINS', default=False
)
SECURE_HSTS_PRELOAD = SECURE_HSTS_SECONDS > 0 and env_bool(
    'DJANGO_HSTS_PRELOAD', default=False
)

# Set to True when running behind a reverse proxy that terminates TLS.
if env_bool('DJANGO_TRUST_PROXY_SSL_HEADER', default=False):
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
