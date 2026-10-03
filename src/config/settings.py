from __future__ import annotations

import os
from pathlib import Path

from .environment import env_or_file


BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


def env_int(name: str, default: int = 0) -> int:
    return int(os.getenv(name, str(default)).strip())


SECRET_KEY = env_or_file("DJANGO_SECRET_KEY", "unsafe-development-key")
DEBUG = env_bool("DJANGO_DEBUG")
if not DEBUG and SECRET_KEY == "unsafe-development-key":
    raise RuntimeError("DJANGO_SECRET_KEY must be configured when debug is disabled")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")
SITE_ORIGIN = os.getenv("DJANGO_SITE_ORIGIN", "http://127.0.0.1:18574").rstrip("/")
PUBLIC_SITE_ORIGIN = os.getenv("DJANGO_PUBLIC_SITE_ORIGIN", SITE_ORIGIN).rstrip("/")
AGENT_SITE_ORIGIN = os.getenv("DJANGO_AGENT_SITE_ORIGIN", SITE_ORIGIN).rstrip("/")
SECURITY_LAB_ORIGIN = os.getenv("TTC_SECURITY_LAB_ORIGIN", "https://security.teachthecompany.com").rstrip("/")
PUBLIC_MANUALS_REPOSITORY_URL = os.getenv(
    "TTC_PUBLIC_MANUALS_REPOSITORY_URL",
    "https://gitlab.finnandre.no/finnandrehotvedt/teach-the-company-public-manuals",
).strip()
SOURCE_REPOSITORY_URL = os.getenv(
    "TTC_SOURCE_REPOSITORY_URL",
    "https://gitlab.finnandre.no/finnandrehotvedt/teach-the-company",
).strip()
GITHUB_SOURCE_REPOSITORY_URL = os.getenv(
    "TTC_GITHUB_SOURCE_REPOSITORY_URL",
    "https://github.com/finnandrehotvedt/teach-the-company",
).strip()
PUBLIC_HOSTS = set(env_list("TTC_PUBLIC_HOSTS", "teachthecompany.com,www.teachthecompany.com"))
AGENT_HOSTS = set(env_list("TTC_AGENT_HOSTS", "agent.teachthecompany.com"))
AGENT_SITE_LIVE = env_bool("TTC_AGENT_SITE_LIVE")
SECURITY_LAB_LIVE = env_bool("TTC_SECURITY_LAB_LIVE")
ENFORCE_HOST_ROUTES = env_bool("TTC_ENFORCE_HOST_ROUTES")
TRUST_PROXY_HEADERS = env_bool("DJANGO_TRUST_PROXY_HEADERS")
TRUSTED_PROXY_IPS = set(env_list("DJANGO_TRUSTED_PROXY_IPS"))
OPEN_SIGNUP = env_bool("TTC_OPEN_SIGNUP")
AGENT_BACKEND = os.getenv("TTC_AGENT_BACKEND", "evidence").strip().lower()
AGENT_API_URL = os.getenv("TTC_AGENT_API_URL", "").strip()
AGENT_MODEL = os.getenv("TTC_AGENT_MODEL", "local-model").strip()
AGENT_API_KEY = env_or_file("TTC_AGENT_API_KEY", "")
AGENT_TIMEOUT_SECONDS = max(2, min(env_int("TTC_AGENT_TIMEOUT_SECONDS", 180), 300))
AGENT_CONTEXT_TOKENS = max(2048, min(env_int("TTC_AGENT_CONTEXT_TOKENS", 8192), 32768))
AGENT_CONTEXT_CHAR_LIMIT = max(8000, min(env_int("TTC_AGENT_CONTEXT_CHAR_LIMIT", 48000), 160000))
AGENT_MAX_OUTPUT_TOKENS = max(128, min(env_int("TTC_AGENT_MAX_OUTPUT_TOKENS", 768), 4096))
FETCH_PROXY_URL = os.getenv("TTC_FETCH_PROXY_URL", "").strip()
FETCH_PROXY_SOCKET = os.getenv("TTC_FETCH_PROXY_SOCKET", "").strip()

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "academy",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "academy.middleware.HostRoutingMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
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
                "academy.context_processors.site_context",
            ],
        },
    }
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

if os.getenv("DATABASE_ENGINE") == "sqlite":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.getenv("SQLITE_PATH", str(BASE_DIR / "test.sqlite3")),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB", "teach_the_company"),
            "USER": os.getenv("POSTGRES_USER", "teach_the_company"),
            "PASSWORD": env_or_file("POSTGRES_PASSWORD"),
            "HOST": os.getenv("POSTGRES_HOST", "db"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
            "CONN_MAX_AGE": 60,
            "CONN_HEALTH_CHECKS": True,
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en"
TIME_ZONE = "Europe/Oslo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_ROOT = Path(os.getenv("TTC_PRIVATE_DATA_ROOT", "/app/private-data"))
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT")
SECURE_HSTS_SECONDS = env_int("DJANGO_SECURE_HSTS_SECONDS")
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
X_FRAME_OPTIONS = "DENY"
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 365
SESSION_SAVE_EVERY_REQUEST = True
CSRF_COOKIE_SECURE = env_bool("DJANGO_SECURE_COOKIES")
SESSION_COOKIE_SECURE = env_bool("DJANGO_SECURE_COOKIES")
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https") if TRUST_PROXY_HEADERS else None

CHALLENGE_LIMIT_PER_HOUR = 20
START_LIMIT_PER_HOUR = 3
ACCESS_REQUEST_LIMIT_PER_HOUR = 3
ACCESS_REQUEST_LIMIT_PER_RECIPIENT_PER_DAY = 3
PUBLIC_SUGGESTION_LIMIT_PER_HOUR = 3
TRANSACTIONAL_NOTIFICATIONS_ENABLED = env_bool("TTC_TRANSACTIONAL_NOTIFICATIONS_ENABLED")
TRANSACTIONAL_EMAIL_DELIVERY_ENABLED = env_bool("TTC_TRANSACTIONAL_EMAIL_DELIVERY_ENABLED")
TRANSACTIONAL_EMAIL_DAILY_CAP = max(1, min(env_int("TTC_TRANSACTIONAL_EMAIL_DAILY_CAP", 100), 1000))
TRANSACTIONAL_EMAIL_RECIPIENT_DAILY_CAP = max(1, min(env_int("TTC_TRANSACTIONAL_EMAIL_RECIPIENT_DAILY_CAP", 4), 10))
TRANSACTIONAL_EMAIL_SOURCE_DAILY_CAP = max(1, min(env_int("TTC_TRANSACTIONAL_EMAIL_SOURCE_DAILY_CAP", 4), 20))
TRANSACTIONAL_EMAIL_MAX_ATTEMPTS = max(1, min(env_int("TTC_TRANSACTIONAL_EMAIL_MAX_ATTEMPTS", 3), 5))
TRANSACTIONAL_EMAIL_FROM = os.getenv("TTC_TRANSACTIONAL_EMAIL_FROM", "teachthecompany@example.invalid").strip()
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = os.getenv("EMAIL_HOST", "localhost")
EMAIL_PORT = env_int("EMAIL_PORT", 25)
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS")
EMAIL_HOST_USER = env_or_file("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env_or_file("EMAIL_HOST_PASSWORD", "")
EMAIL_TIMEOUT = max(1, min(env_int("EMAIL_TIMEOUT", 10), 60))
STUDIO_SESSION_KEY = "ttc_owned_projects"
