"""Item 2.5: el ingreso web de extremo a extremo con el cliente de Django (RF-01, RF-02, RF-04, CA-14).

Corre el adaptador REAL de Supabase contra el GoTrue simulado, y la base de pruebas por el ORM.
"""

import re
from datetime import timedelta
from typing import Any

import pytest
from django.test import Client

from jml.adaptadores.entrada.web import composicion
from jml.adaptadores.salida.identidad.supabase import ProveedorSupabase
from jml.adaptadores.salida.persistencia.repositorios import RepositoriosDjango
from tests.dobles.gotrue import CLAVE_PUBLICA, GoTrueSimulado
from tests.dobles.identidad import CODIGO_VALIDO
from tests.mundo import Mundo

pytestmark = pytest.mark.django_db

CORREO, CLAVE = "maria.gomez@andina.example", "una-clave-larga-123"


@pytest.fixture
def gotrue(monkeypatch: pytest.MonkeyPatch) -> GoTrueSimulado:
    m = Mundo.nuevo(repositorios=RepositoriosDjango)
    g = GoTrueSimulado()
    g.registrar(CORREO, CLAVE, "u-col")
    g.registrar("sin.alta@andina.example", CLAVE, "u-desconocido")
    proveedor = ProveedorSupabase("https://x.supabase.co", CLAVE_PUBLICA, g.cliente())
    monkeypatch.setattr(composicion, "proveedor_de_identidad", lambda: proveedor)
    monkeypatch.setattr(composicion, "reloj", lambda: m.reloj)
    g.mundo = m  # type: ignore[attr-defined]  # para avanzar el reloj en las pruebas
    return g


def texto(r: Any) -> str:
    return bytes(r.content).decode()


def contrasena(c: Client, correo: str = CORREO, clave: str = CLAVE) -> Any:
    return c.post("/ingreso", {"correo": correo, "contrasena": clave})


def ingresar(c: Client, correo: str = CORREO) -> Any:
    contrasena(c, correo)
    c.get("/ingreso/segundo-factor")  # primer ingreso: inscribe el TOTP
    return c.post("/ingreso/segundo-factor", {"codigo": CODIGO_VALIDO})


def test_contrasena_y_codigo_crean_la_sesion(gotrue: GoTrueSimulado) -> None:
    c = Client()
    r = ingresar(c)
    assert (r.status_code, r["Location"]) == (302, "/")
    assert c.session["usuario_id"] == "u-col"
    assert c.get("/solicitudes").status_code == 200


def test_CA_14_contrasena_correcta_sin_codigo_no_crea_sesion(gotrue: GoTrueSimulado) -> None:
    c = Client()
    r = contrasena(c)
    assert (r.status_code, r["Location"]) == (302, "/ingreso/segundo-factor")
    assert "usuario_id" not in c.session
    assert c.get("/solicitudes")["Location"] == "/ingreso"
    c.get("/ingreso/segundo-factor")
    r = c.post("/ingreso/segundo-factor", {"codigo": "000000"})
    assert "Código incorrecto" in texto(r)
    assert "usuario_id" not in c.session


def test_RF_02_el_primer_ingreso_muestra_la_clave_para_inscribir(gotrue: GoTrueSimulado) -> None:
    """S-30: clave para escribir a mano, sin QR."""
    c = Client()
    contrasena(c)
    r = c.get("/ingreso/segundo-factor")
    assert "JBSWY3DPEHPK3PXP" in texto(r)
    assert "no-store" in r["Cache-Control"]  # el secreto no queda en ninguna cache
    c.post("/ingreso/segundo-factor", {"codigo": CODIGO_VALIDO})
    c.post("/salir")
    otro = Client()
    contrasena(otro)
    assert "JBSWY3DPEHPK3PXP" not in texto(otro.get("/ingreso/segundo-factor"))


def test_RS_08_el_error_de_contrasena_es_generico(gotrue: GoTrueSimulado) -> None:
    mala = texto(contrasena(Client(), clave="incorrecta-123"))
    desconocido = texto(contrasena(Client(), correo="nadie@andina.example"))
    assert "Correo o contraseña incorrectos." in mala
    sin_csrf = re.compile(r'name="csrfmiddlewaretoken" value="[^"]+"')
    assert sin_csrf.sub("", mala.replace(CORREO, "")) == sin_csrf.sub(
        "", desconocido.replace("nadie@andina.example", "")
    )


def test_la_sesion_nunca_guarda_un_token_de_supabase(gotrue: GoTrueSimulado) -> None:
    c = Client()
    contrasena(c)
    a_medio = dict(c.session.items())
    c.get("/ingreso/segundo-factor")
    c.post("/ingreso/segundo-factor", {"codigo": CODIGO_VALIDO})
    completa = dict(c.session.items())
    for valores in (a_medio, completa):
        assert not any("." in str(v) and str(v).count(".") >= 2 for v in valores.values())  # JWT
    assert set(completa) <= {"usuario_id", "inicio", "_messages"}


def test_el_id_de_sesion_rota_en_cada_paso(gotrue: GoTrueSimulado) -> None:
    c = Client()
    c.get("/ingreso")
    contrasena(c)
    tras_contrasena = c.session.session_key
    c.get("/ingreso/segundo-factor")
    c.post("/ingreso/segundo-factor", {"codigo": CODIGO_VALIDO})
    assert c.session.session_key != tras_contrasena


def test_quien_no_tiene_alta_en_la_aplicacion_no_entra(gotrue: GoTrueSimulado) -> None:
    c = Client()
    r = ingresar(c, "sin.alta@andina.example")
    assert r.status_code == 403
    assert "no tiene acceso" in texto(r)
    assert "usuario_id" not in c.session


def test_sin_desafio_el_segundo_factor_vuelve_al_ingreso(gotrue: GoTrueSimulado) -> None:
    r = Client().get("/ingreso/segundo-factor")
    assert (r.status_code, r["Location"]) == (302, "/ingreso")


def test_supabase_caido_se_explica_sin_detalles(gotrue: GoTrueSimulado) -> None:
    gotrue.caido = True
    r = contrasena(Client())
    assert "no está disponible" in texto(r)
    assert "503" not in texto(r)


def test_salir_cierra_la_sesion(gotrue: GoTrueSimulado) -> None:
    c = Client()
    ingresar(c)
    assert c.post("/salir")["Location"] == "/ingreso"
    assert c.get("/solicitudes")["Location"] == "/ingreso"


def test_RF_04_la_sesion_dura_como_maximo_8_horas(gotrue: GoTrueSimulado) -> None:
    c = Client()
    ingresar(c)
    gotrue.mundo.reloj.avanzar(timedelta(hours=8, minutes=1))  # type: ignore[attr-defined]
    assert c.get("/solicitudes")["Location"] == "/ingreso"
    assert "usuario_id" not in c.session


def test_RF_04_la_inactividad_maxima_es_de_30_minutos() -> None:
    from django.conf import settings

    assert settings.SESSION_COOKIE_AGE == 30 * 60
    assert settings.SESSION_SAVE_EVERY_REQUEST is True  # cada peticion renueva los 30 min


def test_con_sesion_iniciada_el_ingreso_lleva_al_inicio(gotrue: GoTrueSimulado) -> None:
    c = Client()
    ingresar(c)
    assert c.get("/ingreso")["Location"] == "/"
