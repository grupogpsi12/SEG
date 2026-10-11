"""Item 2.1: logs JSON con correlation_id y sin campos prohibidos (RS-09, RD-05, CA-10 en los logs)."""

import json
import logging

import pytest

from jml.adaptadores.registro import (
    CORRELACION,
    FiltroDeCamposProhibidos,
    FiltroDeCorrelacion,
    FormatoJSON,
)
from jml.dominio.valores import CampoRestringido

SENTINELA = "SENTINELA-LOG-5521"


def _formatear(mensaje: str, *args: object, **extra: object) -> dict[str, object]:
    registro = logging.LogRecord(
        "jml.prueba", logging.INFO, __file__, 1, mensaje, args or None, None
    )
    for clave, valor in extra.items():
        setattr(registro, clave, valor)
    for filtro in (FiltroDeCorrelacion(), FiltroDeCamposProhibidos()):
        assert filtro.filter(registro) is True
    salida = FormatoJSON().format(registro)
    assert SENTINELA not in salida
    datos = json.loads(salida)
    assert isinstance(datos, dict)
    return datos


def test_el_log_es_json_con_los_campos_basicos() -> None:
    d = _formatear("solicitud %s aprobada", "SOL-2026-000001", solicitud="SOL-2026-000001")
    assert d["mensaje"] == "solicitud SOL-2026-000001 aprobada"
    assert d["nivel"] == "INFO"
    assert d["logger"] == "jml.prueba"
    assert d["solicitud"] == "SOL-2026-000001"
    assert str(d["fecha"]).endswith("Z")


def test_lleva_el_correlation_id_de_la_peticion() -> None:
    marca = CORRELACION.set("abc-123")
    try:
        assert _formatear("x")["correlation_id"] == "abc-123"
    finally:
        CORRELACION.reset(marca)
    assert _formatear("x")["correlation_id"] == "-"


@pytest.mark.parametrize(
    "clave",
    ["password", "contrasena", "token", "totp", "secret", "motivo", "descripcion",
     "db_password", "glpi_token", "Motivo", "codigo_totp", "client_secret"],
)  # fmt: skip
def test_RS_09_los_campos_prohibidos_se_filtran(clave: str) -> None:
    d = _formatear("evento", **{clave: SENTINELA})
    assert d[clave] == "[filtrado]"


def test_tambien_se_filtran_dentro_de_diccionarios_anidados() -> None:
    d = _formatear(
        "evento",
        datos={"usuario": "ana", "credenciales": {"password": SENTINELA}, "motivo": SENTINELA},
    )
    assert d["datos"] == {
        "usuario": "ana",
        "credenciales": {"password": "[filtrado]"},
        "motivo": "[filtrado]",
    }


def test_un_campo_restringido_nunca_se_imprime() -> None:
    d = _formatear("retiro %s", CampoRestringido(SENTINELA), dato=CampoRestringido(SENTINELA))
    assert d["mensaje"] == "retiro CampoRestringido(<oculto>)"
    assert d["dato"] == "CampoRestringido(<oculto>)"


def test_las_excepciones_se_registran_con_su_tipo() -> None:
    try:
        raise ValueError("fallo de prueba")
    except ValueError:
        import sys

        registro = logging.LogRecord(
            "jml", logging.ERROR, __file__, 1, "fallo", None, sys.exc_info()
        )
    FiltroDeCorrelacion().filter(registro)
    d = json.loads(FormatoJSON().format(registro))
    assert "ValueError" in d["excepcion"]
