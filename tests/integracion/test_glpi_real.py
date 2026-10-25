"""Spike 0.3 y item 3.1 contra un GLPI REAL: el enrutamiento por categoria (CA-03), el SLA de la
emergencia, que ningun campo restringido llegue al ticket (CA-10, RF-20) y la configuracion.

Se corre dentro de la red de Docker con `infra/scripts/contrato-glpi.sh` (que ya configura GLPI).
Sin las variables de entorno se omite, con el ID S-28 (credenciales externas).
"""

import os
from dataclasses import replace
from datetime import UTC, datetime

import httpx
import pytest

from jml.adaptadores.salida.glpi.cliente import SistemaDeTicketsGlpi
from jml.adaptadores.salida.glpi.configuracion import GRUPOS, categorias
from jml.dominio.tickets import TicketDeCola, generar_tickets
from jml.dominio.tipos import Cola, Prioridad, Subtipo, TipoEvento
from jml.dominio.valores import CalendarioHabil
from tests.dobles.glpi_real import TecnicoGlpiReal
from tests.fabricas import HOY, SENTINELA, caso

# El reloj de GLPI es el real: con una fecha fija, el vencimiento queda antes de la apertura del
# ticket y GLPI lo rechaza («Invalid dates. Update cancelled.»). B-17.
AHORA = datetime.now(UTC)

SIN_GLPI = "JML_GLPI_API_URL" not in os.environ
pytestmark = pytest.mark.skipif(SIN_GLPI, reason="S-28: sin un GLPI real (variables JML_GLPI_*)")


@pytest.fixture
def glpi() -> tuple[SistemaDeTicketsGlpi, TecnicoGlpiReal]:
    url, app = os.environ["JML_GLPI_API_URL"], os.environ["JML_GLPI_APP_TOKEN"]
    tecnico = TecnicoGlpiReal(url, app, os.environ["JML_GLPI_ADMIN_TOKEN"])
    tecnico.limpiar()
    adaptador = SistemaDeTicketsGlpi(
        url,
        app,
        os.environ["JML_GLPI_USER_TOKEN"],
        lambda: AHORA,
        httpx.Client(timeout=60.0),
    )
    return adaptador, tecnico


def tickets_de(tipo: TipoEvento, sub: Subtipo | None) -> list[TicketDeCola]:
    # La fecha efectiva (y con ella el vencimiento) se mide desde el dia real, no desde HOY.
    c = caso(tipo, sub, dias=7 + (AHORA.date() - HOY).days)
    return list(
        generar_tickets(c.solicitud, c.actual, c.nuevo, c.colaborador, CalendarioHabil(), AHORA)
    )


def test_CA_03_cada_ticket_llega_al_grupo_de_su_cola(
    glpi: tuple[SistemaDeTicketsGlpi, TecnicoGlpiReal],
) -> None:
    adaptador, tecnico = glpi
    vistos: dict[Cola, set[str]] = {}
    for t in tickets_de(TipoEvento.RET, Subtipo.RENUNCIA):
        gid = adaptador.crear_ticket(t).id_externo
        vistos.setdefault(t.cola, set()).update(tecnico.grupos_asignados(gid))
    assert set(vistos) >= {Cola.AD, Cola.COMUNICACIONES, Cola.LICENCIAS, Cola.INVENTARIO}
    for cola, grupos in vistos.items():
        assert grupos == {GRUPOS[cola]}, (cola, grupos)


def test_CA_03_una_categoria_desconocida_va_a_revision_manual(
    glpi: tuple[SistemaDeTicketsGlpi, TecnicoGlpiReal],
) -> None:
    adaptador, tecnico = glpi
    base = tickets_de(TipoEvento.RET, Subtipo.RENUNCIA)[0]
    raro = replace(
        base,
        categoria="JML/RET/AD/inventada",
        clave_de_idempotencia="SOL-2026-000099:AD:cierre_inmediato:1",
    )
    gid = adaptador.crear_ticket(raro).id_externo
    assert tecnico.grupos_asignados(gid) == {GRUPOS[Cola.REVISION_MANUAL]}


def test_RF_16_la_prioridad_y_el_vencimiento_del_dominio_llegan_a_glpi(
    glpi: tuple[SistemaDeTicketsGlpi, TecnicoGlpiReal],
) -> None:
    """Spike 0.3: GLPI ignora `priority` y `time_to_resolve` al crear; el adaptador los consigue
    con urgencia = impacto y con un PUT posterior, en UTC (la zona de GLPI)."""
    adaptador, tecnico = glpi
    nivel = {Prioridad.MEDIA: 3, Prioridad.ALTA: 4, Prioridad.MUY_ALTA: 5}
    for t in tickets_de(TipoEvento.RET, Subtipo.RENUNCIA):
        ticket = tecnico.ticket(adaptador.crear_ticket(t).id_externo)
        assert int(ticket["priority"]) == nivel[t.prioridad], t.titulo
        assert ticket["time_to_resolve"] == t.vence_en.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")


def test_CA_06_la_emergencia_lleva_el_sla_de_una_hora(
    glpi: tuple[SistemaDeTicketsGlpi, TecnicoGlpiReal],
) -> None:
    adaptador, tecnico = glpi
    emergencia = [
        t
        for t in tickets_de(TipoEvento.EMG, Subtipo.FUGA_DETECTADA)
        if t.prioridad is Prioridad.MUY_ALTA
    ]
    assert emergencia
    ticket = tecnico.ticket(adaptador.crear_ticket(emergencia[0]).id_externo)
    assert tecnico.sla_de(ticket["slas_id_ttr"]) == ("JML - Emergencia 1 h", 1, "hour")


def test_CA_10_ningun_campo_restringido_llega_a_glpi(
    glpi: tuple[SistemaDeTicketsGlpi, TecnicoGlpiReal],
) -> None:
    adaptador, tecnico = glpi
    for t in tickets_de(TipoEvento.RET, Subtipo.RENUNCIA):
        gid = adaptador.crear_ticket(t).id_externo
        assert SENTINELA not in repr(tecnico.ticket(gid))


def test_3_1_las_categorias_y_las_plantillas_existen_y_sin_contrasenas(
    glpi: tuple[SistemaDeTicketsGlpi, TecnicoGlpiReal],
) -> None:
    _, tecnico = glpi
    existentes = tecnico.nombres("ITILCategory", "completename")
    assert set(categorias()) <= existentes
    plantillas = tecnico.contenidos("SolutionTemplate", "JML - ")
    assert len(plantillas) == 4
    assert not [p for p in plantillas if "contraseña" in p.lower()]
