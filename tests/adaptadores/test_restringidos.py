"""Item 2.8 / CA-10: el centinela del motivo de retiro y de la descripcion de una emergencia no
aparece en respuestas ni logs para roles distintos de RRHH, y nunca en la auditoria ni en logs.

Recorre las paginas con el cliente de Django sobre el ORM y captura TODOS los logs del proceso.
"""

import logging
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from django.test import Client

from jml.adaptadores.entrada.web import composicion
from jml.adaptadores.registro import FormatoJSON
from jml.adaptadores.salida.persistencia.repositorios import RepositoriosDjango
from jml.dominio.valores import BOGOTA
from tests.fabricas import AHORA, HOY, SENTINELA
from tests.mundo import Mundo

pytestmark = pytest.mark.django_db

USUARIOS = [
    "u-col",
    "u-jefe",
    "u-otro",
    "u-tec-ad",
    "u-tec-com",
    "u-tec-lic",
    "u-tec-inv",
    "u-aud",
    "u-admin",
]


@pytest.fixture
def mundo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Mundo:
    m = Mundo.nuevo(repositorios=RepositoriosDjango)
    monkeypatch.setattr(composicion, "reloj", lambda: m.reloj)
    monkeypatch.setattr(composicion, "directorio_de_soportes", lambda: tmp_path)
    return m


def como(usuario: str) -> Client:
    c = Client()
    s = c.session
    s["usuario_id"], s["inicio"] = usuario, AHORA.timestamp()
    s.save()
    return c


def texto(r: Any) -> str:
    return bytes(r.content).decode()


class Todo(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.lineas: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lineas.append(FormatoJSON().format(record))


@pytest.fixture
def logs() -> Any:
    h = Todo()
    raiz = logging.getLogger()
    nivel = raiz.level
    raiz.addHandler(h)
    raiz.setLevel(logging.DEBUG)
    yield h
    raiz.removeHandler(h)
    raiz.setLevel(nivel)


def ids(c: Client) -> list[str]:
    pagina = texto(c.get("/solicitudes"))
    return sorted({pagina[i : i + 15] for i in range(len(pagina)) if pagina.startswith("SOL-", i)})


def test_CA_10_el_centinela_solo_lo_ve_rrhh_y_nunca_llega_a_los_logs(
    mundo: Mundo, logs: Any
) -> None:
    rrhh = como("u-rrhh")
    rrhh.post(
        "/solicitudes/nueva/RET",
        {
            "fecha_efectiva": (HOY + timedelta(days=10)).isoformat(),
            "documento_del_colaborador": "70000009",
            "subtipo_elegido": "fin_de_contrato",
            "motivo": SENTINELA,
            "justificacion": "Cierre",
        },
    )
    rrhh.post(
        "/solicitudes/nueva/EMG",
        {
            "documento_del_colaborador": "70000002",
            "subtipo_elegido": "fuga_detectada",
            "reportado_por": "Seguridad",
            "hora_del_hecho": (AHORA.astimezone(BOGOTA) - timedelta(hours=1)).strftime(
                "%Y-%m-%dT%H:%M"
            ),
            "descripcion": SENTINELA + "-EMG",
            "justificacion": "Alerta",
        },
    )
    col = como("u-col")
    col.post(
        "/solicitudes/nueva/RET",
        {"fecha_efectiva": (HOY + timedelta(days=20)).isoformat(), "motivo": SENTINELA},
    )
    solicitudes = ids(rrhh) + ids(col)
    assert len(solicitudes) == 3

    # RRHH lo ve en el detalle, y la pagina no se guarda en cache
    detalle = rrhh.get(f"/solicitudes/{ids(rrhh)[0]}")
    assert SENTINELA in texto(detalle)
    assert detalle["Cache-Control"] == "no-store"

    for usuario in USUARIOS:
        c = como(usuario)
        for ruta in ["/solicitudes", "/solicitudes/nueva", "/bandeja"] + [
            f"/solicitudes/{s}" for s in solicitudes
        ]:
            assert SENTINELA not in texto(c.get(ruta)), (usuario, ruta)

    with RepositoriosDjango(mundo.reloj).unidad_de_trabajo() as u:
        assert SENTINELA not in repr(
            [(r.accion, r.objeto, dict(r.datos)) for r in u.auditoria.registros()]
        )
    assert logs.lineas, "la prueba debe haber capturado logs"
    assert not [linea for linea in logs.lineas if SENTINELA in linea]
