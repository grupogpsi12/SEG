"""F3-U01 (T1, T2): un desafío de segundo factor sirve una sola vez y solo a su sesión.

Defecto sembrado F5-09: quitar `_descartar` tras verificar permitiría un segundo uso del mismo
desafío. La unicidad del código TOTP en sí la impone Supabase (no se puede probar sin secreto real).
"""

import pytest
from django.test import Client

from jml.adaptadores.entrada.web import composicion
from jml.adaptadores.entrada.web.ingreso import SESION_DESAFIO
from jml.adaptadores.salida.identidad.supabase import VIGENCIA_S, ProveedorSupabase
from jml.adaptadores.salida.persistencia.repositorios import RepositoriosDjango
from jml.aplicacion.puertos import CredencialesInvalidas
from tests.dobles.gotrue import CLAVE_PUBLICA, GoTrueSimulado
from tests.dobles.identidad import CODIGO_VALIDO
from tests.mundo import Mundo

pytestmark = pytest.mark.seguridad

CORREO, CLAVE = "maria.gomez@andina.example", "una-clave-larga-123"
URL = "https://x.supabase.co"


@pytest.fixture
def servidor() -> GoTrueSimulado:
    g = GoTrueSimulado()
    g.registrar(CORREO, CLAVE, "u-col")
    g.registrar("otro@andina.example", CLAVE, "u-otro")
    return g


@pytest.fixture
def web(servidor: GoTrueSimulado, monkeypatch: pytest.MonkeyPatch) -> GoTrueSimulado:
    m = Mundo.nuevo(repositorios=RepositoriosDjango)
    proveedor = ProveedorSupabase(URL, CLAVE_PUBLICA, servidor.cliente())
    monkeypatch.setattr(composicion, "proveedor_de_identidad", lambda: proveedor)
    monkeypatch.setattr(composicion, "reloj", lambda: m.reloj)
    return servidor


def test_U01_un_desafio_ya_verificado_no_vuelve_a_servir(servidor: GoTrueSimulado) -> None:
    p = ProveedorSupabase(URL, CLAVE_PUBLICA, servidor.cliente())
    primer = p.autenticar(CORREO, CLAVE)
    p.inscribir_totp(primer.desafio_id)
    assert p.verificar_totp(primer.desafio_id, CODIGO_VALIDO).nivel == 2
    with pytest.raises(CredencialesInvalidas):
        p.verificar_totp(primer.desafio_id, CODIGO_VALIDO)


def test_U01_cada_desafio_resuelve_a_su_dueno_y_uno_inventado_no_existe(
    servidor: GoTrueSimulado,
) -> None:
    p = ProveedorSupabase(URL, CLAVE_PUBLICA, servidor.cliente())
    a = p.autenticar(CORREO, CLAVE)
    b = p.autenticar("otro@andina.example", CLAVE)
    p.inscribir_totp(a.desafio_id)
    p.inscribir_totp(b.desafio_id)
    assert p.verificar_totp(b.desafio_id, CODIGO_VALIDO).usuario_id == "u-otro"
    assert p.verificar_totp(a.desafio_id, CODIGO_VALIDO).usuario_id == "u-col"
    with pytest.raises(CredencialesInvalidas):
        p.verificar_totp(a.desafio_id[:-1] + "x", CODIGO_VALIDO)


@pytest.mark.django_db
def test_U01_una_sesion_sin_contrasena_no_entra_con_un_codigo_valido(web: GoTrueSimulado) -> None:
    atacante = Client()
    r = atacante.post("/ingreso/segundo-factor", {"codigo": CODIGO_VALIDO})
    assert (r.status_code, r["Location"]) == (302, "/ingreso")
    assert "usuario_id" not in atacante.session


@pytest.mark.django_db
def test_U01_el_desafio_de_una_sesion_no_abre_la_de_otra(web: GoTrueSimulado) -> None:
    victima, atacante = Client(), Client()
    victima.post("/ingreso", {"correo": CORREO, "contrasena": CLAVE})  # espera su código
    atacante.post("/ingreso", {"correo": "otro@andina.example", "contrasena": CLAVE})
    atacante.get("/ingreso/segundo-factor")
    atacante.post("/ingreso/segundo-factor", {"codigo": CODIGO_VALIDO})
    # el atacante, a lo sumo, es él mismo (cuenta sin alta en la aplicación): nunca la víctima
    assert atacante.session.get("usuario_id") != "u-col"
    assert "usuario_id" not in victima.session


@pytest.mark.django_db
def test_U01_tras_entrar_el_desafio_ya_no_esta_en_la_sesion(web: GoTrueSimulado) -> None:
    c = Client()
    c.post("/ingreso", {"correo": CORREO, "contrasena": CLAVE})
    c.get("/ingreso/segundo-factor")
    c.post("/ingreso/segundo-factor", {"codigo": CODIGO_VALIDO})
    assert c.session["usuario_id"] == "u-col"
    assert SESION_DESAFIO not in c.session


@pytest.mark.django_db
def test_U01_si_supabase_cae_entre_la_contrasena_y_el_codigo_no_hay_sesion(
    web: GoTrueSimulado,
) -> None:
    c = Client()
    c.post("/ingreso", {"correo": CORREO, "contrasena": CLAVE})
    web.caido = True
    r = c.get("/ingreso/segundo-factor")  # intenta inscribir el TOTP
    assert r.status_code == 200
    assert "no está disponible" in r.content.decode()
    r = c.post("/ingreso/segundo-factor", {"codigo": CODIGO_VALIDO})
    assert r.status_code == 200
    assert "no está disponible" in r.content.decode()
    assert "usuario_id" not in c.session


@pytest.mark.django_db
def test_U01_un_desafio_vencido_manda_de_nuevo_al_ingreso_y_limpia_la_sesion(
    servidor: GoTrueSimulado, monkeypatch: pytest.MonkeyPatch
) -> None:
    ahora = [1000.0]
    m = Mundo.nuevo(repositorios=RepositoriosDjango)
    proveedor = ProveedorSupabase(URL, CLAVE_PUBLICA, servidor.cliente(), lambda: ahora[0])
    monkeypatch.setattr(composicion, "proveedor_de_identidad", lambda: proveedor)
    monkeypatch.setattr(composicion, "reloj", lambda: m.reloj)
    c = Client()
    c.post("/ingreso", {"correo": CORREO, "contrasena": CLAVE})
    ahora[0] += VIGENCIA_S + 1
    r = c.get("/ingreso/segundo-factor")
    assert (r.status_code, r["Location"]) == (302, "/ingreso")
    assert SESION_DESAFIO not in c.session
