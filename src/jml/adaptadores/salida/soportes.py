"""Adaptador de AlmacenDeSoportes sobre el volumen `noexec` compartido por web y worker (ADR-021).

RD-12 y RS-17: nombre aleatorio sin extension, fuera de la raiz web, permisos solo para el
duenio. El nombre que llega de la base se valida antes de tocar el disco (recorrido de rutas).
La aplicacion nunca abre, procesa ni sirve el archivo: lo guarda, se lo da al worker y lo borra.
"""

import os
import re
import secrets
from pathlib import Path

from jml.aplicacion.puertos import SoporteNoDisponible

_NOMBRE = re.compile(r"^[0-9a-f]{32}$")


class AlmacenDeSoportesEnDisco:
    def __init__(self, directorio: Path) -> None:
        self._dir = directorio

    def _ruta(self, nombre: str) -> Path:
        if not _NOMBRE.fullmatch(nombre):
            raise SoporteNoDisponible(f"nombre de soporte invalido: {nombre!r}")
        return self._dir / nombre

    def guardar(self, contenido: bytes) -> str:
        nombre = secrets.token_hex(16)
        # 'x': falla si el nombre ya existiera; 0o600: solo el duenio del proceso lo lee.
        descriptor = os.open(self._ruta(nombre), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as archivo:
            archivo.write(contenido)
        return nombre

    def leer(self, nombre: str) -> bytes:
        try:
            return self._ruta(nombre).read_bytes()
        except FileNotFoundError:
            raise SoporteNoDisponible(nombre) from None

    def borrar(self, nombre: str) -> None:
        """Idempotente. Un nombre no aleatorio no puede estar en el volumen: no se toca nada."""
        if _NOMBRE.fullmatch(nombre):
            self._ruta(nombre).unlink(missing_ok=True)

    def existe(self, nombre: str) -> bool:
        try:
            return self._ruta(nombre).is_file()
        except SoporteNoDisponible:
            return False
