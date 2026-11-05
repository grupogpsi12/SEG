"""Doble en memoria de `AdministradorDeCuentas`: la segunda implementacion del puerto (ADR-035)."""

import uuid
from collections.abc import Mapping

from jml.aplicacion.puertos import CuentaCreada, CuentaRechazada, IdentidadNoDisponible


class CuentasEnMemoria:
    def __init__(self) -> None:
        self.correo_de: dict[str, str] = {}
        self.baneadas: set[str] = set()
        self.caido = False

    def _exigir(self, usuario_id: str) -> None:
        if self.caido:
            raise IdentidadNoDisponible("simulado")
        if usuario_id not in self.correo_de:
            raise CuentaRechazada("user_not_found")

    def crear(self, correo: str) -> CuentaCreada:
        if self.caido:
            raise IdentidadNoDisponible("simulado")
        if correo.strip().lower() in self.correo_de.values():
            raise CuentaRechazada("email_exists")
        uid = str(uuid.uuid4())
        self.correo_de[uid] = correo.strip().lower()
        return CuentaCreada(uid, "contrasena-inicial-" + uid[:8])

    def desactivar(self, usuario_id: str) -> None:
        self._exigir(usuario_id)
        self.baneadas.add(usuario_id)

    def reactivar(self, usuario_id: str) -> None:
        self._exigir(usuario_id)
        self.baneadas.discard(usuario_id)

    def eliminar(self, usuario_id: str) -> None:
        self._exigir(usuario_id)
        del self.correo_de[usuario_id]
        self.baneadas.discard(usuario_id)

    def correos(self) -> Mapping[str, str]:
        if self.caido:
            raise IdentidadNoDisponible("simulado")
        return dict(self.correo_de)
