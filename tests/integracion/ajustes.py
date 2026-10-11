"""Ajustes para las pruebas de integracion contra PostgreSQL real (contenedor o Supabase de pruebas).

Uso (la clave sale del archivo de secretos, no del entorno ni del repositorio):

    JML_PG_HOST=aws-0-us-east-1.pooler.supabase.com JML_PG_USUARIO=app_backend.<proyecto> \
    JML_PG_CLAVE="$(cat secrets/db_password)" JML_PG_CA=secrets/supabase_ca_crt \
        pytest --ds tests.integracion.ajustes tests/integracion

Se conecta como `app_backend` (nunca `postgres`) y trabaja en el esquema `app_test`, que el
conftest crea y borra: asi se prueba lo que de verdad podra hacer la aplicacion en produccion.
"""

import os

from tests.adaptadores.ajustes import *  # noqa: F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": os.environ["JML_PG_HOST"],
        "PORT": os.environ.get("JML_PG_PUERTO", "5432"),
        "NAME": os.environ.get("JML_PG_BASE", "postgres"),
        "USER": os.environ.get("JML_PG_USUARIO", "app_backend"),
        "PASSWORD": os.environ["JML_PG_CLAVE"],
        "OPTIONS": {
            "sslmode": "verify-full",
            "sslrootcert": os.environ["JML_PG_CA"],
            # Si la red corta una corrida, el servidor cierra la transaccion huerfana sola y no
            # deja bloqueado app_test para la siguiente (docs/spikes/supabase.md).
            "options": f"-c search_path={os.environ.get('JML_PG_ESQUEMA', 'app_test')}"
            " -c idle_in_transaction_session_timeout=60000",
        },
    }
}
