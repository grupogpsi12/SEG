"""Ajustes de Django para las pruebas: secretos falsos en un directorio temporal y SQLite en memoria.

PostgreSQL llega con el adaptador de persistencia (2.3); aqui solo se prueba la configuracion,
el registro y la vista de salud, que no dependen del motor.
"""

import os
import tempfile
from pathlib import Path

_secretos = Path(tempfile.mkdtemp(prefix="jml-secretos-"))
(_secretos / "django_secret_key").write_text("clave-de-prueba-" + "x" * 50, encoding="utf-8")
(_secretos / "db_password").write_text("no-se-usa-en-pruebas", encoding="utf-8")
os.environ["JML_SECRETOS_DIR"] = str(_secretos)
os.environ.setdefault("DJANGO_ALLOWED_HOSTS", "testserver,app.localhost")

from config.settings import *  # noqa: E402, F403

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
# Las pruebas no corren `collectstatic`: el almacen con manifiesto se prueba en el contenedor.
STORAGES = {
    **STORAGES,  # noqa: F405
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
JML_PROXIES_CONFIABLES = ["10.20.40.2"]
WHITENOISE_USE_FINDERS = True  # sin collectstatic; en el contenedor sirve desde STATIC_ROOT
STATIC_ROOT = Path(tempfile.mkdtemp(prefix="jml-static-"))
