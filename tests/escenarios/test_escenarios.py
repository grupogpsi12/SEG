"""Item 1.12: escenarios de extremo a extremo en memoria (CA-05, CA-06, CA-07, CA-08).

Cada uno recorre el sistema entero con los casos de uso reales, un reloj simulado y un GLPI falso
con fallos programados. Al terminar TODOS pasan por las mismas invariantes: ninguna ejecucion
duplica un ticket, la auditoria verifica, las cuentas solo cambiaron por la sincronizacion y una
solicitud cerrada tiene de verdad todos sus tickets de cierre resueltos con solucion.
"""

import dataclasses
from datetime import timedelta

import pytest

from jml.aplicacion.bandeja import espera_de_reintento
from jml.dominio.errores import (
    CancelacionNoPermitida,
    NoAutorizado,
    SolicitudDuplicada,
    SoporteInvalido,
)
from jml.dominio.resolucion import solicitud_cerrable, ticket_resuelto
from jml.dominio.tipos import (
    ESTADOS_ABIERTOS,
    ClaseTicket,
    EstadoColaborador,
    EstadoDeCuenta,
    EstadoDeTicket,
    EstadoSolicitud,
    MarcaDeCuenta,
    SistemaDeCuenta,
    Subtipo,
    TipoDeVinculacion,
)
from jml.dominio.valores import SolicitudId
from tests.aplicacion.test_sincronizacion import _sembrar_cuentas_activas
from tests.dobles.glpi import Fallo
from tests.fabricas import AHORA, SENTINELA
from tests.mundo import (
    Mundo,
    cambio_de_departamento,
    cambio_de_sucursal,
    emergencia,
    ingreso,
    retiro,
    vacaciones,
)

S, E = EstadoSolicitud, EstadoDeCuenta
AD, RED, M365 = SistemaDeCuenta.AD, SistemaDeCuenta.RED, SistemaDeCuenta.M365


def invariantes(m: Mundo) -> None:
    """Lo que debe ser cierto al final de CUALQUIER escenario."""
    # 1. ninguna ejecucion duplica un ticket
    assert set(m.glpi.creaciones_reales.values()) <= {1}
    # 2. la auditoria encadenada verifica y sus secuencias son contiguas
    registros = m.repos.auditoria().registros()
    assert m.repos.auditoria().verificar().valida
    assert [r.secuencia for r in registros] == list(range(1, len(registros) + 1))
    # 3. el campo restringido nunca salio de la solicitud
    todo = "\n".join(repr(r) + r.contenido().decode() for r in registros)
    todo += "\n".join(t.como_texto() for t in m.glpi.tickets_remotos())
    assert SENTINELA not in todo
    # 4. nunca dos abiertas del mismo colaborador y tipo
    abiertas = [
        (s.colaborador_id, s.tipo)
        for s in m.repos.almacen.solicitudes.values()
        if s.estado in ESTADOS_ABIERTOS
    ]
    assert len(abiertas) == len(set(abiertas))
    # 5. cada cuenta es el ultimo estado de su historial (solo la sincronizacion las cambia)
    for (cid, sistema), cuenta in m.repos.almacen.cuentas.items():
        propio = [
            h for h in m.repos.almacen.historial if h.colaborador_id == cid and h.sistema is sistema
        ]
        if propio:
            assert cuenta.estado is propio[-1].estado_nuevo
    # 6. toda solicitud cerrada tiene sus tickets de cierre resueltos con solucion
    for s in m.repos.almacen.solicitudes.values():
        if s.estado is S.CERRADA:
            tickets = [
                t for t in m.repos.almacen.tickets.values() if t.ticket.solicitud_id == s.id.valor
            ]
            assert all(ticket_resuelto(t) for t in tickets if t.ticket.bloquea_el_cierre)
            assert solicitud_cerrable(tickets)


def cuentas(m: Mundo, colaborador: str) -> dict[SistemaDeCuenta, EstadoDeCuenta | None]:
    return {
        s: (c.estado if (c := m.repos.almacen.cuentas.get((colaborador, s))) else None)
        for s in SistemaDeCuenta
    }


def gid(m: Mundo, sid: SolicitudId, cola: str, clase: str = "cierre_inmediato") -> str:
    t = next(
        t for t in m.repos.almacen.tickets.values()
        if t.ticket.solicitud_id == sid.valor and t.ticket.cola.value == cola and t.ticket.clase.value == clase
    )  # fmt: skip
    assert t.id_externo is not None
    return t.id_externo


# --- ING (CA-05) ------------------------------------------------------------------------------


def test_CA_05_ING_de_punta_a_punta_con_fallos_de_glpi() -> None:
    m = Mundo.nuevo()
    # 1. RRHH emite el ingreso con su soporte; GLPI esta inestable
    m.glpi.programar(Fallo.ANTES, Fallo.DESPUES, Fallo.DUPLICADA, Fallo.ANTES)
    r = m.emitir(ingreso(vinculacion=TipoDeVinculacion.CONTRATISTA))
    assert r.estado is S.APROBADA
    assert r.tickets_encolados == 4
    # 2. la bandeja insiste hasta crear los 4 tickets, sin duplicar ni perder el soporte
    m.correr_bandeja_hasta_vaciar()
    assert m.solicitud(r.solicitud_id).estado is S.EN_EJECUCION
    assert len(m.glpi.creaciones_reales) == 4
    assert m.glpi.documentos_subidos() == 1
    assert m.soportes.nombres() == []  # la copia local ya no esta
    # 3. mientras los tecnicos trabajan, las cuentas estan pendientes
    m.sincronizar()
    assert cuentas(m, r.colaborador_id) == {
        AD: E.PENDIENTE_ALTA,
        RED: E.PENDIENTE_ALTA,
        M365: E.PENDIENTE_ALTA,
    }
    # 4. resuelven con plantilla (solucion) y acta en Inventario
    m.tecnico_resuelve_todo(r.solicitud_id)
    m.avanzar(timedelta(minutes=5))
    m.sincronizar()
    # 5. la solicitud cierra, las cuentas quedan activas y el colaborador activo
    assert m.solicitud(r.solicitud_id).estado is S.CERRADA
    assert cuentas(m, r.colaborador_id) == {AD: E.ACTIVA, RED: E.ACTIVA, M365: E.ACTIVA}
    assert m.colaborador(r.colaborador_id).estado is EstadoColaborador.ACTIVO
    invariantes(m)


def test_ING_con_soporte_invalido_no_deja_nada() -> None:
    m = Mundo.nuevo()
    from jml.aplicacion.dtos import ArchivoRecibido

    antes = m.repos.almacen.instantanea()
    with pytest.raises(SoporteInvalido):
        m.emitir(ingreso(soporte=ArchivoRecibido("acta.pdf", b"MZ\x90\x00 no soy un pdf" * 4)))
    assert m.repos.almacen.instantanea() == antes
    assert m.soportes.nombres() == []
    invariantes(m)


# --- VAC ---------------------------------------------------------------------------------------


def test_VAC_de_punta_a_punta_con_reactivacion_programada() -> None:
    m = Mundo.nuevo()
    _sembrar_cuentas_activas(m, "col-1")
    # el colaborador solicita; RRHH aprueba; se crean los 4 tickets (2 inmediatos y 2 programados)
    a = m.registrar(vacaciones(dias=2, regreso=9))
    m.aprobar("u-rrhh", a.solicitud_id)
    m.correr_bandeja_hasta_vaciar()
    assert (
        m.glpi.leer_tickets([gid(m, a.solicitud_id, "AD", "cierre_programado")])[
            gid(m, a.solicitud_id, "AD", "cierre_programado")
        ].estado
        is EstadoDeTicket.EN_ESPERA
    )
    m.sincronizar()
    # CA-04: la reactivacion programada todavia no cuenta
    assert cuentas(m, "col-1") == {
        AD: E.PENDIENTE_SUSPENSION,
        RED: E.ACTIVA,
        M365: E.PENDIENTE_SUSPENSION,
    }
    # suspension resuelta el dia de inicio
    for cola in ("AD", "LICENCIAS"):
        m.glpi.resolver(gid(m, a.solicitud_id, cola))
    m.avanzar(timedelta(days=2))
    m.sincronizar()
    assert cuentas(m, "col-1") == {AD: E.SUSPENDIDA, RED: E.ACTIVA, M365: E.SUSPENDIDA}
    assert m.colaborador("col-1").estado is EstadoColaborador.SUSPENDIDO
    assert m.solicitud(a.solicitud_id).estado is S.EN_EJECUCION
    # el dia de regreso la reactivacion pasa a pendiente y el tecnico la resuelve
    m.avanzar(timedelta(days=8))
    ind = m.dashboard("u-tec-ad")
    assert {(f.cola.value, f.prioridad.value) for f in ind.pendientes} >= {
        ("AD", "Media"),
        ("LICENCIAS", "Media"),
    }
    for cola in ("AD", "LICENCIAS"):
        m.glpi.resolver(gid(m, a.solicitud_id, cola, "cierre_programado"))
    m.sincronizar()
    assert cuentas(m, "col-1") == {AD: E.ACTIVA, RED: E.ACTIVA, M365: E.ACTIVA}
    assert m.solicitud(a.solicitud_id).estado is S.CERRADA
    assert m.colaborador("col-1").estado is EstadoColaborador.ACTIVO
    invariantes(m)


# --- CDP / CSU ---------------------------------------------------------------------------------


def test_CDP_de_punta_a_punta_aplica_el_perfil_nuevo() -> None:
    m = Mundo.nuevo()
    _sembrar_cuentas_activas(m, "col-1")
    a = m.registrar(cambio_de_departamento(destino="TI"))  # lo pide el jefe
    m.aprobar("u-rrhh", a.solicitud_id, "autorizado")
    m.correr_bandeja_hasta_vaciar()
    m.sincronizar()
    assert all(c.marca is MarcaDeCuenta.CAMBIO_PENDIENTE for c in m.repos.almacen.cuentas.values())
    m.tecnico_resuelve_todo(a.solicitud_id)
    m.avanzar(timedelta(hours=2))
    m.sincronizar()
    assert m.solicitud(a.solicitud_id).estado is S.CERRADA
    assert all(c.marca is None and c.estado is E.ACTIVA for c in m.repos.almacen.cuentas.values())
    assert m.colaborador("col-1").departamento == "TI"
    invariantes(m)


def test_CSU_de_punta_a_punta_traslada_el_equipo() -> None:
    m = Mundo.nuevo()
    _sembrar_cuentas_activas(m, "col-1")
    a = m.emitir(
        dataclasses.replace(
            cambio_de_sucursal(usuario="u-rrhh", sede="Cali", traslada=True),
            justificacion="traslado",
        )
    )
    assert a.tickets_encolados == 3  # AD, Comunicaciones e Inventario (no Licencias)
    m.correr_bandeja_hasta_vaciar()
    m.tecnico_resuelve_todo(a.solicitud_id)
    m.sincronizar()
    assert m.solicitud(a.solicitud_id).estado is S.CERRADA
    assert m.colaborador("col-1").sede == "Cali"
    assert cuentas(m, "col-1")[M365] is E.ACTIVA  # Licencias no participo
    invariantes(m)


# --- RET ---------------------------------------------------------------------------------------


def test_RET_de_punta_a_punta_con_eliminacion_posterior_a_los_90_dias() -> None:
    m = Mundo.nuevo()
    _sembrar_cuentas_activas(m, "col-1")
    a = m.registrar(
        retiro("u-col", subtipo=Subtipo.RENUNCIA, dias=5)
    )  # renuncia del propio colaborador
    m.aprobar("u-rrhh", a.solicitud_id)
    m.correr_bandeja_hasta_vaciar()
    m.sincronizar()
    assert set(cuentas(m, "col-1").values()) == {E.PENDIENTE_BAJA}
    # llega el ultimo dia laborado y se ejecutan las bajas (los posteriores siguen En espera)
    m.avanzar(timedelta(days=6))
    m.tecnico_resuelve_todo(a.solicitud_id)  # resuelve todo lo creado, incluidos los posteriores
    with m.repos.unidad_de_trabajo() as u:
        posteriores = [
            t
            for t in u.tickets.de_solicitud(a.solicitud_id)
            if t.ticket.clase is ClaseTicket.POSTERIOR
        ]
    for t in posteriores:  # los posteriores NO estan resueltos todavia: se devuelven a En espera
        assert t.id_externo is not None
        m.glpi.poner_estado(t.id_externo, EstadoDeTicket.EN_ESPERA)
        m.glpi._remotos[t.id_externo].solucion = False
    m.sincronizar()
    assert m.solicitud(a.solicitud_id).estado is S.CERRADA  # CA-04: el posterior no bloquea
    assert set(cuentas(m, "col-1").values()) == {E.DESHABILITADA}
    assert m.colaborador("col-1").estado is EstadoColaborador.RETIRADO
    # 90 dias despues
    m.avanzar(timedelta(days=95))
    for t in posteriores:
        assert t.id_externo is not None
        m.glpi.resolver(t.id_externo)
    m.sincronizar()
    assert cuentas(m, "col-1") == {AD: E.ELIMINADA, RED: E.DESHABILITADA, M365: E.ELIMINADA}
    assert m.solicitud(a.solicitud_id).estado is S.CERRADA  # sigue cerrada
    invariantes(m)


# --- EMG (CA-06) -------------------------------------------------------------------------------


def test_CA_06_EMG_de_punta_a_punta_con_reloj_simulado() -> None:
    m = Mundo.nuevo()
    _sembrar_cuentas_activas(m, "col-1")
    vac = m.registrar(vacaciones())  # hay una VAC abierta (RF-10)
    r = m.emitir(emergencia(subtipo=Subtipo.DESPIDO_CON_JUSTA_CAUSA))
    assert r.marcadas_para_revision == (vac.solicitud_id,)
    assert m.solicitud(vac.solicitud_id).estado is S.PENDIENTE_APROBACION  # no se toca
    m.correr_bandeja_hasta_vaciar()
    # prioridad «Muy alta» y SLA de 1 hora
    with m.repos.unidad_de_trabajo() as u:
        bajas = [
            t.ticket
            for t in u.tickets.de_solicitud(r.solicitud_id)
            if t.ticket.clase is ClaseTicket.CIERRE_INMEDIATO
        ]
    assert {t.prioridad.value for t in bajas} == {"Muy alta"}
    assert {t.vence_en - t.emitido_en for t in bajas} == {timedelta(hours=1)}
    # la exposicion corre hasta que se resuelven las bajas
    m.avanzar(timedelta(hours=2, minutes=10))
    m.sincronizar()
    (fila,) = m.dashboard("u-tec-ad").exposicion
    assert (fila.horas_de_exposicion, fila.tickets_de_baja_abiertos) == (2, 3)
    assert {f.cola.value for f in m.dashboard("u-tec-ad").vencidos} == {
        "AD",
        "COMUNICACIONES",
        "LICENCIAS",
        "INVENTARIO",
    }
    m.tecnico_resuelve_todo(r.solicitud_id)
    m.sincronizar()
    assert m.dashboard("u-tec-ad").exposicion == ()
    assert m.solicitud(r.solicitud_id).estado is S.CERRADA
    assert m.colaborador("col-1").estado is EstadoColaborador.RETIRADO
    # RRHH ve la VAC marcada y decide
    assert m.solicitud(vac.solicitud_id).para_revision
    invariantes(m)


# --- resiliencia (CA-07) ---------------------------------------------------------------------


def test_CA_07_caida_larga_de_glpi_error_y_reintento_del_administrador() -> None:
    m = Mundo.nuevo()
    r = m.emitir(retiro())
    m.glpi.caer()
    for ronda in range(1, 11):  # 10 intentos con las esperas de S-13
        m.bandeja()
        m.avanzar(espera_de_reintento(ronda))
    assert m.solicitud(r.solicitud_id).estado is S.ERROR
    assert m.glpi.creaciones_reales == {}
    # mientras tanto el sistema sigue aceptando y aprobando otras solicitudes (RNF-02)
    otra = m.registrar(vacaciones())
    assert m.aprobar("u-rrhh", otra.solicitud_id).tickets_encolados == 4
    m.glpi.recuperar()
    m.reintentar("u-admin", r.solicitud_id)
    m.correr_bandeja_hasta_vaciar()
    assert m.solicitud(r.solicitud_id).estado is S.EN_EJECUCION
    assert m.solicitud(otra.solicitud_id).estado is S.EN_EJECUCION
    assert len(m.glpi.creaciones_reales) == 6 + 4
    invariantes(m)


def test_cancelacion_antes_y_despues_de_crearse_los_tickets() -> None:
    m = Mundo.nuevo()
    antes = m.registrar(vacaciones())
    m.aprobar("u-rrhh", antes.solicitud_id)
    m.cancelar("u-rrhh", antes.solicitud_id, "error de fechas")  # antes de crear: se puede
    assert m.solicitud(antes.solicitud_id).estado is S.CANCELADA
    despues = m.registrar(vacaciones())
    m.aprobar("u-rrhh", despues.solicitud_id)
    m.bandeja(limite=1)  # un ticket ya existe en GLPI
    with pytest.raises(CancelacionNoPermitida):
        m.cancelar("u-rrhh", despues.solicitud_id)
    m.correr_bandeja_hasta_vaciar()
    with pytest.raises(NoAutorizado):
        m.cancelar("u-col", despues.solicitud_id)  # y el solicitante tampoco, ya no esta pendiente
    assert set(m.glpi.creaciones_reales.values()) == {1}
    invariantes(m)


def test_RRHH_como_sujeto_lo_emite_el_administrador_por_excepcion_S_08() -> None:
    m = Mundo.nuevo()
    _sembrar_cuentas_activas(m, "col-rrhh")
    propia = dataclasses.replace(
        vacaciones("u-rrhh", "col-rrhh"), justificacion="vacaciones de RRHH"
    )
    with pytest.raises(NoAutorizado):
        m.emitir(propia)
    a = m.emitir_por_excepcion(
        dataclasses.replace(vacaciones("u-admin", "col-rrhh"), justificacion="excepcion registrada")
    )
    m.correr_bandeja_hasta_vaciar()
    for cola in ("AD", "LICENCIAS"):  # solo la suspension: la reactivacion espera su fecha
        m.glpi.resolver(gid(m, a.solicitud_id, cola))
    m.sincronizar()
    assert m.solicitud(a.solicitud_id).estado is S.EN_EJECUCION  # falta la reactivacion programada
    assert "solicitud.emitida_por_excepcion" in m.acciones_de_auditoria()
    invariantes(m)


def test_un_duplicado_durante_la_ejecucion_se_rechaza_hasta_cerrar() -> None:
    m = Mundo.nuevo()
    a = m.emitir(dataclasses.replace(vacaciones("u-rrhh"), justificacion="ok"))
    m.correr_bandeja_hasta_vaciar()  # en_ejecucion
    with pytest.raises(SolicitudDuplicada):
        m.registrar(vacaciones())
    m.tecnico_resuelve_todo(a.solicitud_id)
    m.avanzar(timedelta(days=30))
    m.sincronizar()
    assert m.solicitud(a.solicitud_id).estado in (S.CERRADA, S.EN_EJECUCION)


def test_la_hora_de_la_sincronizacion_avanza_con_el_reloj() -> None:
    m = Mundo.nuevo()
    m.sincronizar()
    m.avanzar(timedelta(minutes=5))
    m.sincronizar()
    ultima = m.dashboard("u-tec-ad").ultima_sincronizacion
    assert ultima is not None
    assert ultima.fin == AHORA + timedelta(minutes=5)
