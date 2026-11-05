"""Gherkin de cabeceras hostiles. La versión contra el WAF real es `auditoria/scripts/cabeceras-hostiles.sh`."""

import pytest
from django.http import HttpRequest, HttpResponse
from django.test import Client, RequestFactory
from pytest_bdd import given, parsers, scenarios, then, when

from jml.adaptadores.entrada.web import middleware
from jml.adaptadores.salida.persistencia import models as mod
from tests.bdd.conftest import como
from tests.mundo import Mundo, vacaciones

pytestmark = [pytest.mark.django_db]
scenarios("features/cabeceras.feature")


def _huella() -> dict[str, int]:
    return {
        "solicitudes": mod.Solicitud.objects.count(),
        "auditoria": mod.RegistroDeAuditoria.objects.count(),
        "colaboradores": mod.Colaborador.objects.count(),
    }


@given("la base de datos con sus filas contadas", target_fixture="antes")
def _(mundo_web: Mundo) -> dict[str, int]:
    mundo_web.registrar(vacaciones())
    return _huella()


@when(
    parsers.parse('se envía una petición válida con la cabecera "{cabecera}" y el valor "{valor}"'),
    target_fixture="respuesta",
)
def _(cabecera: str, valor: str) -> HttpResponse:
    cliente = como("u-col")
    if cabecera == "Cookie":
        nombre, _, contenido = valor.partition("=")
        cliente.cookies[nombre] = contenido
        return cliente.get("/solicitudes")  # type: ignore[return-value]
    return cliente.get("/solicitudes", headers={cabecera: valor})  # type: ignore[return-value]


@when(parsers.parse('se envía una petición con "Host: {host}"'), target_fixture="respuesta")
def _(host: str) -> HttpResponse:
    return Client().get("/salud", HTTP_HOST=host)  # type: ignore[return-value]


@when(
    parsers.parse('una petición llega desde "{origen}" declarando "X-Forwarded-For: {reenviada}"'),
    target_fixture="peticion",
)
def _(origen: str, reenviada: str) -> HttpRequest:
    visto: dict[str, HttpRequest] = {}

    def vista(request: HttpRequest) -> HttpResponse:
        visto["peticion"] = request
        return HttpResponse()

    request = RequestFactory().get("/salud", REMOTE_ADDR=origen, HTTP_X_FORWARDED_FOR=reenviada)
    middleware.proxy_confiable(vista)(request)
    return visto["peticion"]


@then(
    "la aplicación responde con una redirección o una página normal, nunca con un error de servidor"
)
def _(respuesta: HttpResponse) -> None:
    assert respuesta.status_code < 500


@then("la base de datos conserva las mismas filas")
def _(antes: dict[str, int]) -> None:
    assert _huella() == antes


@then(parsers.parse("la respuesta es {codigo:d}"))
def _(respuesta: HttpResponse, codigo: int) -> None:
    assert respuesta.status_code == codigo


@then(parsers.parse('la dirección del cliente sigue siendo "{ip}"'))
@then(parsers.parse('la dirección del cliente es "{ip}"'))
def _(peticion: HttpRequest, ip: str) -> None:
    assert peticion.META["REMOTE_ADDR"] == ip


@then("la cabecera reenviada ya no está en la petición")
def _(peticion: HttpRequest) -> None:
    assert "HTTP_X_FORWARDED_FOR" not in peticion.META
