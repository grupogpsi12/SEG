"""Gherkin del aislamiento de Supabase: configuración, código fuente, scripts y las instantáneas de F3-PAR."""

import json
import re
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

scenarios("features/supabase-aislada.feature")

RAIZ = Path(__file__).resolve().parents[2]
INSTANTANEAS = RAIZ / "auditoria" / "evidencia" / "funcionales" / "F3-PAR-INSTANTANEAS"


@given("la configuración de producción de la base de datos", target_fixture="codigo")
def _() -> str:
    return (RAIZ / "src" / "config" / "settings.py").read_text(encoding="utf-8")


@then(
    parsers.parse(
        'se conecta con el usuario "{usuario}", con TLS verify-full y en el esquema "{esquema}"'
    )
)
def _(codigo: str, usuario: str, esquema: str) -> None:
    assert f'"JML_DB_USUARIO", "{usuario}"' in codigo
    assert '"JML_DB_SSLMODE", "verify-full"' in codigo
    assert f"-c search_path={esquema}" in codigo


@when("se busca en el código la API REST de datos de Supabase", target_fixture="hallazgos")
def _() -> list[str]:
    patron = re.compile(r"rest/v1|postgrest|anon_key|SUPABASE_ANON", re.IGNORECASE)
    return [
        f"{ruta.relative_to(RAIZ)}:{n}"
        for ruta in (RAIZ / "src").rglob("*.py")
        for n, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), 1)
        if patron.search(linea)
    ]


@then('no hay ninguna referencia a "rest/v1", "postgrest" ni a la clave anon')
def _(hallazgos: list[str]) -> None:
    assert hallazgos == []


@when("se lee el script que deja al dueño separado", target_fixture="sql")
def _() -> str:
    return (RAIZ / "infra" / "supabase" / "duenio-separado.sql").read_text(encoding="utf-8")


@then("revoca todo sobre el esquema de la aplicación a PUBLIC, anon, authenticated y service_role")
def _(sql: str) -> None:
    assert "REVOKE ALL ON SCHEMA %I FROM public, anon, authenticated, service_role" in sql


@given("las instantáneas de catálogo de F3-PAR", target_fixture="catalogos")
def _() -> tuple[dict[str, object], dict[str, object]]:
    local = json.loads((INSTANTANEAS / "catalogo-local.json").read_text(encoding="utf-8"))
    supabase = json.loads((INSTANTANEAS / "catalogo-supabase.json").read_text(encoding="utf-8"))
    return local, supabase


@when("se comparan sección por sección", target_fixture="diferencias")
def _(catalogos: tuple[dict[str, object], dict[str, object]]) -> set[str]:
    local, supabase = catalogos
    return {k for k in set(local) | set(supabase) if local.get(k) != supabase.get(k)}


@then("solo difieren las extensiones de la plataforma y los roles propios de Supabase")
def _(diferencias: set[str]) -> None:
    assert diferencias == {"extensiones", "roles"}


@when(
    parsers.parse(
        'se pide una tabla del esquema "{esquema}" a la API de datos con la clave pública'
    )
)
def _() -> None:
    pytest.skip("S-38 [PENDIENTE: F7] petición a la Data API del proyecto de desarrollo")


@then("la respuesta no contiene filas")
def _() -> None:
    pytest.skip("S-38 [PENDIENTE: F7]")
