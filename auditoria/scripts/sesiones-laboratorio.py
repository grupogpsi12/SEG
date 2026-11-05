"""F6: sesiones de Django para los escáneres autenticados, en el stack LOCAL de pruebas.

    docker compose -f infra/compose.yaml -f infra/compose.local.yaml run --rm --no-deps -T \
      -v "$PWD:/repo:ro" -w /repo -e PYTHONPATH=/repo web python auditoria/scripts/sesiones-laboratorio.py

Equivale a una persona que ya pasó el TOTP: guarda `usuario_id` e `inicio`, como `ingreso.py`.
Toma, para cada rol, una cuenta de prueba que tenga SOLO ese rol (los roles incompatibles se
rechazan). Imprime {rol: clave de sesión} y un colaborador y una solicitud de ejemplo. Las claves
valen lo que dura la sesión (30 minutos de inactividad) y se borran al restaurar la base.
"""

import json

import django

django.setup()

from django.contrib.auth.models import User  # noqa: E402
from django.contrib.sessions.backends.db import SessionStore  # noqa: E402

from jml.adaptadores.entrada.web.vistas import SESION_INICIO, SESION_USUARIO  # noqa: E402
from jml.adaptadores.salida.persistencia import models as m  # noqa: E402
from jml.adaptadores.salida.reloj import RelojDelSistema  # noqa: E402

ROLES = {
    "rrhh": "rrhh",
    "tecnico": "tecnico_ad",
    "auditor": "auditor",
    "administrador": "administrador",
    "solicitante": "solicitante",
}


def cuenta_de(grupo: str) -> str:
    for u in User.objects.filter(groups__name=grupo, is_active=True).order_by("username"):
        if u.groups.count() == 1:
            return u.username
    raise SystemExit(f"no hay una cuenta de prueba con solo el rol {grupo}")


def main() -> None:
    claves = {}
    for nombre, grupo in ROLES.items():
        sesion = SessionStore()
        sesion[SESION_USUARIO] = cuenta_de(grupo)
        sesion[SESION_INICIO] = RelojDelSistema().ahora().timestamp()
        sesion.create()
        assert sesion.session_key is not None
        claves[nombre] = sesion.session_key
    colaborador = m.Colaborador.objects.order_by("pk").first()
    solicitud = m.Solicitud.objects.order_by("pk").first()
    print(
        json.dumps(
            {
                "sesiones": claves,
                "colaborador": colaborador.pk if colaborador else None,
                "solicitud": solicitud.pk if solicitud else None,
            }
        )
    )


main()
