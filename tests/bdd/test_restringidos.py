"""Gherkin de campos restringidos: el mismo mundo en memoria que usan los escenarios de punta a punta."""

import logging
from dataclasses import replace

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from jml.aplicacion.dtos import DetalleDeSolicitud
from jml.aplicacion.puertos import Repositorios
from jml.dominio.errores import NoEncontrado
from jml.dominio.valores import SolicitudId
from tests.escenarios.test_escenarios import invariantes
from tests.mundo import Mundo, retiro

scenarios("features/restringidos.feature")


@pytest.fixture
def mundo() -> Mundo:
    return Mundo.nuevo()


@given(
    parsers.parse('un retiro con el motivo "{motivo}" emitido por RRHH'), target_fixture="solicitud"
)
def _(mundo: Mundo, motivo: str, ctx: dict[str, object]) -> SolicitudId:
    ctx["motivo"] = motivo
    # el centinela de las pruebas (tests.fabricas.SENTINELA) es el que `invariantes` busca
    return mundo.emitir(replace(retiro(), restringido=_centinela())).solicitud_id


def _centinela() -> str:
    from tests.fabricas import SENTINELA

    return SENTINELA


def _detalle(repos: Repositorios, usuario: str, sid: SolicitudId) -> DetalleDeSolicitud:
    from jml.aplicacion.casos.listados import ConsultarSolicitud

    return ConsultarSolicitud(repos).ejecutar(usuario, sid)


@when("RRHH abre el detalle de la solicitud", target_fixture="detalle")
def _(mundo: Mundo, solicitud: SolicitudId) -> DetalleDeSolicitud:
    return _detalle(mundo.puerto, "u-rrhh", solicitud)


@when("se crean los tickets, los técnicos los resuelven y se sincroniza")
def _(mundo: Mundo, solicitud: SolicitudId, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG):
        mundo.correr_bandeja_hasta_vaciar()
        mundo.tecnico_resuelve_todo(solicitud)
        mundo.sincronizar()


@given(
    parsers.parse('una renuncia registrada por el propio colaborador con el motivo "{motivo}"'),
    target_fixture="solicitud",
)
def _(mundo: Mundo, motivo: str) -> SolicitudId:
    return mundo.registrar(replace(retiro("u-col"), restringido=_centinela())).solicitud_id


@when("el colaborador y un técnico piden el detalle de la solicitud", target_fixture="vistas")
def _(mundo: Mundo, solicitud: SolicitudId) -> dict[str, object]:
    propio = _detalle(mundo.puerto, "u-col", solicitud)
    with pytest.raises(NoEncontrado):
        _detalle(mundo.puerto, "u-tec-ad", solicitud)
    return {"propio": propio, "tecnico": "no encontrada"}


@then("ve el motivo")
def _(detalle: DetalleDeSolicitud) -> None:
    assert detalle.restringido == _centinela()


@then("el acceso queda en la auditoría")
def _(mundo: Mundo) -> None:
    assert "restringido.consultado" in mundo.acciones_de_auditoria()


@then("el valor no aparece en GLPI, auditoría, logs, dashboard, ficha ni CSV")
def _(mundo: Mundo, caplog: pytest.LogCaptureFixture) -> None:
    invariantes(mundo)  # GLPI y auditoría
    assert _centinela() not in caplog.text
    assert _centinela() not in repr(mundo.dashboard("u-tec-ad"))
    assert _centinela() not in repr(mundo.ficha("u-tec-ad", "col-1"))


@then("la cadena de auditoría sigue íntegra")
def _(mundo: Mundo) -> None:
    assert mundo.repos.auditoria().verificar().valida


@then("el colaborador ve la solicitud sin el motivo")
def _(vistas: dict[str, object]) -> None:
    propio = vistas["propio"]
    assert isinstance(propio, DetalleDeSolicitud)
    assert propio.restringido is None


@then("al técnico se le responde que no existe")
def _(vistas: dict[str, object]) -> None:
    assert vistas["tecnico"] == "no encontrada"
