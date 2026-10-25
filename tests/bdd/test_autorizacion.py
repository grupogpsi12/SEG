"""Gherkin de autorización: usa la misma petición que recorre la matriz de 440 celdas."""

import logging
from dataclasses import replace

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from jml.adaptadores.salida.persistencia import models as mod
from jml.dominio.errores import AutoAprobacionProhibida, SolicitudDuplicada
from tests.bdd.conftest import como
from tests.mundo import Mundo, vacaciones
from tests.seguridad.rutas import rutas
from tests.seguridad.test_idor_csrf import normalizar
from tests.seguridad.test_matriz_authz import USUARIOS

pytestmark = [pytest.mark.django_db]
scenarios("features/autorizacion.feature")


@given(parsers.parse('un usuario con rol "{rol}" autenticado'), target_fixture="usuario")
def _(rol: str, mundo_web: Mundo, ctx: dict[str, object]) -> str | None:
    ctx["rol"] = rol
    return USUARIOS[rol]


@given(parsers.parse('que "{usuario}" registró unas vacaciones'), target_fixture="sid")
def _(usuario: str, mundo_web: Mundo) -> str:
    return mundo_web.registrar(vacaciones(usuario)).solicitud_id.valor


@given("que RRHH intenta emitir una solicitud sobre su propia persona", target_fixture="intento")
def _() -> object:
    m = Mundo.nuevo()
    propia = replace(vacaciones("u-rrhh", "col-rrhh"), justificacion="vacaciones de RRHH")

    def intentar() -> None:
        m.emitir(propia)

    return intentar


@when(parsers.parse('solicita "{metodo} {ruta}"'), target_fixture="respuesta")
def _(
    metodo: str, ruta: str, usuario: str | None, mundo_web: Mundo, caplog: pytest.LogCaptureFixture
) -> object:
    sid = mundo_web.registrar(vacaciones()).solicitud_id.valor
    url = rutas()[ruta].replace("SOL-2026-000001", sid)
    with caplog.at_level(logging.WARNING, logger="jml.seguridad"):
        return getattr(como(usuario), metodo.lower())(url)


@when(parsers.parse('"{espectador}" solicita su detalle'), target_fixture="respuestas")
def _(espectador: str, sid: str) -> tuple[object, object]:
    c = como(espectador)
    return c.get(f"/solicitudes/{sid}"), c.get("/solicitudes/SOL-2026-999999")


@when(
    parsers.parse(
        '"{usuario}" registra otras vacaciones iguales mientras la primera sigue abierta'
    ),
    target_fixture="duplicado",
)
def _(usuario: str, mundo_web: Mundo) -> bool:
    with pytest.raises(SolicitudDuplicada):
        mundo_web.registrar(vacaciones(usuario))
    return True


@then(parsers.parse('la respuesta es "{resultado}"'))
def _(respuesta: object, resultado: str) -> None:
    codigo = respuesta.status_code  # type: ignore[attr-defined]
    assert str(codigo) == resultado


@then(parsers.parse('queda un evento "{evento}" con su usuario y la ruta'))
def _(evento: str, usuario: str | None, caplog: pytest.LogCaptureFixture) -> None:
    registros = [r for r in caplog.records if r.getMessage() == evento]
    assert len(registros) == 1
    assert registros[0].usuario == usuario  # type: ignore[attr-defined]
    assert registros[0].ruta == "bandeja"  # type: ignore[attr-defined]


@then("la respuesta es idéntica a la de un identificador inexistente")
def _(respuestas: tuple[object, object]) -> None:
    ajena, inexistente = respuestas
    assert ajena.status_code == inexistente.status_code == 404  # type: ignore[attr-defined]
    assert normalizar(bytes(ajena.content).decode()) == normalizar(  # type: ignore[attr-defined]
        bytes(inexistente.content).decode()  # type: ignore[attr-defined]
    )


@then("es rechazada con el motivo de autoaprobación")
def _(intento: object) -> None:
    with pytest.raises(AutoAprobacionProhibida):
        intento()  # type: ignore[operator]


@then("la segunda se rechaza como duplicada y queda una sola abierta")
def _(duplicado: bool) -> None:
    assert duplicado
    assert mod.Solicitud.objects.filter(estado="pendiente_aprobacion").count() == 1
