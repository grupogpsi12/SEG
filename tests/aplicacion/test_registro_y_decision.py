"""Item 1.10: registrar, emitir, aprobar, rechazar y cancelar (RF-07 a RF-15, RF-39, CA-01, CA-02)."""

from dataclasses import replace

import pytest

from jml.aplicacion.bandeja import EstadoDeEntrada
from jml.aplicacion.dtos import ArchivoRecibido
from jml.dominio.errores import (
    AutoAprobacionProhibida,
    CancelacionNoPermitida,
    DatoInvalido,
    DocumentoDuplicado,
    ErrorDeDominio,
    JustificacionRequerida,
    NoAutorizado,
    NoEncontrado,
    SolicitudDuplicada,
    SoporteInvalido,
    TransicionInvalida,
)
from jml.dominio.permisos import UsuarioDelSistema
from jml.dominio.tipos import (
    ESTADOS_ABIERTOS,
    ESTADOS_FINALES,
    EstadoColaborador,
    EstadoDeSoporte,
    EstadoSolicitud,
    Rol,
    Subtipo,
    TipoDeVinculacion,
    TipoEvento,
)
from jml.dominio.valores import MAX_SOPORTE_BYTES, SolicitudId
from tests.dobles.memoria import FalloInyectado
from tests.mundo import (
    PDF_VALIDO,
    Mundo,
    cambio_de_departamento,
    cambio_de_sucursal,
    emergencia,
    ingreso,
    retiro,
    vacaciones,
)

S = EstadoSolicitud


# --- registrar (RF-07, RF-09) ---------------------------------------------------------------


def test_el_colaborador_registra_sus_vacaciones_y_quedan_pendientes_RF_07() -> None:
    m = Mundo.nuevo()
    r = m.registrar(vacaciones())
    assert r.estado is S.PENDIENTE_APROBACION
    assert r.tickets_encolados == 0
    assert r.solicitud_id.valor == "SOL-2026-000001"
    assert m.acciones_de_auditoria() == ["solicitud.registrada"]
    with m.repos.unidad_de_trabajo() as u:
        assert u.bandeja.de_solicitud(r.solicitud_id) == []  # nada se crea sin una decision (CA-02)
        assert u.decisiones.de_solicitud(r.solicitud_id) == []


def test_un_tercero_no_registra_por_otro_y_no_queda_rastro() -> None:
    m = Mundo.nuevo()
    antes = m.repos.almacen.instantanea()
    with pytest.raises(NoAutorizado):
        m.registrar(vacaciones(usuario="u-otro"))
    assert m.repos.almacen.instantanea() == antes  # tampoco gasta un consecutivo


def test_el_jefe_registra_un_cambio_de_departamento_de_su_subordinado() -> None:
    m = Mundo.nuevo()
    assert m.registrar(cambio_de_departamento()).estado is S.PENDIENTE_APROBACION
    with pytest.raises(NoAutorizado):
        m.registrar(cambio_de_sucursal(usuario="u-col"))  # el propio empleado no pide su traslado


def test_usuario_inexistente_o_inactivo_no_registra() -> None:
    m = Mundo.nuevo()
    with pytest.raises(NoAutorizado):
        m.registrar(vacaciones(usuario="fantasma"))
    with m.repos.unidad_de_trabajo() as u:
        u.usuarios.guardar(
            UsuarioDelSistema("u-col", "col-1", frozenset({Rol.SOLICITANTE}), activo=False)
        )
    with pytest.raises(NoAutorizado):
        m.registrar(vacaciones())


def test_colaborador_inexistente() -> None:
    m = Mundo.nuevo()
    with pytest.raises(NoEncontrado):
        m.registrar(vacaciones(colaborador="no-existe"))


def test_falta_el_colaborador_en_un_evento_que_no_es_ingreso() -> None:
    m = Mundo.nuevo()
    with pytest.raises(DatoInvalido, match="colaborador_id"):
        m.registrar(replace(vacaciones(), colaborador_id=None))


def test_un_soporte_solo_aplica_al_ingreso() -> None:
    m = Mundo.nuevo()
    with pytest.raises(DatoInvalido, match="soporte"):
        m.registrar(replace(vacaciones(), soporte=ArchivoRecibido("a.pdf", PDF_VALIDO)))


def test_RF_09_el_duplicado_abierto_se_rechaza_con_la_referencia_a_la_existente() -> None:
    m = Mundo.nuevo()
    primera = m.registrar(vacaciones())
    antes = m.repos.almacen.instantanea()
    with pytest.raises(SolicitudDuplicada) as e:
        m.registrar(vacaciones())
    assert e.value.existente_id == primera.solicitud_id.valor
    assert m.repos.almacen.instantanea() == antes


@pytest.mark.parametrize("estado", sorted(ESTADOS_ABIERTOS))
def test_CA_01_cualquier_estado_abierto_bloquea_el_duplicado(estado: EstadoSolicitud) -> None:
    """lessons n.1: duplicar estando en `en_ejecucion` o `error` DEBE fallar."""
    m = Mundo.nuevo()
    primera = m.registrar(vacaciones())
    with m.repos.unidad_de_trabajo() as u:
        s = u.solicitudes.obtener(primera.solicitud_id)
        assert s is not None
        u.solicitudes.guardar(replace(s, estado=estado))
    with pytest.raises(SolicitudDuplicada):
        m.registrar(vacaciones())


@pytest.mark.parametrize("estado", sorted(ESTADOS_FINALES))
def test_CA_01_al_cerrarse_la_primera_se_puede_registrar_otra(estado: EstadoSolicitud) -> None:
    m = Mundo.nuevo()
    primera = m.registrar(vacaciones())
    with m.repos.unidad_de_trabajo() as u:
        s = u.solicitudes.obtener(primera.solicitud_id)
        assert s is not None
        u.solicitudes.guardar(replace(s, estado=estado))
    segunda = m.registrar(vacaciones())
    assert segunda.solicitud_id.valor == "SOL-2026-000002"


def test_los_errores_de_validacion_no_dejan_rastro() -> None:
    m = Mundo.nuevo()
    antes = m.repos.almacen.instantanea()
    with pytest.raises(ErrorDeDominio):
        m.registrar(vacaciones(dias=-3))  # fecha efectiva en el pasado
    assert m.repos.almacen.instantanea() == antes


# --- ingreso y soporte de vinculacion (RF-39, CA-18) -------------------------------------------


def test_RRHH_emite_un_ingreso_con_soporte_valido() -> None:
    m = Mundo.nuevo()
    r = m.emitir(ingreso())
    assert r.estado is S.APROBADA
    assert r.tickets_encolados == 4
    c = m.colaborador(r.colaborador_id)
    assert c.estado is EstadoColaborador.POR_INGRESAR  # S-06
    assert c.usuario is not None
    assert c.usuario.valor == "camila.torres"
    with m.repos.unidad_de_trabajo() as u:
        soporte = u.soportes.obtener(r.solicitud_id)
        assert soporte is not None
        assert soporte.estado is EstadoDeSoporte.PENDIENTE
        assert m.soportes.existe(soporte.nombre_almacenado)
        assert soporte.nombre_almacenado != "acta_de_inicio.pdf"
        assert len(u.bandeja.de_solicitud(r.solicitud_id)) == 4
        assert len(u.tickets.de_solicitud(r.solicitud_id)) == 4
        decisiones = u.decisiones.de_solicitud(r.solicitud_id)
        assert [d.tipo.value for d in decisiones] == ["emitir"]
    assert m.repos.auditoria().verificar().valida


def test_CA_18_un_ingreso_sin_soporte_se_rechaza_sin_rastro() -> None:
    m = Mundo.nuevo()
    antes = m.repos.almacen.instantanea()
    with pytest.raises(SoporteInvalido):
        m.emitir(ingreso(soporte=None))
    assert m.repos.almacen.instantanea() == antes
    assert m.soportes.nombres() == []


@pytest.mark.parametrize(
    "archivo",
    [
        ArchivoRecibido("acta.pdf", b"MZ\x90\x00 ejecutable renombrado" + b"x" * 40),
        ArchivoRecibido("acta.exe", PDF_VALIDO),
        ArchivoRecibido("acta.pdf", b""),
        ArchivoRecibido("acta.pdf", b"%PDF-" + b"0" * MAX_SOPORTE_BYTES),  # 1 byte de mas
    ],
)
def test_CA_18_soportes_invalidos_se_rechazan_y_no_se_guardan(archivo: ArchivoRecibido) -> None:
    m = Mundo.nuevo()
    antes = m.repos.almacen.instantanea()
    with pytest.raises(SoporteInvalido):
        m.emitir(ingreso(soporte=archivo))
    assert m.repos.almacen.instantanea() == antes
    assert m.soportes.nombres() == []


def test_S_12_veinte_MiB_exactos_se_aceptan() -> None:
    m = Mundo.nuevo()
    exacto = ArchivoRecibido("acta.pdf", b"%PDF-" + b"0" * (MAX_SOPORTE_BYTES - 5))
    assert m.emitir(ingreso(soporte=exacto)).estado is S.APROBADA


def test_si_la_transaccion_falla_no_queda_la_copia_del_soporte_RD_12() -> None:
    m = Mundo.nuevo()
    m.repos.control.fallar_en_la_llamada(1)
    with pytest.raises(FalloInyectado):
        m.emitir(ingreso())
    assert m.soportes.nombres() == []


def test_solo_RRHH_emite_un_ingreso() -> None:
    m = Mundo.nuevo()
    for usuario in ("u-col", "u-jefe", "u-admin"):
        with pytest.raises(NoAutorizado):
            m.emitir(ingreso(usuario=usuario))


def test_RD_09_un_documento_existente_se_rechaza_con_referencia() -> None:
    m = Mundo.nuevo()
    with pytest.raises(DocumentoDuplicado) as e:
        m.emitir(ingreso(documento="10203040"))  # el de María, activa
    assert e.value.existente_id == "col-1"


def test_RD_09_dos_ingresos_del_mismo_documento_en_curso_se_rechazan() -> None:
    m = Mundo.nuevo()
    primero = m.emitir(ingreso())
    with pytest.raises(DocumentoDuplicado) as e:
        m.emitir(ingreso())
    assert e.value.existente_id == primero.colaborador_id


def test_S_26_tras_cancelar_se_puede_registrar_de_nuevo_el_mismo_documento() -> None:
    """RD-12: «RRHH vuelve a registrar el ingreso» sin chocar con el documento unico."""
    m = Mundo.nuevo()
    primero = m.emitir(ingreso())
    m.cancelar("u-rrhh", primero.solicitud_id, "se corrige el cargo")
    segundo = m.emitir(ingreso(apellidos="Torres Vega"))
    assert segundo.colaborador_id == primero.colaborador_id  # reutiliza el registro por_ingresar
    assert segundo.solicitud_id != primero.solicitud_id
    assert m.colaborador(segundo.colaborador_id).usuario is not None


def test_S_26_un_retirado_permite_un_reingreso_nuevo() -> None:
    m = Mundo.nuevo()
    with m.repos.unidad_de_trabajo() as u:
        viejo = m.colaborador("col-9")
        u.colaboradores.guardar(replace(viejo, estado=EstadoColaborador.RETIRADO))
    r = m.emitir(ingreso(documento="70000009", nombres="Otto", apellidos="Nieto"))
    assert r.colaborador_id != "col-9"
    assert m.colaborador(r.colaborador_id).usuario is not None
    assert m.colaborador(r.colaborador_id).usuario != m.colaborador("col-9").usuario


def test_el_usuario_sugerido_es_unico_entre_ingresos_S_23() -> None:
    m = Mundo.nuevo()
    a = m.emitir(ingreso(documento="80000001", nombres="Camila", apellidos="Torres Vega"))
    b = m.emitir(ingreso(documento="80000002", nombres="Camila", apellidos="Torres Rojas"))
    c = m.emitir(ingreso(documento="80000003", nombres="Camila", apellidos="Torres Vera"))
    usuarios = [m.colaborador(x.colaborador_id).usuario for x in (a, b, c)]
    assert [u.valor for u in usuarios if u] == [
        "camila.torres",
        "camila.torres.r",
        "camila.torres.v",
    ]


def test_ingreso_de_contratista_lleva_su_fecha_de_expiracion() -> None:
    m = Mundo.nuevo()
    r = m.emitir(ingreso(vinculacion=TipoDeVinculacion.CONTRATISTA))
    with m.repos.unidad_de_trabajo() as u:
        ad = next(t for t in u.tickets.de_solicitud(r.solicitud_id) if t.ticket.cola.value == "AD")
    assert any("expiración" in x for x in ad.ticket.lista_de_verificacion)


def test_los_datos_de_otro_tipo_en_un_ingreso_se_rechazan() -> None:
    m = Mundo.nuevo()
    malo = replace(ingreso(), datos=vacaciones().datos)
    with pytest.raises(DatoInvalido, match="ingreso"):
        m.emitir(malo)


def test_falta_el_perfil_de_acceso_aborta_todo() -> None:
    m = Mundo.nuevo()
    del m.repos.almacen.perfiles[("Finanzas", "Bogotá")]
    antes = m.repos.almacen.instantanea()
    with pytest.raises(NoEncontrado, match="perfil"):
        m.emitir(ingreso())
    assert m.repos.almacen.instantanea() == antes
    assert m.soportes.nombres() == []


# --- emitir (RF-13, RF-15) y por excepcion (S-08) ----------------------------------------------


def test_RF_13_emitir_exige_justificacion() -> None:
    m = Mundo.nuevo()
    for vacia in (None, "", "  "):
        with pytest.raises(JustificacionRequerida):
            m.emitir(
                retiro(restringido="x")
                if False
                else replace(vacaciones("u-rrhh"), justificacion=vacia)
            )


def test_RF_15_rrhh_no_emite_sobre_si_misma_y_el_admin_si_por_excepcion_S_08() -> None:
    m = Mundo.nuevo()
    propia = vacaciones("u-rrhh", "col-rrhh")
    with pytest.raises(AutoAprobacionProhibida):
        m.emitir(replace(propia, justificacion="vacaciones de RRHH"))
    r = m.emitir_por_excepcion(
        replace(vacaciones("u-admin", "col-rrhh"), justificacion="RRHH sale de vacaciones")
    )
    assert r.estado is S.APROBADA
    assert r.tickets_encolados == 4
    assert "solicitud.emitida_por_excepcion" in m.acciones_de_auditoria()
    assert (
        "solicitud.emitida" not in m.acciones_de_auditoria()
    )  # no se confunde con una emision normal


def test_S_08_el_admin_solo_emite_por_excepcion_sobre_rrhh() -> None:
    m = Mundo.nuevo()
    with pytest.raises(NoAutorizado):
        m.emitir_por_excepcion(replace(vacaciones("u-admin", "col-1"), justificacion="x"))
    with pytest.raises(NoAutorizado):
        m.emitir_por_excepcion(replace(vacaciones("u-rrhh", "col-rrhh"), justificacion="x"))
    with pytest.raises(JustificacionRequerida):
        m.emitir_por_excepcion(vacaciones("u-admin", "col-rrhh"))


def test_S_08_el_administrador_no_aprueba() -> None:
    m = Mundo.nuevo()
    r = m.registrar(vacaciones())
    with pytest.raises(NoAutorizado):
        m.aprobar("u-admin", r.solicitud_id)


def test_S_18_una_pendiente_propia_de_rrhh_bloquea_la_excepcion_hasta_cancelarla() -> None:
    m = Mundo.nuevo()
    with m.repos.unidad_de_trabajo() as u:
        u.usuarios.guardar(
            UsuarioDelSistema("u-rrhh", "col-rrhh", frozenset({Rol.RRHH, Rol.SOLICITANTE}))
        )
    pendiente = m.registrar(vacaciones("u-rrhh", "col-rrhh"))
    with pytest.raises(AutoAprobacionProhibida):
        m.aprobar("u-rrhh", pendiente.solicitud_id)
    with pytest.raises(SolicitudDuplicada) as e:
        m.emitir_por_excepcion(replace(vacaciones("u-admin", "col-rrhh"), justificacion="x"))
    assert e.value.existente_id == pendiente.solicitud_id.valor
    m.cancelar("u-rrhh", pendiente.solicitud_id)  # el solicitante cancela la propia (RF-11)
    assert (
        m.emitir_por_excepcion(replace(vacaciones("u-admin", "col-rrhh"), justificacion="x")).estado
        is S.APROBADA
    )


# --- RF-10: la emergencia por encima de otras abiertas ----------------------------------------


def test_RF_10_una_emergencia_se_acepta_con_otras_abiertas_y_las_marca() -> None:
    m = Mundo.nuevo()
    vac = m.registrar(vacaciones())
    cdp = m.registrar(cambio_de_departamento())
    emg = m.emitir(emergencia())
    assert emg.estado is S.APROBADA
    assert set(emg.marcadas_para_revision) == {vac.solicitud_id, cdp.solicitud_id}
    for sid in (vac.solicitud_id, cdp.solicitud_id):
        s = m.solicitud(sid)
        assert s.para_revision
        assert s.estado is S.PENDIENTE_APROBACION  # su estado no se toca
    assert m.acciones_de_auditoria().count("solicitud.marcada_para_revision") == 2


def test_RF_10_otra_emergencia_abierta_si_es_duplicado() -> None:
    m = Mundo.nuevo()
    m.emitir(emergencia())
    with pytest.raises(SolicitudDuplicada):
        m.emitir(emergencia())


def test_las_marcadas_ya_marcadas_no_generan_ruido() -> None:
    m = Mundo.nuevo()
    m.registrar(vacaciones())
    m.emitir(emergencia())
    assert m.acciones_de_auditoria().count("solicitud.marcada_para_revision") == 1


# --- S-05: sin diferencia no hay tickets ------------------------------------------------------


def test_S_05_un_cdp_sin_diferencia_se_aprueba_y_cierra_sin_tickets() -> None:
    m = Mundo.nuevo()
    r = m.registrar(cambio_de_departamento(destino="Finanzas"))
    d = m.aprobar("u-rrhh", r.solicitud_id)
    assert d.estado is S.CERRADA
    assert d.tickets_encolados == 0
    assert "solicitud.sin_tickets" in m.acciones_de_auditoria()
    with m.repos.unidad_de_trabajo() as u:
        assert u.bandeja.de_solicitud(r.solicitud_id) == []
        assert u.tickets.de_solicitud(r.solicitud_id) == []
    assert m.colaborador("col-1").departamento == "Finanzas"


# --- aprobar / rechazar (RF-12, CA-02) --------------------------------------------------------


def test_aprobar_encola_los_tickets_y_registra_la_decision_CA_02() -> None:
    m = Mundo.nuevo()
    r = m.registrar(vacaciones())
    d = m.aprobar("u-rrhh", r.solicitud_id, "autorizado")
    assert (d.estado, d.tickets_encolados) == (S.APROBADA, 4)
    with m.repos.unidad_de_trabajo() as u:
        (decision,) = u.decisiones.de_solicitud(r.solicitud_id)
        assert (decision.tipo.value, decision.justificacion, decision.usuario_id) == (
            "aprobar",
            "autorizado",
            "u-rrhh",
        )
        assert {e.estado for e in u.bandeja.de_solicitud(r.solicitud_id)} == {
            EstadoDeEntrada.PENDIENTE
        }
    assert m.acciones_de_auditoria() == [
        "solicitud.registrada",
        "solicitud.aprobada",
        "solicitud.tickets_encolados",
    ]


@pytest.mark.parametrize("llamada_que_falla", [1, 2])
def test_CA_02_si_falla_la_auditoria_no_queda_decision_ni_bandeja(llamada_que_falla: int) -> None:
    m = Mundo.nuevo()
    r = m.registrar(vacaciones())
    antes = m.repos.almacen.instantanea()
    m.repos.control.fallar_en_la_llamada(llamada_que_falla)
    with pytest.raises(FalloInyectado):
        m.aprobar("u-rrhh", r.solicitud_id)
    assert m.repos.almacen.instantanea() == antes  # NADA de lo anterior sobrevive
    assert m.solicitud(r.solicitud_id).estado is S.PENDIENTE_APROBACION
    m.repos.control.sin_fallos()
    assert m.aprobar("u-rrhh", r.solicitud_id).estado is S.APROBADA  # y se puede reintentar


def test_CA_02_ningun_ticket_se_crea_sin_una_decision_de_RRHH() -> None:
    m = Mundo.nuevo()
    m.registrar(vacaciones())
    assert m.bandeja().procesadas == 0
    assert m.glpi.tickets_remotos() == []


def test_CA_02_solo_rrhh_aprueba_y_rechazar_exige_justificacion() -> None:
    m = Mundo.nuevo()
    r = m.registrar(vacaciones())
    for usuario in ("u-col", "u-jefe", "u-admin", "u-tec-ad"):
        with pytest.raises(NoAutorizado):
            m.aprobar(usuario, r.solicitud_id)
    with pytest.raises(JustificacionRequerida):
        m.rechazar("u-rrhh", r.solicitud_id, "  ")
    assert m.solicitud(r.solicitud_id).estado is S.PENDIENTE_APROBACION
    assert m.rechazar("u-rrhh", r.solicitud_id, "no hay cobertura").estado is S.RECHAZADA


def test_aprobar_una_solicitud_que_no_existe_o_ya_decidida() -> None:
    m = Mundo.nuevo()
    with pytest.raises(NoEncontrado):
        m.aprobar("u-rrhh", SolicitudId.de(2026, 99))
    r = m.registrar(vacaciones())
    m.aprobar("u-rrhh", r.solicitud_id)
    with pytest.raises(TransicionInvalida):
        m.aprobar("u-rrhh", r.solicitud_id)
    with pytest.raises(TransicionInvalida):
        m.rechazar("u-rrhh", r.solicitud_id, "tarde")


def test_RF_15_rrhh_no_aprueba_lo_propio_y_no_queda_rastro() -> None:
    m = Mundo.nuevo()
    with m.repos.unidad_de_trabajo() as u:
        u.usuarios.guardar(
            UsuarioDelSistema("u-rrhh", "col-rrhh", frozenset({Rol.RRHH, Rol.SOLICITANTE}))
        )
    r = m.registrar(vacaciones("u-rrhh", "col-rrhh"))
    antes = m.repos.almacen.instantanea()
    with pytest.raises(AutoAprobacionProhibida):
        m.aprobar("u-rrhh", r.solicitud_id)
    with pytest.raises(AutoAprobacionProhibida):
        m.rechazar("u-rrhh", r.solicitud_id, "x")
    assert m.repos.almacen.instantanea() == antes


def test_aprobar_una_EMG_pendiente_no_existe_porque_se_emite_pero_aprobar_marca_otras() -> None:
    """Una EMG solo la emite RRHH (4.1); su registro pendiente ni siquiera es posible."""
    m = Mundo.nuevo()
    with pytest.raises(NoAutorizado):
        m.registrar(emergencia(usuario="u-col"))


# --- rechazar / cancelar y el soporte (RF-11, RF-40) -------------------------------------------


def test_rechazar_un_ingreso_descarta_el_soporte_RF_40() -> None:
    """Si RRHH rechaza un ingreso pendiente, la copia se borra sin subirse."""
    m = Mundo.nuevo()
    # un ingreso solo lo emite RRHH; se simula uno pendiente guardado a mano para este caso
    e = m.emitir(ingreso())
    with m.repos.unidad_de_trabajo() as u:
        s = u.solicitudes.obtener(e.solicitud_id)
        assert s is not None
        u.solicitudes.guardar(replace(s, estado=S.PENDIENTE_APROBACION))
    m.rechazar("u-rrhh", e.solicitud_id, "documentos incompletos")
    with m.repos.unidad_de_trabajo() as u:
        soporte = u.soportes.obtener(e.solicitud_id)
        assert soporte is not None
        assert soporte.estado is EstadoDeSoporte.DESCARTADO
    assert m.soportes.nombres() == []


def test_el_solicitante_cancela_su_pendiente_RF_11() -> None:
    m = Mundo.nuevo()
    r = m.registrar(vacaciones())
    c = m.cancelar("u-col", r.solicitud_id)
    assert c.estado is S.CANCELADA
    with pytest.raises(NoAutorizado):
        m.cancelar("u-otro", m.registrar(vacaciones()).solicitud_id)


def test_rrhh_cancela_una_aprobada_sin_tickets_y_se_descarta_la_bandeja_RF_11() -> None:
    m = Mundo.nuevo()
    r = m.registrar(vacaciones())
    m.aprobar("u-rrhh", r.solicitud_id)
    assert m.cancelar("u-rrhh", r.solicitud_id, "error de fechas").estado is S.CANCELADA
    with m.repos.unidad_de_trabajo() as u:
        assert {e.estado for e in u.bandeja.de_solicitud(r.solicitud_id)} == {
            EstadoDeEntrada.DESCARTADA
        }
    assert m.bandeja().procesadas == 0  # lo descartado jamas llega a GLPI
    assert m.glpi.tickets_remotos() == []


def test_cancelar_un_ingreso_borra_la_copia_del_soporte_sin_subirla_RF_40() -> None:
    m = Mundo.nuevo()
    e = m.emitir(ingreso())
    assert len(m.soportes.nombres()) == 1
    m.cancelar("u-rrhh", e.solicitud_id, "se cae la contratacion")
    assert m.soportes.nombres() == []
    assert m.glpi.documentos_subidos() == 0
    with m.repos.unidad_de_trabajo() as u:
        soporte = u.soportes.obtener(e.solicitud_id)
        assert soporte is not None
        assert soporte.estado is EstadoDeSoporte.DESCARTADO
    # el colaborador queda por_ingresar y el documento reservado (S-06)
    assert m.colaborador(e.colaborador_id).estado is EstadoColaborador.POR_INGRESAR


def test_rrhh_no_cancela_una_aprobada_con_tickets_creados() -> None:
    m = Mundo.nuevo()
    r = m.emitir(replace(vacaciones("u-rrhh"), justificacion="ok"))
    m.glpi.programar()  # sin fallos
    primera = m.bandeja(limite=1)
    assert primera.creadas == 1
    with pytest.raises(CancelacionNoPermitida):
        m.cancelar("u-rrhh", r.solicitud_id)
    assert m.solicitud(r.solicitud_id).estado is S.APROBADA


def test_no_se_cancela_una_solicitud_cerrada_ni_rechazada() -> None:
    m = Mundo.nuevo()
    r = m.registrar(vacaciones())
    m.rechazar("u-rrhh", r.solicitud_id, "no")
    with pytest.raises(NoAutorizado):  # fuera de `pendiente` solo RRHH cancela
        m.cancelar("u-col", r.solicitud_id)
    with pytest.raises(TransicionInvalida):
        m.cancelar("u-rrhh", r.solicitud_id)


def test_corregir_es_cancelar_y_registrar_una_nueva_vinculada_RF_14() -> None:
    m = Mundo.nuevo()
    a = m.registrar(vacaciones())
    m.aprobar("u-rrhh", a.solicitud_id)
    m.cancelar("u-rrhh", a.solicitud_id, "fecha equivocada")
    nueva = m.registrar(replace(vacaciones(), solicitud_origen_id=a.solicitud_id))
    assert m.solicitud(nueva.solicitud_id).solicitud_origen_id == a.solicitud_id


def test_el_tipo_subtipo_invalido_no_deja_rastro() -> None:
    m = Mundo.nuevo()
    antes = m.repos.almacen.instantanea()
    with pytest.raises(DatoInvalido, match="subtipo"):
        m.emitir(retiro(subtipo=Subtipo.FUGA_DETECTADA))
    assert m.repos.almacen.instantanea() == antes


def test_el_tipo_se_conserva() -> None:
    m = Mundo.nuevo()
    r = m.emitir(retiro())
    assert m.solicitud(r.solicitud_id).tipo is TipoEvento.RET
