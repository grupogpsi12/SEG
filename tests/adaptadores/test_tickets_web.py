"""RF-41: consulta de tickets en la aplicacion. Es solo lectura: se crean, trabajan y cierran en GLPI
(ADR-001). La consulta SQL se compara con el oraculo en memoria, como el dashboard (CA-15)."""

from typing import Any

import pytest
from django.test import Client

from jml.adaptadores.entrada.web import composicion
from jml.adaptadores.salida.persistencia.repositorios import RepositoriosDjango
from jml.aplicacion.casos.consultas import BuscarTickets
from jml.aplicacion.dtos import FiltroDeTickets
from jml.dominio.errores import DatoInvalido, NoAutorizado
from jml.dominio.tipos import Cola, EstadoDeTicket
from tests.aplicacion.test_consultas import semilla
from tests.fabricas import AHORA, SENTINELA
from tests.mundo import Mundo

FILTROS = [
    FiltroDeTickets(),
    FiltroDeTickets(cola=Cola.AD),
    FiltroDeTickets(estado=EstadoDeTicket.NUEVO),
    FiltroDeTickets(cola=Cola.INVENTARIO, estado=EstadoDeTicket.CERRADO),
    FiltroDeTickets(tamano=3),
    FiltroDeTickets(pagina=2, tamano=3),
    FiltroDeTickets(pagina=99),
    FiltroDeTickets(solicitud="sol-"),
    FiltroDeTickets(solicitud="no-existe"),
]


@pytest.fixture
def mundo(monkeypatch: pytest.MonkeyPatch) -> Mundo:
    m, _ = semilla(RepositoriosDjango)
    monkeypatch.setattr(composicion, "reloj", lambda: m.reloj)
    return m


def como(usuario: str) -> Client:
    c = Client()
    s = c.session
    s["usuario_id"], s["inicio"] = usuario, AHORA.timestamp()
    s.save()
    return c


def texto(r: Any) -> str:
    return bytes(r.content).decode()


@pytest.mark.django_db
def test_RF_41_el_orm_coincide_con_el_oraculo() -> None:
    oraculo, _ = semilla()
    real, _ = semilla(RepositoriosDjango)
    for filtro in FILTROS:
        assert real.puerto.buscar_tickets(filtro) == oraculo.puerto.buscar_tickets(filtro), filtro


def test_RF_41_pagina_del_mas_urgente_al_menos_urgente() -> None:
    m, _ = semilla()
    p = m.puerto.buscar_tickets(FiltroDeTickets(tamano=100))
    assert p.total == len(p.filas) > 0
    llaves = [(f.vence_en, f.ticket.clave) for f in p.filas]
    assert llaves == sorted(llaves)
    assert m.puerto.buscar_tickets(FiltroDeTickets(tamano=2)).filas == p.filas[:2]


def test_RF_41_el_filtro_rechaza_una_pagina_invalida() -> None:
    with pytest.raises(DatoInvalido):
        FiltroDeTickets(pagina=0)
    with pytest.raises(DatoInvalido):
        FiltroDeTickets(tamano=101)


@pytest.mark.parametrize("usuario", ["u-tec-ad", "u-tec-inv", "u-admin"])
def test_RF_41_tecnicos_y_administrador_consultan(usuario: str) -> None:
    m, _ = semilla()
    assert BuscarTickets(m._consulta).ejecutar(usuario, FiltroDeTickets()).total > 0


def test_RF_41_cada_tecnico_ve_resaltada_su_cola() -> None:
    m, _ = semilla()
    caso = BuscarTickets(m._consulta)
    assert caso.ejecutar("u-tec-ad", FiltroDeTickets()).cola_resaltada is Cola.AD
    assert caso.ejecutar("u-admin", FiltroDeTickets()).cola_resaltada is None


@pytest.mark.parametrize("usuario", ["u-rrhh", "u-col", "u-jefe", "u-aud", "fantasma"])
def test_RF_41_los_demas_no_consultan(usuario: str) -> None:
    m, _ = semilla()
    with pytest.raises(NoAutorizado):
        BuscarTickets(m._consulta).ejecutar(usuario, FiltroDeTickets())


@pytest.mark.django_db
@pytest.mark.parametrize("usuario", ["u-rrhh", "u-col", "u-jefe", "u-aud"])
def test_RF_41_la_pagina_responde_403_a_los_demas(mundo: Mundo, usuario: str) -> None:
    assert como(usuario).get("/tickets").status_code == 403


@pytest.mark.django_db
def test_RF_41_la_pagina_filtra_y_es_de_solo_lectura(mundo: Mundo) -> None:
    pagina = texto(como("u-tec-ad").get("/tickets", {"cola": "INVENTARIO"}))
    assert "<td>INVENTARIO</td>" in pagina
    assert "<td>AD</td>" not in pagina
    assert 'method="post"' not in pagina.split("<main")[1]
    assert como("u-admin").post("/tickets").status_code == 405


@pytest.mark.django_db
def test_RF_41_parametros_manipulados_dan_404(mundo: Mundo) -> None:
    assert como("u-tec-ad").get("/tickets", {"cola": "NINGUNA"}).status_code == 404
    assert como("u-tec-ad").get("/tickets", {"pagina": "0"}).status_code == 404


@pytest.mark.django_db
def test_RF_41_ningun_campo_restringido_llega_a_la_pagina(mundo: Mundo) -> None:
    assert SENTINELA not in texto(como("u-admin").get("/tickets"))


@pytest.mark.django_db
def test_RF_41_el_menu_muestra_tickets_a_quien_puede_verlos(mundo: Mundo) -> None:
    assert 'href="/tickets"' in texto(como("u-admin").get("/solicitudes"))
    assert 'href="/tickets"' in texto(como("u-tec-ad").get("/solicitudes"))
    assert 'href="/tickets"' not in texto(como("u-rrhh").get("/solicitudes"))


@pytest.mark.django_db
def test_RF_41_resalta_la_cola_propia_solo_si_no_se_filtro_por_cola(mundo: Mundo) -> None:
    assert 'class="resaltada"' in texto(como("u-tec-ad").get("/tickets"))
    assert 'class="resaltada"' not in texto(como("u-tec-ad").get("/tickets", {"cola": "AD"}))
