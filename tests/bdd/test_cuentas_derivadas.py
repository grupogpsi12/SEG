"""Gherkin de cuentas derivadas: el mundo en memoria con el GLPI simulado, como los escenarios de punta a punta."""

from datetime import timedelta

import pytest
from pytest_bdd import given, scenarios, then, when

from jml.dominio.cuentas import Cuenta
from jml.dominio.tipos import EstadoDeCuenta, EstadoSolicitud, MarcaDeCuenta, SistemaDeCuenta
from jml.dominio.valores import SolicitudId
from tests.mundo import Mundo, ingreso

scenarios("features/cuentas-derivadas.feature")

S, E = EstadoSolicitud, EstadoDeCuenta


@pytest.fixture
def mundo() -> Mundo:
    return Mundo.nuevo()


def _gid(m: Mundo, sid: SolicitudId, cola: str) -> str:
    with m.puerto.unidad_de_trabajo() as u:
        t = next(
            t
            for t in u.tickets.de_solicitud(sid)
            if t.ticket.cola.value == cola and t.ticket.clase.value == "cierre_inmediato"
        )
    assert t.id_externo is not None
    return t.id_externo


def _cuenta(m: Mundo, sid: SolicitudId, sistema: SistemaDeCuenta) -> Cuenta:
    colaborador = m.solicitud(sid).colaborador_id
    with m.puerto.unidad_de_trabajo() as u:
        c = u.cuentas.obtener(colaborador, sistema)
    assert c is not None
    return c


def _sincronizar(m: Mundo) -> None:
    m.avanzar(timedelta(minutes=5))
    m.sincronizar()


@given("un ingreso con sus tickets creados en GLPI", target_fixture="sid")
def _(mundo: Mundo) -> SolicitudId:
    r = mundo.emitir(ingreso())
    mundo.correr_bandeja_hasta_vaciar()
    mundo.sincronizar()
    return r.solicitud_id


@given("que el técnico de AD resolvió sin solución y se sincronizó")
def _(mundo: Mundo, sid: SolicitudId) -> None:
    for cola in ("COMUNICACIONES", "LICENCIAS"):
        mundo.glpi.resolver(_gid(mundo, sid, cola), con_solucion=True)
    mundo.glpi.resolver(_gid(mundo, sid, "INVENTARIO"), con_solucion=True, documentos=1)
    mundo.glpi.resolver(_gid(mundo, sid, "AD"), con_solucion=False)
    _sincronizar(mundo)


@given("que todo se resolvió y la solicitud cerró")
def _(mundo: Mundo, sid: SolicitudId) -> None:
    mundo.tecnico_resuelve_todo(sid)
    mundo.sincronizar()
    assert mundo.solicitud(sid).estado is S.CERRADA


@when("los técnicos resuelven todos los tickets con solución y acta, y se sincroniza")
def _(mundo: Mundo, sid: SolicitudId) -> None:
    mundo.tecnico_resuelve_todo(sid)
    mundo.sincronizar()


@when("el técnico de AD resuelve su ticket sin escribir la solución y se sincroniza")
def _(mundo: Mundo, sid: SolicitudId) -> None:
    for cola in ("COMUNICACIONES", "LICENCIAS"):
        mundo.glpi.resolver(_gid(mundo, sid, cola), con_solucion=True)
    mundo.glpi.resolver(_gid(mundo, sid, "INVENTARIO"), con_solucion=True, documentos=1)
    mundo.glpi.resolver(_gid(mundo, sid, "AD"), con_solucion=False)
    _sincronizar(mundo)


@when("el técnico registra la solución y se sincroniza otra vez")
def _(mundo: Mundo, sid: SolicitudId) -> None:
    mundo.glpi.resolver(_gid(mundo, sid, "AD"), con_solucion=True)
    _sincronizar(mundo)


@when(
    "los técnicos resuelven todos los tickets con solución pero sin el acta de Inventario, y se sincroniza"
)
def _(mundo: Mundo, sid: SolicitudId) -> None:
    mundo.tecnico_resuelve_todo(sid, con_acta=False)
    mundo.sincronizar()


@when("el ticket de Licencias se reabre en GLPI y se sincroniza")
def _(mundo: Mundo, sid: SolicitudId) -> None:
    mundo.glpi.reabrir(_gid(mundo, sid, "LICENCIAS"))
    _sincronizar(mundo)


@then("la solicitud queda cerrada")
@then("la solicitud sigue cerrada")
def _(mundo: Mundo, sid: SolicitudId) -> None:
    assert mundo.solicitud(sid).estado is S.CERRADA


@then("la solicitud sigue en ejecución")
def _(mundo: Mundo, sid: SolicitudId) -> None:
    assert mundo.solicitud(sid).estado is S.EN_EJECUCION


@then("las cuentas de AD, RED y M365 quedan activas")
def _(mundo: Mundo, sid: SolicitudId) -> None:
    for sistema in (SistemaDeCuenta.AD, SistemaDeCuenta.RED, SistemaDeCuenta.M365):
        assert _cuenta(mundo, sid, sistema).estado is E.ACTIVA


@then("la cuenta de AD no se activa y queda marcada como cierre sin solución")
def _(mundo: Mundo, sid: SolicitudId) -> None:
    c = _cuenta(mundo, sid, SistemaDeCuenta.AD)
    assert (c.estado, c.marca) == (E.PENDIENTE_ALTA, MarcaDeCuenta.CIERRE_SIN_SOLUCION)


@then("la cuenta de AD queda activa")
def _(mundo: Mundo, sid: SolicitudId) -> None:
    c = _cuenta(mundo, sid, SistemaDeCuenta.AD)
    assert (c.estado, c.marca) == (E.ACTIVA, None)


@then("la cuenta de M365 vuelve a pendiente con la marca de reabierto")
def _(mundo: Mundo, sid: SolicitudId) -> None:
    c = _cuenta(mundo, sid, SistemaDeCuenta.M365)
    assert (c.estado, c.marca) == (E.PENDIENTE_ALTA, MarcaDeCuenta.REABIERTO)
