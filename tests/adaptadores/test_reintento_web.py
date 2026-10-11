"""Item 2.12: el Administrador ve las solicitudes en `error` y las reintenta (RF-38, ADR-026)."""

from typing import Any

import pytest
from django.test import Client

from jml.adaptadores.entrada.web import composicion
from jml.adaptadores.salida.persistencia.repositorios import RepositoriosDjango
from jml.dominio.tipos import EstadoSolicitud
from jml.dominio.valores import SolicitudId
from tests.fabricas import AHORA
from tests.mundo import Mundo, ingreso

pytestmark = pytest.mark.django_db


@pytest.fixture
def con_error(monkeypatch: pytest.MonkeyPatch) -> tuple[Mundo, SolicitudId]:
    """Un ingreso cuya copia del soporte se perdio antes de subirse pasa a `error` (RD-12)."""
    m = Mundo.nuevo(repositorios=RepositoriosDjango)
    r = m.emitir(ingreso())
    m.soportes.perder(m.soportes.nombres()[0])
    m.bandeja()
    assert m.solicitud(r.solicitud_id).estado is EstadoSolicitud.ERROR
    monkeypatch.setattr(composicion, "reloj", lambda: m.reloj)
    return m, r.solicitud_id


def como(usuario: str) -> Client:
    c = Client()
    s = c.session
    s["usuario_id"], s["inicio"] = usuario, AHORA.timestamp()
    s.save()
    return c


def texto(r: Any) -> str:
    return bytes(r.content).decode()


def test_el_administrador_ve_la_solicitud_en_error_y_la_reintenta(
    con_error: tuple[Mundo, SolicitudId],
) -> None:
    m, sid = con_error
    admin = como("u-admin")
    assert sid.valor in texto(admin.get("/errores"))
    assert "/errores" in texto(admin.get("/solicitudes"))  # en el menu
    r = admin.post(f"/solicitudes/{sid.valor}/reintentar", follow=True)
    assert "devuelta a la bandeja" in texto(r)
    assert m.solicitud(sid).estado is not EstadoSolicitud.ERROR
    assert sid.valor not in texto(admin.get("/errores"))


@pytest.mark.parametrize("usuario", ["u-rrhh", "u-tec-ad", "u-aud", "u-col"])
def test_RF_38_solo_el_administrador(con_error: tuple[Mundo, SolicitudId], usuario: str) -> None:
    m, sid = con_error
    c = como(usuario)
    assert c.get("/errores").status_code == 403
    r = c.post(f"/solicitudes/{sid.valor}/reintentar", follow=True)
    assert r.status_code == 200
    assert "No tiene permiso" in texto(r)
    assert m.solicitud(sid).estado is EstadoSolicitud.ERROR


def test_reintentar_una_que_no_esta_en_error_se_explica(
    con_error: tuple[Mundo, SolicitudId],
) -> None:
    _, sid = con_error
    admin = como("u-admin")
    admin.post(f"/solicitudes/{sid.valor}/reintentar")
    r = admin.post(f"/solicitudes/{sid.valor}/reintentar", follow=True)
    assert "ya no está en un estado" in texto(r)
