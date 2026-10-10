"""Item 1.7: cierre, cuentas derivadas y colaborador (RF-24 a RF-27, RD-11, S-07, S-09..S-11, P7, P9)."""

import dataclasses
import inspect
import itertools
from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from jml.dominio import cuentas as modulo_cuentas
from jml.dominio.cuentas import (
    ESTADO_AL_RESOLVERSE,
    ESTADO_MIENTRAS_ESTA_ABIERTO,
    Cuenta,
    ResultadoDeDerivacion,
    derivar_cuenta,
)
from jml.dominio.errores import DatoInvalido
from jml.dominio.resolucion import (
    cierre_incompleto,
    estado_derivado_del_colaborador,
    pendientes_de_cierre,
    solicitud_cerrable,
    ticket_resuelto,
)
from jml.dominio.tickets import Observacion, TicketDeCola, TicketSeguido, generar_tickets
from jml.dominio.tipos import (
    AccionDeTicket as A,
)
from jml.dominio.tipos import (
    ClaseTicket,
    Cola,
    EstadoColaborador,
    EstadoDeCuenta,
    EstadoDeTicket,
    MarcaDeCuenta,
    SistemaDeCuenta,
    Subtipo,
    TipoEvento,
)
from jml.dominio.valores import CalendarioHabil
from tests.fabricas import AHORA, Caso, caso

E, M = EstadoDeCuenta, MarcaDeCuenta
ET = EstadoDeTicket
AD, COM, LIC, INV = Cola.AD, Cola.COMUNICACIONES, Cola.LICENCIAS, Cola.INVENTARIO
I, P, POST = ClaseTicket.CIERRE_INMEDIATO, ClaseTicket.CIERRE_PROGRAMADO, ClaseTicket.POSTERIOR  # noqa: E741
TARDE = AHORA + timedelta(days=400)  # despues de cualquier fecha programada


def obs(estado: ET, solucion: bool = True, docs: int = 0, minutos: int = 0) -> Observacion:
    return Observacion(estado, solucion, docs, AHORA + timedelta(minutes=minutos))


def tickets(c: Caso) -> tuple[TicketDeCola, ...]:
    return generar_tickets(c.solicitud, c.actual, c.nuevo, c.colaborador, CalendarioHabil(), AHORA)


def elegir(c: Caso, cola: Cola, clase: ClaseTicket = I) -> TicketDeCola:
    return next(t for t in tickets(c) if t.cola is cola and t.clase is clase)


def cuenta_de(
    t: TicketDeCola, estado: EstadoDeCuenta, marca: MarcaDeCuenta | None = None
) -> Cuenta:
    assert t.sistema is not None
    return Cuenta(
        "col-1",
        t.sistema,
        estado,
        t.clave_de_idempotencia,
        (t.emitido_en, t.vence_en),
        AHORA,
        marca,
    )


def derivar(
    cuenta: Cuenta | None,
    t: TicketDeCola,
    antes: Observacion | None,
    ahora_: Observacion,
    en: datetime = AHORA,
) -> ResultadoDeDerivacion:
    return derivar_cuenta(cuenta, t, antes, ahora_, "col-1", en)


# --- RF-24: ticket resuelto ---------------------------------------------------------------------


def seguido(t: TicketDeCola, o: Observacion | None) -> TicketSeguido:
    return TicketSeguido(t, "g-1", o)


@pytest.mark.parametrize("estado", list(ET))
@pytest.mark.parametrize("solucion", [True, False])
def test_resuelto_exige_estado_y_solucion_RF_24(estado: ET, solucion: bool) -> None:
    t = elegir(caso(TipoEvento.ING), AD)
    esperado = estado >= ET.RESUELTO and solucion
    assert ticket_resuelto(seguido(t, obs(estado, solucion))) is esperado
    assert cierre_incompleto(seguido(t, obs(estado, solucion))) is (
        estado >= ET.RESUELTO and not solucion
    )


def test_inventario_ademas_exige_un_adjunto_RF_24_CA_08() -> None:
    t = elegir(caso(TipoEvento.ING), INV)
    assert not ticket_resuelto(seguido(t, obs(ET.RESUELTO, True, docs=0)))
    assert cierre_incompleto(seguido(t, obs(ET.RESUELTO, True, docs=0)))
    assert ticket_resuelto(seguido(t, obs(ET.RESUELTO, True, docs=1)))
    assert ticket_resuelto(seguido(t, obs(ET.CERRADO, True, docs=3)))
    assert not ticket_resuelto(seguido(t, obs(ET.RESUELTO, False, docs=1)))


def test_un_ticket_sin_observacion_no_esta_resuelto() -> None:
    t = elegir(caso(TipoEvento.ING), AD)
    assert not ticket_resuelto(seguido(t, None))
    assert not cierre_incompleto(seguido(t, None))


def test_otras_colas_no_necesitan_adjunto() -> None:
    for cola in (AD, COM, LIC):
        t = elegir(caso(TipoEvento.ING), cola)
        assert ticket_resuelto(seguido(t, obs(ET.RESUELTO, True, docs=0)))


# --- RF-26: cierre de la solicitud (P9) ----------------------------------------------------------


def resolver(t: TicketDeCola, ok: bool = True) -> TicketSeguido:
    return seguido(t, obs(ET.RESUELTO, ok, docs=1))


def test_los_posteriores_no_bloquean_el_cierre_RF_26() -> None:
    ts = tickets(caso(TipoEvento.RET, Subtipo.RENUNCIA))
    estado = [
        resolver(t) if t.clase is not POST else seguido(t, obs(ET.EN_ESPERA, False)) for t in ts
    ]
    assert solicitud_cerrable(estado)
    assert pendientes_de_cierre(estado) == 0


def test_un_ticket_de_cierre_pendiente_impide_cerrar() -> None:
    ts = tickets(caso(TipoEvento.RET, Subtipo.RENUNCIA))
    estado = [resolver(t) for t in ts]
    assert solicitud_cerrable(estado)
    sin_solucion = [resolver(t, ok=(i != 0)) for i, t in enumerate(ts)]
    assert pendientes_de_cierre(sin_solucion) == 1
    assert not solicitud_cerrable(sin_solucion)
    assert not solicitud_cerrable([seguido(t, None) for t in ts])


def test_el_cierre_programado_de_VAC_bloquea_hasta_la_reactivacion() -> None:
    ts = tickets(caso(TipoEvento.VAC))
    parcial = [resolver(t) if t.clase is I else seguido(t, obs(ET.EN_ESPERA, False)) for t in ts]
    assert pendientes_de_cierre(parcial) == 2
    assert solicitud_cerrable([resolver(t) for t in ts])


@given(
    st.lists(st.booleans(), min_size=6, max_size=6), st.lists(st.booleans(), min_size=6, max_size=6)
)
def test_P9_cerrada_si_y_solo_si_todos_los_de_cierre_estan_resueltos(
    resueltos: list[bool], posteriores_resueltos: list[bool]
) -> None:
    ts = tickets(caso(TipoEvento.RET, Subtipo.RENUNCIA))
    estado: list[TicketSeguido] = []
    for t, r, rp in zip(ts, resueltos, posteriores_resueltos, strict=True):
        ok = rp if t.clase is POST else r
        estado.append(resolver(t) if ok else seguido(t, obs(ET.EN_CURSO, False)))
    de_cierre_ok = all(ticket_resuelto(s) for s in estado if s.ticket.clase is not POST)
    assert solicitud_cerrable(estado) is de_cierre_ok
    # cambiar el estado de un posterior no altera nada
    alterado = [
        seguido(s.ticket, obs(ET.CERRADO, True, docs=1)) if s.ticket.clase is POST else s
        for s in estado
    ]
    assert solicitud_cerrable(alterado) is de_cierre_ok


# --- S-07: estado del colaborador --------------------------------------------------------------


def test_estado_derivado_del_colaborador_S_07() -> None:
    c = caso(TipoEvento.ING)
    ts = tickets(c)
    assert estado_derivado_del_colaborador(c.solicitud, [seguido(t, None) for t in ts]) is None
    assert estado_derivado_del_colaborador(c.solicitud, []) is None
    assert (
        estado_derivado_del_colaborador(c.solicitud, [resolver(t) for t in ts])
        is EstadoColaborador.ACTIVO
    )
    casi = [resolver(t, ok=t.cola is not AD) for t in ts]
    assert estado_derivado_del_colaborador(c.solicitud, casi) is None

    v = caso(TipoEvento.VAC)
    tv = tickets(v)
    solo_suspension = [
        resolver(t) if t.clase is I else seguido(t, obs(ET.EN_ESPERA, False)) for t in tv
    ]
    assert (
        estado_derivado_del_colaborador(v.solicitud, solo_suspension)
        is EstadoColaborador.SUSPENDIDO
    )
    assert (
        estado_derivado_del_colaborador(v.solicitud, [resolver(t) for t in tv])
        is EstadoColaborador.ACTIVO
    )
    assert estado_derivado_del_colaborador(v.solicitud, [seguido(t, None) for t in tv]) is None

    for tipo, sub in ((TipoEvento.RET, Subtipo.RENUNCIA), (TipoEvento.EMG, Subtipo.FUGA_DETECTADA)):
        r = caso(tipo, sub)
        tr = tickets(r)
        assert (
            estado_derivado_del_colaborador(r.solicitud, [resolver(t) for t in tr])
            is EstadoColaborador.RETIRADO
        )
        asi = [resolver(t) if t.clase is I else seguido(t, None) for t in tr]
        assert estado_derivado_del_colaborador(r.solicitud, asi) is EstadoColaborador.RETIRADO
        assert estado_derivado_del_colaborador(r.solicitud, [seguido(t, None) for t in tr]) is None

    for tipo in (TipoEvento.CDP, TipoEvento.CSU):
        x = caso(tipo)
        assert (
            estado_derivado_del_colaborador(x.solicitud, [resolver(t) for t in tickets(x)]) is None
        )


# --- tabla de derivacion SRS 4.7, fila por fila -------------------------------------------------

# (nombre, caso, cola, clase, accion, cuenta previa, estado mientras abierto, estado al resolver, marca abierta)
FILAS = [
    pytest.param(caso(TipoEvento.ING), AD, I, None, E.PENDIENTE_ALTA, E.ACTIVA, None, id="ING"),
    pytest.param(caso(TipoEvento.VAC), AD, I, E.ACTIVA, E.PENDIENTE_SUSPENSION, E.SUSPENDIDA, None, id="VAC suspension"),
    pytest.param(caso(TipoEvento.VAC), AD, P, E.SUSPENDIDA, E.SUSPENDIDA, E.ACTIVA, None, id="VAC reactivacion"),
    pytest.param(caso(TipoEvento.CDP), AD, I, E.ACTIVA, E.ACTIVA, E.ACTIVA, M.CAMBIO_PENDIENTE, id="CDP"),
    pytest.param(caso(TipoEvento.CSU), AD, I, E.ACTIVA, E.ACTIVA, E.ACTIVA, M.CAMBIO_PENDIENTE, id="CSU"),
    pytest.param(caso(TipoEvento.RET, Subtipo.RENUNCIA), AD, I, E.ACTIVA, E.PENDIENTE_BAJA, E.DESHABILITADA, None, id="RET"),
    pytest.param(caso(TipoEvento.EMG, Subtipo.FUGA_DETECTADA), AD, I, E.ACTIVA, E.PENDIENTE_BAJA, E.DESHABILITADA, None, id="EMG"),
    pytest.param(caso(TipoEvento.RET, Subtipo.RENUNCIA), AD, POST, E.DESHABILITADA, E.DESHABILITADA, E.ELIMINADA, None, id="eliminacion"),
]  # fmt: skip


@pytest.mark.parametrize(("c", "cola", "clase", "previo", "abierto", "resuelto", "marca"), FILAS)
def test_fila_de_la_tabla_4_7(
    c: Caso,
    cola: Cola,
    clase: ClaseTicket,
    previo: EstadoDeCuenta | None,
    abierto: EstadoDeCuenta,
    resuelto: EstadoDeCuenta,
    marca: MarcaDeCuenta | None,
) -> None:
    t = elegir(c, cola, clase)
    cuenta = None if previo is None else dataclasses.replace(
        cuenta_de(t, previo), ticket_origen="otro", orden_origen=(AHORA - timedelta(days=9), AHORA)
    )  # fmt: skip
    # mientras esta abierto
    r1 = derivar(cuenta, t, None, obs(ET.EN_CURSO, False), TARDE)
    assert r1.cuenta is not None
    assert (r1.cuenta.estado, r1.cuenta.marca) == (abierto, marca)
    # al resolverse con solucion
    r2 = derivar(r1.cuenta, t, obs(ET.EN_CURSO, False), obs(ET.RESUELTO, True, minutos=5), TARDE)
    assert r2.cuenta is not None
    assert (r2.cuenta.estado, r2.cuenta.marca) == (resuelto, None)
    assert r2.cambio is not None
    assert r2.cambio.estado_nuevo is resuelto
    assert r2.cambio.estado_anterior is r1.cuenta.estado
    assert r2.cuenta.ticket_origen == t.clave_de_idempotencia
    assert [e.accion for e in r2.eventos] == ["cuenta.estado_derivado"]


def test_las_dos_tablas_cubren_todas_las_acciones_con_cuenta() -> None:
    acciones = set(A) - {A.EQUIPO}
    assert set(ESTADO_AL_RESOLVERSE) == acciones
    assert set(ESTADO_MIENTRAS_ESTA_ABIERTO) == acciones


@pytest.mark.parametrize(
    ("cola", "sistema"),
    [(AD, SistemaDeCuenta.AD), (COM, SistemaDeCuenta.RED), (LIC, SistemaDeCuenta.M365)],
)
def test_cada_cola_deriva_la_cuenta_de_su_sistema(cola: Cola, sistema: SistemaDeCuenta) -> None:
    t = elegir(caso(TipoEvento.ING), cola)
    r = derivar(None, t, None, obs(ET.RESUELTO, True))
    assert r.cuenta is not None
    assert r.cuenta.sistema is sistema
    assert r.cuenta.estado is E.ACTIVA


def test_inventario_no_deriva_cuentas() -> None:
    t = elegir(caso(TipoEvento.ING), INV)
    r = derivar(None, t, None, obs(ET.RESUELTO, True, docs=1))
    assert (r.cuenta, r.cambio, r.eventos) == (None, None, ())


def test_un_programado_que_aun_no_llega_su_fecha_no_cambia_la_cuenta() -> None:
    t = elegir(caso(TipoEvento.VAC), AD, P)
    base = cuenta_de(t, E.SUSPENDIDA)
    base = dataclasses.replace(base, ticket_origen="susp", orden_origen=(AHORA, AHORA))
    r = derivar(base, t, None, obs(ET.EN_ESPERA, False), AHORA)
    assert r.cuenta == base
    assert r.cambio is None
    # el dia de regreso ya es pendiente
    r2 = derivar(base, t, None, obs(ET.NUEVO, False), TARDE)
    assert r2.cuenta is not None
    assert r2.cuenta.ticket_origen == t.clave_de_idempotencia


# --- reglas complementarias ---------------------------------------------------------------------


def test_cierre_sin_solucion_no_cambia_la_cuenta_RF_24_T5() -> None:
    t = elegir(caso(TipoEvento.RET, Subtipo.RENUNCIA), AD)
    abierta = derivar(cuenta_de(t, E.ACTIVA), t, None, obs(ET.EN_CURSO, False), TARDE).cuenta
    assert abierta is not None
    assert abierta.estado is E.PENDIENTE_BAJA
    r = derivar(abierta, t, obs(ET.EN_CURSO, False), obs(ET.RESUELTO, False, minutos=5), TARDE)
    assert r.cuenta is not None
    assert r.cuenta.estado is E.PENDIENTE_BAJA  # sigue la exposicion
    assert r.cuenta.marca is M.CIERRE_SIN_SOLUCION


def test_cierre_sin_solucion_de_un_alta_sin_cuenta_previa() -> None:
    t = elegir(caso(TipoEvento.ING), AD)
    r = derivar(None, t, None, obs(ET.CERRADO, False))
    assert r.cuenta is not None
    assert (r.cuenta.estado, r.cuenta.marca) == (E.PENDIENTE_ALTA, M.CIERRE_SIN_SOLUCION)


def test_reabierto_devuelve_la_cuenta_al_estado_previo_RF_25() -> None:
    t = elegir(caso(TipoEvento.RET, Subtipo.RENUNCIA), AD)
    o1, o2, o3 = (
        obs(ET.EN_CURSO, False),
        obs(ET.RESUELTO, True, minutos=5),
        obs(ET.EN_CURSO, False, minutos=9),
    )
    c1 = derivar(cuenta_de(t, E.ACTIVA), t, None, o1, TARDE).cuenta
    c2 = derivar(c1, t, o1, o2, TARDE).cuenta
    r3 = derivar(c2, t, o2, o3, TARDE)
    assert c1 is not None
    assert c2 is not None
    assert c2.estado is E.DESHABILITADA
    assert r3.cuenta is not None
    assert (
        (r3.cuenta.estado, r3.cuenta.marca)
        == (c1.estado, M.REABIERTO)
        == (E.PENDIENTE_BAJA, M.REABIERTO)
    )
    assert [e.accion for e in r3.eventos] == ["cuenta.reabierta"]
    # la marca persiste mientras siga abierto y no genera ruido
    o4 = obs(ET.EN_CURSO, False, minutos=14)
    r4 = derivar(r3.cuenta, t, o3, o4, TARDE)
    assert r4.cuenta == r3.cuenta
    assert r4.cambio is None
    # al resolverse de nuevo, la marca se limpia
    r5 = derivar(r4.cuenta, t, o4, obs(ET.RESUELTO, True, minutos=20), TARDE)
    assert r5.cuenta is not None
    assert (r5.cuenta.estado, r5.cuenta.marca) == (E.DESHABILITADA, None)


def test_reabierto_en_un_CDP_conserva_el_estado_y_marca_reabierto() -> None:
    t = elegir(caso(TipoEvento.CDP), AD)
    o1, o2 = obs(ET.RESUELTO, True), obs(ET.EN_CURSO, False, minutos=5)
    c1 = derivar(cuenta_de(t, E.ACTIVA), t, None, o1, TARDE).cuenta
    r = derivar(c1, t, o1, o2, TARDE)
    assert r.cuenta is not None
    assert (r.cuenta.estado, r.cuenta.marca) == (E.ACTIVA, M.REABIERTO)


# --- S-09, S-10, S-11 ----------------------------------------------------------------------------


def test_S_09_sin_cuenta_una_baja_posterior_se_ignora_y_se_audita_una_sola_vez() -> None:
    t = elegir(caso(TipoEvento.RET, Subtipo.RENUNCIA), AD, POST)
    r = derivar(None, t, None, obs(ET.RESUELTO, True), TARDE)
    assert (r.cuenta, r.cambio) == (None, None)
    assert [e.accion for e in r.eventos] == ["cuenta.inexistente"]
    repetida = derivar(None, t, obs(ET.RESUELTO, True), obs(ET.RESUELTO, True, minutos=5), TARDE)
    assert repetida.eventos == ()  # misma observacion de nuevo: sin ruido


def test_S_10_prevalece_el_ticket_mas_reciente_por_fecha_de_emision() -> None:
    cdp = elegir(caso(TipoEvento.CDP, numero=1), AD)
    ret_caso = caso(TipoEvento.RET, Subtipo.RENUNCIA, numero=2)
    ret = elegir(ret_caso, AD)
    ret = dataclasses.replace(
        ret, emitido_en=AHORA + timedelta(hours=1), vence_en=AHORA + timedelta(days=9)
    )
    gobierna = cuenta_de(ret, E.PENDIENTE_BAJA)
    # el CDP (mas antiguo) se resuelve despues: no puede reactivar la cuenta
    r = derivar(gobierna, cdp, obs(ET.EN_CURSO, False), obs(ET.RESUELTO, True, minutos=5), TARDE)
    assert r.cuenta == gobierna
    assert r.cambio is None


def test_S_10_el_mas_reciente_toma_el_control_aunque_llegue_primero() -> None:
    cdp = elegir(caso(TipoEvento.CDP, numero=1), AD)
    cuenta_cdp = derivar(cuenta_de(cdp, E.ACTIVA), cdp, None, obs(ET.EN_CURSO, False), TARDE).cuenta
    ret = dataclasses.replace(
        elegir(caso(TipoEvento.RET, Subtipo.RENUNCIA, numero=2), AD),
        emitido_en=AHORA + timedelta(hours=1),
        vence_en=AHORA + timedelta(days=9),
    )
    r = derivar(cuenta_cdp, ret, None, obs(ET.NUEVO, False), TARDE)
    assert r.cuenta is not None
    assert (r.cuenta.estado, r.cuenta.ticket_origen) == (
        E.PENDIENTE_BAJA,
        ret.clave_de_idempotencia,
    )
    assert r.cuenta.marca is None  # el cambio pendiente se limpia


def test_S_11_reabrir_un_ticket_antiguo_marca_pero_no_cambia_el_estado() -> None:
    cdp = elegir(caso(TipoEvento.CDP, numero=1), AD)
    ret = dataclasses.replace(
        elegir(caso(TipoEvento.RET, Subtipo.RENUNCIA, numero=2), AD),
        emitido_en=AHORA + timedelta(hours=1),
        vence_en=AHORA + timedelta(days=9),
    )
    gobierna = cuenta_de(ret, E.DESHABILITADA)
    r = derivar(gobierna, cdp, obs(ET.RESUELTO, True), obs(ET.EN_CURSO, False, minutos=5), TARDE)
    assert r.cuenta is not None
    assert (r.cuenta.estado, r.cuenta.marca) == (E.DESHABILITADA, M.REABIERTO)
    assert r.cuenta.ticket_origen == ret.clave_de_idempotencia
    assert [e.accion for e in r.eventos] == ["cuenta.reapertura_de_ticket_antiguo"]
    # repetirlo no vuelve a escribir historial
    otra = derivar(
        r.cuenta, cdp, obs(ET.EN_CURSO, False, minutos=5), obs(ET.EN_CURSO, False, minutos=9), TARDE
    )
    assert otra.cuenta == r.cuenta
    assert otra.cambio is None


def test_una_observacion_mas_vieja_se_ignora() -> None:
    t = elegir(caso(TipoEvento.ING), AD)
    nueva, vieja = obs(ET.RESUELTO, True, minutos=10), obs(ET.EN_CURSO, False, minutos=2)
    c = derivar(None, t, None, nueva).cuenta
    r = derivar(c, t, nueva, vieja)
    assert r.cuenta == c
    assert r.cambio is None


# --- RD-11: no hay forma de editar una cuenta a mano ---------------------------------------------


def test_RD_11_cuenta_no_expone_operaciones_de_edicion() -> None:
    publicos = [n for n, v in vars(Cuenta).items() if not n.startswith("_") and callable(v)]
    assert publicos == []
    with pytest.raises(dataclasses.FrozenInstanceError):
        cuenta_de(elegir(caso(TipoEvento.ING), AD), E.ACTIVA).estado = E.ELIMINADA  # type: ignore[misc]


def test_RD_11_la_unica_funcion_publica_que_produce_cuentas_es_derivar_cuenta() -> None:
    funciones = [
        n
        for n, v in vars(modulo_cuentas).items()
        if inspect.isfunction(v)
        and v.__module__ == modulo_cuentas.__name__
        and not n.startswith("_")
    ]
    assert funciones == ["derivar_cuenta"]


def test_el_historial_de_un_cambio_lleva_ticket_y_fecha() -> None:
    t = elegir(caso(TipoEvento.ING), AD)
    r = derivar(None, t, None, obs(ET.RESUELTO, True), TARDE)
    assert r.cambio is not None
    assert (r.cambio.ticket, r.cambio.fecha, r.cambio.estado_anterior) == (
        t.clave_de_idempotencia,
        TARDE,
        None,
    )
    assert r.cambio.colaborador_id == "col-1"
    with pytest.raises(DatoInvalido):
        derivar(None, t, None, obs(ET.RESUELTO, True), datetime(2026, 1, 1))


# --- P7 ------------------------------------------------------------------------------------------

OBSERVACIONES = st.lists(
    st.tuples(st.sampled_from(list(ET)), st.booleans(), st.integers(0, 2)), min_size=1, max_size=8
)


@pytest.mark.parametrize(
    "c",
    [
        pytest.param(caso(TipoEvento.RET, Subtipo.RENUNCIA), id="RET"),
        pytest.param(caso(TipoEvento.CDP), id="CDP"),
        pytest.param(caso(TipoEvento.ING), id="ING"),
    ],
)
@given(secuencia=OBSERVACIONES)
def test_P7_observar_dos_veces_lo_mismo_no_cambia_nada(
    c: Caso, secuencia: list[tuple[ET, bool, int]]
) -> None:
    t = elegir(c, AD)
    cuenta: Cuenta | None = None if c.solicitud.tipo is TipoEvento.ING else cuenta_de(t, E.ACTIVA)
    if cuenta is not None:
        cuenta = dataclasses.replace(
            cuenta, ticket_origen="previo", orden_origen=(AHORA - timedelta(days=1), AHORA)
        )
    anterior: Observacion | None = None
    for i, (estado, sol, docs) in enumerate(secuencia):
        actual = obs(estado, sol, docs, minutos=i)
        primera = derivar(cuenta, t, anterior, actual, TARDE)
        segunda = derivar(primera.cuenta, t, actual, actual, TARDE)
        assert segunda.cuenta == primera.cuenta
        assert segunda.cambio is None
        assert segunda.eventos == ()
        cuenta, anterior = primera.cuenta, actual


@given(secuencia=OBSERVACIONES)
def test_P7_reabrir_devuelve_el_estado_previo(secuencia: list[tuple[ET, bool, int]]) -> None:
    t = elegir(caso(TipoEvento.RET, Subtipo.RENUNCIA), AD)
    base = dataclasses.replace(
        cuenta_de(t, E.ACTIVA),
        ticket_origen="previo",
        orden_origen=(AHORA - timedelta(days=1), AHORA),
    )
    abierta = derivar(base, t, None, obs(ET.EN_CURSO, False), TARDE).cuenta
    cuenta, anterior = abierta, obs(ET.EN_CURSO, False)
    for i, (estado, sol, docs) in enumerate(secuencia, start=1):
        actual = obs(estado, sol, docs, minutos=i)
        r = derivar(cuenta, t, anterior, actual, TARDE)
        if anterior.resuelta and not actual.resuelta and anterior.tiene_solucion:
            assert abierta is not None
            assert r.cuenta is not None
            assert r.cuenta.estado is abierta.estado  # vuelve al estado «mientras esta abierto»
            assert r.cuenta.marca is M.REABIERTO
        cuenta, anterior = r.cuenta, actual


@given(
    st.permutations(range(3)),
    st.lists(st.tuples(st.sampled_from(list(ET)), st.booleans()), min_size=3, max_size=3),
)
def test_P7_el_resultado_no_depende_del_orden_entre_sistemas(
    orden: list[int], resultados: list[tuple[ET, bool]]
) -> None:
    c = caso(TipoEvento.ING)
    ts = [elegir(c, cola) for cola in (AD, COM, LIC)]

    def aplicar(indices: list[int]) -> dict[SistemaDeCuenta, Cuenta | None]:
        cuentas: dict[SistemaDeCuenta, Cuenta | None] = {}
        for i in indices:
            t = ts[i]
            assert t.sistema is not None
            estado, sol = resultados[i]
            cuentas[t.sistema] = derivar(
                cuentas.get(t.sistema), t, None, obs(estado, sol), TARDE
            ).cuenta
        return cuentas

    assert aplicar(orden) == aplicar([0, 1, 2])


def test_combinaciones_estado_solucion_nunca_dejan_una_cuenta_activa_sin_solucion() -> None:
    """T5: ningun camino marca `activa` sin que el ticket tenga estado resuelto y solucion."""
    t = elegir(caso(TipoEvento.ING), AD)
    for estado, sol in itertools.product(ET, [True, False]):
        r = derivar(None, t, None, obs(estado, sol), TARDE)
        assert r.cuenta is not None
        if r.cuenta.estado is E.ACTIVA:
            assert estado >= ET.RESUELTO
            assert sol


def test_utc_en_el_modulo() -> None:
    assert AHORA.tzinfo is UTC
