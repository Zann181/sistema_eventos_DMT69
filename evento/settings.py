import os
import socket
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-w!+v6uela@#b+$)8^@95n1f1v&8b(*txblina)i2rqorgkf()w",
)

DEBUG = os.environ.get("DJANGO_DEBUG", "True").lower() == "true"


def _detect_local_ip():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("10.255.255.255", 1))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def _build_allowed_hosts():
    hosts = {
        "127.0.0.1",
        "localhost",
        _detect_local_ip(),
        ".ngrok-free.app",
    }
    env_hosts = os.environ.get("DJANGO_ALLOWED_HOSTS", "")
    hosts.update(host.strip() for host in env_hosts.split(",") if host.strip())
    if DEBUG:
        hosts.update({"0.0.0.0"})
    return sorted(hosts)


ALLOWED_HOSTS = _build_allowed_hosts()


def _build_csrf_trusted_origins():
    local_ip = _detect_local_ip()
    origins = {
        "https://*.ngrok-free.app",
        "https://*.ngrok.io",
        "http://127.0.0.1:8000",
        "https://127.0.0.1:8000",
        "http://localhost:8000",
        "https://localhost:8000",
        f"http://{local_ip}:8000",
        f"https://{local_ip}:8000",
    }
    env_origins = os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "")
    origins.update(origin.strip() for origin in env_origins.split(",") if origin.strip())
    return sorted(origins)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_extensions",
    "branches",
    "events",
    "identity",
    "attendees",
    "catalog",
    "inventory",
    "sales",
    "media_assets",
    "shared_ui",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "identity.middleware.CurrentBranchMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "evento.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "identity.context_processors.branch_context",
            ],
        },
    },
]

WSGI_APPLICATION = "evento.wsgi.application"

if "test" in sys.argv:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "test_db.sqlite3",
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": os.environ.get("DB_ENGINE", "django.db.backends.mysql"),
            "NAME": os.environ.get("DB_NAME", "evento_db_clean_20260316"),
            "USER": os.environ.get("DB_USER", "root"),
            "PASSWORD": os.environ.get("DB_PASSWORD", "12345678"),
            "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
            "PORT": os.environ.get("DB_PORT", "3306"),
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es-es"
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"

CSRF_TRUSTED_ORIGINS = _build_csrf_trusted_origins()
CSRF_FAILURE_VIEW = "shared_ui.views.csrf_failure"

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "True").lower() == "true"
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "zamamotas@gmail.com")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "uxxg iyhg rgsb xbmw")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "EVENT <zamamotas@gmail.com>")
EMAIL_MEDIA_BASE_URL = os.environ.get("EMAIL_MEDIA_BASE_URL", "")
WHATSAPP_MEDIA_BASE_URL = os.environ.get("WHATSAPP_MEDIA_BASE_URL", EMAIL_MEDIA_BASE_URL)
