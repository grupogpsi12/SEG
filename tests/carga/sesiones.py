"""Sesiones de Django para la medición de carga, en la base DESECHABLE de `infra/scripts/carga.sh`.

Equivalen a una persona que ya pasó el TOTP (ingreso.py guarda `usuario_id` e `inicio`). Los
usuarios son los del `Mundo` de las pruebas. Imprime {rol: clave de sesión} en JSON.
"""

import json

import django

django.setup()

from django.contrib.sessions.backends.db import SessionStore  # noqa: E402

from jml.adaptadores.entrada.web.vistas import SESION_INICIO, SESION_USUARIO  # noqa: E402
from jml.adaptadores.salida.reloj import RelojDelSistema  # noqa: E402

USUARIOS = {"tecnico": "u-tec-ad", "rrhh": "u-rrhh", "auditor": "u-aud"}


def crear() -> dict[str, str]:
    claves = {}
    for rol, usuario in USUARIOS.items():
        sesion = SessionStore()
        sesion[SESION_USUARIO] = usuario
        sesion[SESION_INICIO] = RelojDelSistema().ahora().timestamp()
        sesion.create()
        assert sesion.session_key is not None
        claves[rol] = sesion.session_key
    return claves


if __name__ == "__main__":
    print(json.dumps(crear()))
