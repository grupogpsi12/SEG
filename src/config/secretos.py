"""Lectura de secretos montados como archivos (ADR-009, RS-06, invariante 10).

En Azure, la VM los baja de Key Vault a un tmpfs en /run/secrets; en local, son archivos no
versionados. Los mensajes de error nombran el secreto, nunca su contenido.
"""

import os
import re
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

_NOMBRE_VALIDO = re.compile(r"^[a-z0-9_]+$")  # sin separadores: no hay recorrido de rutas


def directorio_de_secretos() -> Path:
    return Path(os.environ.get("JML_SECRETOS_DIR", "/run/secrets"))


def ruta_de_secreto(nombre: str) -> Path:
    if not _NOMBRE_VALIDO.fullmatch(nombre):
        raise ImproperlyConfigured(f"nombre de secreto invalido: {nombre!r}")
    return directorio_de_secretos() / nombre


def leer_secreto(nombre: str) -> str:
    ruta = ruta_de_secreto(nombre)
    try:
        valor = ruta.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        raise ImproperlyConfigured(f"falta el secreto '{nombre}' en {ruta.as_posix()}") from None
    if not valor:
        raise ImproperlyConfigured(f"el secreto '{nombre}' esta vacio")
    return valor


def lista_de_entorno(variable: str) -> list[str]:
    return [v.strip() for v in os.environ.get(variable, "").split(",") if v.strip()]
