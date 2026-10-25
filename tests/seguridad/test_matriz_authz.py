"""F5-02, F3-U03, F3-U09 (T3, T4, T10; RF-03, RF-35): la matriz de autorización, celda por celda.

`auditoria/matriz-authz.csv` dice qué debe pasar (según el SRS) para cada ruta, método y rol; esta
prueba hace la petición de verdad y compara. Una desviación conocida lleva su hallazgo en el CSV;
cualquier otra, o una ruta nueva sin clasificar, hace fallar la prueba.
"""

import csv
import logging
from dataclasses import dataclass
from pathlib import Path

import pytest
from django.test import Client

from jml.adaptadores.entrada.web import composicion
from jml.adaptadores.salida.persistencia.repositorios import RepositoriosDjango
from tests.fabricas import AHORA
from tests.mundo import Mundo, vacaciones
from tests.seguridad.rutas import rutas

pytestmark = [pytest.mark.seguridad, pytest.mark.django_db]

CSV = Path(__file__).resolve().parents[2] / "auditoria" / "matriz-authz.csv"
USUARIOS = {
    "anonimo": None,
    "solicitante": "u-col",
    "jefe": "u-jefe",
    "rrhh": "u-rrhh",
    "tecnico_ad": "u-tec-ad",
    "tecnico_comunicaciones": "u-tec-com",
    "tecnico_licencias": "u-tec-lic",
    "tecnico_inventario": "u-tec-inv",
    "auditor": "u-aud",
    "administrador": "u-admin",
}


@dataclass(frozen=True)
class Celda:
    ruta: str
    metodo: str
    rol: str
    esperado: str
    excepcion: str
    observado: str

    def __str__(self) -> str:
        return f"{self.ruta}-{self.metodo}-{self.rol}"


def celdas() -> list[Celda]:
    with CSV.open(encoding="utf-8", newline="") as f:
        return [
            Celda(
                r["ruta"],
                r["metodo"],
                r["rol"],
                r["esperado"],
                r["excepcion"],
                r["observado_conocido"],
            )
            for r in csv.DictReader(f)
        ]


@pytest.fixture
def mundo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Mundo:
    m = Mundo.nuevo(repositorios=RepositoriosDjango)
    monkeypatch.setattr(composicion, "reloj", lambda: m.reloj)
    monkeypatch.setattr(composicion, "directorio_de_soportes", lambda: tmp_path)
    return m


def peticion(m: Mundo, celda: Celda) -> tuple[str, str]:
    """Ejecuta la celda sobre una solicitud pendiente recién creada. Devuelve (resultado, url)."""
    sid = m.registrar(vacaciones()).solicitud_id.valor
    url = rutas()[celda.ruta].replace("SOL-2026-000001", sid)
    cliente = Client()
    usuario = USUARIOS[celda.rol]
    if usuario is not None:
        sesion = cliente.session
        sesion["usuario_id"] = usuario
        sesion["inicio"] = AHORA.timestamp()
        sesion.save()
    respuesta = getattr(cliente, celda.metodo.lower())(url)
    codigo = respuesta.status_code
    return (f"302:{respuesta['Location']}" if codigo == 302 else str(codigo)), url


def test_U03_toda_ruta_de_urlpatterns_esta_en_la_matriz_y_no_sobra_ninguna() -> None:
    en_matriz = {c.ruta for c in celdas()}
    assert set(rutas()) == en_matriz, set(rutas()) ^ en_matriz


def test_F5_01_la_matriz_clasifica_el_100_por_ciento_de_las_celdas() -> None:
    hechas = {(c.ruta, c.metodo, c.rol) for c in celdas()}
    todas = {(r, m, rol) for r in rutas() for m in ("GET", "POST") for rol in USUARIOS}
    assert hechas == todas
    assert all(c.esperado for c in celdas())


@pytest.mark.parametrize("celda", celdas(), ids=str)
def test_F5_02_cada_celda_da_lo_esperado(mundo: Mundo, celda: Celda) -> None:
    resultado, _ = peticion(mundo, celda)
    if celda.excepcion and resultado == celda.observado:
        return  # desviación conocida y rastreada (hallazgo en el CSV)
    assert resultado == celda.esperado, f"{celda}: esperado {celda.esperado}, obtenido {resultado}"


def es_denegacion_por_rol(c: Celda) -> bool:
    """403 o aviso de «no tiene permiso» tras un POST: la persona tiene sesión y no el rol."""
    if c.rol == "anonimo" or c.esperado == "405":
        return False
    return c.esperado == "403" or (
        c.ruta in ("admin_roles", "reintentar", "decidir") and c.esperado == "302:/solicitudes"
    )


@pytest.mark.parametrize("celda", [c for c in celdas() if es_denegacion_por_rol(c)], ids=str)
def test_U09_cada_denegacion_por_rol_deja_un_evento(
    mundo: Mundo, celda: Celda, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="jml.seguridad"):
        peticion(mundo, celda)
    eventos = [
        r
        for r in caplog.records
        if r.name == "jml.seguridad" and r.getMessage() == "acceso.denegado"
    ]
    assert len(eventos) == 1, f"{celda}: {len(eventos)} eventos"
    e = eventos[0]
    assert (e.usuario, e.ruta, e.metodo) == (USUARIOS[celda.rol], celda.ruta, celda.metodo)  # type: ignore[attr-defined]
