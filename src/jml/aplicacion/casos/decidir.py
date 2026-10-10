"""Aprobar, rechazar y cancelar (RF-11, RF-12, RF-15, CA-02).

La decision, el cambio de estado, los tickets en la bandeja y la auditoria se escriben en UNA
unidad de trabajo: si falla cualquier paso, no queda decision ni bandeja (CA-02).
"""

from dataclasses import dataclass

from jml.aplicacion.bandeja import EstadoDeEntrada
from jml.aplicacion.casos._emision import (
    emitir_tickets,
    guardar_decision,
    marcar_otras_para_revision,
    registrar_eventos,
)
from jml.aplicacion.dtos import ResultadoDeDecision
from jml.aplicacion.puertos import AlmacenDeSoportes, Reloj, Repositorios, UnidadDeTrabajo
from jml.dominio.errores import NoAutorizado, NoEncontrado
from jml.dominio.permisos import Actor
from jml.dominio.solicitud import Solicitud
from jml.dominio.tipos import EstadoDeSoporte, EstadoSolicitud, TipoEvento
from jml.dominio.valores import CalendarioHabil, SolicitudId


@dataclass(frozen=True, slots=True)
class DependenciasDeDecision:
    repos: Repositorios
    reloj: Reloj
    calendario: CalendarioHabil
    soportes: AlmacenDeSoportes


def _actor(uow: UnidadDeTrabajo, usuario_id: str) -> Actor:
    actor = uow.usuarios.actor_de(usuario_id)
    if actor is None:
        raise NoAutorizado("decidir", "el usuario no existe o esta inactivo")
    return actor


def _solicitud(uow: UnidadDeTrabajo, solicitud_id: SolicitudId) -> Solicitud:
    s = uow.solicitudes.obtener(solicitud_id)
    if s is None:
        raise NoEncontrado("solicitud", solicitud_id.valor)
    return s


def _descartar_soporte(uow: UnidadDeTrabajo, solicitud_id: SolicitudId) -> str | None:
    """RF-40: si la solicitud no sigue, el soporte pendiente se descarta sin subirse.

    Devuelve el nombre de la copia para borrarla DESPUES de confirmar la transaccion.
    """
    soporte = uow.soportes.obtener(solicitud_id)
    if soporte is None or soporte.estado is not EstadoDeSoporte.PENDIENTE:
        return None
    uow.soportes.guardar(soporte.descartado())
    return soporte.nombre_almacenado


class AprobarSolicitud:
    def __init__(self, dependencias: DependenciasDeDecision) -> None:
        self._dep = dependencias

    def ejecutar(
        self, usuario_id: str, solicitud_id: SolicitudId, justificacion: str | None = None
    ) -> ResultadoDeDecision:
        ahora = self._dep.reloj.ahora()
        with self._dep.repos.unidad_de_trabajo() as uow:
            actor = _actor(uow, usuario_id)
            s = _solicitud(uow, solicitud_id)
            colaborador = uow.colaboradores.obtener(s.colaborador_id)
            if colaborador is None:
                raise NoEncontrado("colaborador", s.colaborador_id)
            r = s.aprobar(actor, justificacion, ahora)
            uow.solicitudes.guardar(r.solicitud)
            guardar_decision(uow, r.decision)
            registrar_eventos(uow, actor.usuario_id, r.eventos)
            final, encolados = emitir_tickets(
                uow, r.solicitud, colaborador, actor.usuario_id, ahora, self._dep.calendario
            )
            if final.tipo is TipoEvento.EMG:
                marcar_otras_para_revision(uow, final, actor.usuario_id)
            return ResultadoDeDecision(final.id, final.estado, encolados)


class RechazarSolicitud:
    def __init__(self, dependencias: DependenciasDeDecision) -> None:
        self._dep = dependencias

    def ejecutar(
        self, usuario_id: str, solicitud_id: SolicitudId, justificacion: str | None
    ) -> ResultadoDeDecision:
        ahora = self._dep.reloj.ahora()
        with self._dep.repos.unidad_de_trabajo() as uow:
            actor = _actor(uow, usuario_id)
            s = _solicitud(uow, solicitud_id)
            r = s.rechazar(actor, justificacion, ahora)
            uow.solicitudes.guardar(r.solicitud)
            guardar_decision(uow, r.decision)
            registrar_eventos(uow, actor.usuario_id, r.eventos)
            copia = _descartar_soporte(uow, solicitud_id)
        if copia is not None:
            self._dep.soportes.borrar(copia)
        return ResultadoDeDecision(r.solicitud.id, r.solicitud.estado)


class CancelarSolicitud:
    """RF-11: el solicitante cancela una pendiente; RRHH, una aprobada sin tickets creados."""

    def __init__(self, dependencias: DependenciasDeDecision) -> None:
        self._dep = dependencias

    def ejecutar(
        self, usuario_id: str, solicitud_id: SolicitudId, justificacion: str | None = None
    ) -> ResultadoDeDecision:
        ahora = self._dep.reloj.ahora()
        with self._dep.repos.unidad_de_trabajo() as uow:
            actor = _actor(uow, usuario_id)
            s = _solicitud(uow, solicitud_id)
            if s.estado is EstadoSolicitud.PENDIENTE_APROBACION:
                r = s.cancelar_por_solicitante(actor, ahora)
            else:
                r = s.cancelar_por_rrhh(actor, justificacion, ahora)
            uow.solicitudes.guardar(r.solicitud)
            guardar_decision(uow, r.decision)
            registrar_eventos(uow, actor.usuario_id, r.eventos)
            for entrada in uow.bandeja.de_solicitud(solicitud_id):
                if entrada.estado is EstadoDeEntrada.PENDIENTE:
                    uow.bandeja.guardar(entrada.descartada())
            copia = _descartar_soporte(uow, solicitud_id)
        if copia is not None:
            self._dep.soportes.borrar(copia)
        return ResultadoDeDecision(r.solicitud.id, r.solicitud.estado)
