"""Ayudas de la suite de contrato que cada implementacion (doble o real) debe ofrecer.

La suite de contrato solo usa el puerto mas estos dos protocolos de PRUEBA. Con GLPI en
contenedor, `Tecnico` sera un cliente de la API que trabaja los tickets como una persona, y
`InyectorDeFallos` un proxy que corta o retrasa las respuestas. Las pruebas no cambian.
"""

from typing import Protocol

from jml.dominio.activos import ActivoAsignado, LicenciaAsignada
from jml.dominio.tipos import EstadoDeTicket


class Tecnico(Protocol):
    """Una persona de TI trabajando en GLPI."""

    def resolver(
        self,
        id_externo: str,
        con_solucion: bool = True,
        documentos: int = 0,
        estado: EstadoDeTicket = EstadoDeTicket.RESUELTO,
    ) -> None: ...

    def reabrir(self, id_externo: str) -> None: ...

    def asignar_activo(self, id_usuario: str, activo: ActivoAsignado) -> None: ...

    def asignar_licencia(self, id_usuario: str, licencia: LicenciaAsignada) -> None: ...

    def creaciones(self, clave: str) -> int:
        """Cuantos tickets existen realmente en GLPI con esa clave de idempotencia."""
        ...


class InyectorDeFallos(Protocol):
    def timeout_despues_de_crear(self) -> None:
        """La proxima escritura se aplica en GLPI pero la respuesta nunca llega."""
        ...

    def error_antes_de_crear(self) -> None: ...

    def respuesta_duplicada(self) -> None: ...

    def caida(self, llamadas: int) -> None:
        """Las proximas `llamadas` fallan por no disponibilidad."""
        ...
