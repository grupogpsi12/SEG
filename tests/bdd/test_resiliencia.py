"""Gherkin de resiliencia: reutiliza los fallos programables del GLPI simulado y el adaptador de Supabase."""

from dataclasses import replace

import pytest
from django.db import DatabaseError, connections
from django.test import Client
from pytest_bdd import given, scenarios, then, when

from jml.adaptadores.salida.identidad.supabase import ProveedorSupabase
from jml.aplicacion.bandeja import MAX_INTENTOS, espera_de_reintento
from jml.aplicacion.puertos import CredencialesInvalidas
from jml.dominio.tipos import EstadoSolicitud
from jml.dominio.valores import SolicitudId
from tests.dobles.glpi import Fallo
from tests.dobles.gotrue import CLAVE_PUBLICA, GoTrueSimulado
from tests.dobles.identidad import CODIGO_VALIDO
from tests.mundo import Mundo, ingreso, vacaciones

scenarios("features/resiliencia.feature")

S = EstadoSolicitud


@pytest.fixture
def mundo() -> Mundo:
    return Mundo.nuevo()


@given("que GLPI está caído")
def _(mundo: Mundo) -> None:
    mundo.glpi.caer()


@given("que GLPI crea el ticket pero la respuesta se pierde")
def _(mundo: Mundo) -> None:
    mundo.glpi.programar(Fallo.DESPUES)


@when("RRHH emite un ingreso y el worker lo intenta varias veces", target_fixture="sid")
def _(mundo: Mundo) -> SolicitudId:
    r = mundo.emitir(ingreso())
    for _ in range(3):
        mundo.bandeja()
        mundo.avanzar(espera_de_reintento(1))
    return r.solicitud_id


@when("RRHH emite unas vacaciones y el worker agota los diez intentos", target_fixture="sid")
def _(mundo: Mundo) -> SolicitudId:
    r = mundo.emitir(replace(vacaciones("u-rrhh"), justificacion="vacaciones"))
    for ronda in range(1, MAX_INTENTOS + 1):
        mundo.bandeja()
        mundo.avanzar(espera_de_reintento(ronda))
    return r.solicitud_id


@when("GLPI se recupera y el worker procesa la bandeja")
def _(mundo: Mundo) -> None:
    mundo.glpi.recuperar()
    mundo.correr_bandeja_hasta_vaciar()


@when("GLPI se recupera y el Administrador reintenta la emisión")
def _(mundo: Mundo, sid: SolicitudId) -> None:
    mundo.glpi.recuperar()
    mundo.reintentar("u-admin", sid)
    mundo.correr_bandeja_hasta_vaciar()


@when("el worker reintenta la creación", target_fixture="sid")
def _(mundo: Mundo) -> SolicitudId:
    r = mundo.emitir(replace(vacaciones("u-rrhh"), justificacion="vacaciones"))
    mundo.correr_bandeja_hasta_vaciar()
    return r.solicitud_id


@when("la base de datos no responde", target_fixture="respuesta")
def _(monkeypatch: pytest.MonkeyPatch, django_db_blocker: object) -> object:
    def caida() -> None:
        raise DatabaseError("sin conexion")

    with django_db_blocker.unblock():  # type: ignore[attr-defined]
        monkeypatch.setattr(connections["default"], "ensure_connection", caida)
        return Client().get("/salud")


@given("una persona que ya pasó la contraseña y espera su código", target_fixture="desafio")
def _() -> str:
    g = GoTrueSimulado()
    g.registrar("ana@andina.example", "una-clave-larga-123", "u-ana")
    antes = ProveedorSupabase("https://x.supabase.co", CLAVE_PUBLICA, g.cliente())
    primer = antes.autenticar("ana@andina.example", "una-clave-larga-123")
    antes.inscribir_totp(primer.desafio_id)
    return primer.desafio_id


@when("el proceso web se reinicia y presenta su código", target_fixture="rechazo")
def _(desafio: str) -> bool:
    g = GoTrueSimulado()
    g.registrar("ana@andina.example", "una-clave-larga-123", "u-ana")
    despues = ProveedorSupabase(
        "https://x.supabase.co", CLAVE_PUBLICA, g.cliente()
    )  # memoria vacía
    with pytest.raises(CredencialesInvalidas):
        despues.verificar_totp(desafio, CODIGO_VALIDO)
    return True


@then("la solicitud sigue aprobada y no se creó nada en GLPI")
def _(mundo: Mundo, sid: SolicitudId) -> None:
    assert mundo.solicitud(sid).estado is S.APROBADA
    assert mundo.glpi.tickets_remotos() == []


@then("existe exactamente un ticket por cada clave")
def _(mundo: Mundo) -> None:
    assert mundo.glpi.creaciones_reales
    assert set(mundo.glpi.creaciones_reales.values()) == {1}


@then("la solicitud queda en error")
def _(mundo: Mundo, sid: SolicitudId) -> None:
    assert mundo.solicitud(sid).estado is S.ERROR


@then("la solicitud llega a en ejecución sin tickets duplicados")
def _(mundo: Mundo, sid: SolicitudId) -> None:
    assert mundo.solicitud(sid).estado is S.EN_EJECUCION
    assert set(mundo.glpi.creaciones_reales.values()) == {1}


@then("el chequeo de salud responde 503 con un cuerpo genérico")
def _(respuesta: object) -> None:
    assert respuesta.status_code == 503  # type: ignore[attr-defined]
    cuerpo = bytes(respuesta.content).decode()  # type: ignore[attr-defined]
    assert cuerpo == '{"estado": "no_disponible"}'


@then("el desafío ya no existe y no entra")
def _(rechazo: bool) -> None:
    assert rechazo
