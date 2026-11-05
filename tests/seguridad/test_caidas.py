"""F3-U07 (T11): con Supabase y GLPI caídos, ninguna ruta protegida responde 200 ni filtra detalle.

GLPI: la web nunca lo llama (el worker es su único cliente), así que su caída no puede cambiar lo
que responde la web; se comprueba por estructura. Supabase: el ingreso falla con un mensaje
genérico y, sin sesión, todas las rutas protegidas redirigen al ingreso.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from django.test import Client

from jml.adaptadores.entrada.web import composicion
from jml.adaptadores.salida.identidad.supabase import ProveedorSupabase
from jml.adaptadores.salida.persistencia.repositorios import RepositoriosDjango
from tests.dobles.gotrue import CLAVE_PUBLICA, GoTrueSimulado
from tests.mundo import Mundo
from tests.seguridad.rutas import rutas

pytestmark = [pytest.mark.seguridad, pytest.mark.django_db]

RAIZ = Path(__file__).resolve().parents[2]
PUBLICAS = {"salud", "ingreso", "segundo_factor", "salir"}
PROHIBIDO_EN_RESPUESTAS = ("supabase", "traceback", "gotrue", "httpx", "503", "exception", "/run/")


@pytest.fixture
def caido(monkeypatch: pytest.MonkeyPatch) -> GoTrueSimulado:
    m = Mundo.nuevo(repositorios=RepositoriosDjango)
    g = GoTrueSimulado()
    g.registrar("maria.gomez@andina.example", "una-clave-larga-123", "u-col")
    g.caido = True
    proveedor = ProveedorSupabase("https://x.supabase.co", CLAVE_PUBLICA, g.cliente())
    monkeypatch.setattr(composicion, "proveedor_de_identidad", lambda: proveedor)
    monkeypatch.setattr(composicion, "reloj", lambda: m.reloj)
    return g


def test_U07_la_web_no_importa_el_adaptador_de_glpi() -> None:
    """Sin importación no hay llamada: la caída de GLPI no puede alterar una respuesta web."""
    for ruta in (RAIZ / "src" / "jml" / "adaptadores" / "entrada" / "web").rglob("*.py"):
        assert "salida.glpi" not in ruta.read_text(encoding="utf-8"), ruta.name


def seguir_hasta_el_ingreso(c: Client, nombre: str, url: str) -> None:
    """Sin sesión nunca hay un 200: o redirige hasta /ingreso o es una vista solo POST (405 al GET)."""
    destino = url
    metodo: Callable[[str], Any] = c.get
    for _ in range(3):  # `/` redirige a /solicitudes y de ahí al ingreso
        r = metodo(destino)
        if r.status_code == 405:  # solo POST: el método se comprueba antes que la sesión
            assert r.content == b"", (nombre, "el 405 no debe llevar cuerpo")
            metodo = c.post
            r = metodo(destino)
        assert r.status_code == 302, (nombre, destino, r.status_code)
        assert r.content == b"", (nombre, "la redirección no debe llevar cuerpo")
        destino = r["Location"]
        if destino == "/ingreso":
            return
    raise AssertionError((nombre, destino))


def test_U07_sin_sesion_ninguna_ruta_protegida_responde_200(caido: GoTrueSimulado) -> None:
    c = Client()
    for nombre, url in rutas().items():
        if nombre not in PUBLICAS:
            seguir_hasta_el_ingreso(c, nombre, url)


def test_U07_con_supabase_caido_el_ingreso_falla_sin_detalles(caido: GoTrueSimulado) -> None:
    c = Client()
    r = c.post(
        "/ingreso", {"correo": "maria.gomez@andina.example", "contrasena": "una-clave-larga-123"}
    )
    cuerpo = bytes(r.content).decode().lower()
    assert r.status_code == 200
    assert "no está disponible" in cuerpo
    for palabra in PROHIBIDO_EN_RESPUESTAS:
        assert palabra not in cuerpo, palabra
    assert "usuario_id" not in c.session


def test_U07_las_rutas_publicas_no_filtran_detalle_con_supabase_caido(
    caido: GoTrueSimulado,
) -> None:
    c = Client()
    for nombre in ("salud", "ingreso", "segundo_factor"):
        r = c.get(rutas()[nombre])
        cuerpo = bytes(r.content).decode().lower()
        for palabra in PROHIBIDO_EN_RESPUESTAS:
            assert palabra not in cuerpo, (nombre, palabra)
