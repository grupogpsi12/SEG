"""F8-02 (B-09): el middleware de seguridad y el formato de los logs, comparados exactos.

La mutacion mostro cuatro huecos: el middleware del proxy no se probaba con la cabecera ausente ni con cada
esquema; la correlacion no se probaba dentro de la vista; y el log JSON no fijaba su forma. Un log sin
`correlation_id` o con la fecha en otra zona rompe la trazabilidad que pide RS-09.
"""

import json
import logging
import re
from contextvars import Token

import pytest
from django.http import HttpRequest, HttpResponse
from django.test import RequestFactory, override_settings

from jml.adaptadores.entrada.web.middleware import (
    correlacion,
    politica_de_contenido,
    proxy_confiable,
    registrar_denegacion,
)
from jml.adaptadores.registro import CORRELACION, FormatoJSON

BUNKERWEB = "10.20.30.2"


def _ok(_: HttpRequest) -> HttpResponse:
    return HttpResponse("ok")


def _pasar(request: HttpRequest) -> HttpRequest:
    proxy_confiable(_ok)(request)
    return request


# --- proxy confiable (RS-05) --------------------------------------------------------------------


@override_settings(JML_PROXIES_CONFIABLES=[BUNKERWEB])
def test_del_proxy_confiable_se_toma_la_ultima_ip_y_el_esquema() -> None:
    r = RequestFactory().get(
        "/",
        REMOTE_ADDR=BUNKERWEB,
        HTTP_X_FORWARDED_FOR="9.9.9.9, 203.0.113.7",
        HTTP_X_FORWARDED_PROTO="https",
    )
    _pasar(r)
    assert (
        r.META["REMOTE_ADDR"] == "203.0.113.7"
    )  # la que agrego BunkerWeb, no la que mando el cliente
    assert r.META["wsgi.url_scheme"] == "https"
    assert "HTTP_X_FORWARDED_FOR" not in r.META
    assert "HTTP_X_FORWARDED_PROTO" not in r.META


@override_settings(JML_PROXIES_CONFIABLES=[BUNKERWEB])
@pytest.mark.parametrize(
    ("esquema", "queda"),
    [("http", "http"), ("https", "https"), ("gopher", "https"), ("HTTP", "https"), ("", "https")],
)
def test_solo_se_aceptan_los_esquemas_http_y_https(esquema: str, queda: str) -> None:
    r = RequestFactory().get(
        "/",
        REMOTE_ADDR=BUNKERWEB,
        HTTP_X_FORWARDED_FOR="203.0.113.7",
        HTTP_X_FORWARDED_PROTO=esquema,
    )
    r.META["wsgi.url_scheme"] = "https"  # el valor de partida; un esquema invalido no lo cambia
    _pasar(r)
    assert r.META["wsgi.url_scheme"] == queda


@override_settings(JML_PROXIES_CONFIABLES=[BUNKERWEB])
def test_sin_las_cabeceras_del_proxy_la_peticion_conserva_la_ip_de_bunkerweb() -> None:
    r = RequestFactory().get("/", REMOTE_ADDR=BUNKERWEB)
    _pasar(r)  # no debe lanzar aunque falten las dos cabeceras
    assert r.META["REMOTE_ADDR"] == BUNKERWEB


@override_settings(JML_PROXIES_CONFIABLES=[BUNKERWEB])
def test_una_ip_invalida_en_la_cabecera_deja_la_del_proxy() -> None:
    r = RequestFactory().get("/", REMOTE_ADDR=BUNKERWEB, HTTP_X_FORWARDED_FOR="no-soy-una-ip")
    _pasar(r)
    assert r.META["REMOTE_ADDR"] == BUNKERWEB


@override_settings(JML_PROXIES_CONFIABLES=[BUNKERWEB])
def test_de_un_origen_desconocido_las_cabeceras_se_descartan() -> None:
    r = RequestFactory().get(
        "/",
        REMOTE_ADDR="198.51.100.9",
        HTTP_X_FORWARDED_FOR="203.0.113.7",
        HTTP_X_FORWARDED_PROTO="http",
    )
    r.META["wsgi.url_scheme"] = "https"
    _pasar(r)
    assert r.META["REMOTE_ADDR"] == "198.51.100.9"
    assert r.META["wsgi.url_scheme"] == "https"
    assert (
        "HTTP_X_FORWARDED_FOR" not in r.META
    )  # ni siquiera quedan disponibles para el resto de la aplicacion


# --- correlation_id y CSP (RS-07, RS-09) -------------------------------------------------------


def test_sin_cabecera_se_genera_un_id_y_se_usa_dentro_de_la_vista_y_en_la_respuesta() -> None:
    visto: list[str] = []

    def vista(_: HttpRequest) -> HttpResponse:
        visto.append(CORRELACION.get())
        return HttpResponse("ok")

    respuesta = correlacion(vista)(RequestFactory().get("/"))
    assert re.fullmatch(r"[0-9a-f]{32}", respuesta["X-Request-ID"])
    assert visto == [respuesta["X-Request-ID"]]  # la vista y la respuesta comparten el id
    assert CORRELACION.get() == "-"  # y al terminar se restablece
    assert "X-Request-ID" in list(respuesta.headers)  # con la caja que busca el WAF


def test_un_id_recibido_con_forma_segura_se_conserva_y_uno_inseguro_se_cambia() -> None:
    bueno = correlacion(_ok)(RequestFactory().get("/", HTTP_X_REQUEST_ID="lab-f6-1234abcd"))
    assert bueno["X-Request-ID"] == "lab-f6-1234abcd"
    for malo in ("corto", "con espacios y simbolos <script>", "x" * 65):
        r = correlacion(_ok)(RequestFactory().get("/", HTTP_X_REQUEST_ID=malo))
        assert r["X-Request-ID"] != malo
        assert re.fullmatch(r"[0-9a-f]{32}", r["X-Request-ID"])


@override_settings(POLITICA_DE_CONTENIDO="default-src 'self'")
def test_la_politica_de_contenido_sale_con_su_nombre_canonico() -> None:
    r = politica_de_contenido(_ok)(RequestFactory().get("/"))
    assert "Content-Security-Policy" in list(r.headers)
    assert r["Content-Security-Policy"] == "default-src 'self'"


# --- denegaciones (B-25) ----------------------------------------------------------------------------


def test_una_denegacion_sin_ruta_resuelta_deja_el_evento_con_ruta_nula(
    caplog: pytest.LogCaptureFixture,
) -> None:
    r = RequestFactory().post("/ruta-que-no-existe")
    r.session = {"usuario_id": "u-col"}  # type: ignore[assignment]
    with caplog.at_level(logging.WARNING, logger="jml.seguridad"):
        registrar_denegacion(r)
    (registro,) = caplog.records
    assert registro.getMessage() == "acceso.denegado"
    assert (
        getattr(registro, "usuario"),  # noqa: B009  # `extra` del log, no un atributo declarado
        getattr(registro, "ruta"),  # noqa: B009
        getattr(registro, "metodo"),  # noqa: B009
    ) == ("u-col", None, "POST")


# --- formato JSON de los logs (RS-09) ----------------------------------------------------------


def _registro(**extra: object) -> logging.LogRecord:
    r = logging.LogRecord(
        "jml.prueba", logging.INFO, __file__, 1, "mensaje %s", ("con argumento",), None
    )
    r.created = 1760284800.123456  # 2025-10-12T16:00:00.123456Z
    for k, v in extra.items():
        setattr(r, k, v)
    return r


def test_el_log_json_tiene_exactamente_estos_campos_y_esta_forma() -> None:
    salida = json.loads(FormatoJSON().format(_registro()))
    assert salida == {
        "fecha": "2025-10-12T16:00:00.123456Z",
        "nivel": "INFO",
        "logger": "jml.prueba",
        "mensaje": "mensaje con argumento",
        "correlation_id": "-",  # sin el filtro de correlacion: el valor por defecto
    }


def test_los_campos_extra_se_agregan_y_los_estandar_no_se_duplican() -> None:
    salida = json.loads(FormatoJSON().format(_registro(usuario="u-col", correlation_id="abc12345")))
    assert salida["usuario"] == "u-col"
    assert salida["correlation_id"] == "abc12345"
    assert not ({"name", "msg", "args", "levelname", "pathname", "created"} & set(salida))


def test_el_log_json_conserva_los_acentos_sin_escaparlos() -> None:
    texto = FormatoJSON().format(_registro(nombre="María Gómez"))
    assert "María Gómez" in texto
    assert "\\u" not in texto


def test_la_excepcion_va_en_su_propio_campo() -> None:
    try:
        raise ValueError("fallo de prueba")
    except ValueError:
        import sys

        r = _registro()
        r.exc_info = sys.exc_info()
    salida = json.loads(FormatoJSON().format(r))
    assert "ValueError: fallo de prueba" in salida["excepcion"]


def test_la_marca_de_correlacion_se_restablece_tras_usarse() -> None:
    marca: Token[str] = CORRELACION.set("x")
    CORRELACION.reset(marca)
    assert CORRELACION.get() == "-"
