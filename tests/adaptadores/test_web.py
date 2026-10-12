"""Item 2.1: /salud y cabeceras de la aplicacion (RNF-01, RS-07)."""

from typing import Any

import pytest
from django.db import OperationalError
from django.test import Client

from jml.adaptadores.entrada.web import vistas

CSP = "default-src 'self'; script-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"


@pytest.mark.django_db
def test_salud_responde_200_si_la_base_responde() -> None:
    r = Client().get("/salud")
    assert r.status_code == 200
    assert r.json() == {"estado": "ok"}


def test_salud_responde_503_generico_si_la_base_no_responde(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Caida:
        def ensure_connection(self) -> None:
            raise OperationalError("could not connect to server: SECRETO-INTERNO")

    # Se reemplaza la referencia que usa la vista, NO la conexion compartida: al restaurar un
    # atributo de la instancia, monkeypatch dejaria fijo el bloqueo de pytest-django.
    monkeypatch.setattr(vistas, "connections", {"default": _Caida()})
    r = Client().get("/salud")
    assert r.status_code == 503
    assert r.json() == {"estado": "no_disponible"}
    assert b"SECRETO-INTERNO" not in r.content  # RNF-02: sin errores internos


@pytest.mark.django_db
def test_salud_solo_acepta_get() -> None:
    assert Client().post("/salud").status_code == 405


@pytest.mark.django_db
def test_RS_07_django_envia_la_csp_y_x_frame_options() -> None:
    r = Client().get("/salud")
    assert r["Content-Security-Policy"] == CSP
    assert r["X-Frame-Options"] == "DENY"
    for propia_de_bunkerweb in (
        "Strict-Transport-Security",
        "Referrer-Policy",
        "X-Content-Type-Options",
    ):
        assert propia_de_bunkerweb not in r


@pytest.mark.django_db
def test_cada_respuesta_lleva_un_correlation_id() -> None:
    r = Client().get("/salud")
    assert len(r["X-Request-ID"]) == 32


@pytest.mark.django_db
def test_un_correlation_id_valido_del_borde_se_respeta() -> None:
    r = Client().get("/salud", HTTP_X_REQUEST_ID="abcdef12-3456-7890")
    assert r["X-Request-ID"] == "abcdef12-3456-7890"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "malo",
    [
        "corto",
        "con espacios largos aqui",
        "<script>alert(1)</script>",
        "x" * 200,
        "a\r\nSet-Cookie: x=1",
    ],
)
def test_un_correlation_id_malicioso_se_reemplaza(malo: str) -> None:
    """Las cabeceras son input no confiable (RS-05): no se reflejan sin validar."""
    r = Client().get("/salud", HTTP_X_REQUEST_ID=malo)
    assert r["X-Request-ID"] != malo
    assert len(r["X-Request-ID"]) == 32


@pytest.mark.django_db
def test_un_host_no_permitido_se_rechaza() -> None:
    assert Client(HTTP_HOST="atacante.example").get("/salud").status_code == 400


# --- RS-05: confianza en X-Forwarded-* solo desde BunkerWeb -------------------------------------


def _por_el_proxy(remoto: str, **cabeceras: str) -> tuple[str, str]:
    from django.http import HttpRequest, HttpResponse
    from django.test import RequestFactory

    from jml.adaptadores.entrada.web.middleware import proxy_confiable

    visto: dict[str, str] = {}

    def vista(request: HttpRequest) -> HttpResponse:
        visto["ip"], visto["esquema"] = str(request.META["REMOTE_ADDR"]), str(request.scheme)
        visto["xff"] = str(request.META.get("HTTP_X_FORWARDED_FOR", "<borrada>"))
        return HttpResponse()

    fabrica: Any = RequestFactory()  # los META extra van como kwargs, que el stub no tipa
    proxy_confiable(vista)(fabrica.get("/", REMOTE_ADDR=remoto, **cabeceras))
    assert visto["xff"] == "<borrada>"  # nadie mas abajo la vuelve a leer
    return visto["ip"], visto["esquema"]


def test_RS_05_desde_bunkerweb_se_toma_el_cliente_y_el_esquema() -> None:
    assert _por_el_proxy(
        "10.20.40.2", HTTP_X_FORWARDED_FOR="1.1.1.1, 203.0.113.9", HTTP_X_FORWARDED_PROTO="https"
    ) == ("203.0.113.9", "https")


def test_RS_05_desde_otro_origen_las_cabeceras_se_ignoran() -> None:
    assert _por_el_proxy(
        "172.18.0.9", HTTP_X_FORWARDED_FOR="203.0.113.9", HTTP_X_FORWARDED_PROTO="https"
    ) == ("172.18.0.9", "http")


@pytest.mark.parametrize("xff", ["", "no-es-una-ip", "203.0.113.9, <script>"])
def test_RS_05_una_cabecera_invalida_deja_la_ip_del_proxy(xff: str) -> None:
    assert _por_el_proxy(
        "10.20.40.2", HTTP_X_FORWARDED_FOR=xff, HTTP_X_FORWARDED_PROTO="gopher"
    ) == (
        "10.20.40.2",
        "http",
    )


@pytest.mark.django_db
def test_whitenoise_sirve_los_estaticos_sin_nginx() -> None:
    r = Client().get("/static/web/estilo.css")
    assert r.status_code == 200
    assert b".grafico" in b"".join(r.streaming_content)  # type: ignore[attr-defined]
