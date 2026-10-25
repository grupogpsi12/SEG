"""Gherkin de la auditoría encadenada: el Auditor verifica desde la interfaz, sobre el ORM."""

from typing import Any

import pytest
from django.db import connection
from pytest_bdd import given, scenarios, then, when

from jml.adaptadores.salida.persistencia.repositorios import RepositoriosDjango
from jml.dominio.auditoria import EventoDeAuditoria
from tests.bdd.conftest import como
from tests.mundo import Mundo

pytestmark = [pytest.mark.django_db]
scenarios("features/inmutabilidad.feature")


def texto(r: Any) -> str:
    return bytes(r.content).decode()


def _escribir(m: Mundo, cuantos: int) -> None:
    with RepositoriosDjango(m.reloj).unidad_de_trabajo() as u:
        actuales = len(u.auditoria.registros())
        for i in range(cuantos - actuales):
            u.auditoria.registrar(
                "u-prueba", EventoDeAuditoria(f"prueba.{i}", f"obj-{i}", {"n": i})
            )


@given("una cadena de auditoría con más de cincuenta eventos")
def _(mundo_web: Mundo) -> None:
    _escribir(mundo_web, 55)


@given("una cadena de auditoría con un solo evento")
def _(mundo_web: Mundo) -> None:
    _escribir(mundo_web, 1)


@given("que la verificación devuelve íntegra")
def _() -> None:
    assert "La cadena es íntegra" in texto(como("u-aud").post("/auditoria"))


@when("el Auditor ejecuta la verificación", target_fixture="pagina")
def _() -> str:
    return texto(como("u-aud").post("/auditoria"))


@when(
    "alguien altera el actor del evento diecisiete directamente en la base", target_fixture="pagina"
)
def _(ctx: dict[str, object]) -> str:
    with connection.cursor() as c:
        c.execute("SELECT actor FROM auditoria WHERE secuencia = %s", [17])
        fila = c.fetchone()
        assert fila is not None
        ctx["original"] = str(fila[0])
        c.execute("UPDATE auditoria SET actor = %s WHERE secuencia = %s", ["intruso", 17])
    return texto(como("u-aud").post("/auditoria"))


@then("el resultado dice que la cadena es íntegra")
def _(pagina: str) -> None:
    assert "La cadena es íntegra" in pagina


@then("la verificación queda registrada en la propia cadena")
def _(mundo_web: Mundo) -> None:
    with RepositoriosDjango(mundo_web.reloj).unidad_de_trabajo() as u:
        assert u.auditoria.registros()[-1].accion == "auditoria.verificada"


@then("la verificación señala el evento diecisiete como el primero afectado")
def _(pagina: str) -> None:
    assert "La cadena está ROTA" in pagina
    assert "posición 17" in pagina


@then("al restaurar el valor la verificación vuelve a ser íntegra")
def _(ctx: dict[str, object]) -> None:
    with connection.cursor() as c:
        c.execute(
            "UPDATE auditoria SET actor = %s WHERE secuencia = %s", [str(ctx["original"]), 17]
        )
    assert "La cadena es íntegra" in texto(como("u-aud").post("/auditoria"))
