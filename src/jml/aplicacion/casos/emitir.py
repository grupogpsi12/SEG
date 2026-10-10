"""Emitir en un solo paso (RF-13) y emitir por excepcion (SRS 4.1, S-08)."""

from jml.aplicacion.casos._alta import DependenciasDeAlta, dar_de_alta
from jml.aplicacion.dtos import NuevaSolicitud, SolicitudRegistrada
from jml.aplicacion.puertos import UnidadDeTrabajo
from jml.dominio.colaborador import Colaborador
from jml.dominio.permisos import Actor
from jml.dominio.solicitud import ResultadoSolicitud, Solicitud
from jml.dominio.tipos import Rol
from jml.dominio.valores import CampoRestringido, SolicitudId


class EmitirSolicitud:
    """RRHH registra y emite cualquier tipo de evento, con justificacion obligatoria."""

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
            return Solicitud.emitir_directo(
                id=sid,
                actor=actor,
                sujeto=sujeto,
                tipo=e.tipo,
                subtipo=e.subtipo,
                fecha_efectiva=e.fecha_efectiva,
                datos=e.datos,
                restringido=restringido,
                justificacion=e.justificacion,
                ahora=self._dep.reloj.ahora(),
                solicitud_origen_id=e.solicitud_origen_id,
            )

        return dar_de_alta(self._dep, e, fabrica)


class EmitirPorExcepcion:
    """El Administrador emite cuando el sujeto es una persona de RRHH (RF-15, S-08).

    Emitir no es aprobar: es un caso de uso aparte, siempre justificado y con su propio evento
    de auditoria. El Administrador sigue sin poder aprobar nada.
    """

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
            sujeto_es_rrhh = Rol.RRHH in uow.usuarios.roles_de_colaborador(sujeto.id)
            return Solicitud.emitir_por_excepcion(
                id=sid,
                actor=actor,
                sujeto=sujeto,
                sujeto_es_rrhh=sujeto_es_rrhh,
                tipo=e.tipo,
                subtipo=e.subtipo,
                fecha_efectiva=e.fecha_efectiva,
                datos=e.datos,
                restringido=restringido,
                justificacion=e.justificacion,
                ahora=self._dep.reloj.ahora(),
                solicitud_origen_id=e.solicitud_origen_id,
            )

        return dar_de_alta(self._dep, e, fabrica)
