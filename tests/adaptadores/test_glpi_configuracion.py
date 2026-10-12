"""Item 3.1: configuracion de GLPI como codigo, contra el GLPI simulado (confirmada contra GLPI real en el spike 0.3)."""

from collections import Counter

import pytest

from jml.adaptadores.salida.glpi.cliente import SistemaDeTicketsGlpi
from jml.adaptadores.salida.glpi.configuracion import (
    GRUPOS,
    PLANTILLAS,
    ConfiguradorGlpi,
    categorias,
)
from jml.aplicacion.puertos import GlpiRechazo
from jml.dominio.tickets import generar_tickets
from jml.dominio.tipos import Subtipo, TipoEvento
from jml.dominio.valores import CalendarioHabil
from tests.dobles.glpi_api import APP_TOKEN, BASE, USER_TOKEN, GlpiSimulado
from tests.dominio.golden_tickets import CASOS
from tests.fabricas import AHORA, caso


def configurador(glpi: GlpiSimulado) -> ConfiguradorGlpi:
    return ConfiguradorGlpi(BASE, APP_TOKEN, USER_TOKEN, lambda: AHORA, glpi.cliente())


def test_crea_grupos_categorias_reglas_sla_y_plantillas() -> None:
    """S-33: el SLA de emergencia escala a «Revision manual» al vencer."""
    glpi = GlpiSimulado()
    r = configurador(glpi).configurar()
    assert (r.grupos, r.categorias, r.reglas, r.plantillas) == (5, len(categorias()), 6, 4)
    assert {g["name"] for g in glpi.items["Group"].values()} == set(GRUPOS.values())
    assert len(glpi.items["RuleCriteria"]) == len(glpi.items["RuleAction"]) == 6
    assert glpi.items["SLA"][r.sla_de_emergencia]["number_time"] == 1


def test_es_idempotente() -> None:
    glpi = GlpiSimulado()
    configurador(glpi).configurar()
    antes = Counter({tipo: len(filas) for tipo, filas in glpi.items.items()})
    configurador(glpi).configurar()
    assert Counter({tipo: len(filas) for tipo, filas in glpi.items.items()}) == antes


def test_con_duplicados_se_detiene_y_dice_cuales_son() -> None:
    """Dos corridas a la vez dejan duplicados (busca, no encuentra y crea, cada una). Con dos
    grupos del mismo nombre el enrutamiento queda ambiguo: se detiene en vez de elegir uno
    (auditoria del 12/10/2026)."""
    glpi = GlpiSimulado()
    configurador(glpi).configurar()
    glpi._agregar("Group", {"name": GRUPOS[next(iter(GRUPOS))], "is_assign": 1})
    with pytest.raises(GlpiRechazo, match="duplicad"):
        configurador(glpi).configurar()


def test_cubre_todas_las_categorias_que_genera_el_dominio() -> None:
    """Las categorias de la prueba dorada (todos los caminos del dominio) existen en GLPI."""
    conocidas = set(categorias())
    for nombre in sorted(CASOS):
        c = caso(**CASOS[nombre])  # type: ignore[arg-type]
        for t in generar_tickets(
            c.solicitud, c.actual, c.nuevo, c.colaborador, CalendarioHabil(), AHORA
        ):
            assert t.categoria in conocidas, (nombre, t.categoria)


def test_tras_configurar_los_tickets_llevan_su_categoria() -> None:
    glpi = GlpiSimulado()
    configurador(glpi).configurar()
    c = caso(TipoEvento.RET, Subtipo.RENUNCIA)
    t = generar_tickets(c.solicitud, c.actual, c.nuevo, c.colaborador, CalendarioHabil(), AHORA)[0]
    cliente = SistemaDeTicketsGlpi(BASE, APP_TOKEN, USER_TOKEN, lambda: AHORA, glpi.cliente())
    assert glpi.ticket(cliente.crear_ticket(t).id_externo)["itilcategories_id"] != 0


def test_T9_ninguna_plantilla_pide_una_contrasena() -> None:
    for texto in PLANTILLAS.values():
        assert "contraseña" not in texto.lower()
        assert "password" not in texto.lower()


def test_el_comando_exige_el_token_de_administrador(tmp_path: object, monkeypatch: object) -> None:
    import pytest
    from django.core.management import call_command
    from django.core.management.base import CommandError

    monkeypatch.setenv("JML_SECRETOS_DIR", str(tmp_path))  # type: ignore[attr-defined]
    (tmp_path / "glpi_app_token").write_text("x", encoding="utf-8")  # type: ignore[operator]
    with pytest.raises(CommandError, match="glpi_admin_user_token"):
        call_command("configurar_glpi")
