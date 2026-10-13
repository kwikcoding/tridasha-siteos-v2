"""Django settings for Tridasha SiteOS v2. Everything environment-specific comes from env vars (see .env.example)."""
import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name, default=None):
    return os.environ.get(name, default)


def env_bool(name, default=False):
    return str(env(name, default)).lower() in ("1", "true", "yes", "on")


def env_list(name, default=""):
    return [x.strip() for x in str(env(name, default)).split(",") if x.strip()]


DEBUG = env_bool("DJANGO_DEBUG", False)
SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-only-insecure-key" if DEBUG else None)
if not SECRET_KEY:
    raise RuntimeError("Set DJANGO_SECRET_KEY")
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS", "http://localhost:5173")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    "apps.accounts",
    "apps.sites",
    "apps.indents",
    "apps.alerts",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {"default": dj_database_url.parse(
    env("DATABASE_URL", "postgres://siteos:siteos@localhost:5432/siteos"), conn_max_age=60)}

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

LANGUAGE_CODE = "en-in"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Sessions + CSRF: the React app is served from the same domain (Caddy routes /api to Django),
# so a secure HttpOnly session cookie is the simplest safe choice — no tokens in localStorage.
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_CONTENT_TYPE_NOSNIFF = True

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend",
                                "rest_framework.filters.SearchFilter", "rest_framework.filters.OrderingFilter"],
    "DEFAULT_PAGINATION_CLASS": "config.pagination.Pagination",
    "PAGE_SIZE": 50,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_RATES": {"login": "10/min"},
}
SPECTACULAR_SETTINGS = {"TITLE": "Tridasha SiteOS API", "VERSION": "2.0.0"}

# Celery (alerts and scheduled checks)
CELERY_BROKER_URL = env("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = None
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_EAGER", False)
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    "overdue-deliveries": {"task": "apps.alerts.tasks.overdue_deliveries", "schedule": 60 * 60 * 3},
    "daily-pending-digest": {"task": "apps.alerts.tasks.pending_digest", "schedule": 60 * 60 * 24},
}

# Alerts — each channel is off until its settings are filled in.
EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", "")
EMAIL_PORT = int(env("EMAIL_PORT", "587"))
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "SiteOS <no-reply@tridashaimperial.com>")
WHATSAPP_TOKEN = env("WHATSAPP_TOKEN", "")              # Meta WhatsApp Cloud API
WHATSAPP_PHONE_ID = env("WHATSAPP_PHONE_ID", "")
WHATSAPP_TEMPLATE = env("WHATSAPP_TEMPLATE", "siteos_alert")  # approved template with one {{1}} body param
SMS_PROVIDER = env("SMS_PROVIDER", "")                   # "msg91" or empty
MSG91_AUTH_KEY = env("MSG91_AUTH_KEY", "")
MSG91_FLOW_ID = env("MSG91_FLOW_ID", "")
APP_URL = env("APP_URL", "http://localhost:5173")

LOGGING = {
    "version": 1,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
}
