"""F5 (plan §7): los métodos no previstos (PUT, DELETE, PATCH, OPTIONS, TRACE, HEAD) dan 405 siempre.

El decorador de método va antes que la sesión: ni siquiera quien no ha ingresado aprende nada de
una ruta por probar un método raro, y ningún rol puede usar un método que la vista no declara.
"""

from pathlib import Path

import pytest
from django.test import Client

from jml.adaptadores.entrada.web import composicion
from jml.adaptadores.salida.persistencia.repositorios import RepositoriosDjango
from tests.fabricas import AHORA
from tests.mundo import Mundo
from tests.seguridad.rutas import rutas
from tests.seguridad.test_matriz_authz import USUARIOS

pytestmark = [pytest.mark.seguridad, pytest.mark.django_db]

METODOS_RAROS = ["PUT", "DELETE", "PATCH", "OPTIONS", "TRACE", "HEAD"]
ROLES = ["anonimo", "solicitante", "rrhh", "tecnico_ad", "auditor", "administrador"]


@pytest.fixture
def mundo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Mundo:
    m = Mundo.nuevo(repositorios=RepositoriosDjango)
    monkeypatch.setattr(composicion, "reloj", lambda: m.reloj)
    monkeypatch.setattr(composicion, "directorio_de_soportes", lambda: tmp_path)
    return m


@pytest.mark.parametrize("rol", ROLES)
@pytest.mark.parametrize("metodo", METODOS_RAROS)
def test_F5_un_metodo_no_previsto_da_405_en_toda_ruta(mundo: Mundo, rol: str, metodo: str) -> None:
    c = Client()
    usuario = USUARIOS[rol]
    if usuario is not None:
        sesion = c.session
        sesion["usuario_id"], sesion["inicio"] = usuario, AHORA.timestamp()
        sesion.save()
    distintos = {nombre: c.generic(metodo, url).status_code for nombre, url in rutas().items()}
    assert set(distintos.values()) == {405}, {n: s for n, s in distintos.items() if s != 405}
