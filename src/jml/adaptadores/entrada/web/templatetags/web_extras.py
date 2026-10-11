"""Filtros de plantilla: etiquetas legibles para tipos y estados."""

from django import template

from jml.adaptadores.entrada.web.formularios import ETIQUETAS_DE_TIPO
from jml.dominio.tipos import EstadoSolicitud, TipoEvento

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


@register.filter
def etiqueta(valor: TipoEvento | EstadoSolicitud) -> str:
    if isinstance(valor, TipoEvento):
        return ETIQUETAS_DE_TIPO[valor]
    return _ESTADOS[valor]
