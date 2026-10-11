"""Las reglas escritas en SQL no se separan del dominio (revision externa H2 y H1)."""

import importlib

from jml.dominio.solicitud import TRANSICIONES

transiciones = importlib.import_module(
    "jml.adaptadores.salida.persistencia.migrations.0003_transiciones_en_el_disparador"
)


def _cierre_transitivo() -> set[tuple[str, str]]:
    pares = {(o.value, n.value) for (o, _), n in TRANSICIONES.items()}
    while True:
        nuevos = {(a, d) for a, b in pares for c, d in pares if b == c} - pares
        if not nuevos:
            return {(a, b) for a, b in pares if a != b}  # sin cambio de estado no se valida
        pares |= nuevos


def test_H2_el_disparador_permite_exactamente_el_cierre_de_las_transiciones_del_dominio() -> None:
    assert set(transiciones.TRANSICIONES_PERMITIDAS) == _cierre_transitivo()


def test_H2_nunca_se_vuelve_a_pendiente_ni_se_sale_de_un_estado_final() -> None:
    permitidas = set(transiciones.TRANSICIONES_PERMITIDAS)
    assert not {p for p in permitidas if p[1] == "pendiente_aprobacion"}
    assert not {p for p in permitidas if p[0] in ("cerrada", "rechazada", "cancelada")}
