"""Ajustes de Django. Ningun secreto vive aqui: todos salen de /run/secrets (invariante 10)."""

import os
from pathlib import Path

from config.secretos import leer_secreto, lista_de_entorno, ruta_de_secreto

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = leer_secreto("django_secret_key")
DEBUG = os.environ.get("DJANGO_DEBUG") == "1"
ALLOWED_HOSTS = lista_de_entorno("DJANGO_ALLOWED_HOSTS")  # explicito; vacio = ninguno

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
]

MIDDLEWARE = [
    "jml.adaptadores.entrada.web.middleware.correlacion",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "jml.adaptadores.entrada.web.middleware.politica_de_contenido",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": ["django.template.context_processors.request"]},
    }
]

# Supabase por el session pooler (puerto 5432, admite prepared statements; lessons n.9), con
# el rol dedicado app_backend (nunca postgres) y TLS verificando el certificado (RI-03).
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": os.environ.get("JML_DB_HOST", ""),
        "PORT": "5432",
        "NAME": os.environ.get("JML_DB_NAME", "postgres"),
        "USER": "app_backend",
        "PASSWORD": leer_secreto("db_password"),
        "OPTIONS": {
            "sslmode": "verify-full",
            "sslrootcert": str(ruta_de_secreto("supabase_ca_crt")),
            "options": "-c search_path=app",  # esquema no expuesto en la Data API (RD-10)
        },
    }
}

LANGUAGE_CODE = "es-co"
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- seguridad (RS-04, RS-07) -----------------------------------------------------------------
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
# HSTS, Referrer-Policy y X-Content-Type-Options las pone BunkerWeb: una sola fuente por cabecera.
SECURE_HSTS_SECONDS = 0
SECURE_CONTENT_TYPE_NOSNIFF = False
SECURE_REFERRER_POLICY = None
# Estos avisos de `check --deploy` cubren lo que hace BunkerWeb, no Django: HSTS, nosniff y
# Referrer-Policy (RS-07, una sola fuente por cabecera) y la redireccion a HTTPS (RS-01).
SILENCED_SYSTEM_CHECKS = ["security.W004", "security.W006", "security.W008", "security.W022"]
POLITICA_DE_CONTENIDO = (
    "default-src 'self'; script-src 'self'; object-src 'none'; frame-ancestors 'none'"
)

# --- logs JSON con correlation_id y sin campos prohibidos (RS-09) ------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "correlacion": {"()": "jml.adaptadores.registro.FiltroDeCorrelacion"},
        "prohibidos": {"()": "jml.adaptadores.registro.FiltroDeCamposProhibidos"},
    },
    "formatters": {"json": {"()": "jml.adaptadores.registro.FormatoJSON"}},
    "handlers": {
        "consola": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "filters": ["correlacion", "prohibidos"],
        }
    },
    "root": {"handlers": ["consola"], "level": os.environ.get("JML_NIVEL_DE_LOG", "INFO")},
}
