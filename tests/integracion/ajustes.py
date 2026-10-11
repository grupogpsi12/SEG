"""Ajustes para las pruebas de integracion contra PostgreSQL real (contenedor o Supabase de pruebas).

Uso (con la misma version mayor de PostgreSQL que Supabase, SRS 3.5):

    JML_PG_HOST=localhost JML_PG_USUARIO=app_backend JML_PG_CLAVE=... \
        pytest --ds tests.integracion.ajustes tests/integracion tests/contratos -k "orm or integracion"

El usuario de la conexion debe ser `app_backend` y duenio del esquema `app` (ver la migracion
0002): asi se prueba lo que de verdad podra hacer la aplicacion en produccion.
"""

import os

from tests.adaptadores.ajustes import *  # noqa: F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": os.environ["JML_PG_HOST"],
        "PORT": os.environ.get("JML_PG_PUERTO", "5432"),
        "NAME": os.environ.get("JML_PG_BASE", "jml"),
        "USER": os.environ.get("JML_PG_USUARIO", "app_backend"),
        "PASSWORD": os.environ["JML_PG_CLAVE"],
        "OPTIONS": {"options": "-c search_path=app"},
        "TEST": {"NAME": os.environ.get("JML_PG_BASE_PRUEBAS", "jml_pruebas")},
    }
}
