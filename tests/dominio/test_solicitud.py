"""Item 1.4: agregado Solicitud (RF-07 a RF-15, RF-38, CA-02, P2)."""

import dataclasses
import itertools
from collections.abc import Callable
from dataclasses import replace
from datetime import timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from jml.dominio.catalogo import (
    DatosCambioDepartamento,
    DatosEmergencia,
    DatosRetiro,
    DatosVacaciones,
)
from jml.dominio.errores import (
    AutoAprobacionProhibida,
    CancelacionNoPermitida,
    CierreNoPermitido,
    ColaboradorNoElegible,
    ErrorDeDominio,
    JustificacionRequerida,
    NoAutorizado,
    OperacionNoPermitida,
    TransicionInvalida,
)
from jml.dominio.permisos import Actor
from jml.dominio.solicitud import (
    ESTADOS_ELEGIBLES,
    TRANSICIONES,
    Accion,
    ResultadoSolicitud,
    Solicitud,
    TipoDeDecision,
)
from jml.dominio.tipos import (
    ESTADOS_ABIERTOS,
    ESTADOS_FINALES,
    EstadoColaborador,
    EstadoSolicitud,
    Rol,
    Subtipo,
    TipoEvento,
)
from jml.dominio.valores import CampoRestringido, SolicitudId
from tests.fabricas import AHORA, HOY, colaborador, datos_ingreso

S = EstadoSolicitud
RRHH = Actor("u-rrhh", "col-rrhh", frozenset({Rol.RRHH}))
ADMIN = Actor("u-admin", None, frozenset({Rol.ADMINISTRADOR}))
EMPLEADO = Actor("u-col", "col-1", frozenset({Rol.SOLICITANTE}))
JEFE = Actor("u-jefe", "jefe-1", frozenset({Rol.SOLICITANTE}))
TERCERO = Actor("u-otro", "col-9", frozenset({Rol.SOLICITANTE}))
FUTURO = HOY + timedelta(days=7)
SID = SolicitudId.de(2026, 1)
MOTIVO = CampoRestringido("motivo reservado")


def vacaciones(estado: EstadoSolicitud = S.PENDIENTE_APROBACION, **kw: object) -> Solicitud:
    base = Solicitud(
        id=SID,
        colaborador_id="col-1",
        tipo=TipoEvento.VAC,
        subtipo=None,
        fecha_efectiva=FUTURO,
        datos=DatosVacaciones(FUTURO + timedelta(days=14)),
        restringido=None,
        solicitante_id="u-col",
        estado=estado,
        creada_en=AHORA,
    )
    return replace(base, **kw)  # type: ignore[arg-type]  # kwargs de prueba


def registrar_vac(actor: Actor = EMPLEADO) -> ResultadoSolicitud:
    return Solicitud.registrar_pendiente(
        id=SID,
        actor=actor,
        sujeto=colaborador(),
        tipo=TipoEvento.VAC,
        subtipo=None,
        fecha_efectiva=FUTURO,
        datos=DatosVacaciones(FUTURO + timedelta(days=14)),
        restringido=None,
        ahora=AHORA,
    )


# --- tabla de transiciones --------------------------------------------------------------------

# Escrita a mano desde docs/img/estados.dot (+ S-19); es la fuente contra la que se compara.
ESPERADAS: dict[tuple[EstadoSolicitud, Accion], EstadoSolicitud] = {
    (S.PENDIENTE_APROBACION, Accion.APROBAR): S.APROBADA,
    (S.PENDIENTE_APROBACION, Accion.RECHAZAR): S.RECHAZADA,
    (S.PENDIENTE_APROBACION, Accion.CANCELAR_SOLICITANTE): S.CANCELADA,
    (S.APROBADA, Accion.INICIAR_EJECUCION): S.EN_EJECUCION,
    (S.APROBADA, Accion.FALLAR_EMISION): S.ERROR,
    (S.APROBADA, Accion.CANCELAR_RRHH): S.CANCELADA,
    (S.ERROR, Accion.REINTENTAR): S.APROBADA,
    (S.ERROR, Accion.CANCELAR_RRHH): S.CANCELADA,
    (S.EN_EJECUCION, Accion.CERRAR): S.CERRADA,
}

OPERACION: dict[Accion, Callable[[Solicitud], ResultadoSolicitud]] = {
    Accion.APROBAR: lambda s: s.aprobar(RRHH, None, AHORA),
    Accion.RECHAZAR: lambda s: s.rechazar(RRHH, "no procede", AHORA),
    Accion.CANCELAR_SOLICITANTE: lambda s: s.cancelar_por_solicitante(EMPLEADO, AHORA),
    Accion.CANCELAR_RRHH: lambda s: s.cancelar_por_rrhh(RRHH, None, AHORA),
    Accion.INICIAR_EJECUCION: lambda s: s.iniciar_ejecucion(frozenset()),
    Accion.FALLAR_EMISION: lambda s: s.fallar_emision("glpi_500"),
    Accion.REINTENTAR: lambda s: s.reintentar(ADMIN),
    Accion.CERRAR: lambda s: s.cerrar(0),
}


def test_la_tabla_de_transiciones_es_la_del_diagrama() -> None:
    assert dict(TRANSICIONES) == ESPERADAS


def test_toda_accion_tiene_operacion() -> None:
    assert set(OPERACION) == set(Accion)


@pytest.mark.parametrize(("estado", "accion"), list(itertools.product(S, Accion)))
def test_cada_celda_estado_x_accion(estado: EstadoSolicitud, accion: Accion) -> None:
    """RF-11, RF-12, RF-18, RF-26: permitida lleva al estado esperado; el resto es TransicionInvalida."""
    s = vacaciones(estado)
    if (estado, accion) in ESPERADAS:
        r = OPERACION[accion](s)
        assert r.solicitud.estado is ESPERADAS[(estado, accion)]
        assert r.solicitud.contenido() == s.contenido()
        assert r.eventos  # cada transicion deja rastro
    else:
        with pytest.raises(TransicionInvalida) as e:
            OPERACION[accion](s)
        assert (e.value.estado, e.value.accion) == (estado.value, accion.value)


def test_los_estados_finales_son_absorbentes() -> None:
    for (origen, _), _destino in ESPERADAS.items():
        assert origen not in ESTADOS_FINALES
    assert {S.CERRADA, S.RECHAZADA, S.CANCELADA} == ESTADOS_FINALES


# --- registro: quien registra que (RF-07, RF-15) ----------------------------------------------


def test_el_colaborador_registra_sus_vacaciones_pendientes() -> None:
    r = registrar_vac()
    assert r.solicitud.estado is S.PENDIENTE_APROBACION
    assert r.decision is None
    assert r.solicitud.solicitante_id == "u-col"
    assert r.eventos[0].accion == "solicitud.registrada"


def test_un_tercero_no_registra_vacaciones_ajenas() -> None:
    with pytest.raises(NoAutorizado):
        registrar_vac(TERCERO)
    with pytest.raises(NoAutorizado):
        registrar_vac(JEFE)  # el jefe no registra vacaciones del subordinado


def test_el_jefe_registra_cdp_de_su_subordinado_y_el_empleado_no() -> None:
    kw = dict(
        id=SID, sujeto=colaborador(), tipo=TipoEvento.CDP, subtipo=None, fecha_efectiva=FUTURO,
        datos=DatosCambioDepartamento("TI", "Dev", None), restringido=None, ahora=AHORA,
    )  # fmt: skip
    assert Solicitud.registrar_pendiente(actor=JEFE, **kw).solicitud.tipo is TipoEvento.CDP  # type: ignore[arg-type]
    with pytest.raises(NoAutorizado):
        Solicitud.registrar_pendiente(actor=EMPLEADO, **kw)  # type: ignore[arg-type]


def test_renuncia_la_registra_el_colaborador_pero_fin_de_contrato_no() -> None:
    kw = dict(
        id=SID, actor=EMPLEADO, sujeto=colaborador(), tipo=TipoEvento.RET, fecha_efectiva=FUTURO,
        datos=DatosRetiro(), restringido=MOTIVO, ahora=AHORA,
    )  # fmt: skip
    ok = Solicitud.registrar_pendiente(subtipo=Subtipo.RENUNCIA, **kw)  # type: ignore[arg-type]
    assert ok.solicitud.subtipo is Subtipo.RENUNCIA
    with pytest.raises(NoAutorizado):
        Solicitud.registrar_pendiente(subtipo=Subtipo.FIN_DE_CONTRATO, **kw)  # type: ignore[arg-type]


def emitir(
    actor: Actor, justificacion: str | None = "orden de RRHH", **over: object
) -> ResultadoSolicitud:
    kw: dict[str, object] = dict(
        id=SID, actor=actor, sujeto=colaborador(), tipo=TipoEvento.VAC, subtipo=None,
        fecha_efectiva=FUTURO, datos=DatosVacaciones(FUTURO + timedelta(days=3)),
        restringido=None, justificacion=justificacion, ahora=AHORA,
    )  # fmt: skip
    kw.update(over)
    return Solicitud.emitir_directo(**kw)  # type: ignore[arg-type]


def test_rrhh_emite_en_un_paso_con_justificacion_RF_13() -> None:
    r = emitir(RRHH)
    assert r.solicitud.estado is S.APROBADA
    assert r.decision is not None
    assert r.decision.tipo is TipoDeDecision.EMITIR
    assert r.decision.justificacion == "orden de RRHH"
    assert [e.accion for e in r.eventos] == ["solicitud.registrada", "solicitud.emitida"]


@pytest.mark.parametrize("vacia", [None, "", "   "])
def test_emitir_sin_justificacion_se_rechaza_RF_13(vacia: str | None) -> None:
    with pytest.raises(JustificacionRequerida):
        emitir(RRHH, vacia)


def test_nadie_mas_que_rrhh_emite_directo() -> None:
    for actor in (EMPLEADO, JEFE, ADMIN):
        with pytest.raises(NoAutorizado):
            emitir(actor)


def test_rrhh_no_emite_sobre_si_misma_RF_15() -> None:
    propio = colaborador(id="col-rrhh")
    with pytest.raises(AutoAprobacionProhibida):
        emitir(RRHH, sujeto=propio)


def test_el_administrador_emite_por_excepcion_solo_si_el_sujeto_es_rrhh_S_08() -> None:
    kw: dict[str, object] = dict(
        id=SID, actor=ADMIN, sujeto=colaborador(id="col-rrhh"), tipo=TipoEvento.VAC, subtipo=None,
        fecha_efectiva=FUTURO, datos=DatosVacaciones(FUTURO + timedelta(days=3)),
        restringido=None, justificacion="RRHH sale de vacaciones", ahora=AHORA,
    )  # fmt: skip
    r = Solicitud.emitir_por_excepcion(sujeto_es_rrhh=True, **kw)  # type: ignore[arg-type]
    assert r.solicitud.estado is S.APROBADA
    assert r.decision is not None
    assert r.decision.tipo is TipoDeDecision.EMITIR_POR_EXCEPCION
    assert "solicitud.emitida_por_excepcion" in [e.accion for e in r.eventos]
    with pytest.raises(NoAutorizado):
        Solicitud.emitir_por_excepcion(sujeto_es_rrhh=False, **kw)  # type: ignore[arg-type]
    with pytest.raises(NoAutorizado):
        Solicitud.emitir_por_excepcion(**{**kw, "actor": RRHH}, sujeto_es_rrhh=True)  # type: ignore[arg-type]
    with pytest.raises(JustificacionRequerida):
        Solicitud.emitir_por_excepcion(**{**kw, "justificacion": " "}, sujeto_es_rrhh=True)  # type: ignore[arg-type]


@pytest.mark.parametrize("estado_col", list(EstadoColaborador))
@pytest.mark.parametrize("tipo", list(TipoEvento))
def test_elegibilidad_del_colaborador_por_tipo_S_25(
    estado_col: EstadoColaborador, tipo: TipoEvento
) -> None:
    sujeto = replace(colaborador(), estado=estado_col)
    datos, restringido, sub, fe = {
        TipoEvento.ING: (datos_ingreso(), None, None, FUTURO),
        TipoEvento.VAC: (DatosVacaciones(FUTURO + timedelta(days=2)), None, None, FUTURO),
        TipoEvento.CDP: (DatosCambioDepartamento("TI", "x", None), None, None, FUTURO),
        TipoEvento.CSU: (None, None, None, FUTURO),
        TipoEvento.RET: (DatosRetiro(), MOTIVO, Subtipo.RENUNCIA, FUTURO),
        TipoEvento.EMG: (
            DatosEmergencia("Seguridad", AHORA - timedelta(hours=1)), MOTIVO, Subtipo.FUGA_DETECTADA, HOY,
        ),
    }[tipo]  # fmt: skip
    if tipo is TipoEvento.CSU:
        from jml.dominio.catalogo import DatosCambioSucursal

        datos = DatosCambioSucursal("Cali", False)
    kw: dict[str, object] = dict(
        id=SID, actor=RRHH, sujeto=sujeto, tipo=tipo, subtipo=sub, fecha_efectiva=fe, datos=datos,
        restringido=restringido, justificacion="j", ahora=AHORA,
    )  # fmt: skip
    if estado_col in ESTADOS_ELEGIBLES[tipo]:
        assert Solicitud.emitir_directo(**kw).solicitud.tipo is tipo  # type: ignore[arg-type]
    else:
        with pytest.raises(ColaboradorNoElegible):
            Solicitud.emitir_directo(**kw)  # type: ignore[arg-type]


def test_nunca_se_emite_sobre_un_retirado() -> None:
    assert all(EstadoColaborador.RETIRADO not in v for v in ESTADOS_ELEGIBLES.values())


def test_el_evento_invalido_no_crea_solicitud() -> None:
    with pytest.raises(ErrorDeDominio):
        emitir(RRHH, fecha_efectiva=HOY - timedelta(days=1))


# --- decisiones (RF-12, RF-15, CA-02) ---------------------------------------------------------


def test_aprobar_acepta_justificacion_opcional_RF_12() -> None:
    sin = vacaciones().aprobar(RRHH, None, AHORA)
    con = vacaciones().aprobar(RRHH, "  ok  ", AHORA)
    assert sin.decision is not None
    assert con.decision is not None
    assert sin.decision.justificacion is None
    assert con.decision.justificacion == "ok"
    assert (sin.decision.tipo, sin.decision.usuario_id) == (TipoDeDecision.APROBAR, "u-rrhh")
    assert sin.decision.fecha == AHORA


@pytest.mark.parametrize("vacia", [None, "", " \n "])
def test_rechazar_exige_justificacion_CA_02(vacia: str | None) -> None:
    with pytest.raises(JustificacionRequerida):
        vacaciones().rechazar(RRHH, vacia, AHORA)
    r = vacaciones().rechazar(RRHH, "datos incompletos", AHORA)
    assert r.solicitud.estado is S.RECHAZADA
    assert r.decision is not None
    assert r.decision.justificacion == "datos incompletos"


def test_solo_rrhh_decide() -> None:
    for actor in (EMPLEADO, JEFE, ADMIN):
        with pytest.raises(NoAutorizado):
            vacaciones().aprobar(actor, None, AHORA)
        with pytest.raises(NoAutorizado):
            vacaciones().rechazar(actor, "x", AHORA)
        with pytest.raises(NoAutorizado):
            vacaciones(S.APROBADA).cancelar_por_rrhh(actor, None, AHORA)


def test_rrhh_no_aprueba_ni_rechaza_ni_cancela_lo_propio_RF_15() -> None:
    propia = vacaciones(colaborador_id="col-rrhh")
    with pytest.raises(AutoAprobacionProhibida):
        propia.aprobar(RRHH, None, AHORA)
    with pytest.raises(AutoAprobacionProhibida):
        propia.rechazar(RRHH, "x", AHORA)
    with pytest.raises(AutoAprobacionProhibida):
        vacaciones(S.APROBADA, colaborador_id="col-rrhh").cancelar_por_rrhh(RRHH, None, AHORA)


def test_la_autoaprobacion_se_comprueba_antes_que_el_estado() -> None:
    with pytest.raises(AutoAprobacionProhibida):
        vacaciones(S.CERRADA, colaborador_id="col-rrhh").aprobar(RRHH, None, AHORA)


def test_el_administrador_no_aprueba_S_08() -> None:
    with pytest.raises(NoAutorizado):
        vacaciones().aprobar(ADMIN, None, AHORA)


# --- cancelacion (RF-11) ----------------------------------------------------------------------


def test_solo_quien_registro_cancela_su_pendiente() -> None:
    assert vacaciones().cancelar_por_solicitante(EMPLEADO, AHORA).solicitud.estado is S.CANCELADA
    with pytest.raises(NoAutorizado):
        vacaciones().cancelar_por_solicitante(TERCERO, AHORA)
    with pytest.raises(TransicionInvalida):  # RRHH tampoco por esta via
        vacaciones(S.APROBADA).cancelar_por_solicitante(EMPLEADO, AHORA)


def test_rrhh_cancela_una_aprobada_sin_tickets_pero_no_con_tickets_RF_11() -> None:
    s = vacaciones(S.APROBADA)
    assert s.cancelar_por_rrhh(RRHH, "se corrige", AHORA).solicitud.estado is S.CANCELADA
    con_tickets = s.registrar_ticket_creado("SOL-2026-000001:AD:cierre_inmediato:1")
    with pytest.raises(CancelacionNoPermitida):
        con_tickets.cancelar_por_rrhh(RRHH, None, AHORA)
    with pytest.raises(CancelacionNoPermitida):
        replace(con_tickets, estado=S.ERROR).cancelar_por_rrhh(RRHH, None, AHORA)


def test_rrhh_no_cancela_una_en_ejecucion() -> None:
    with pytest.raises(TransicionInvalida):
        vacaciones(S.EN_EJECUCION).cancelar_por_rrhh(RRHH, None, AHORA)


def test_una_solicitud_en_error_sin_tickets_se_cancela_para_registrar_de_nuevo_S_19() -> None:
    """RD-12: tras perder el soporte, RRHH registra de nuevo; `error` es abierto, hay que cancelar."""
    assert vacaciones(S.ERROR).cancelar_por_rrhh(RRHH, None, AHORA).solicitud.estado is S.CANCELADA


# --- tickets, ejecucion, error, reintento y cierre --------------------------------------------


def test_registrar_ticket_creado_es_idempotente_y_solo_en_aprobada() -> None:
    s = vacaciones(S.APROBADA).registrar_ticket_creado("k1")
    assert s.registrar_ticket_creado("k1") is s
    assert s.registrar_ticket_creado("k2").tickets == ("k1", "k2")
    for estado in (S.PENDIENTE_APROBACION, S.EN_EJECUCION, S.ERROR, S.CERRADA):
        with pytest.raises(TransicionInvalida):
            vacaciones(estado).registrar_ticket_creado("k1")


def test_iniciar_ejecucion_exige_todos_los_tickets() -> None:
    s = vacaciones(S.APROBADA).registrar_ticket_creado("k1")
    with pytest.raises(OperacionNoPermitida):
        s.iniciar_ejecucion(frozenset({"k1", "k2"}))
    ok = s.registrar_ticket_creado("k2").iniciar_ejecucion(frozenset({"k1", "k2"}))
    assert ok.solicitud.estado is S.EN_EJECUCION


def test_reintentar_solo_el_administrador_RF_38() -> None:
    err = vacaciones(S.ERROR)
    assert err.reintentar(ADMIN).solicitud.estado is S.APROBADA
    for actor in (RRHH, EMPLEADO):
        with pytest.raises(NoAutorizado):
            err.reintentar(actor)


def test_error_lleva_el_codigo_en_la_auditoria() -> None:
    r = vacaciones(S.APROBADA).fallar_emision("glpi_500")
    assert r.solicitud.estado is S.ERROR
    assert r.eventos[0].datos["codigo"] == "glpi_500"


def test_cerrar_solo_sin_pendientes_RF_26() -> None:
    s = vacaciones(S.EN_EJECUCION)
    with pytest.raises(CierreNoPermitido) as e:
        s.cerrar(2)
    assert e.value.pendientes == 2
    assert s.cerrar(0).solicitud.estado is S.CERRADA


# --- RF-10: EMG marca otras abiertas ----------------------------------------------------------


def test_marcar_para_revision_no_toca_estado_ni_contenido_RF_10() -> None:
    for estado in ESTADOS_ABIERTOS:
        s = vacaciones(estado)
        r = s.marcar_para_revision()
        assert r.solicitud.para_revision
        assert r.solicitud.estado is estado
        assert r.solicitud.contenido() == s.contenido()
        assert r.eventos[0].accion == "solicitud.marcada_para_revision"
        assert r.solicitud.marcar_para_revision().eventos == ()  # idempotente, sin ruido
    for estado in ESTADOS_FINALES:
        with pytest.raises(TransicionInvalida):
            vacaciones(estado).marcar_para_revision()


# --- inmutabilidad (RF-14) y confidencialidad (RD-05) -----------------------------------------


def test_la_solicitud_es_un_valor_inmutable() -> None:
    s = vacaciones(S.APROBADA)
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.estado = S.PENDIENTE_APROBACION  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.fecha_efectiva = HOY  # type: ignore[misc]


def test_estado_y_tickets_no_forman_parte_del_contenido_RF_14() -> None:
    s = vacaciones()
    assert (
        replace(s, estado=S.APROBADA, tickets=("k",), para_revision=True).contenido()
        == s.contenido()
    )
    assert replace(s, fecha_efectiva=HOY).contenido() != s.contenido()
    assert replace(s, restringido=MOTIVO).contenido() != s.contenido()


def test_el_motivo_no_aparece_en_repr_ni_en_eventos_ni_en_errores() -> None:
    r = Solicitud.emitir_directo(
        id=SID, actor=RRHH, sujeto=colaborador(), tipo=TipoEvento.RET, subtipo=Subtipo.RENUNCIA,
        fecha_efectiva=FUTURO, datos=DatosRetiro(), restringido=CampoRestringido("SENTINELA-77"),
        justificacion="j", ahora=AHORA,
    )  # fmt: skip
    textos = [repr(r.solicitud), str(r.solicitud), repr(r)]
    for e in r.eventos:
        textos.append(repr(e))
        textos.append(repr(dict(e.datos)))
    assert all("SENTINELA-77" not in t for t in textos)


# --- P2: recorridos aleatorios ----------------------------------------------------------------


def _alcanzables() -> set[EstadoSolicitud]:
    vistos = {S.PENDIENTE_APROBACION, S.APROBADA}  # los dos estados de entrada del diagrama
    cola = list(vistos)
    while cola:
        e = cola.pop()
        for (origen, _), destino in ESPERADAS.items():
            if origen is e and destino not in vistos:
                vistos.add(destino)
                cola.append(destino)
    return vistos


def test_todos_los_estados_son_alcanzables_desde_el_registro() -> None:
    assert _alcanzables() == set(S)


@given(
    st.sampled_from([S.PENDIENTE_APROBACION, S.APROBADA]),
    st.lists(st.sampled_from(list(Accion)), max_size=25),
)
def test_P2_recorridos_aleatorios(inicio: EstadoSolicitud, acciones: list[Accion]) -> None:
    s = vacaciones(inicio)
    contenido = s.contenido()
    alcanzables = _alcanzables()
    for accion in acciones:
        antes = s
        try:
            s = OPERACION[accion](s).solicitud
        except ErrorDeDominio:
            assert s is antes  # un intento fallido no cambia nada
            continue
        assert s.estado in alcanzables
        assert (antes.estado, accion) in ESPERADAS
        assert s.contenido() == contenido  # RF-14
        assert antes.estado not in ESTADOS_FINALES  # los finales son absorbentes
    if s.estado in ESTADOS_FINALES:
        for accion in Accion:
            with pytest.raises(ErrorDeDominio):
                OPERACION[accion](s)
