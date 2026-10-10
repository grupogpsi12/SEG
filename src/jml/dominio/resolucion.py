"""Ticket resuelto, solicitud cerrable y estado derivado del colaborador (RF-24, RF-26, S-07).

La fuente de la verdad es GLPI (ADR-001): aqui solo se interpreta lo que GLPI informo.
"""

from collections.abc import Iterable

from jml.dominio.solicitud import Solicitud
from jml.dominio.tickets import TicketSeguido
from jml.dominio.tipos import ClaseTicket, Cola, EstadoColaborador, TipoEvento


def ticket_resuelto(seguido: TicketSeguido) -> bool:
    """RF-24: estado >= Resuelto Y solucion registrada; Inventario ademas necesita un adjunto.

    Un ticket resuelto sin solucion (o de Inventario sin acta) es «cierre incompleto» y no
    cierra la solicitud ni cambia ninguna cuenta (invariante 7).
    """
    obs = seguido.observacion
    if obs is None or not obs.resuelta or not obs.tiene_solucion:
        return False
    return not (seguido.ticket.cola is Cola.INVENTARIO and obs.documentos < 1)


def cierre_incompleto(seguido: TicketSeguido) -> bool:
    obs = seguido.observacion
    return obs is not None and obs.resuelta and not ticket_resuelto(seguido)


def _de_cierre(tickets: Iterable[TicketSeguido]) -> list[TicketSeguido]:
    return [t for t in tickets if t.ticket.bloquea_el_cierre]


def pendientes_de_cierre(tickets: Iterable[TicketSeguido]) -> int:
    """RF-26: los posteriores (eliminacion a 90 dias) no cuentan."""
    return sum(1 for t in _de_cierre(tickets) if not ticket_resuelto(t))


def solicitud_cerrable(tickets: Iterable[TicketSeguido]) -> bool:
    return pendientes_de_cierre(tickets) == 0


def estado_derivado_del_colaborador(
    solicitud: Solicitud, tickets: Iterable[TicketSeguido]
) -> EstadoColaborador | None:
    """S-07: el estado del colaborador lo deriva la sincronizacion, nunca una edicion manual."""
    de_cierre = _de_cierre(tickets)
    if not de_cierre:
        return None
    tipo = solicitud.tipo
    if tipo in (TipoEvento.CDP, TipoEvento.CSU):
        return None
    if tipo is TipoEvento.VAC:
        inmediatos = [t for t in de_cierre if t.ticket.clase is ClaseTicket.CIERRE_INMEDIATO]
        programados = [t for t in de_cierre if t.ticket.clase is ClaseTicket.CIERRE_PROGRAMADO]
        if all(ticket_resuelto(t) for t in inmediatos + programados):
            return EstadoColaborador.ACTIVO
        if all(ticket_resuelto(t) for t in inmediatos):
            return EstadoColaborador.SUSPENDIDO
        return None
    if not all(ticket_resuelto(t) for t in de_cierre):
        return None
    if tipo is TipoEvento.ING:
        return EstadoColaborador.ACTIVO
    return EstadoColaborador.RETIRADO  # RET y EMG
