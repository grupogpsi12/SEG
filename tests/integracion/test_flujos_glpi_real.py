"""Item 5.1: VAC, RET y EMG de extremo a extremo con TODO real salvo el reloj (CA-04, CA-06, CA-07).

Los mismos pasos que `tests/escenarios`, pero con los repositorios contra PostgreSQL, el worker
(bandeja y sincronizacion) contra GLPI 11 real y una persona de TI que resuelve en GLPI. El reloj
es simulado para no esperar dias. Lo corre `infra/scripts/contrato-glpi.sh` dentro de la red de
Docker, con un PostgreSQL desechable. Sin las variables se omite, con el ID S-28.
"""

import os
from dataclasses import replace
from datetime import timedelta
from typing import Any, cast

import httpx
import pytest

from jml.adaptadores.salida.glpi.cliente import SistemaDeTicketsGlpi
from jml.adaptadores.salida.persistencia.repositorios import RepositoriosDjango
from jml.aplicacion.bandeja import espera_de_reintento
from jml.dominio.cuentas import Cuenta
from jml.dominio.tipos import (
    ClaseTicket,
    EstadoColaborador,
    EstadoDeCuenta,
    EstadoSolicitud,
    SistemaDeCuenta,
    Subtipo,
)
from jml.dominio.valores import SolicitudId
from tests.dobles.glpi_real import TecnicoGlpiReal, TransporteConFallos
from tests.fabricas import SENTINELA
from tests.mundo import Mundo, emergencia, retiro, vacaciones

SIN_GLPI = "JML_GLPI_API_URL" not in os.environ
pytestmark = [
    pytest.mark.skipif(SIN_GLPI, reason="S-28: sin un GLPI real (variables JML_GLPI_*)"),
    pytest.mark.django_db,
]

S, E = EstadoSolicitud, EstadoDeCuenta
AD, RED, M365 = SistemaDeCuenta.AD, SistemaDeCuenta.RED, SistemaDeCuenta.M365


class Real:
    """Un Mundo con PostgreSQL y GLPI reales, y la persona de TI que trabaja en GLPI."""

    def __init__(self) -> None:
        url, app = os.environ["JML_GLPI_API_URL"], os.environ["JML_GLPI_APP_TOKEN"]
        self.tecnico = TecnicoGlpiReal(url, app, os.environ["JML_GLPI_ADMIN_TOKEN"])
        self.tecnico.limpiar()
        self.red = TransporteConFallos(httpx.HTTPTransport())
        m = Mundo.nuevo(repositorios=RepositoriosDjango)
        adaptador = SistemaDeTicketsGlpi(
            url,
            app,
            os.environ["JML_GLPI_USER_TOKEN"],
            m.reloj.ahora,
            httpx.Client(timeout=60.0, transport=self.red),
        )
        # El Mundo tipa su GLPI como el doble; aqui va el adaptador real (mismo puerto).
        self.m = replace(m, glpi=cast(Any, adaptador))

    def sembrar_cuentas_activas(self, colaborador: str) -> None:
        ahora = self.m.reloj.ahora()
        with self.m.puerto.unidad_de_trabajo() as u:
            for sistema in SistemaDeCuenta:
                antes = ahora - timedelta(days=900)
                u.cuentas.guardar(
                    Cuenta(colaborador, sistema, E.ACTIVA, "semilla", (antes,) * 2, ahora)
                )

    def cuentas(self, colaborador: str) -> dict[SistemaDeCuenta, EstadoDeCuenta | None]:
        with self.m.puerto.unidad_de_trabajo() as u:
            return {
                s: (c.estado if (c := u.cuentas.obtener(colaborador, s)) else None)
                for s in SistemaDeCuenta
            }

    def ids(self, sid: SolicitudId, clase: ClaseTicket | None = None) -> dict[str, str]:
        """cola -> id en GLPI de los tickets creados de la solicitud (de una clase, si se pide)."""
        with self.m.puerto.unidad_de_trabajo() as u:
            tickets = list(u.tickets.de_solicitud(sid))
        return {
            t.ticket.cola.value: t.id_externo
            for t in tickets
            if t.id_externo is not None and (clase is None or t.ticket.clase is clase)
        }

    def resolver(self, sid: SolicitudId, clase: ClaseTicket, colas: tuple[str, ...] = ()) -> None:
        for cola, gid in self.ids(sid, clase).items():
            if not colas or cola in colas:
                self.tecnico.resolver(gid, True, documentos=1 if cola == "INVENTARIO" else 0)

    def invariantes(self, *solicitudes: SolicitudId) -> None:
        # ninguna ejecucion duplico un ticket en GLPI
        for sid in solicitudes:
            with self.m.puerto.unidad_de_trabajo() as u:
                claves = [
                    t.ticket.clave_de_idempotencia
                    for t in u.tickets.de_solicitud(sid)
                    if t.id_externo
                ]
            assert all(self.tecnico.creaciones(c) == 1 for c in claves), sid
        # la auditoria encadenada verifica
        with self.m.puerto.unidad_de_trabajo() as u:
            assert u.auditoria.verificar().valida
        # el campo restringido nunca llego a GLPI (CA-10)
        for sid in solicitudes:
            assert not any(SENTINELA in c for c in self.tecnico.contenidos("Ticket", sid.valor))


@pytest.fixture
def real() -> Real:
    return Real()


def test_VAC_real_suspende_y_reactiva_en_su_fecha(real: Real) -> None:
    m = real.m
    real.sembrar_cuentas_activas("col-1")
    a = m.registrar(vacaciones(dias=2, regreso=9))
    m.aprobar("u-rrhh", a.solicitud_id)
    m.correr_bandeja_hasta_vaciar()
    # suspension inmediata y reactivacion programada, cada una en AD y Licencias
    assert set(real.ids(a.solicitud_id, ClaseTicket.CIERRE_INMEDIATO)) == {"AD", "LICENCIAS"}
    assert set(real.ids(a.solicitud_id, ClaseTicket.CIERRE_PROGRAMADO)) == {"AD", "LICENCIAS"}
    m.sincronizar()
    # CA-04: la reactivacion programada (En espera en GLPI) todavia no cuenta
    assert real.cuentas("col-1") == {
        AD: E.PENDIENTE_SUSPENSION,
        RED: E.ACTIVA,
        M365: E.PENDIENTE_SUSPENSION,
    }
    real.resolver(a.solicitud_id, ClaseTicket.CIERRE_INMEDIATO)
    m.avanzar(timedelta(days=2))
    m.sincronizar()
    assert real.cuentas("col-1") == {AD: E.SUSPENDIDA, RED: E.ACTIVA, M365: E.SUSPENDIDA}
    assert m.colaborador("col-1").estado is EstadoColaborador.SUSPENDIDO
    assert m.solicitud(a.solicitud_id).estado is S.EN_EJECUCION
    m.avanzar(timedelta(days=8))  # dia de regreso
    real.resolver(a.solicitud_id, ClaseTicket.CIERRE_PROGRAMADO)
    m.sincronizar()
    assert real.cuentas("col-1") == {AD: E.ACTIVA, RED: E.ACTIVA, M365: E.ACTIVA}
    assert m.solicitud(a.solicitud_id).estado is S.CERRADA
    assert m.colaborador("col-1").estado is EstadoColaborador.ACTIVO
    real.invariantes(a.solicitud_id)


def test_RET_real_cierra_sin_esperar_la_eliminacion_posterior(real: Real) -> None:
    m = real.m
    real.sembrar_cuentas_activas("col-1")
    a = m.registrar(retiro("u-col", subtipo=Subtipo.RENUNCIA, dias=5))
    m.aprobar("u-rrhh", a.solicitud_id)
    m.correr_bandeja_hasta_vaciar()
    m.sincronizar()
    assert set(real.cuentas("col-1").values()) == {E.PENDIENTE_BAJA}
    m.avanzar(timedelta(days=6))
    real.resolver(a.solicitud_id, ClaseTicket.CIERRE_INMEDIATO)
    m.sincronizar()
    # CA-04: los tickets posteriores (eliminacion a los 90 dias) siguen En espera y no bloquean
    assert real.ids(a.solicitud_id, ClaseTicket.POSTERIOR)
    assert m.solicitud(a.solicitud_id).estado is S.CERRADA
    assert set(real.cuentas("col-1").values()) == {E.DESHABILITADA}
    assert m.colaborador("col-1").estado is EstadoColaborador.RETIRADO
    m.avanzar(timedelta(days=95))
    real.resolver(a.solicitud_id, ClaseTicket.POSTERIOR)
    m.sincronizar()
    assert real.cuentas("col-1") == {AD: E.ELIMINADA, RED: E.DESHABILITADA, M365: E.ELIMINADA}
    real.invariantes(a.solicitud_id)


def test_CA_06_EMG_real_con_SLA_de_una_hora_y_exposicion(real: Real) -> None:
    m = real.m
    real.sembrar_cuentas_activas("col-1")
    vac = m.registrar(vacaciones())
    r = m.emitir(emergencia(subtipo=Subtipo.DESPIDO_CON_JUSTA_CAUSA))
    assert r.marcadas_para_revision == (vac.solicitud_id,)
    m.correr_bandeja_hasta_vaciar()
    # GLPI calcula prioridad 5 (Muy alta) y aplica el SLA de 1 hora por su regla (3.1)
    bajas = real.ids(r.solicitud_id, ClaseTicket.CIERRE_INMEDIATO)
    assert len(bajas) == 4
    for gid in bajas.values():
        t = real.tecnico.ticket(gid)
        assert int(t["priority"]) == 5, t["priority"]
        assert real.tecnico.sla_de(t["slas_id_ttr"])[1:] == (1, "hour"), gid
    m.avanzar(timedelta(hours=2, minutes=10))
    m.sincronizar()
    (fila,) = m.dashboard("u-tec-ad").exposicion
    assert (fila.horas_de_exposicion, fila.tickets_de_baja_abiertos) == (2, 3)
    real.resolver(r.solicitud_id, ClaseTicket.CIERRE_INMEDIATO)
    m.sincronizar()
    assert m.dashboard("u-tec-ad").exposicion == ()
    assert m.solicitud(r.solicitud_id).estado is S.CERRADA
    assert m.colaborador("col-1").estado is EstadoColaborador.RETIRADO
    assert m.solicitud(vac.solicitud_id).para_revision
    real.invariantes(r.solicitud_id)


def test_CA_07_real_GLPI_caido_lleva_a_error_y_el_reintento_no_duplica(real: Real) -> None:
    m = real.m
    r = m.emitir(retiro())
    real.red.caida(100_000)  # GLPI no responde (503) a nada
    for ronda in range(1, 11):  # los 10 intentos con las esperas de S-13
        m.bandeja()
        m.avanzar(espera_de_reintento(ronda))
    assert m.solicitud(r.solicitud_id).estado is S.ERROR
    assert real.ids(r.solicitud_id) == {}
    # mientras tanto la aplicacion sigue aceptando y aprobando (RNF-02)
    otra = m.registrar(vacaciones())
    assert m.aprobar("u-rrhh", otra.solicitud_id).tickets_encolados == 4
    real.red.recuperar()  # GLPI vuelve
    m.reintentar("u-admin", r.solicitud_id)
    m.correr_bandeja_hasta_vaciar()
    assert m.solicitud(r.solicitud_id).estado is S.EN_EJECUCION
    assert m.solicitud(otra.solicitud_id).estado is S.EN_EJECUCION
    real.invariantes(r.solicitud_id, otra.solicitud_id)
