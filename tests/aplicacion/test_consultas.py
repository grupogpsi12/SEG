"""Item 1.11: dashboard, busqueda y ficha (RF-29 a RF-33, CA-15, CA-16, CA-10).

El resultado del doble en memoria es el ORACULO de la consulta SQL. Por eso cada indicador se
compara aqui con una expectativa ESCRITA A MANO sobre una semilla pequena.

Semilla (lunes 12-oct-2026, 10:00 Bogota; se consulta 3 h 30 min despues):
  RET  col-1   renuncia, ultimo dia 22-oct       6 tickets (3 bajas + equipo + 2 posteriores)
  VAC  col-9   inicia 14-oct, regresa 17-oct     4 tickets (2 suspensiones + 2 reactivaciones)
  ING  Camila  ingresa 26-oct                    4 tickets
  EMG  jefe-1  emitida a las 10:00               6 tickets (3 bajas + equipo + 2 posteriores)
"""

import dataclasses
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from jml.aplicacion.dtos import (
    FilaCuentas,
    FilaExposicion,
    FilaIncompleto,
    FilaPendientes,
    FilaSolicitudesDelMes,
    FilaVencidos,
    FiltroDeCuentas,
    IndicadorDeEquipos,
)
from jml.dominio.activos import ActivoAsignado, LicenciaAsignada
from jml.dominio.cuentas import Cuenta
from jml.dominio.errores import DatoInvalido, NoAutorizado, NoEncontrado
from jml.dominio.tipos import (
    Cola,
    EstadoColaborador,
    EstadoDeCuenta,
    EstadoSolicitud,
    Prioridad,
    SistemaDeCuenta,
    Subtipo,
    TipoEvento,
)
from jml.dominio.valores import SolicitudId
from tests.fabricas import AHORA, HOY, SENTINELA
from tests.mundo import Mundo, emergencia, ingreso, retiro, vacaciones

AD, COM, LIC, INV = Cola.AD, Cola.COMUNICACIONES, Cola.LICENCIAS, Cola.INVENTARIO
MEDIA, ALTA, MUY_ALTA = Prioridad.MEDIA, Prioridad.ALTA, Prioridad.MUY_ALTA
E = EstadoDeCuenta


def semilla() -> tuple[Mundo, dict[str, SolicitudId]]:
    m = Mundo.nuevo()
    with m.repos.unidad_de_trabajo() as u:
        for sistema in SistemaDeCuenta:
            u.cuentas.guardar(
                Cuenta(
                    "col-1", sistema, E.ACTIVA, "semilla", (AHORA - timedelta(days=900),) * 2, AHORA
                )
            )
    ids = {
        "ret": m.emitir(retiro(colaborador="col-1", dias=10)).solicitud_id,
        "vac": m.emitir(
            dataclasses.replace(
                vacaciones("u-rrhh", "col-9", dias=2, regreso=5), justificacion="ok"
            )
        ).solicitud_id,
        "ing": m.emitir(ingreso()).solicitud_id,
        "emg": m.emitir(emergencia(colaborador="jefe-1")).solicitud_id,
    }
    m.correr_bandeja_hasta_vaciar()
    with m.repos.unidad_de_trabajo() as u:
        u.activos.reemplazar(
            "col-1", [ActivoAsignado("A1", "Portátil", "SN-1", "ThinkPad", HOY, True)], []
        )
        u.activos.reemplazar(
            "col-9", [ActivoAsignado("A2", "Portátil", "SN-2", "Dell", HOY, True)], []
        )
        u.activos.reemplazar(
            "jefe-1", [ActivoAsignado("A3", "Escritorio", "SN-3", "HP", HOY, False)], []
        )
    m.reloj.fijar(AHORA + timedelta(hours=3, minutes=30))
    m.sincronizar()
    return m, ids


# --- RF-29: acceso -----------------------------------------------------------------------------


def test_RF_29_solo_los_roles_tecnicos_ven_el_dashboard_y_RRHH_recibe_403() -> None:
    m, _ = semilla()
    for usuario in ("u-tec-ad", "u-tec-com", "u-tec-lic", "u-tec-inv"):
        assert m.dashboard(usuario).generados_en == m.reloj.ahora()
    for usuario in ("u-rrhh", "u-admin", "u-aud", "u-col", "fantasma"):
        with pytest.raises(NoAutorizado):
            m.dashboard(usuario)


def test_RF_31_cada_tecnico_ve_su_cola_resaltada() -> None:
    m, _ = semilla()
    assert {u: m.dashboard(u).cola_resaltada for u in ("u-tec-ad", "u-tec-com", "u-tec-lic", "u-tec-inv")} == {
        "u-tec-ad": AD, "u-tec-com": COM, "u-tec-lic": LIC, "u-tec-inv": INV,
    }  # fmt: skip
    # y ven los mismos datos de todas las colas
    assert m.dashboard("u-tec-ad").pendientes == m.dashboard("u-tec-inv").pendientes


def test_RF_29_el_dashboard_muestra_la_hora_de_la_ultima_sincronizacion() -> None:
    m, _ = semilla()
    ind = m.dashboard("u-tec-ad")
    assert ind.ultima_sincronizacion is not None
    assert ind.ultima_sincronizacion.resultado == "ok"
    assert ind.ultima_sincronizacion.fin == m.reloj.ahora()


# --- RF-30 (a) a (h): expectativas escritas a mano ---------------------------------------------


def test_RF_30_a_pendientes_por_cola_y_prioridad_sin_los_programados_futuros() -> None:
    m, _ = semilla()
    assert m.dashboard("u-tec-ad").pendientes == (
        FilaPendientes(AD, MEDIA, 2),  # suspension de col-9 + alta de Camila
        FilaPendientes(AD, ALTA, 1),  # baja de col-1
        FilaPendientes(AD, MUY_ALTA, 1),  # baja de jefe-1 (EMG)
        FilaPendientes(COM, MEDIA, 1),
        FilaPendientes(COM, ALTA, 1),
        FilaPendientes(COM, MUY_ALTA, 1),
        FilaPendientes(LIC, MEDIA, 2),  # suspension de col-9 + alta de Camila
        FilaPendientes(LIC, ALTA, 1),
        FilaPendientes(LIC, MUY_ALTA, 1),
        FilaPendientes(INV, MEDIA, 1),  # equipo de Camila
        FilaPendientes(INV, ALTA, 1),
        FilaPendientes(INV, MUY_ALTA, 1),
    )  # las 2 reactivaciones de VAC y los 4 posteriores (a 90 dias) NO cuentan todavia


def test_RF_30_b_vencidos_segun_sla() -> None:
    m, _ = semilla()
    # a +3 h 30 solo vencieron los 4 tickets de la emergencia (SLA de 1 hora)
    assert m.dashboard("u-tec-ad").vencidos == (
        FilaVencidos(AD, 1),
        FilaVencidos(COM, 1),
        FilaVencidos(LIC, 1),
        FilaVencidos(INV, 1),
    )


def test_RF_30_c_exposicion_de_retiros_y_emergencias() -> None:
    m, ids = semilla()
    desde_emg = AHORA
    desde_ret = m.solicitud(ids["ret"]).fecha_efectiva  # 22-oct, aun no llega: 0 horas
    assert desde_ret > HOY
    ind = m.dashboard("u-tec-ad")
    assert ind.exposicion == (
        FilaExposicion(ids["emg"], TipoEvento.EMG, "jefe-1", 3, 3, desde_emg),  # 3 h 30 -> 3 horas
        FilaExposicion(ids["ret"], TipoEvento.RET, "col-1", 3, 0, ind.exposicion[1].desde),
    )
    assert ind.exposicion[1].desde > m.reloj.ahora()


def test_RF_30_d_solicitudes_por_estado_y_tipo_en_el_mes() -> None:
    m, _ = semilla()
    EN = EstadoSolicitud.EN_EJECUCION
    assert m.dashboard("u-tec-ad").solicitudes_del_mes == (
        FilaSolicitudesDelMes(EN, TipoEvento.ING, 1),
        FilaSolicitudesDelMes(EN, TipoEvento.VAC, 1),
        FilaSolicitudesDelMes(EN, TipoEvento.RET, 1),
        FilaSolicitudesDelMes(EN, TipoEvento.EMG, 1),
    )
    # el mes siguiente no cuenta las de octubre
    m.reloj.fijar(AHORA + timedelta(days=30))
    assert m.dashboard("u-tec-ad").solicitudes_del_mes == ()


def test_RF_30_d_el_mes_se_mide_en_bogota() -> None:
    """Creada el 31-oct a las 22:00 en Bogota (ya es 1-nov en UTC): cuenta como octubre."""
    m = Mundo.nuevo()
    r = m.registrar(vacaciones())
    creada = datetime(2026, 11, 1, 3, 0, tzinfo=UTC)  # 22:00 del 31-oct en Bogota
    with m.repos.unidad_de_trabajo() as u:
        u.solicitudes.guardar(replace(m.solicitud(r.solicitud_id), creada_en=creada))
    m.reloj.fijar(datetime(2026, 11, 1, 4, 0, tzinfo=UTC))  # 23:00 del 31-oct en Bogota
    assert len(m.dashboard("u-tec-ad").solicitudes_del_mes) == 1
    m.reloj.fijar(datetime(2026, 11, 1, 6, 0, tzinfo=UTC))  # 01:00 del 1-nov en Bogota
    assert m.dashboard("u-tec-ad").solicitudes_del_mes == ()


def test_RF_30_e_cuentas_por_estado_y_sistema() -> None:
    m, _ = semilla()
    assert m.dashboard("u-tec-ad").cuentas == (
        FilaCuentas(SistemaDeCuenta.AD, E.PENDIENTE_ALTA, 1),  # Camila
        FilaCuentas(SistemaDeCuenta.AD, E.PENDIENTE_BAJA, 1),  # col-1
        FilaCuentas(SistemaDeCuenta.RED, E.PENDIENTE_ALTA, 1),
        FilaCuentas(SistemaDeCuenta.RED, E.PENDIENTE_BAJA, 1),
        FilaCuentas(SistemaDeCuenta.M365, E.PENDIENTE_ALTA, 1),
        FilaCuentas(SistemaDeCuenta.M365, E.PENDIENTE_BAJA, 1),
    )  # col-9 y jefe-1 no tienen cuentas registradas (S-09)


def test_RF_30_f_equipos_asignados_y_pendientes_de_devolucion() -> None:
    m, _ = semilla()
    # 3 equipos asignados; los de col-1 (RET abierto) y jefe-1 (EMG abierta) deben devolverse (S-27)
    assert m.dashboard("u-tec-inv").equipos == IndicadorDeEquipos(
        asignados=3, pendientes_de_devolucion=2
    )


def test_RF_30_g_tickets_programados_de_los_proximos_7_dias() -> None:
    m, ids = semilla()
    # las reactivaciones de VAC llegan el 17-oct 00:00 Bogota (5 h UTC); los posteriores, en enero
    desde = HOY + timedelta(days=5)
    filas = m.dashboard("u-tec-ad").programados
    assert [(f.cola, f.solicitud_id) for f in filas] == [(AD, ids["vac"]), (LIC, ids["vac"])]
    assert all(f.pendiente_desde.date() == desde for f in filas)
    assert all(f.clave.endswith("cierre_programado:1") for f in filas)
    m.reloj.fijar(AHORA + timedelta(days=6))
    assert m.dashboard("u-tec-ad").programados == ()  # ya paso su fecha: ahora son pendientes (a)


def test_RF_30_g_un_programado_cuenta_como_pendiente_solo_cuando_llega_su_fecha() -> None:
    m, _ = semilla()
    antes = {(f.cola, f.prioridad): f.cantidad for f in m.dashboard("u-tec-ad").pendientes}
    m.reloj.fijar(AHORA + timedelta(days=6))
    despues = {(f.cola, f.prioridad): f.cantidad for f in m.dashboard("u-tec-ad").pendientes}
    assert despues[(AD, MEDIA)] == antes[(AD, MEDIA)] + 1  # la reactivacion de AD
    assert despues[(LIC, MEDIA)] == antes[(LIC, MEDIA)] + 1


def test_RF_30_h_cierre_incompleto_y_reabiertos() -> None:
    m, ids = semilla()
    assert m.dashboard("u-tec-ad").incompletos == ()
    with m.repos.unidad_de_trabajo() as u:
        por_cola = {t.ticket.cola: t for t in u.tickets.de_solicitud(ids["ing"])}
    gid = {cola: t.id_externo or "" for cola, t in por_cola.items()}
    m.glpi.resolver(gid[AD], con_solucion=False)  # sin solucion
    m.glpi.resolver(gid[INV], con_solucion=True, documentos=0)  # sin acta
    m.glpi.resolver(gid[LIC], con_solucion=True)
    m.sincronizar()
    m.glpi.reabrir(gid[LIC])
    m.avanzar(timedelta(minutes=5))
    m.sincronizar()
    assert m.dashboard("u-tec-ad").incompletos == (
        FilaIncompleto(
            por_cola[AD].ticket.clave_de_idempotencia, AD, ids["ing"], "cierre_incompleto"
        ),
        FilaIncompleto(
            por_cola[INV].ticket.clave_de_idempotencia, INV, ids["ing"], "cierre_incompleto"
        ),
        FilaIncompleto(por_cola[LIC].ticket.clave_de_idempotencia, LIC, ids["ing"], "reabierto"),
    )


def test_el_dashboard_vacio_no_falla() -> None:
    m = Mundo.nuevo()
    ind = m.dashboard("u-tec-ad")
    assert (ind.pendientes, ind.exposicion, ind.cuentas, ind.ultima_sincronizacion) == (
        (),
        (),
        (),
        None,
    )
    assert ind.equipos == IndicadorDeEquipos(0, 0)


# --- RF-32: busqueda con filtros y paginacion --------------------------------------------------


def test_RF_32_la_busqueda_sin_filtros_lista_a_todos_ordenados_y_paginados() -> None:
    m, _ = semilla()
    pagina = m.buscar("u-tec-ad", FiltroDeCuentas())
    # col-rrhh Herrera, col-1 Gómez Ramírez, jefe-1 Mejía, col-9 Nieto, y Camila Torres (ING)
    assert [f.nombre_completo for f in pagina.filas] == [
        "María José Gómez Ramírez", "Rosa Herrera", "Jorge Mejía", "Otto Nieto", "Camila Torres Vega",
    ]  # fmt: skip
    assert (pagina.total, pagina.pagina, pagina.tamano) == (5, 1, 20)
    segunda = m.buscar("u-tec-ad", FiltroDeCuentas(pagina=2, tamano=2))
    assert [f.nombre_completo for f in segunda.filas] == ["Jorge Mejía", "Otto Nieto"]
    assert segunda.total == 5
    assert m.buscar("u-tec-ad", FiltroDeCuentas(pagina=9, tamano=2)).filas == ()


@pytest.mark.parametrize(
    ("filtro", "esperados"),
    [
        (FiltroDeCuentas(nombre="maria gomez"), ["col-1"]),
        (FiltroDeCuentas(nombre="MARIA"), ["col-1"]),
        (FiltroDeCuentas(nombre="mejia"), ["jefe-1"]),  # sin tildes
        (FiltroDeCuentas(documento="70000009"), ["col-9"]),
        (FiltroDeCuentas(usuario="otto"), ["col-9"]),
        (FiltroDeCuentas(departamento="finanzas"), ["col-1", "jefe-1", "col-n1"]),
        (FiltroDeCuentas(departamento="Comercial"), ["col-9"]),
        (FiltroDeCuentas(sede="bogota"), ["col-1", "col-rrhh", "jefe-1", "col-9", "col-n1"]),
        (FiltroDeCuentas(sede="Cali"), []),
        (FiltroDeCuentas(sistema=SistemaDeCuenta.AD), ["col-1", "col-n1"]),
        (FiltroDeCuentas(estado_de_cuenta=E.PENDIENTE_BAJA), ["col-1"]),
        (
            FiltroDeCuentas(sistema=SistemaDeCuenta.M365, estado_de_cuenta=E.PENDIENTE_ALTA),
            ["col-n1"],
        ),
        (FiltroDeCuentas(sistema=SistemaDeCuenta.RED, estado_de_cuenta=E.ACTIVA), []),
        (FiltroDeCuentas(nombre="otto", departamento="Finanzas"), []),
    ],
)
def test_RF_32_CA_16_los_filtros_devuelven_los_colaboradores_correctos(
    filtro: FiltroDeCuentas, esperados: list[str]
) -> None:
    m, _ = semilla()
    ids = {f.colaborador_id for f in m.buscar("u-tec-ad", filtro).filas}
    assert ids == set(esperados)


def test_RF_32_los_filtros_de_sistema_y_estado_aplican_a_la_misma_cuenta() -> None:
    m, _ = semilla()
    with m.repos.unidad_de_trabajo() as u:
        u.cuentas.guardar(Cuenta("col-9", SistemaDeCuenta.AD, E.ACTIVA, "x", (AHORA, AHORA), AHORA))
        u.cuentas.guardar(
            Cuenta("col-9", SistemaDeCuenta.RED, E.SUSPENDIDA, "x", (AHORA, AHORA), AHORA)
        )
    # col-9 tiene AD activa y Red suspendida: no tiene «AD suspendida»
    assert (
        m.buscar(
            "u-tec-ad", FiltroDeCuentas(sistema=SistemaDeCuenta.AD, estado_de_cuenta=E.SUSPENDIDA)
        ).filas
        == ()
    )
    assert [
        f.colaborador_id
        for f in m.buscar(
            "u-tec-ad", FiltroDeCuentas(sistema=SistemaDeCuenta.RED, estado_de_cuenta=E.SUSPENDIDA)
        ).filas
    ] == ["col-9"]


def test_los_filtros_de_pagina_son_validos() -> None:
    for malo in (dict(pagina=0), dict(tamano=0), dict(tamano=101)):
        with pytest.raises(DatoInvalido):
            FiltroDeCuentas(**malo)  # type: ignore[arg-type]  # valores invalidos a proposito
    assert FiltroDeCuentas(tamano=100).tamano == 100


def test_la_busqueda_y_la_ficha_son_solo_para_tecnicos() -> None:
    m, _ = semilla()
    for usuario in ("u-rrhh", "u-admin", "u-aud", "u-col"):
        with pytest.raises(NoAutorizado):
            m.buscar(usuario, FiltroDeCuentas())
        with pytest.raises(NoAutorizado):
            m.ficha(usuario, "col-1")


# --- RF-33: ficha -----------------------------------------------------------------------------


def test_RF_33_la_ficha_muestra_datos_cuentas_equipos_licencias_historial() -> None:
    m, ids = semilla()
    with m.repos.unidad_de_trabajo() as u:
        u.activos.reemplazar(
            "col-1",
            [ActivoAsignado("A1", "Portátil", "SN-1", "ThinkPad", HOY, True)],
            [LicenciaAsignada("L1", "Suite ofimática", "K-1")],
        )
    f = m.ficha("u-tec-lic", "col-1")
    assert (f.nombre_completo, f.documento, f.departamento, f.sede) == (
        "María José Gómez Ramírez",
        "10203040",
        "Finanzas",
        "Bogotá",
    )
    assert (f.cargo, f.jefe_id, f.usuario, f.estado) == (
        "Analista",
        "jefe-1",
        "maria.gomez",
        EstadoColaborador.ACTIVO,
    )
    assert [(c.sistema, c.estado) for c in f.cuentas] == [
        (SistemaDeCuenta.AD, E.PENDIENTE_BAJA),
        (SistemaDeCuenta.RED, E.PENDIENTE_BAJA),
        (SistemaDeCuenta.M365, E.PENDIENTE_BAJA),
    ]
    assert all(c.ticket_origen.startswith(ids["ret"].valor) for c in f.cuentas)  # ticket de origen
    assert [(e.serie, e.modelo, e.tiene_acta) for e in f.equipos] == [("SN-1", "ThinkPad", True)]
    assert [lic.software for lic in f.licencias] == ["Suite ofimática"]
    assert [(s.id, s.tipo) for s in f.solicitudes] == [(ids["ret"], TipoEvento.RET)]
    assert len(f.tickets) == 6
    assert all(t.id_externo is not None for t in f.tickets)  # enlace a GLPI
    assert {t.solicitud_id for t in f.tickets} == {ids["ret"]}


def test_RF_33_la_ficha_de_alguien_inexistente() -> None:
    m, _ = semilla()
    with pytest.raises(NoEncontrado):
        m.ficha("u-tec-ad", "no-existe")


def test_RF_35_T10_cada_consulta_de_ficha_queda_auditada() -> None:
    m, _ = semilla()
    antes = m.acciones_de_auditoria().count("ficha.consultada")
    m.ficha("u-tec-ad", "col-1")
    m.ficha("u-tec-com", "col-9")
    registros = [r for r in m.repos.auditoria().registros() if r.accion == "ficha.consultada"]
    assert len(registros) == antes + 2
    assert [(r.actor, r.objeto) for r in registros[-2:]] == [
        ("u-tec-ad", "col-1"),
        ("u-tec-com", "col-9"),
    ]
    assert m.repos.auditoria().verificar().valida


def test_CA_16_CA_10_ni_el_dashboard_ni_la_busqueda_ni_la_ficha_contienen_el_motivo() -> None:
    m, ids = semilla()
    assert m.solicitud(ids["ret"]).restringido is not None  # el centinela SI esta guardado
    assert m.solicitud(ids["emg"]).restringido is not None
    salidas = [
        repr(m.dashboard("u-tec-ad")),
        repr(m.buscar("u-tec-ad", FiltroDeCuentas())),
        repr(m.ficha("u-tec-ad", "col-1")),
        repr(m.ficha("u-tec-ad", "jefe-1")),
        json.dumps(dataclasses.asdict(m.dashboard("u-tec-ad")), default=str),
        json.dumps(dataclasses.asdict(m.ficha("u-tec-ad", "col-1")), default=str),
    ]
    assert all(SENTINELA not in s for s in salidas)
    assert all("motivo" not in s.lower() and "descripcion" not in s.lower() for s in salidas)
    assert Subtipo.FUGA_DETECTADA.value not in "".join(
        salidas
    )  # ni siquiera el subtipo de la emergencia
