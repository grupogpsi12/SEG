"""Emision de una solicitud aprobada: genera los tickets y los deja en la bandeja de salida.

Corre DENTRO de la unidad de trabajo de quien aprueba o emite, de modo que la decision, el
cambio de estado, los tickets en la bandeja y la auditoria se confirman juntos o ninguno (CA-02).
"""

from collections.abc import Sequence
from datetime import datetime

from jml.aplicacion.bandeja import EntradaDeBandeja
from jml.aplicacion.puertos import UnidadDeTrabajo
from jml.dominio.auditoria import EventoDeAuditoria
from jml.dominio.catalogo import DatosCambioDepartamento, DatosCambioSucursal
from jml.dominio.colaborador import Colaborador
from jml.dominio.errores import NoEncontrado
from jml.dominio.perfiles import PerfilDeAcceso
from jml.dominio.solicitud import Decision, ResultadoSolicitud, Solicitud
from jml.dominio.tickets import TicketSeguido, generar_tickets
from jml.dominio.tipos import TipoEvento
from jml.dominio.valores import CalendarioHabil


def registrar_eventos(
    uow: UnidadDeTrabajo, actor: str, eventos: Sequence[EventoDeAuditoria]
) -> None:
    for evento in eventos:
        uow.auditoria.registrar(actor, evento)


def _perfil(uow: UnidadDeTrabajo, departamento: str, sede: str) -> PerfilDeAcceso:
    perfil = uow.perfiles.obtener(departamento, sede)
    if perfil is None:
        raise NoEncontrado("perfil de acceso", f"{departamento} / {sede}")
    return perfil


def perfiles_del_evento(
    uow: UnidadDeTrabajo, s: Solicitud, c: Colaborador
) -> tuple[PerfilDeAcceso | None, PerfilDeAcceso | None]:
    """(perfil actual, perfil nuevo) segun el tipo de evento (SRS 4.4)."""
    if s.tipo is TipoEvento.ING:
        return None, _perfil(uow, c.departamento, c.sede)
    actual = _perfil(uow, c.departamento, c.sede)
    if s.tipo is TipoEvento.CDP and isinstance(s.datos, DatosCambioDepartamento):
        return actual, _perfil(uow, s.datos.departamento_nuevo, c.sede)
    if s.tipo is TipoEvento.CSU and isinstance(s.datos, DatosCambioSucursal):
        return actual, _perfil(uow, c.departamento, s.datos.sede_nueva)
    return actual, None


def emitir_tickets(
    uow: UnidadDeTrabajo,
    solicitud: Solicitud,
    colaborador: Colaborador,
    actor: str,
    ahora: datetime,
    calendario: CalendarioHabil,
) -> tuple[Solicitud, int]:
    """Genera los tickets, los encola y devuelve la solicitud final y cuantos se encolaron.

    S-05: si ninguna cola tiene trabajo (CDP/CSU sin diferencia) la solicitud se cierra en el
    acto y se audita, sin tickets vacios.
    """
    actual, nuevo = perfiles_del_evento(uow, solicitud, colaborador)
    tickets = generar_tickets(solicitud, actual, nuevo, colaborador, calendario, ahora)
    if not tickets:
        r = solicitud.iniciar_ejecucion(frozenset())
        cerrada: ResultadoSolicitud = r.solicitud.cerrar(0)
        uow.solicitudes.guardar(cerrada.solicitud)
        registrar_eventos(uow, actor, r.eventos + cerrada.eventos)
        uow.auditoria.registrar(
            actor,
            EventoDeAuditoria("solicitud.sin_tickets", solicitud.id.valor, {"supuesto": "S-05"}),
        )
        return cerrada.solicitud, 0
    for ticket in tickets:
        uow.tickets.guardar(TicketSeguido(ticket))
    uow.bandeja.encolar([EntradaDeBandeja.nueva(t, ahora) for t in tickets])
    uow.auditoria.registrar(
        actor,
        EventoDeAuditoria(
            "solicitud.tickets_encolados", solicitud.id.valor, {"cantidad": len(tickets)}
        ),
    )
    return solicitud, len(tickets)


def marcar_otras_para_revision(
    uow: UnidadDeTrabajo, emergencia: Solicitud, actor: str
) -> tuple[Solicitud, ...]:
    """RF-10: al emitirse una EMG, las otras abiertas del colaborador pasan a revision de RRHH."""
    marcadas: list[Solicitud] = []
    for otra in uow.solicitudes.abiertas_de(emergencia.colaborador_id):
        if otra.id == emergencia.id:
            continue
        r = otra.marcar_para_revision()
        if r.solicitud is not otra:
            uow.solicitudes.guardar(r.solicitud)
            registrar_eventos(uow, actor, r.eventos)
            marcadas.append(r.solicitud)
    return tuple(marcadas)


def guardar_decision(uow: UnidadDeTrabajo, decision: Decision | None) -> None:
    if decision is not None:
        uow.decisiones.agregar(decision)
