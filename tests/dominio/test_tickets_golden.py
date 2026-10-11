"""Prueba dorada de la generacion de tickets (RF-16, RF-17, RF-20, CA-19).

Congela, para cada caso de la matriz evento x cola, TODO lo que un tecnico veria: titulo,
categoria, prioridad, vencimientos, estado inicial, clave de idempotencia y la lista de
verificacion completa. Las listas son texto del SRS (secciones 4.4, 4.5 y 4.9): un cambio de
redaccion debe ser una decision visible en el diff de `golden_tickets.json`, no un accidente.
"""

import json

import pytest

from tests.dominio.golden_tickets import CASOS, RUTA, generar, serializar
from tests.fabricas import caso

ESPERADO = json.loads(RUTA.read_text(encoding="utf-8"))


def test_el_archivo_dorado_cubre_todos_los_casos() -> None:
    assert set(ESPERADO) == set(CASOS)
    assert sum(len(v) for v in ESPERADO.values()) >= 55


@pytest.mark.parametrize("nombre", sorted(CASOS))
def test_los_tickets_son_los_aprobados(nombre: str) -> None:
    obtenidos = [serializar(t) for t in generar(caso(**CASOS[nombre]))]  # type: ignore[arg-type]  # parametros nombrados
    # json ida y vuelta: compara exactamente lo que se guardo (tuplas -> listas)
    assert json.loads(json.dumps(obtenidos, ensure_ascii=False)) == ESPERADO[nombre]


def test_la_recuperacion_de_un_caso_sin_tickets_es_vacia() -> None:
    assert ESPERADO["CDP sin diferencia"] == []


def test_ningun_ticket_dorado_contiene_el_motivo_ni_contrasenas_ni_el_subtipo() -> None:
    texto = json.dumps(
        list(ESPERADO.values()), ensure_ascii=False
    ).lower()  # solo los tickets, no los nombres de caso
    assert "sentinela" not in texto
    assert "password" not in texto
    assert "contraseña:" not in texto
    for subtipo in ("renuncia", "fin_de_contrato", "despido", "fuga"):
        assert subtipo not in texto
