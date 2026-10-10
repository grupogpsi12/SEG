"""Registrar una solicitud que queda pendiente de aprobacion (RF-07, RF-08, RF-09, RF-39)."""

from jml.aplicacion.casos._alta import DependenciasDeAlta, dar_de_alta
from jml.aplicacion.dtos import NuevaSolicitud, SolicitudRegistrada
from jml.aplicacion.puertos import UnidadDeTrabajo
from jml.dominio.colaborador import Colaborador
from jml.dominio.permisos import Actor
from jml.dominio.solicitud import ResultadoSolicitud, Solicitud
from jml.dominio.valores import CampoRestringido, SolicitudId


class RegistrarSolicitud:
    """El colaborador registra sus vacaciones o su renuncia; el jefe, un CDP o CSU de su equipo."""

    def __init__(self, dependencias: DependenciasDeAlta) -> None:
        self._dep = dependencias

    def ejecutar(self, e: NuevaSolicitud) -> SolicitudRegistrada:
        def fabrica(
            uow: UnidadDeTrabajo,
            sid: SolicitudId,
            actor: Actor,
            sujeto: Colaborador,
            restringido: CampoRestringido | None,
        ) -> ResultadoSolicitud:
            return Solicitud.registrar_pendiente(
                id=sid,
                actor=actor,
                sujeto=sujeto,
                tipo=e.tipo,
                subtipo=e.subtipo,
                fecha_efectiva=e.fecha_efectiva,
                datos=e.datos,
                restringido=restringido,
                ahora=self._dep.reloj.ahora(),
                solicitud_origen_id=e.solicitud_origen_id,
            )

        return dar_de_alta(self._dep, e, fabrica)
