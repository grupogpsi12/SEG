"""Sincronizacion, cierre y cuentas derivadas con dobles (RF-22 a RF-27, CA-05, CA-08, S-07, S-09, S-20)."""

from dataclasses import replace
from datetime import timedelta

import pytest

from jml.aplicacion.dtos import SolicitudRegistrada
from jml.dominio.activos import ActivoAsignado, LicenciaAsignada
from jml.dominio.cuentas import Cuenta
from jml.dominio.tipos import (
    EstadoColaborador,
    EstadoDeCuenta,
    EstadoDeTicket,
    EstadoSolicitud,
    MarcaDeCuenta,
    SistemaDeCuenta,
    Subtipo,
)
from jml.dominio.valores import SolicitudId
from tests.dobles.glpi import Fallo
from tests.fabricas import HOY
from tests.mundo import (
    Mundo,
    cambio_de_departamento,
    cambio_de_sucursal,
    emergencia,
    ingreso,
    retiro,
    vacaciones,
)

S, E, ET = EstadoSolicitud, EstadoDeCuenta, EstadoDeTicket
AD, RED, M365 = SistemaDeCuenta.AD, SistemaDeCuenta.RED, SistemaDeCuenta.M365


def cuenta(m: Mundo, colaborador: str, sistema: SistemaDeCuenta) -> Cuenta | None:
    with m.repos.unidad_de_trabajo() as u:
        return u.cuentas.obtener(colaborador, sistema)


def cuenta_ok(m: Mundo, colaborador: str, sistema: SistemaDeCuenta) -> Cuenta:
    c = cuenta(m, colaborador, sistema)
    assert c is not None
    return c


def estados_de_cuentas(m: Mundo, colaborador: str) -> dict[SistemaDeCuenta, EstadoDeCuenta | None]:
    return {s: (c.estado if (c := cuenta(m, colaborador, s)) else None) for s in SistemaDeCuenta}


def gid_de(m: Mundo, sid: SolicitudId, cola: str) -> str:
    with m.repos.unidad_de_trabajo() as u:
        t = next(
            t
            for t in u.tickets.de_solicitud(sid)
            if t.ticket.cola.value == cola and t.ticket.clase.value == "cierre_inmediato"
        )
    assert t.id_externo is not None
    return t.id_externo


def ing_creado(m: Mundo) -> SolicitudRegistrada:
    r = m.emitir(ingreso())
    m.correr_bandeja_hasta_vaciar()
    return r


# --- flujo ING completo (CA-05) ---------------------------------------------------------------


def test_CA_05_ingreso_completo_hasta_cerrada_con_cuentas_activas_y_colaborador_activo() -> None:
    m = Mundo.nuevo()
    r = ing_creado(m)
    assert m.solicitud(r.solicitud_id).estado is S.EN_EJECUCION
    # mientras estan abiertos: pendiente_alta en los tres sistemas
    res = m.sincronizar()
    assert (res.resultado, res.tickets_leidos, res.errores) == ("ok", 4, 0)
    assert estados_de_cuentas(m, r.colaborador_id) == {
        AD: E.PENDIENTE_ALTA,
        RED: E.PENDIENTE_ALTA,
        M365: E.PENDIENTE_ALTA,
    }
    assert m.colaborador(r.colaborador_id).estado is EstadoColaborador.POR_INGRESAR
    # los tecnicos resuelven con solucion y acta
    m.tecnico_resuelve_todo(r.solicitud_id)
    m.avanzar(timedelta(minutes=5))
    m.sincronizar()
    assert estados_de_cuentas(m, r.colaborador_id) == {AD: E.ACTIVA, RED: E.ACTIVA, M365: E.ACTIVA}
    assert m.solicitud(r.solicitud_id).estado is S.CERRADA
    assert m.colaborador(r.colaborador_id).estado is EstadoColaborador.ACTIVO  # S-07
    with m.repos.unidad_de_trabajo() as u:
        historial = u.cuentas.historial(r.colaborador_id)
    assert len(historial) == 6  # pendiente_alta y activa por cada sistema
    assert {h.sistema for h in historial} == set(SistemaDeCuenta)
    assert "solicitud.cerrada" in m.acciones_de_auditoria()
    assert m.repos.auditoria().verificar().valida


def test_la_sincronizacion_es_idempotente_y_no_escribe_ruido() -> None:
    m = Mundo.nuevo()
    r = ing_creado(m)
    m.sincronizar()
    antes = m.repos.almacen.instantanea()
    m.avanzar(timedelta(minutes=5))
    m.sincronizar()
    despues = m.repos.almacen.instantanea()
    # lo unico que cambia es el registro de que se sincronizo (hora de actualizacion)
    assert replace(despues, sincronizaciones=[]) == replace(antes, sincronizaciones=[])
    assert len(despues.sincronizaciones) == 2
    assert estados_de_cuentas(m, r.colaborador_id)[AD] is E.PENDIENTE_ALTA


def test_CA_08_un_ticket_resuelto_sin_solucion_no_cierra_ni_cambia_la_cuenta() -> None:
    m = Mundo.nuevo()
    r = ing_creado(m)
    m.sincronizar()
    for cola in ("AD", "COMUNICACIONES", "LICENCIAS"):
        m.glpi.resolver(gid_de(m, r.solicitud_id, cola), con_solucion=(cola != "AD"))
    m.glpi.resolver(gid_de(m, r.solicitud_id, "INVENTARIO"), con_solucion=True, documentos=1)
    m.avanzar(timedelta(minutes=5))
    m.sincronizar()
    assert m.solicitud(r.solicitud_id).estado is S.EN_EJECUCION  # AD sin solucion bloquea el cierre
    ad = cuenta_ok(m, r.colaborador_id, AD)
    assert (ad.estado, ad.marca) == (E.PENDIENTE_ALTA, MarcaDeCuenta.CIERRE_SIN_SOLUCION)
    assert cuenta_ok(m, r.colaborador_id, RED).estado is E.ACTIVA
    assert "ticket.cierre_incompleto" in m.acciones_de_auditoria()
    ind = m.dashboard("u-tec-ad")
    assert [(f.cola.value, f.motivo) for f in ind.incompletos] == [("AD", "cierre_incompleto")]
    # el tecnico corrige y registra la solucion: ahora si cierra
    m.glpi.resolver(gid_de(m, r.solicitud_id, "AD"), con_solucion=True)
    m.avanzar(timedelta(minutes=5))
    m.sincronizar()
    assert m.solicitud(r.solicitud_id).estado is S.CERRADA
    assert cuenta_ok(m, r.colaborador_id, AD).estado is E.ACTIVA
    assert cuenta_ok(m, r.colaborador_id, AD).marca is None


def test_CA_08_inventario_sin_acta_no_cierra_la_solicitud() -> None:
    m = Mundo.nuevo()
    r = ing_creado(m)
    m.tecnico_resuelve_todo(r.solicitud_id, con_acta=False)
    m.sincronizar()
    assert m.solicitud(r.solicitud_id).estado is S.EN_EJECUCION
    assert [f.cola.value for f in m.dashboard("u-tec-inv").incompletos] == ["INVENTARIO"]
    m.glpi.adjuntar(gid_de(m, r.solicitud_id, "INVENTARIO"))
    m.avanzar(timedelta(minutes=5))
    m.sincronizar()
    assert m.solicitud(r.solicitud_id).estado is S.CERRADA
    assert m.dashboard("u-tec-inv").incompletos == ()


def test_RF_25_un_ticket_reabierto_se_refleja_pero_la_solicitud_sigue_cerrada() -> None:
    m = Mundo.nuevo()
    r = ing_creado(m)
    m.tecnico_resuelve_todo(r.solicitud_id)
    m.sincronizar()
    assert m.solicitud(r.solicitud_id).estado is S.CERRADA
    m.glpi.reabrir(gid_de(m, r.solicitud_id, "LICENCIAS"))
    m.avanzar(timedelta(minutes=5))
    m.sincronizar()
    assert m.solicitud(r.solicitud_id).estado is S.CERRADA  # SRS 4.2: no se reabre la solicitud
    c = cuenta_ok(m, r.colaborador_id, M365)
    assert (c.estado, c.marca) == (E.PENDIENTE_ALTA, MarcaDeCuenta.REABIERTO)
    assert cuenta_ok(m, r.colaborador_id, AD).estado is E.ACTIVA
    assert "ticket.reabierto" in m.acciones_de_auditoria()
    assert [(f.cola.value, f.motivo) for f in m.dashboard("u-tec-lic").incompletos] == [
        ("LICENCIAS", "reabierto")
    ]
    assert m.colaborador(r.colaborador_id).estado is EstadoColaborador.ACTIVO  # no retrocede


def test_glpi_caido_registra_la_sincronizacion_fallida_sin_tocar_nada() -> None:
    m = Mundo.nuevo()
    ing_creado(m)
    m.sincronizar()
    m.glpi.caer()
    antes = m.repos.almacen.instantanea()
    res = m.sincronizar()
    assert (res.resultado, res.tickets_leidos, res.errores) == ("error", 0, 1)
    assert replace(m.repos.almacen.instantanea(), sincronizaciones=[]) == replace(
        antes, sincronizaciones=[]
    )
    assert m.repos.almacen.sincronizaciones[-1] == res
    assert m.dashboard("u-tec-ad").ultima_sincronizacion == res


def test_ticket_que_glpi_no_devuelve_se_deja_como_estaba() -> None:
    m = Mundo.nuevo()
    r = ing_creado(m)
    m.glpi._remotos.clear()
    res = m.sincronizar()
    assert res.tickets_leidos == 0
    assert m.solicitud(r.solicitud_id).estado is S.EN_EJECUCION


# --- VAC: suspension y reactivacion programada ------------------------------------------------


def test_S_09_vacaciones_de_alguien_sin_cuentas_registradas_se_ignoran_y_se_auditan() -> None:
    m = Mundo.nuevo()
    m.emitir(replace(vacaciones("u-rrhh"), justificacion="ok"))
    m.correr_bandeja_hasta_vaciar()
    m.sincronizar()
    assert estados_de_cuentas(m, "col-1") == {AD: None, RED: None, M365: None}
    # una vez por ticket observado (suspension y reactivacion en AD y Licencias), sin repetirse
    assert m.acciones_de_auditoria().count("cuenta.inexistente") == 4
    m.avanzar(timedelta(minutes=5))
    m.sincronizar()
    assert m.acciones_de_auditoria().count("cuenta.inexistente") == 4


def test_vacaciones_suspenden_y_reactivan_en_su_fecha() -> None:
    m = Mundo.nuevo()
    _sembrar_cuentas_activas(m, "col-1")
    r = m.emitir(replace(vacaciones("u-rrhh"), justificacion="ok"))
    m.correr_bandeja_hasta_vaciar()
    m.sincronizar()
    assert estados_de_cuentas(m, "col-1") == {
        AD: E.PENDIENTE_SUSPENSION,
        RED: E.ACTIVA,
        M365: E.PENDIENTE_SUSPENSION,
    }
    # el tecnico suspende
    m.glpi.resolver(gid_de(m, r.solicitud_id, "AD"))
    m.glpi.resolver(gid_de(m, r.solicitud_id, "LICENCIAS"))
    m.avanzar(timedelta(minutes=5))
    m.sincronizar()
    assert estados_de_cuentas(m, "col-1") == {AD: E.SUSPENDIDA, RED: E.ACTIVA, M365: E.SUSPENDIDA}
    assert m.colaborador("col-1").estado is EstadoColaborador.SUSPENDIDO  # S-07
    assert m.solicitud(r.solicitud_id).estado is S.EN_EJECUCION  # falta la reactivacion
    # llega el dia de regreso y el tecnico reactiva
    m.reloj.fijar(m.reloj.ahora() + timedelta(days=22))
    for cola in ("AD", "LICENCIAS"):
        with m.repos.unidad_de_trabajo() as u:
            t = next(
                t for t in u.tickets.de_solicitud(r.solicitud_id)
                if t.ticket.cola.value == cola and t.ticket.clase.value == "cierre_programado"
            )  # fmt: skip
        assert t.id_externo is not None
        m.glpi.resolver(t.id_externo)
    m.sincronizar()
    assert estados_de_cuentas(m, "col-1") == {AD: E.ACTIVA, RED: E.ACTIVA, M365: E.ACTIVA}
    assert m.colaborador("col-1").estado is EstadoColaborador.ACTIVO
    assert m.solicitud(r.solicitud_id).estado is S.CERRADA


def _sembrar_cuentas_activas(m: Mundo, colaborador: str) -> None:
    """Cuentas que ya existian al arrancar el sistema (las crea la semilla de la Fase 2)."""
    from jml.dominio.cuentas import Cuenta

    with m.repos.unidad_de_trabajo() as u:
        for sistema in SistemaDeCuenta:
            u.cuentas.guardar(
                Cuenta(
                    colaborador,
                    sistema,
                    E.ACTIVA,
                    "semilla",
                    (m.reloj.ahora() - timedelta(days=900),) * 2,
                    m.reloj.ahora(),
                )
            )


# --- RET / EMG: baja, posterior y exposicion ---------------------------------------------------


def test_retiro_cierra_con_las_bajas_y_el_posterior_no_bloquea_RF_26() -> None:
    m = Mundo.nuevo()
    _sembrar_cuentas_activas(m, "col-1")
    r = m.emitir(retiro())
    m.correr_bandeja_hasta_vaciar()
    m.sincronizar()
    assert estados_de_cuentas(m, "col-1") == {
        AD: E.PENDIENTE_BAJA,
        RED: E.PENDIENTE_BAJA,
        M365: E.PENDIENTE_BAJA,
    }
    # solo los tickets de cierre (baja + equipo) se resuelven; los posteriores siguen En espera
    with m.repos.unidad_de_trabajo() as u:
        tickets = list(u.tickets.de_solicitud(r.solicitud_id))
    for t in tickets:
        if t.ticket.clase.value == "cierre_inmediato" and t.id_externo:
            m.glpi.resolver(
                t.id_externo, documentos=1 if t.ticket.cola.value == "INVENTARIO" else 0
            )
    m.avanzar(timedelta(minutes=5))
    m.sincronizar()
    assert m.solicitud(r.solicitud_id).estado is S.CERRADA  # los posteriores no bloquean
    assert estados_de_cuentas(m, "col-1") == {
        AD: E.DESHABILITADA,
        RED: E.DESHABILITADA,
        M365: E.DESHABILITADA,
    }
    assert m.colaborador("col-1").estado is EstadoColaborador.RETIRADO  # S-07
    # 90 dias despues el tecnico elimina
    m.reloj.fijar(m.reloj.ahora() + timedelta(days=120))
    for t in tickets:
        if t.ticket.clase.value == "posterior" and t.id_externo:
            m.glpi.resolver(t.id_externo)
    m.sincronizar()
    assert estados_de_cuentas(m, "col-1") == {
        AD: E.ELIMINADA,
        RED: E.DESHABILITADA,
        M365: E.ELIMINADA,
    }


def test_el_posterior_resuelto_sin_cuenta_se_ignora_y_se_audita_S_09() -> None:
    m = Mundo.nuevo()  # col-1 no tiene cuentas registradas
    r = m.emitir(retiro())
    m.correr_bandeja_hasta_vaciar()
    m.reloj.fijar(m.reloj.ahora() + timedelta(days=120))
    with m.repos.unidad_de_trabajo() as u:
        posteriores = [
            t for t in u.tickets.de_solicitud(r.solicitud_id) if t.ticket.clase.value == "posterior"
        ]
    for t in posteriores:
        assert t.id_externo is not None
        m.glpi.resolver(t.id_externo)
    m.sincronizar()
    assert estados_de_cuentas(m, "col-1") == {AD: None, RED: None, M365: None}
    assert m.acciones_de_auditoria().count("cuenta.inexistente") == 5  # 3 bajas + 2 posteriores
    m.sincronizar()  # no repite el aviso
    assert m.acciones_de_auditoria().count("cuenta.inexistente") == 5


def test_CA_06_la_emergencia_expone_horas_hasta_que_se_resuelven_las_bajas() -> None:
    m = Mundo.nuevo()
    _sembrar_cuentas_activas(m, "col-1")
    r = m.emitir(emergencia())
    m.correr_bandeja_hasta_vaciar()
    m.sincronizar()
    m.avanzar(timedelta(hours=3, minutes=30))
    m.sincronizar()
    (fila,) = m.dashboard("u-tec-ad").exposicion
    assert (fila.solicitud_id, fila.horas_de_exposicion, fila.tickets_de_baja_abiertos) == (
        r.solicitud_id,
        3,
        3,
    )
    # una baja resuelta reduce los abiertos; al resolver las tres, desaparece del indicador
    with m.repos.unidad_de_trabajo() as u:
        bajas = [
            t for t in u.tickets.de_solicitud(r.solicitud_id) if t.ticket.accion.value == "baja"
        ]
    for t in bajas:
        assert t.id_externo is not None
        m.glpi.resolver(t.id_externo)
    m.sincronizar()
    assert m.dashboard("u-tec-ad").exposicion == ()
    vencidos = m.dashboard("u-tec-ad").vencidos
    assert [(f.cola.value, f.cantidad) for f in vencidos] == [
        ("INVENTARIO", 1)
    ]  # el equipo sigue pendiente


# --- CDP / CSU: el cierre actualiza los datos laborales (S-20) ---------------------------------


def test_S_20_el_cdp_cerrado_actualiza_departamento_cargo_y_jefe() -> None:
    m = Mundo.nuevo()
    _sembrar_cuentas_activas(m, "col-1")
    a = m.registrar(cambio_de_departamento(destino="TI"))
    m.aprobar("u-rrhh", a.solicitud_id)
    m.correr_bandeja_hasta_vaciar()
    m.sincronizar()
    assert estados_de_cuentas(m, "col-1") == {AD: E.ACTIVA, RED: E.ACTIVA, M365: E.ACTIVA}
    assert cuenta_ok(m, "col-1", AD).marca is MarcaDeCuenta.CAMBIO_PENDIENTE
    assert m.colaborador("col-1").departamento == "Finanzas"
    m.tecnico_resuelve_todo(a.solicitud_id)
    m.avanzar(timedelta(minutes=5))
    m.sincronizar()
    assert m.solicitud(a.solicitud_id).estado is S.CERRADA
    c = m.colaborador("col-1")
    assert (c.departamento, c.cargo, c.jefe_id) == ("TI", "Desarrollador", "jefe-1")
    assert cuenta_ok(m, "col-1", AD).marca is None


def test_S_20_el_csu_cerrado_actualiza_la_sede() -> None:
    m = Mundo.nuevo()
    a = m.registrar(cambio_de_sucursal(sede="Medellín", traslada=True))
    m.aprobar("u-rrhh", a.solicitud_id)
    m.correr_bandeja_hasta_vaciar()
    m.tecnico_resuelve_todo(a.solicitud_id)
    m.sincronizar()
    assert m.solicitud(a.solicitud_id).estado is S.CERRADA
    assert m.colaborador("col-1").sede == "Medellín"


# --- RF-23: activos y licencias ---------------------------------------------------------------


def test_RF_23_se_sincronizan_activos_y_licencias_de_los_colaboradores_con_usuario_glpi() -> None:
    m = Mundo.nuevo()
    emitir_y_crear = m.emitir(replace(vacaciones("u-rrhh"), justificacion="ok"))
    m.correr_bandeja_hasta_vaciar()  # asegura el usuario de GLPI de col-1
    activo = ActivoAsignado("A-1", "Portátil", "SN-100", "ThinkPad", HOY - timedelta(days=40), True)
    lic = LicenciaAsignada("L-1", "Suite ofimática", "K-001")
    m.glpi.asignar_activo("u-col-1", activo)
    m.glpi.asignar_licencia("u-col-1", lic)
    res = m.sincronizar_activos()
    assert (res.resultado, res.tickets_leidos, res.errores) == ("ok", 1, 0)
    with m.repos.unidad_de_trabajo() as u:
        assert list(u.activos.activos_de("col-1")) == [activo]
        assert list(u.activos.licencias_de("col-1")) == [lic]
    # lo que GLPI quita, se quita (copia reemplazada)
    m.glpi._activos.clear()
    m.sincronizar_activos()
    with m.repos.unidad_de_trabajo() as u:
        assert list(u.activos.activos_de("col-1")) == []
    assert emitir_y_crear.estado is S.APROBADA


def test_activos_con_glpi_caido_cuenta_el_error() -> None:
    m = Mundo.nuevo()
    m.emitir(replace(vacaciones("u-rrhh"), justificacion="ok"))
    m.correr_bandeja_hasta_vaciar()
    m.glpi.caer()
    res = m.sincronizar_activos()
    assert (res.resultado, res.errores) == ("error", 1)


def test_sin_usuarios_de_glpi_no_hay_nada_que_sincronizar() -> None:
    m = Mundo.nuevo()
    res = m.sincronizar_activos()
    assert (res.resultado, res.tickets_leidos, res.errores) == ("ok", 0, 0)


# --- RF-28: contratos por vencer -------------------------------------------------------------


def test_RF_28_contratos_por_vencer_en_7_dias_sin_retiro_abierto() -> None:
    m = Mundo.nuevo()
    with m.repos.unidad_de_trabajo() as u:
        base = m.colaborador("col-9")
        u.colaboradores.guardar(replace(base, fecha_fin=HOY + timedelta(days=3)))
        u.colaboradores.guardar(replace(m.colaborador("jefe-1"), fecha_fin=HOY + timedelta(days=7)))
        u.colaboradores.guardar(
            replace(m.colaborador("col-rrhh"), fecha_fin=HOY + timedelta(days=8))
        )  # fuera
        u.colaboradores.guardar(
            replace(m.colaborador("col-1"), fecha_fin=HOY - timedelta(days=1))
        )  # ya vencio
    filas = m.contratos_por_vencer("u-rrhh")
    assert [(f.colaborador_id, f.dias_restantes) for f in filas] == [("col-9", 3), ("jefe-1", 7)]
    # al emitir el retiro por fin de contrato, deja de aparecer
    m.emitir(retiro(colaborador="col-9", subtipo=Subtipo.FIN_DE_CONTRATO, dias=3))
    assert [f.colaborador_id for f in m.contratos_por_vencer("u-rrhh")] == ["jefe-1"]


def test_RF_28_solo_rrhh_ve_los_contratos() -> None:
    from jml.dominio.errores import NoAutorizado

    m = Mundo.nuevo()
    for u in ("u-tec-ad", "u-col", "u-admin"):
        with pytest.raises(NoAutorizado):
            m.contratos_por_vencer(u)


def test_los_fallos_programados_no_afectan_la_derivacion() -> None:
    m = Mundo.nuevo()
    r = m.emitir(ingreso())
    m.glpi.programar(Fallo.DESPUES, Fallo.ANTES)
    m.correr_bandeja_hasta_vaciar()
    m.tecnico_resuelve_todo(r.solicitud_id)
    m.sincronizar()
    assert m.solicitud(r.solicitud_id).estado is S.CERRADA
