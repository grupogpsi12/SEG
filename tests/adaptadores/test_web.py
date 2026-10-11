"""Item 2.1: /salud y cabeceras de la aplicacion (RNF-01, RS-07)."""

import pytest
from django.db import OperationalError
from django.test import Client

from jml.adaptadores.entrada.web import vistas

CSP = "default-src 'self'; script-src 'self'; object-src 'none'; frame-ancestors 'none'"


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
