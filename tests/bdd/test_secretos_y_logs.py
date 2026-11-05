"""Gherkin de secretos y registros: compose, git, el filtro de logs y el contenido de los tickets."""

import json
import logging
import re
import subprocess
from pathlib import Path

import yaml
from pytest_bdd import parsers, scenarios, then, when

from jml.adaptadores.registro import (
    CORRELACION,
    FiltroDeCamposProhibidos,
    FiltroDeCorrelacion,
    FormatoJSON,
)
from jml.dominio.tickets import generar_tickets
from jml.dominio.tipos import TipoEvento
from jml.dominio.valores import CalendarioHabil
from tests.fabricas import AHORA, caso

scenarios("features/secretos-y-logs.feature")

RAIZ = Path(__file__).resolve().parents[2]


@when(
    parsers.parse('se revisa qué servicios del compose montan el secreto "{secreto}"'),
    target_fixture="montan",
)
def _(secreto: str) -> set[str]:
    montan: set[str] = set()
    for compose in (RAIZ / "infra").glob("compose*.yaml"):
        servicios = yaml.safe_load(compose.read_text(encoding="utf-8")).get("services", {})
        montan |= {n for n, s in servicios.items() if secreto in (s.get("secrets") or [])}
    return montan


@then(parsers.parse('solo lo monta "{servicio}"'))
def _(montan: set[str], servicio: str) -> None:
    assert montan == {servicio}


@when("se lista lo que git versiona", target_fixture="versionado")
def _() -> list[str]:
    salida = subprocess.run(
        ["git", "ls-files"], cwd=RAIZ, capture_output=True, text=True, check=True
    ).stdout
    return salida.splitlines()


@then('no hay nada bajo "secrets/" salvo el aviso y los cifrados, ni un infra/.env')
def _(versionado: list[str]) -> None:
    permitidos = re.compile(
        r"^secrets/(LEEME.*|.*\.enc\.(json|yaml|env|bin)|.*\.sops\..*|.*\.age)$"
    )
    ajenos = [f for f in versionado if f.startswith("secrets/") and not permitidos.match(f)]
    assert ajenos == [], ajenos
    assert "infra/.env" not in versionado
    assert not [f for f in versionado if f.endswith("/.env") or f == ".env"]


@when(
    "se registra un evento con la contraseña, el token, el motivo y la descripción de una persona",
    target_fixture="salida",
)
def _() -> str:
    marca = CORRELACION.set("corr-de-prueba-01")
    try:
        r = logging.LogRecord("jml.prueba", logging.INFO, __file__, 1, "evento", None, None)
        r.datos = {  # atributo extra, como `extra=` de logging
            "contraseña": "V-CLAVE-1",
            "token": "V-TOKEN-2",
            "motivo": "V-MOTIVO-3",
            "descripcion": "V-DESC-4",
        }
        for filtro in (FiltroDeCorrelacion(), FiltroDeCamposProhibidos()):
            filtro.filter(r)
        return FormatoJSON().format(r)
    finally:
        CORRELACION.reset(marca)


@then("ninguno de esos valores aparece en el registro JSON")
def _(salida: str) -> None:
    for valor in ("V-CLAVE-1", "V-TOKEN-2", "V-MOTIVO-3", "V-DESC-4"):
        assert valor not in salida


@then("el registro conserva el correlation_id")
def _(salida: str) -> None:
    assert json.loads(salida)["correlation_id"] == "corr-de-prueba-01"


@when("se generan los tickets de un ingreso", target_fixture="textos")
def _() -> list[str]:
    c = caso(TipoEvento.ING)
    tickets = generar_tickets(
        c.solicitud, c.actual, c.nuevo, c.colaborador, CalendarioHabil(), AHORA
    )
    return [f"{t.titulo}\n{t.como_texto()}" for t in tickets]


@then("ningún título ni contenido menciona contraseñas ni claves")
def _(textos: list[str]) -> None:
    assert textos
    for texto in textos:
        assert not re.search(r"contrase|password|clave\s*:|secret", texto, re.IGNORECASE), texto
