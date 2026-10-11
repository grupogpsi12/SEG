"""Item 3.2: lo propio del adaptador de GLPI (API v1), mas alla de la suite de contrato.

PROVISIONAL hasta el spike 0.3: el GLPI simulado sigue la documentacion de la API v1.
"""

from dataclasses import replace

import httpx
import pytest

from jml.adaptadores.salida.glpi.cliente import DE_GLPI, SistemaDeTicketsGlpi
from jml.aplicacion.puertos import GlpiNoDisponible, GlpiRechazo
from jml.dominio.tickets import TicketDeCola, generar_tickets
from jml.dominio.tipos import Cola, EstadoDeTicket, Prioridad, Subtipo, TipoEvento
from jml.dominio.valores import CalendarioHabil
from tests.dobles.glpi_api import APP_TOKEN, BASE, USER_TOKEN, GlpiSimulado
from tests.fabricas import AHORA, SENTINELA, caso, colaborador


def armar(
    glpi: GlpiSimulado, app: str = APP_TOKEN, usuario: str = USER_TOKEN
) -> SistemaDeTicketsGlpi:
    return SistemaDeTicketsGlpi(BASE, app, usuario, lambda: AHORA, glpi.cliente())


def tickets(
    tipo: TipoEvento = TipoEvento.RET, sub: Subtipo | None = Subtipo.RENUNCIA
) -> list[TicketDeCola]:
    c = caso(tipo, sub)
    return list(
        generar_tickets(c.solicitud, c.actual, c.nuevo, c.colaborador, CalendarioHabil(), AHORA)
    )


def test_el_ticket_lleva_titulo_contenido_tecnico_prioridad_categoria_y_vencimiento() -> None:
    glpi = GlpiSimulado()
    t = tickets()[0]
    cat = glpi.agregar_categoria(t.categoria)
    creado = glpi.ticket(armar(glpi).crear_ticket(t).id_externo)
    assert creado["name"] == t.titulo
    assert creado["content"] == t.como_texto()
    assert creado["externalid"] == t.clave_de_idempotencia
    assert (
        creado["priority"]
        == {Prioridad.MEDIA: 3, Prioridad.ALTA: 4, Prioridad.MUY_ALTA: 5}[t.prioridad]
    )
    assert creado["itilcategories_id"] == cat
    assert len(creado["time_to_resolve"]) == 19  # "AAAA-MM-DD HH:MM:SS" en hora de Bogota


def test_RF_20_ningun_campo_restringido_llega_a_glpi() -> None:
    glpi = GlpiSimulado()
    cliente = armar(glpi)
    for t in tickets():
        cliente.crear_ticket(t)
    assert SENTINELA not in repr(glpi.items)


def test_una_categoria_desconocida_queda_para_revision_manual_y_se_consulta_una_vez() -> None:
    glpi = GlpiSimulado()
    cliente = armar(glpi)
    ts = [t for t in tickets() if t.cola is Cola.AD]
    for t in ts:
        assert glpi.ticket(cliente.crear_ticket(t).id_externo)["itilcategories_id"] == 0
    consultas = [x for x in glpi.llamadas if x == "GET ITILCategory"]
    assert len(consultas) == len({t.categoria for t in ts})


def test_una_sesion_vencida_se_renueva_sola() -> None:
    glpi = GlpiSimulado()
    cliente = armar(glpi)
    gid = cliente.crear_ticket(tickets()[0]).id_externo
    glpi.expirar_sesiones()
    assert gid in cliente.leer_tickets([gid])
    assert glpi.llamadas.count("GET initSession") == 2


def test_credenciales_invalidas_son_un_rechazo_y_no_se_reintentan_sin_fin() -> None:
    with pytest.raises(GlpiRechazo):
        armar(GlpiSimulado(), usuario="otro").leer_tickets(["1"])
    with pytest.raises(GlpiRechazo):
        armar(GlpiSimulado(), app="otro").leer_tickets(["1"])


def test_los_duplicados_que_ya_existian_se_purgan_al_crear() -> None:
    glpi = GlpiSimulado()
    t = tickets()[0]
    for _ in range(3):  # tres tickets con la misma clave (por ejemplo, de una version anterior)
        glpi._agregar("Ticket", {"externalid": t.clave_de_idempotencia, "status": 1})
    creado = armar(glpi).crear_ticket(t)
    assert creado.ya_existia is True
    assert glpi.creaciones(t.clave_de_idempotencia) == 1


def test_la_busqueda_por_subcadena_no_confunde_claves_parecidas() -> None:
    glpi = GlpiSimulado()
    t = tickets()[0]
    glpi._agregar("Ticket", {"externalid": t.clave_de_idempotencia + "0", "status": 1})
    assert armar(glpi).crear_ticket(t).ya_existia is False


def test_los_estados_de_glpi_se_ordenan_como_espera_el_nucleo() -> None:
    assert DE_GLPI[3] is EstadoDeTicket.EN_CURSO  # «en curso (planificado)»
    assert all(DE_GLPI[e] >= EstadoDeTicket.RESUELTO for e in (5, 6))
    assert all(DE_GLPI[e] < EstadoDeTicket.RESUELTO for e in (1, 2, 3, 4))


def test_el_usuario_se_actualiza_si_ya_existia() -> None:
    glpi = GlpiSimulado()
    cliente = armar(glpi)
    uid = cliente.asegurar_usuario(colaborador())
    cliente.asegurar_usuario(replace(colaborador(), nombres="Ana"))
    assert glpi.items["User"][uid]["firstname"] == "Ana"
    assert "password" not in glpi.items["User"][uid]  # RF-21: sin credenciales


@pytest.mark.parametrize("error", [httpx.ConnectError("x"), httpx.ReadTimeout("x")])
def test_una_lectura_sin_respuesta_es_no_disponible(error: Exception) -> None:
    def falla(_: httpx.Request) -> httpx.Response:
        raise error

    cliente = SistemaDeTicketsGlpi(
        BASE,
        APP_TOKEN,
        USER_TOKEN,
        lambda: AHORA,
        httpx.Client(transport=httpx.MockTransport(falla)),
    )
    with pytest.raises(GlpiNoDisponible):
        cliente.leer_tickets(["1"])


def test_cerrar_termina_la_sesion() -> None:
    glpi = GlpiSimulado()
    cliente = armar(glpi)
    cliente.leer_tickets([])
    cliente.leer_tickets(["999"])
    cliente.cerrar()
    assert glpi.sesiones == set()
    cliente.cerrar()  # idempotente
