"""Piezas compartidas de los escenarios Gherkin.

Los `.feature` son la vista trazable de la suite: sus pasos llaman a las mismas piezas que las
pruebas ya existentes (`Mundo`, el cliente de Django, la matriz de autorización), no las repiten.
"""

from pathlib import Path

import pytest
from django.test import Client

from jml.adaptadores.entrada.web import composicion
from jml.adaptadores.salida.identidad.supabase import ProveedorSupabase
from jml.adaptadores.salida.persistencia.repositorios import RepositoriosDjango
from tests.dobles.gotrue import CLAVE_PUBLICA, GoTrueSimulado
from tests.fabricas import AHORA
from tests.mundo import Mundo

CORREO, CLAVE = "maria.gomez@andina.example", "una-clave-larga-123"


@pytest.fixture
def ctx() -> dict[str, object]:
    """Lo que un paso le deja al siguiente."""
    return {}


@pytest.fixture
def mundo_web(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Mundo:
    """Un mundo sobre el ORM, con la composición web apuntando a él."""
    m = Mundo.nuevo(repositorios=RepositoriosDjango)
    monkeypatch.setattr(composicion, "reloj", lambda: m.reloj)
    monkeypatch.setattr(composicion, "directorio_de_soportes", lambda: tmp_path)
    return m


@pytest.fixture
def supabase(mundo_web: Mundo, monkeypatch: pytest.MonkeyPatch) -> GoTrueSimulado:
    g = GoTrueSimulado()
    g.registrar(CORREO, CLAVE, "u-col")
    g.registrar("otro@andina.example", CLAVE, "u-otro")
    proveedor = ProveedorSupabase("https://x.supabase.co", CLAVE_PUBLICA, g.cliente())
    monkeypatch.setattr(composicion, "proveedor_de_identidad", lambda: proveedor)
    return g


def como(usuario: str | None, **opciones: bool) -> Client:
    """Un navegador con la sesión de `usuario` ya iniciada (o anónimo si es None)."""
    cliente = Client(**opciones)  # type: ignore[arg-type]  # enforce_csrf_checks
    if usuario is not None:
        sesion = cliente.session
        sesion["usuario_id"] = usuario
        sesion["inicio"] = AHORA.timestamp()
        sesion.save()
    return cliente
