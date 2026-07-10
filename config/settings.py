"""
Django settings for ops-event-tools.

Environment-driven single settings file. Secrets and machine-specific values
come from a .env file loaded by systemd (EnvironmentFile=) in production, or
exported manually in development. See .env.example.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv():
    """Minimal .env loader so `manage.py runserver` works without systemd."""
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "insecure-dev-key-change-me")
DEBUG = os.getenv("DEBUG", "false").lower() in ("1", "true", "yes")
ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
    "events",
    "sync",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.auth.middleware.LoginRequiredMiddleware",
    "accounts.middleware.HtmxLoginRedirectMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "events.context_processors.nav_events",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Database: SQLite by default, Postgres via env vars (ORM-portable, no raw SQL)
_db_engine = os.getenv("DB_ENGINE", "sqlite3")
if _db_engine == "sqlite3":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / os.getenv("DB_NAME", "db.sqlite3"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": f"django.db.backends.{_db_engine}",
            "NAME": os.getenv("DB_NAME", "ops_event_tools"),
            "HOST": os.getenv("DB_HOST", "localhost"),
            "USER": os.getenv("DB_USER", ""),
            "PASSWORD": os.getenv("DB_PASSWORD", ""),
            "PORT": os.getenv("DB_PORT", ""),
        }
    }

AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

# Sessions: default 4 days (parity with old app); kiosk checkbox extends to 90 days
SESSION_COOKIE_AGE = 4 * 24 * 60 * 60
KIOSK_SESSION_AGE = 90 * 24 * 60 * 60
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

LANGUAGE_CODE = "en-us"
# Server clock stays UTC; all event-facing "today"/"now" logic uses Event.tz explicitly.
TIME_ZONE = "UTC"
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Sized for the PDF room-layout upload flow
DATA_UPLOAD_MAX_MEMORY_SIZE = 60 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 60 * 1024 * 1024

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", str(BASE_DIR / "credentials.json"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}
