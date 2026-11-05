"""F3-U04 (T9, RS-09): propiedad: ningún valor bajo una clave prohibida sobrevive al filtro de logs.

Se generan estructuras anidadas (diccionarios, listas, tuplas y conjuntos) con claves que contienen
una palabra prohibida en mayúsculas, minúsculas, con acento o incrustada en otro texto, y se
comprueba que el valor centinela jamás llega al JSON final. Un contraejemplo es un hallazgo.
"""

import json
import logging

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from jml.adaptadores.registro import FiltroDeCamposProhibidos, FormatoJSON

pytestmark = pytest.mark.seguridad

# Las de CLAUDE.md más las variantes con acento que un desarrollador hispanohablante escribiría
PALABRAS = [
    "password",
    "contrasena",
    "contraseña",
    "token",
    "totp",
    "secret",
    "motivo",
    "descripcion",
    "descripción",
]
RELLENO = st.text(alphabet="abcdefghijklmnopqrstuvwxyz_-0123456789", max_size=6)


@st.composite
def claves_prohibidas(draw: st.DrawFn) -> str:
    palabra = draw(st.sampled_from(PALABRAS))
    palabra = "".join(draw(st.sampled_from([c.lower(), c.upper()])) for c in palabra)
    return draw(RELLENO) + palabra + draw(RELLENO)


def envolver(clave: str, valor: object) -> st.SearchStrategy[object]:
    return st.sampled_from(
        [
            {clave: valor},
            [{clave: valor}],
            ({"otro": 1}, {clave: valor}),
            {"datos": {"mas": [{clave: valor}]}},
        ]
    )


def registro_con(extra: object) -> str:
    r = logging.LogRecord("jml.prueba", logging.INFO, __file__, 1, "evento", None, None)
    r.datos = extra  # atributo extra, como `extra=` de logging
    assert FiltroDeCamposProhibidos().filter(r) is True
    return FormatoJSON().format(r)


@settings(max_examples=1000, deadline=None, suppress_health_check=list(HealthCheck))
@given(clave=claves_prohibidas(), numero=st.integers(min_value=0, max_value=10**9), data=st.data())
def test_U04_ningun_valor_bajo_una_clave_prohibida_llega_al_log(
    clave: str, numero: int, data: st.DataObject
) -> None:
    centinela = f"VALOR-SECRETO-{numero}"
    estructura = data.draw(envolver(clave, centinela))
    assert centinela not in registro_con(estructura), (clave, estructura)


@settings(max_examples=300, deadline=None, suppress_health_check=list(HealthCheck))
@given(clave=claves_prohibidas(), numero=st.integers(min_value=0, max_value=10**9), data=st.data())
def test_U04_el_log_sigue_siendo_json_valido(clave: str, numero: int, data: st.DataObject) -> None:
    estructura = data.draw(envolver(clave, f"v{numero}"))
    assert isinstance(json.loads(registro_con(estructura)), dict)


@pytest.mark.parametrize("clave", ["contraseña", "CONTRASEÑA", "descripción", "Descripción_Larga"])
def test_B_21_las_claves_prohibidas_con_acento_tambien_se_filtran(clave: str) -> None:
    """Hypothesis encontró `contraseña`: la lista es ASCII y el filtro comparaba sin normalizar."""
    assert "VALOR-SECRETO" not in registro_con({clave: "VALOR-SECRETO"})
