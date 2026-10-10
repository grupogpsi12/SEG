"""Errores tipados del dominio. Cada violacion de regla tiene nombre, codigo estable y datos.

Los datos que llevan nunca incluyen campos restringidos (RD-05).
"""

from typing import ClassVar

Dato = str | int


class ErrorDeDominio(Exception):
    codigo: ClassVar[str] = "error_de_dominio"

    def __init__(self, mensaje: str, **datos: Dato) -> None:
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.datos: dict[str, Dato] = dict(datos)


class DatoInvalido(ErrorDeDominio):
    codigo = "dato_invalido"

    def __init__(self, campo: str, motivo: str) -> None:
        super().__init__(f"{campo}: {motivo}", campo=campo, motivo=motivo)
        self.campo = campo
        self.motivo = motivo


class TransicionInvalida(ErrorDeDominio):
    codigo = "transicion_invalida"

    def __init__(self, estado: str, accion: str) -> None:
        super().__init__(f"No se puede '{accion}' desde '{estado}'", estado=estado, accion=accion)
        self.estado = estado
        self.accion = accion


class SolicitudDuplicada(ErrorDeDominio):
    codigo = "solicitud_duplicada"

    def __init__(self, existente_id: str) -> None:
        super().__init__(
            f"Ya existe una solicitud abierta: {existente_id}", existente_id=existente_id
        )
        self.existente_id = existente_id


class DocumentoDuplicado(ErrorDeDominio):
    codigo = "documento_duplicado"

    def __init__(self, existente_id: str) -> None:
        super().__init__(
            f"El documento ya existe y no esta retirado: {existente_id}",
            existente_id=existente_id,
        )
        self.existente_id = existente_id


class NoAutorizado(ErrorDeDominio):
    codigo = "no_autorizado"

    def __init__(self, accion: str, motivo: str) -> None:
        super().__init__(f"No autorizado para '{accion}': {motivo}", accion=accion, motivo=motivo)
        self.accion = accion
        self.motivo = motivo


class AutoAprobacionProhibida(NoAutorizado):
    """RF-15, T15: RRHH no decide sobre su propia persona."""

    codigo = "auto_aprobacion_prohibida"

    def __init__(self, accion: str) -> None:
        super().__init__(accion, "quien decide no puede ser el sujeto de la solicitud")


class RolesIncompatibles(ErrorDeDominio):
    codigo = "roles_incompatibles"

    def __init__(self, uno: str, otro: str) -> None:
        super().__init__(f"Roles incompatibles: {uno} y {otro}", uno=uno, otro=otro)
        self.uno = uno
        self.otro = otro


class JustificacionRequerida(ErrorDeDominio):
    codigo = "justificacion_requerida"

    def __init__(self, accion: str) -> None:
        super().__init__(f"La accion '{accion}' exige una justificacion", accion=accion)
        self.accion = accion


class SolicitudInmutable(ErrorDeDominio):
    codigo = "solicitud_inmutable"

    def __init__(self, estado: str) -> None:
        super().__init__(f"El contenido no se modifica en estado '{estado}' (RF-14)", estado=estado)
        self.estado = estado


class CancelacionNoPermitida(ErrorDeDominio):
    codigo = "cancelacion_no_permitida"

    def __init__(self, motivo: str) -> None:
        super().__init__(f"No se puede cancelar: {motivo}", motivo=motivo)
        self.motivo = motivo


class CierreNoPermitido(ErrorDeDominio):
    codigo = "cierre_no_permitido"

    def __init__(self, pendientes: int) -> None:
        super().__init__(f"Hay {pendientes} tickets de cierre sin resolver", pendientes=pendientes)
        self.pendientes = pendientes


class ColaboradorNoElegible(ErrorDeDominio):
    codigo = "colaborador_no_elegible"

    def __init__(self, tipo: str, estado: str) -> None:
        super().__init__(
            f"Un evento {tipo} no aplica a un colaborador '{estado}'", tipo=tipo, estado=estado
        )
        self.tipo = tipo
        self.estado = estado


class SoporteInvalido(ErrorDeDominio):
    codigo = "soporte_invalido"

    def __init__(self, motivo: str) -> None:
        super().__init__(f"Soporte de vinculacion invalido: {motivo}", motivo=motivo)
        self.motivo = motivo


class CampoRestringidoProhibido(ErrorDeDominio):
    """RD-05: un campo restringido intento salir hacia un destino que no le corresponde."""

    codigo = "campo_restringido_prohibido"

    def __init__(self, destino: str) -> None:
        super().__init__(f"Un campo restringido no puede ir a {destino}", destino=destino)
        self.destino = destino


class OperacionNoPermitida(ErrorDeDominio):
    codigo = "operacion_no_permitida"

    def __init__(self, motivo: str) -> None:
        super().__init__(motivo, motivo=motivo)
        self.motivo = motivo


class NoEncontrado(ErrorDeDominio):
    codigo = "no_encontrado"

    def __init__(self, entidad: str, referencia: str) -> None:
        super().__init__(
            f"No existe {entidad}: {referencia}", entidad=entidad, referencia=referencia
        )
        self.entidad = entidad
        self.referencia = referencia
