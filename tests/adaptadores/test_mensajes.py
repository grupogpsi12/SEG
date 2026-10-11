"""Revision externa M6: cada error de dominio tiene su texto para personas, sin detalles internos."""

import pytest

from jml.adaptadores.entrada.web.mensajes import GENERICO, texto_del_error
from jml.dominio.errores import (
    AutoAprobacionProhibida,
    CampoRestringidoProhibido,
    CancelacionNoPermitida,
    CierreNoPermitido,
    ColaboradorNoElegible,
    DatoInvalido,
    DocumentoDuplicado,
    ErrorDeDominio,
    JustificacionRequerida,
    NoAutorizado,
    NoEncontrado,
    OperacionNoPermitida,
    RolesIncompatibles,
    SolicitudDuplicada,
    SoporteInvalido,
    TransicionInvalida,
)


@pytest.mark.parametrize(
    ("error", "esperado"),
    [
        (SolicitudDuplicada("SOL-2026-000007"), "Ya existe una solicitud abierta"),
        (DocumentoDuplicado("col-3"), "Ese documento ya pertenece"),
        (AutoAprobacionProhibida("aprobar"), "RRHH no puede aprobar ni emitir"),
        (NoAutorizado("x", "detalle interno"), "No tiene permiso"),
        (JustificacionRequerida("rechazar"), "Escriba la justificación"),
        (SoporteInvalido("no es PDF"), "no es PDF"),
        (ColaboradorNoElegible("VAC", "retirado"), "no aplica a la persona"),
        (CancelacionNoPermitida("tickets creados"), "Ya no se puede cancelar"),
        (TransicionInvalida("cerrada", "aprobar"), "ya no está en un estado"),
        (RolesIncompatibles("rrhh", "auditor"), "«rrhh» y «auditor»"),
        (OperacionNoPermitida("nadie cambia sus propios roles"), "nadie cambia"),
        (NoEncontrado("solicitud", "SOL-2026-000009"), "No se encontró"),
        (DatoInvalido("fecha_regreso", "debe ser posterior"), "«fecha_regreso»"),
        (CierreNoPermitido(2), GENERICO),
        (CampoRestringidoProhibido("log"), GENERICO),
        (ErrorDeDominio("algo interno"), GENERICO),
    ],
)
def test_cada_error_tiene_su_texto(error: ErrorDeDominio, esperado: str) -> None:
    texto = texto_del_error(error)
    assert esperado in texto
    assert "detalle interno" not in texto  # el motivo tecnico de NoAutorizado no se muestra
    assert "algo interno" not in texto


def test_la_autoaprobacion_va_antes_que_el_no_autorizado_generico() -> None:
    assert texto_del_error(AutoAprobacionProhibida("emitir")) != texto_del_error(
        NoAutorizado("emitir", "x")
    )
