"""Gherkin de ingreso con segundo factor: invoca el ingreso web y el adaptador de Supabase."""

import pytest
from django.test import Client
from pytest_bdd import given, parsers, scenarios, then, when

from jml.adaptadores.entrada.web import composicion
from jml.aplicacion.puertos import CredencialesInvalidas
from tests.bdd.conftest import CLAVE, CORREO
from tests.dobles.gotrue import GoTrueSimulado
from tests.dobles.identidad import CODIGO_VALIDO
from tests.seguridad.rutas import rutas

pytestmark = [pytest.mark.django_db]
scenarios("features/ingreso.feature")

PUBLICAS = {"salud", "ingreso", "segundo_factor", "salir"}


@given("una persona con contraseña válida y el TOTP por inscribir", target_fixture="navegador")
def _(supabase: GoTrueSimulado) -> Client:
    return Client()


@given("una persona que ya consumió con éxito su desafío", target_fixture="desafio")
def _(supabase: GoTrueSimulado) -> str:
    p = composicion.proveedor_de_identidad()
    primer = p.autenticar(CORREO, CLAVE)
    p.inscribir_totp(primer.desafio_id)
    p.verificar_totp(primer.desafio_id, CODIGO_VALIDO)
    return primer.desafio_id


@when("ingresa su contraseña correcta y un código TOTP vigente", target_fixture="resultado")
def _(navegador: Client, ctx: dict[str, object]) -> object:
    ctx["sesion_antes"] = navegador.session.session_key
    navegador.post("/ingreso", {"correo": CORREO, "contrasena": CLAVE})
    navegador.get("/ingreso/segundo-factor")  # primer ingreso: inscribe el TOTP
    return navegador.post("/ingreso/segundo-factor", {"codigo": CODIGO_VALIDO})


@when("ingresa su contraseña correcta y omite el código")
def _(navegador: Client) -> None:
    navegador.post("/ingreso", {"correo": CORREO, "contrasena": CLAVE})


@when("presenta de nuevo el mismo desafío con el mismo código", target_fixture="rechazo")
def _(desafio: str) -> bool:
    with pytest.raises(CredencialesInvalidas):
        composicion.proveedor_de_identidad().verificar_totp(desafio, CODIGO_VALIDO)
    return True


@when(parsers.parse("falla cinco veces el código"), target_fixture="desafio")
def _(navegador: Client) -> str:
    p = composicion.proveedor_de_identidad()
    primer = p.autenticar(CORREO, CLAVE)
    p.inscribir_totp(primer.desafio_id)
    for _ in range(5):
        with pytest.raises(CredencialesInvalidas):
            p.verificar_totp(primer.desafio_id, "000000")
    return primer.desafio_id


@when("Supabase cae justo antes de verificar el código", target_fixture="resultado")
def _(navegador: Client, supabase: GoTrueSimulado) -> object:
    navegador.post("/ingreso", {"correo": CORREO, "contrasena": CLAVE})
    navegador.get("/ingreso/segundo-factor")
    supabase.caido = True
    return navegador.post("/ingreso/segundo-factor", {"codigo": CODIGO_VALIDO})


@then("se crea la sesión")
def _(navegador: Client) -> None:
    assert navegador.session["usuario_id"] == "u-col"


@then("el identificador de sesión cambió")
def _(navegador: Client, ctx: dict[str, object]) -> None:
    assert navegador.session.session_key != ctx["sesion_antes"]


@then("ninguna ruta protegida responde 200")
def _(navegador: Client) -> None:
    for nombre, url in rutas().items():
        if nombre in PUBLICAS:
            continue
        respuesta = navegador.get(url)
        if respuesta.status_code == 405:
            respuesta = navegador.post(url)
        assert respuesta.status_code != 200, (nombre, url)


@then("la sesión no guarda ningún token de Supabase")
def _(navegador: Client) -> None:
    contenido = repr(dict(navegador.session.items()))
    assert "eyJ" not in contenido  # prefijo de todo JWT
    assert "token" not in contenido.lower()


@then("el ingreso es rechazado")
def _(rechazo: bool) -> None:
    assert rechazo


@then("ni el código bueno sirve con ese desafío")
def _(desafio: str) -> None:
    with pytest.raises(CredencialesInvalidas):
        composicion.proveedor_de_identidad().verificar_totp(desafio, CODIGO_VALIDO)


@then("un ingreso nuevo con el código correcto sí funciona")
def _() -> None:
    p = composicion.proveedor_de_identidad()
    primer = p.autenticar(CORREO, CLAVE)
    p.inscribir_totp(primer.desafio_id)
    assert p.verificar_totp(primer.desafio_id, CODIGO_VALIDO).nivel == 2


@then("el ingreso falla con un mensaje genérico y sin sesión")
def _(resultado: object, navegador: Client) -> None:
    cuerpo = bytes(resultado.content).decode().lower()  # type: ignore[attr-defined]
    assert "no está disponible" in cuerpo
    assert "supabase" not in cuerpo
    assert "usuario_id" not in navegador.session
