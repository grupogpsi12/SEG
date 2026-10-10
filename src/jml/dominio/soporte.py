"""Soporte de vinculacion (RF-39, RF-40, RD-12, ADR-021). Se valida sobre los bytes recibidos."""

from dataclasses import dataclass, replace

from jml.dominio.errores import OperacionNoPermitida, SoporteInvalido
from jml.dominio.tipos import EstadoDeSoporte
from jml.dominio.valores import MAX_SOPORTE_BYTES, NombreDeSoporteSaneado, Sha256, SolicitudId

FIRMA_PDF = b"%PDF-"


@dataclass(frozen=True, slots=True)
class SoporteValidado:
    nombre: NombreDeSoporteSaneado
    tamano: int
    sha256: Sha256


def validar_soporte(contenido: bytes, nombre_original: str) -> SoporteValidado:
    """Extension `.pdf`, firma `%PDF-` y como maximo 20 MiB (S-12). Nunca confia en el MIME."""
    nombre = NombreDeSoporteSaneado.sanear(nombre_original)
    if not nombre.valor.lower().endswith(".pdf"):
        raise SoporteInvalido("la extension debe ser .pdf")
    if len(contenido) == 0:
        raise SoporteInvalido("el archivo esta vacio")
    if len(contenido) > MAX_SOPORTE_BYTES:
        raise SoporteInvalido("supera los 20 MB")
    if not contenido.startswith(FIRMA_PDF):
        raise SoporteInvalido("el contenido no es un PDF")
    return SoporteValidado(nombre, len(contenido), Sha256.de_bytes(contenido))


@dataclass(frozen=True, slots=True)
class Soporte:
    solicitud_id: SolicitudId
    nombre_original: NombreDeSoporteSaneado
    tamano: int
    sha256: Sha256
    nombre_almacenado: str
    estado: EstadoDeSoporte = EstadoDeSoporte.PENDIENTE
    id_documento_glpi: str | None = None

    @classmethod
    def pendiente(
        cls, solicitud_id: SolicitudId, validado: SoporteValidado, nombre_almacenado: str
    ) -> "Soporte":
        return cls(
            solicitud_id, validado.nombre, validado.tamano, validado.sha256, nombre_almacenado
        )

    def subido(self, id_documento_glpi: str) -> "Soporte":
        if self.estado is not EstadoDeSoporte.PENDIENTE:
            raise OperacionNoPermitida(f"un soporte '{self.estado.value}' no se sube")
        return replace(self, estado=EstadoDeSoporte.SUBIDO, id_documento_glpi=id_documento_glpi)

    def descartado(self) -> "Soporte":
        if self.estado is not EstadoDeSoporte.PENDIENTE:
            raise OperacionNoPermitida(f"un soporte '{self.estado.value}' no se descarta")
        return replace(self, estado=EstadoDeSoporte.DESCARTADO)
