"""Filtros de plantilla: etiquetas legibles para tipos y estados."""

from django import template

from jml.adaptadores.entrada.web.formularios import ETIQUETAS_DE_TIPO
from jml.aplicacion.dtos import EstadoDeTicketDeSolicitud
from jml.dominio.tipos import EstadoDeTicket, EstadoSolicitud, TipoEvento

register = template.Library()

_ESTADOS = {
    EstadoSolicitud.PENDIENTE_APROBACION: "Pendiente de aprobación",
    EstadoSolicitud.APROBADA: "Aprobada",
    EstadoSolicitud.EN_EJECUCION: "En ejecución",
    EstadoSolicitud.ERROR: "Con error",
    EstadoSolicitud.CERRADA: "Cerrada",
    EstadoSolicitud.RECHAZADA: "Rechazada",
    EstadoSolicitud.CANCELADA: "Cancelada",
}


_TONOS = {
    EstadoSolicitud.PENDIENTE_APROBACION: "pendiente",
    EstadoSolicitud.APROBADA: "curso",
    EstadoSolicitud.EN_EJECUCION: "curso",
    EstadoSolicitud.ERROR: "error",
    EstadoSolicitud.CERRADA: "ok",
}


ESTADOS_DE_TICKET = {
    EstadoDeTicket.NUEVO: "Nuevo",
    EstadoDeTicket.EN_ESPERA: "En espera",
    EstadoDeTicket.EN_CURSO: "En curso",
    EstadoDeTicket.RESUELTO: "Resuelto",
    EstadoDeTicket.CERRADO: "Cerrado",
}


def tono_de_estado(estado: EstadoDeTicket | None) -> str:
    if estado is None:
        return "neutro"
    if estado >= EstadoDeTicket.RESUELTO:
        return "ok"
    return "pendiente" if estado is EstadoDeTicket.EN_ESPERA else "curso"


@register.filter
def tono_de_ticket(t: EstadoDeTicketDeSolicitud) -> str:
    return tono_de_estado(t.estado)


@register.filter
def estado_de_ticket(t: EstadoDeTicketDeSolicitud) -> str:
    return "Sin crear" if t.estado is None else ESTADOS_DE_TICKET[t.estado]


@register.filter
def tono(estado: EstadoSolicitud) -> str:
    """Clase de la pildora. El color acompana al texto, nunca lo reemplaza (WCAG 1.4.1)."""
    return _TONOS.get(estado, "neutro")


@register.filter
def etiqueta(valor: TipoEvento | EstadoSolicitud) -> str:
    if isinstance(valor, TipoEvento):
        return ETIQUETAS_DE_TIPO[valor]
    return _ESTADOS[valor]
