"""Listas para las vistas (ADR-025): mis solicitudes, bandeja de RRHH y subordinados del jefe.

Devuelven DTOs sin campos restringidos. Los permisos se verifican aqui y no solo en la vista:
una vista que olvide el chequeo no abre la informacion (RF-03).
"""

from collections.abc import Sequence
from dataclasses import fields, replace
from datetime import datetime
from enum import Enum

from jml.aplicacion.dtos import (
    AvanceDeSolicitud,
    DetalleDeSolicitud,
    EstadoDeTicketDeSolicitud,
    FilaDeSolicitud,
    OpcionDeColaborador,
    PaginaDeSolicitudes,
    PerfilDeUsuario,
)
from jml.aplicacion.puertos import Repositorios, UnidadDeTrabajo
from jml.dominio.auditoria import EventoDeAuditoria
from jml.dominio.errores import DatoInvalido, NoAutorizado, NoEncontrado
from jml.dominio.permisos import (
    Actor,
    puede_reintentar_emision,
    puede_ver_restringidos,
    puede_ver_solicitud,
)
from jml.dominio.resolucion import ticket_resuelto
from jml.dominio.solicitud import Solicitud
from jml.dominio.tickets import TicketSeguido
from jml.dominio.tipos import EstadoSolicitud, Rol
from jml.dominio.valores import BOGOTA, Documento, SolicitudId

TAMANO_DE_PAGINA = 50  # ADR-030, como la auditoria


def _actor(uow: UnidadDeTrabajo, usuario_id: str) -> Actor:
    actor = uow.usuarios.actor_de(usuario_id)
    if actor is None:
        raise NoAutorizado("consultar", "el usuario no existe o esta inactivo")
    return actor


def _fila(uow: UnidadDeTrabajo, s: Solicitud, usuario_id: str) -> FilaDeSolicitud:
    c = uow.colaboradores.obtener(s.colaborador_id)
    pendiente = s.estado is EstadoSolicitud.PENDIENTE_APROBACION
    return FilaDeSolicitud(
        id=s.id,
        tipo=s.tipo,
        estado=s.estado,
        fecha_efectiva=s.fecha_efectiva,
        creada_en=s.creada_en,
        colaborador_id=s.colaborador_id,
        colaborador_nombre=c.nombre_completo if c is not None else s.colaborador_id,
        para_revision=s.para_revision,
        cancelable=pendiente and s.solicitante_id == usuario_id,
    )


_SIN_AVANCE = AvanceDeSolicitud(0, 0, None)


def _avance(tickets: Sequence[TicketSeguido]) -> AvanceDeSolicitud:
    """RF-11: lo mismo que decide el cierre (RF-26). Solo cambia con la sincronizacion."""
    de_cierre = [t for t in tickets if t.ticket.bloquea_el_cierre]
    vistos = [t.observacion.observada_en for t in tickets if t.observacion is not None]
    return AvanceDeSolicitud(
        sum(ticket_resuelto(t) for t in de_cierre), len(de_cierre), max(vistos, default=None)
    )


class MisSolicitudes:
    """RF-11: el solicitante consulta las que registro, de la mas reciente a la mas antigua.

    ADR-030: por paginas. RRHH emite cientos al ano y la lista entera hacia lenta cada vista.
    """

    def __init__(self, repos: Repositorios, tamano: int = TAMANO_DE_PAGINA) -> None:
        self._repos = repos
        self._tamano = tamano

    def ejecutar(self, usuario_id: str, pagina: int = 1) -> PaginaDeSolicitudes:
        if pagina < 1:
            raise DatoInvalido("pagina", "empieza en 1")
        with self._repos.unidad_de_trabajo() as uow:
            total = uow.solicitudes.contar_del_solicitante(usuario_id)
            hasta = total - (pagina - 1) * self._tamano
            tramo = uow.solicitudes.del_solicitante(
                usuario_id, max(hasta - self._tamano, 0), max(hasta, 0)
            )
            avances = self._repos.avances([s.id for s in tramo])
            filas = tuple(
                replace(_fila(uow, s, usuario_id), avance=avances.get(s.id, _SIN_AVANCE))
                for s in reversed(tramo)
            )
            return PaginaDeSolicitudes(filas, total, pagina, self._tamano)


class PendientesDeAprobacion:
    """RF-12: la bandeja de RRHH."""

    def __init__(self, repos: Repositorios) -> None:
        self._repos = repos

    def ejecutar(self, usuario_id: str) -> tuple[FilaDeSolicitud, ...]:
        with self._repos.unidad_de_trabajo() as uow:
            if Rol.RRHH not in _actor(uow, usuario_id).roles:
                raise NoAutorizado("bandeja", "solo RRHH ve las pendientes de aprobacion")
            return tuple(
                _fila(uow, s, usuario_id) for s in uow.solicitudes.pendientes_de_aprobacion()
            )


class SubordinadosDe:
    """El jefe elige entre sus subordinados directos al pedir un CDP o un CSU."""

    def __init__(self, repos: Repositorios) -> None:
        self._repos = repos

    def ejecutar(self, usuario_id: str) -> Sequence[OpcionDeColaborador]:
        with self._repos.unidad_de_trabajo() as uow:
            actor = _actor(uow, usuario_id)
            if actor.colaborador_id is None:
                return ()
            return tuple(
                OpcionDeColaborador(c.id, c.nombre_completo)
                for c in uow.colaboradores.subordinados_de(actor.colaborador_id)
            )


class MiPerfil:
    """Roles y colaborador del usuario: la vista decide con ellos el menu y los formularios."""

    def __init__(self, repos: Repositorios) -> None:
        self._repos = repos

    def ejecutar(self, usuario_id: str) -> PerfilDeUsuario:
        with self._repos.unidad_de_trabajo() as uow:
            actor = _actor(uow, usuario_id)
            c = (
                None
                if actor.colaborador_id is None
                else uow.colaboradores.obtener(actor.colaborador_id)
            )
            mio = None if c is None else OpcionDeColaborador(c.id, c.nombre_completo)
            return PerfilDeUsuario(actor.usuario_id, actor.roles, mio)


class ColaboradorPorDocumento:
    """Quien emite (RRHH, o el Administrador por excepcion) busca a la persona por documento."""

    def __init__(self, repos: Repositorios) -> None:
        self._repos = repos

    def ejecutar(self, usuario_id: str, documento: str) -> OpcionDeColaborador | None:
        with self._repos.unidad_de_trabajo() as uow:
            if not _actor(uow, usuario_id).roles & {Rol.RRHH, Rol.ADMINISTRADOR}:
                raise NoAutorizado("buscar_colaborador", "solo quien emite busca por documento")
            try:
                clave = Documento(documento)
            except DatoInvalido:
                return None  # un documento invalido no es un error: no hay nadie con ese numero
            c = uow.colaboradores.por_documento(clave)
            return None if c is None else OpcionDeColaborador(c.id, c.nombre_completo)


def _como_texto(valor: object) -> str:
    if valor is None:
        return "—"
    if isinstance(valor, bool):
        return "Sí" if valor else "No"
    if isinstance(valor, datetime):
        return valor.astimezone(BOGOTA).strftime("%Y-%m-%d %H:%M")
    if isinstance(valor, Enum):
        return str(valor.value)
    return str(valor)


class ConsultarSolicitud:
    """El detalle lo ven RRHH y quien la registro; el campo restringido, solo RRHH (RD-05).

    A quien no puede verla se le responde «no encontrada»: no se confirma que el id exista.
    Cada vez que RRHH ve un campo restringido queda en la auditoria (RF-35).
    """

    def __init__(self, repos: Repositorios) -> None:
        self._repos = repos

    def ejecutar(self, usuario_id: str, solicitud_id: SolicitudId) -> DetalleDeSolicitud:
        with self._repos.unidad_de_trabajo() as uow:
            actor = _actor(uow, usuario_id)
            s = uow.solicitudes.obtener(solicitud_id)
            es_rrhh = puede_ver_restringidos(actor.roles)
            if s is None or not puede_ver_solicitud(actor, s.solicitante_id):
                raise NoEncontrado("solicitud", solicitud_id.valor)
            restringido = s.restringido.revelar() if es_rrhh and s.restringido else None
            if restringido is not None:
                uow.auditoria.registrar(
                    usuario_id, EventoDeAuditoria("restringido.consultado", s.id.valor, {})
                )
            datos = tuple((f.name, _como_texto(getattr(s.datos, f.name))) for f in fields(s.datos))
            seguidos = sorted(
                uow.tickets.de_solicitud(s.id), key=lambda t: t.ticket.clave_de_idempotencia
            )
            return DetalleDeSolicitud(
                replace(_fila(uow, s, usuario_id), avance=_avance(seguidos)),
                s.subtipo,
                datos,
                restringido,
                tuple(
                    EstadoDeTicketDeSolicitud(
                        t.ticket.cola,
                        t.ticket.accion,
                        None if t.observacion is None else t.observacion.estado,
                        ticket_resuelto(t),
                        t.ticket.bloquea_el_cierre,
                    )
                    for t in seguidos
                ),
            )


class SolicitudesEnError:
    """RF-38: las que esperan el reintento del Administrador (ADR-026)."""

    def __init__(self, repos: Repositorios) -> None:
        self._repos = repos

    def ejecutar(self, usuario_id: str) -> tuple[FilaDeSolicitud, ...]:
        with self._repos.unidad_de_trabajo() as uow:
            if not puede_reintentar_emision(_actor(uow, usuario_id).roles):
                raise NoAutorizado("solicitudes_en_error", "solo el Administrador reintenta")
            return tuple(_fila(uow, s, usuario_id) for s in uow.solicitudes.en_error())
