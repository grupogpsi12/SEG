"""Errores de dominio -> mensajes para personas no tecnicas (RNF-14).

Nunca se muestra un detalle interno ni un valor de un campo restringido: cada texto sale de una
plantilla fija y solo interpola identificadores que el usuario ya conoce.
"""

from jml.dominio.errores import (
    AutoAprobacionProhibida,
    CancelacionNoPermitida,
    ColaboradorNoElegible,
    DatoInvalido,
    DocumentoDuplicado,
    ErrorDeDominio,
    JustificacionRequerida,
    NoAutorizado,
    NoEncontrado,
    SolicitudDuplicada,
    SoporteInvalido,
    TransicionInvalida,
)

GENERICO = "No se pudo completar la operación. Si el problema continúa, avise al administrador."


def texto_del_error(error: ErrorDeDominio) -> str:
    # AutoAprobacionProhibida hereda de NoAutorizado: debe ir antes.
    match error:
        case SolicitudDuplicada():
            return (
                f"Ya existe una solicitud abierta de este tipo para esa persona "
                f"({error.existente_id}). Espere a que termine o cancélela."
            )
        case DocumentoDuplicado():
            return (
                "Ese documento ya pertenece a un colaborador que no está retirado "
                f"({error.existente_id})."
            )
        case AutoAprobacionProhibida():
            return (
                "RRHH no puede aprobar ni emitir solicitudes sobre su propia persona. "
                "Pida al Administrador que la emita."
            )
        case NoAutorizado():
            return "No tiene permiso para realizar esta acción."
        case JustificacionRequerida():
            return "Escriba la justificación: es obligatoria para esta acción."
        case SoporteInvalido():
            return f"El soporte de vinculación no es válido: {error.motivo}."
        case ColaboradorNoElegible():
            return "Ese tipo de solicitud no aplica a la persona en su estado actual."
        case CancelacionNoPermitida():
            return "Ya no se puede cancelar: se creó al menos un ticket en la mesa de servicio."
        case TransicionInvalida():
            return "La solicitud ya no está en un estado que permita esa acción."
        case NoEncontrado():
            return "No se encontró lo que buscaba."
        case DatoInvalido():
            return f"Dato inválido en «{error.campo}»: {error.motivo}."
        case _:
            return GENERICO
