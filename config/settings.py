"""
Django settings for ops-event-tools.

Environment-driven single settings file. Secrets and machine-specific values
come from a .env file loaded by systemd (EnvironmentFile=) in production, or
exported manually in development. See .env.example.
"""
import os
import sys
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
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
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
    "accounts.middleware.LoginRequiredMiddleware",
    "accounts.middleware.HtmxLoginRedirectMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
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
                "accounts.context_processors.theme",
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

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

# --- django-allauth: Google sign-in + email login codes ---
# Signup is CLOSED (accounts.adapters): Google/code logins only match users an
# Admin already created, by email. Local username/password stays on our own
# login view (kiosk session semantics).
ACCOUNT_ADAPTER = "accounts.adapters.AccountAdapter"
SOCIALACCOUNT_ADAPTER = "accounts.adapters.SocialAccountAdapter"
ACCOUNT_LOGIN_METHODS = {"username"}
ACCOUNT_SIGNUP_FIELDS = ["username*", "password1*", "password2*"]
ACCOUNT_LOGIN_BY_CODE_ENABLED = True
ACCOUNT_FORMS = {
    "request_login_code": "accounts.forms.StyledRequestLoginCodeForm",
    "confirm_login_code": "accounts.forms.StyledConfirmLoginCodeForm",
}
ACCOUNT_EMAIL_VERIFICATION = "none"  # admin-entered emails are trusted
ACCOUNT_PREVENT_ENUMERATION = False  # internal tool: friendly "unknown email" errors
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True
# Google app credentials come from SiteConfig via SocialAccountAdapter.list_apps
# (editable in Site Settings); only non-credential options live here.
SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"prompt": "select_account"},
    },
}

# SMTP settings come from SiteConfig at send time (Site Settings UI); the
# backend falls back to console output (codes in logs) when unconfigured.
# Env EMAIL_*/GOOGLE_OAUTH_* vars are only used to SEED SiteConfig on first run.
EMAIL_BACKEND = "accounts.email.DynamicEmailBackend"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

# Set SECURE_COOKIES=true when serving via HTTPS (e.g. behind the Cloudflare
# tunnel). Leave false for plain-HTTP local-network testing or logins break.
if os.getenv("SECURE_COOKIES", "false").lower() in ("1", "true", "yes"):
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

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

# Keep test-created uploads (clone/backup tests) out of the real media dir
if "test" in sys.argv:
    import tempfile
    MEDIA_ROOT = Path(tempfile.mkdtemp(prefix="ops-test-media-"))
    BACKUP_DIR = Path(tempfile.mkdtemp(prefix="ops-test-backups-"))

# Sized for the PDF room-layout upload flow
DATA_UPLOAD_MAX_MEMORY_SIZE = 60 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 60 * 1024 * 1024

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", str(BASE_DIR / "credentials.json"))

# In-app scheduled backups run inside the web process; enable/interval/keep
# live in SiteConfig (Site Settings UI). Only the destination path is env.
BACKUP_DIR = Path(os.getenv("BACKUP_DIR", BASE_DIR / "backups"))

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
