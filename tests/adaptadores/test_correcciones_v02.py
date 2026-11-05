"""V-02: correcciones pedidas por el equipo el 04/11/2026 (RF-11, RF-41, RS-08)."""

from pathlib import Path
from typing import Any

import pytest
import yaml
from django.test import Client

from jml.adaptadores.entrada.web import composicion
from jml.adaptadores.salida.persistencia.repositorios import RepositoriosDjango
from jml.aplicacion.casos.consultas import BuscarTickets
from jml.aplicacion.casos.listados import ConsultarSolicitud, MisSolicitudes
from jml.aplicacion.dtos import FiltroDeTickets
from jml.dominio.tickets import Observacion
from jml.dominio.tipos import EstadoDeTicket
from tests.aplicacion.test_consultas import semilla
from tests.fabricas import AHORA
from tests.mundo import Mundo, retiro, vacaciones

COMPOSE = yaml.safe_load(
    (Path(__file__).resolve().parents[2] / "infra/compose.yaml").read_text(encoding="utf-8")
)


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


# --- columna Colaborador y enlaces de Tickets ------------------------------------------------


def test_RF_41_la_fila_trae_el_nombre_del_colaborador_no_su_id() -> None:
    m, _ = semilla()
    filas = m.puerto.buscar_tickets(FiltroDeTickets(tamano=100)).filas
    nombres = {f.colaborador_id: f.colaborador_nombre for f in filas}
    assert all(nombres.values())
    assert nombres["col-1"] != "col-1"


def test_RF_41_la_solicitud_solo_es_visible_para_quien_puede_abrirla() -> None:
    """Los tecnicos y el Administrador no abren el detalle salvo el que ellos registraron: sin esto
    cada enlace daba 404 (auditoria funcional, 04/11/2026)."""
    m, _ = semilla()
    caso = BuscarTickets(m._consulta)
    assert not any(
        f.solicitud_visible for f in caso.ejecutar("u-tec-ad", FiltroDeTickets(tamano=100)).filas
    )


@pytest.mark.django_db
def test_RF_41_cada_enlace_de_la_pagina_de_tickets_abre_para_ese_rol(mundo: Mundo) -> None:
    for usuario in ("u-tec-ad", "u-admin"):
        c = como(usuario)
        pagina = texto(c.get("/tickets"))
        assert "/solicitudes/SOL-" not in pagina, "el detalle no es para este rol"
        for ruta in {
            parte.split('"')[0]
            for parte in pagina.split('href="')[1:]
            if parte.startswith("/colaboradores/")
        }:
            assert c.get(ruta).status_code == 200, (usuario, ruta)


@pytest.mark.django_db
def test_RF_41_el_tecnico_ve_nombre_con_enlace_y_el_administrador_sin_enlace(mundo: Mundo) -> None:
    con_enlace = texto(como("u-tec-ad").get("/tickets"))
    sin_enlace = texto(como("u-admin").get("/tickets"))
    nombre = mundo.puerto.buscar_tickets(FiltroDeTickets(tamano=1)).filas[0].colaborador_nombre
    assert f">{nombre}</a>" in con_enlace
    assert nombre in sin_enlace
    assert f">{nombre}</a>" not in sin_enlace
    assert "/colaboradores/" not in sin_enlace


@pytest.mark.django_db
def test_RF_41_la_pagina_ofrece_limpiar_los_filtros(mundo: Mundo) -> None:
    assert 'href="/tickets">Limpiar' in texto(como("u-tec-ad").get("/tickets", {"cola": "AD"}))


# --- avance en Mis solicitudes --------------------------------------------------------------


def _resolver_uno(m: Mundo, sid: Any) -> None:
    with m.puerto.unidad_de_trabajo() as u:
        seguido = sorted(
            (t for t in u.tickets.de_solicitud(sid) if t.ticket.bloquea_el_cierre),
            key=lambda t: t.ticket.clave_de_idempotencia,
        )[0]
        u.tickets.guardar(seguido.observar(Observacion(EstadoDeTicket.RESUELTO, True, 1, AHORA)))


def test_RF_11_mis_solicitudes_muestra_el_avance_sin_contar_los_posteriores() -> None:
    m = Mundo.nuevo()
    sid = m.emitir(retiro(colaborador="col-1", dias=10)).solicitud_id
    m.correr_bandeja_hasta_vaciar()
    fila = MisSolicitudes(m.puerto).ejecutar("u-rrhh").filas[0]
    assert fila.avance is not None
    assert (fila.avance.resueltos, fila.avance.total) == (0, 4)  # RET: 6 tickets, 2 posteriores
    assert fila.avance.actualizada_en is None
    _resolver_uno(m, sid)
    fila = MisSolicitudes(m.puerto).ejecutar("u-rrhh").filas[0]
    assert fila.avance is not None
    assert (fila.avance.resueltos, fila.avance.total) == (1, 4)
    assert fila.avance.actualizada_en == AHORA


def test_RF_11_una_solicitud_pendiente_todavia_no_tiene_avance() -> None:
    m = Mundo.nuevo()
    m.registrar(vacaciones())
    fila = MisSolicitudes(m.puerto).ejecutar("u-col").filas[0]
    assert fila.avance is not None
    assert (fila.avance.resueltos, fila.avance.total) == (0, 0)


def test_RF_11_el_detalle_muestra_el_estado_por_cola() -> None:
    m = Mundo.nuevo()
    sid = m.emitir(retiro(colaborador="col-1", dias=10)).solicitud_id
    m.correr_bandeja_hasta_vaciar()
    _resolver_uno(m, sid)
    d = ConsultarSolicitud(m.puerto).ejecutar("u-rrhh", sid)
    assert len(d.tickets) == 6
    assert sum(t.resuelto for t in d.tickets) == 1
    assert {t.cola.value for t in d.tickets} == {"AD", "COMUNICACIONES", "LICENCIAS", "INVENTARIO"}


@pytest.mark.django_db
def test_RF_11_la_lista_web_muestra_el_avance_y_cuando_se_actualiza(mundo: Mundo) -> None:
    pagina = texto(como("u-rrhh").get("/solicitudes"))
    assert "de 4 tickets" in pagina
    assert "cada 5 minutos" in pagina
    for prohibido in ("<script", "http-equiv"):
        assert prohibido not in pagina  # invariante 11: sin recarga automatica


# --- acceso a Crear usuario -----------------------------------------------------------------


@pytest.mark.django_db
def test_RRHH_tiene_el_acceso_directo_a_crear_usuario(mundo: Mundo) -> None:
    assert 'href="/solicitudes/nueva/ING"' in texto(como("u-rrhh").get("/bandeja"))
    assert como("u-rrhh").get("/solicitudes/nueva/ING").status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("usuario", ["u-col", "u-tec-ad", "u-admin", "u-aud"])
def test_solo_RRHH_ve_crear_usuario_S_08(mundo: Mundo, usuario: str) -> None:
    assert 'href="/solicitudes/nueva/ING"' not in texto(como(usuario).get("/solicitudes"))


# --- filtros: el 429 del WAF ----------------------------------------------------------------


def test_ADR_034_las_paginas_de_consulta_tienen_su_propio_limite() -> None:
    """Filtrar dos veces en menos de 0,7 s daba 429 y la pagina desaparecia (reproducido el
    04/11/2026). Los limites del ingreso y el general no cambian."""
    entorno = "\n".join(COMPOSE["services"]["bw-scheduler"]["environment"])
    assert "app.localhost}_LIMIT_REQ_URL_3=^/(solicitudes|tickets|cuentas" in entorno
    assert "app.localhost}_LIMIT_REQ_RATE_3=10r/s" in entorno
    assert "app.localhost}_LIMIT_REQ_RATE_1=5r/m" in entorno
    assert "LIMIT_REQ_RATE=2r/s" in entorno
    url_3 = next(x for x in entorno.splitlines() if "LIMIT_REQ_URL_3" in x)
    for fuera in ("ingreso", "segundo", "colaboradores"):
        assert fuera not in url_3  # T1 y T10: la verificacion y las fichas siguen con 2 r/s


# --- auditoria funcional del 04/11/2026 ---------------------------------------------------------


@pytest.mark.django_db
def test_toda_pagina_declara_su_icono_y_no_pide_favicon_ico(mundo: Mundo) -> None:
    """El navegador pedia /favicon.ico y recibia 404 en cada sesion nueva."""
    assert 'rel="icon"' in texto(Client().get("/ingreso"))
    assert Client().get("/static/web/icono.svg").status_code == 200


def test_los_espacios_de_trabajo_del_editor_no_entran_a_la_imagen() -> None:
    raiz = Path(__file__).resolve().parents[2]
    assert "**/*.code-workspace" in (raiz / ".dockerignore").read_text(encoding="utf-8")


@pytest.mark.django_db
def test_RF_11_el_avance_sql_coincide_con_el_oraculo() -> None:
    oraculo, ids = semilla()
    real, _ = semilla(RepositoriosDjango)
    todas = list(ids.values())
    for m in (oraculo, real):
        with m.puerto.unidad_de_trabajo() as u:
            for sid, cuantos in zip(todas, (1, 2, 4, 0), strict=False):
                seguidos = sorted(
                    u.tickets.de_solicitud(sid), key=lambda x: x.ticket.clave_de_idempotencia
                )
                for s in seguidos[:cuantos]:
                    u.tickets.guardar(
                        s.observar(Observacion(EstadoDeTicket.RESUELTO, True, 1, AHORA))
                    )
    assert real.puerto.avances(todas) == oraculo.puerto.avances(todas)
    assert real.puerto.avances([]) == {}


@pytest.mark.django_db
def test_RNF_06_mis_solicitudes_no_hace_una_consulta_de_tickets_por_fila() -> None:
    """Con una consulta por fila, el p95 llego a 1058 ms con 300 colaboradores (meta: 800 ms)."""
    m, _ = semilla(RepositoriosDjango)
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as consultas:
        MisSolicitudes(m.puerto).ejecutar("u-rrhh")
    de_tickets = [q for q in consultas if '"ticket"' in q["sql"]]
    assert len(de_tickets) == 1, de_tickets
