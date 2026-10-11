"""Ciclo del worker (ADR-011, RNF-01, RNF-02) con los casos de uso reales y GLPI en memoria."""

from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from jml.adaptadores.entrada.worker.ciclo import (
    INTERVALO_SINCRONIZACION_S,
    LATIDO_MAXIMO_S,
    Worker,
    esta_sano,
)
from tests.mundo import Mundo, vacaciones


class Reloj:
    def __init__(self) -> None:
        self.t = 1_000_000.0

    def __call__(self) -> float:
        return self.t


def armar(m: Mundo, latido: Path, reloj: Reloj) -> Worker:
    return Worker(
        bandeja=m.bandeja,
        sincronizaciones=(m.sincronizar, m.sincronizar_activos),
        latido=latido,
        reloj=reloj,
    )


def test_la_bandeja_corre_en_cada_vuelta_y_la_sincronizacion_cada_5_minutos(tmp_path: Path) -> None:
    reloj = Reloj()
    llamadas: list[str] = []
    w = Worker(
        bandeja=lambda: llamadas.append("bandeja"),
        sincronizaciones=(lambda: llamadas.append("sync"),),
        latido=tmp_path / "latido",
        reloj=reloj,
    )
    for _ in range(3):
        w.una_vuelta()
        reloj.t += 30
    reloj.t += INTERVALO_SINCRONIZACION_S
    w.una_vuelta()
    assert llamadas == ["bandeja", "sync", "bandeja", "bandeja", "bandeja", "sync"]


def test_una_solicitud_aprobada_llega_a_glpi_por_el_worker(tmp_path: Path) -> None:
    m, reloj = Mundo.nuevo(), Reloj()
    r = m.registrar(vacaciones())
    m.aprobar("u-rrhh", r.solicitud_id)
    armar(m, tmp_path / "latido", reloj).una_vuelta()
    assert m.glpi.tickets_remotos()  # el doble de GLPI recibio los tickets
    assert esta_sano(tmp_path / "latido", reloj.t)


def test_RNF_02_si_glpi_falla_el_ciclo_sigue_y_el_latido_no_avanza(tmp_path: Path) -> None:
    reloj = Reloj()

    def caido() -> object:
        raise ConnectionError("GLPI no responde")

    w = Worker(bandeja=caido, sincronizaciones=(caido,), latido=tmp_path / "latido", reloj=reloj)
    w.una_vuelta()  # no lanza
    assert not (tmp_path / "latido").exists()
    vueltas = iter([True, True, False])
    w.correr(lambda: next(vueltas), dormir=lambda _: None)


def test_una_sincronizacion_con_resultado_error_no_marca_latido(tmp_path: Path) -> None:
    class Resultado:
        resultado = "error"

    w = Worker(
        bandeja=lambda: None,
        sincronizaciones=(lambda: Resultado(),),
        latido=tmp_path / "latido",
        reloj=Reloj(),
    )
    w.una_vuelta()
    assert not (tmp_path / "latido").exists()


@pytest.mark.parametrize(
    ("contenido", "edad", "sano"),
    [
        ("1000", 0, True),
        ("1000", LATIDO_MAXIMO_S, True),
        ("1000", LATIDO_MAXIMO_S + 1, False),
        ("x", 0, False),
        ("1000", -5, False),
    ],
)
def test_RNF_01_salud_segun_la_edad_del_latido(
    tmp_path: Path, contenido: str, edad: float, sano: bool
) -> None:
    latido = tmp_path / "latido"
    latido.write_text(contenido, encoding="ascii")
    assert esta_sano(latido, 1000 + edad) is sano
    assert esta_sano(tmp_path / "no-existe", 1000) is False


def test_el_comando_de_salud_falla_sin_latido(tmp_path: Path, settings: object) -> None:
    settings.JML_LATIDO_WORKER = str(tmp_path / "latido")  # type: ignore[attr-defined]
    with pytest.raises(CommandError, match="sin sincronizacion"):
        call_command("worker", "--salud")


def test_el_worker_no_arranca_sin_los_tokens_de_glpi(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JML_SECRETOS_DIR", str(tmp_path))
    with pytest.raises(CommandError, match="glpi_app_token"):
        call_command("worker")


def test_con_los_tokens_el_worker_arma_el_adaptador_de_glpi(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from jml.adaptadores.entrada.worker.management.commands import worker as comando
    from jml.adaptadores.salida.glpi.cliente import SistemaDeTicketsGlpi

    for nombre in ("glpi_app_token", "glpi_user_token"):
        (tmp_path / nombre).write_text("x", encoding="utf-8")
    monkeypatch.setenv("JML_SECRETOS_DIR", str(tmp_path))
    assert isinstance(comando.sistema_de_tickets(), SistemaDeTicketsGlpi)
