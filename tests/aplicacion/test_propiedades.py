"""Propiedades P1 (deduplicacion), P10 (confidencialidad) y auditoria de cada caso de uso (RF-35)."""

import dataclasses
import json
import string
from collections.abc import Callable
from datetime import timedelta

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from jml.aplicacion.bandeja import espera_de_reintento
from jml.aplicacion.dtos import FiltroDeCuentas
from jml.dominio.errores import ErrorDeDominio, SolicitudDuplicada
from jml.dominio.tipos import ESTADOS_ABIERTOS, EstadoSolicitud, Subtipo, TipoEvento
from jml.dominio.valores import SolicitudId
from tests.mundo import (
    Mundo,
    cambio_de_departamento,
    cambio_de_sucursal,
    emergencia,
    ingreso,
    retiro,
    vacaciones,
)

# --- P1: deduplicacion ---------------------------------------------------------------------


def abiertas_por_clave(m: Mundo) -> dict[tuple[str, TipoEvento], list[str]]:
    claves: dict[tuple[str, TipoEvento], list[str]] = {}
    for s in m.repos.almacen.solicitudes.values():
        if s.estado in ESTADOS_ABIERTOS:
            claves.setdefault((s.colaborador_id, s.tipo), []).append(s.id.valor)
    return claves


REGISTRO = {
    "vac": lambda m: m.registrar(vacaciones()),
    "cdp": lambda m: m.registrar(cambio_de_departamento(destino="Comercial")),
    "csu": lambda m: m.registrar(cambio_de_sucursal(sede="Medellín", traslada=False)),
    "ret": lambda m: m.registrar(retiro("u-col", subtipo=Subtipo.RENUNCIA)),
    "emg": lambda m: m.emitir(emergencia()),
}


def crear_tickets(m: Mundo) -> None:
    """La bandeja crea los tickets en GLPI: las solicitudes pasan a `en_ejecucion`."""
    m.glpi.recuperar()
    m.correr_bandeja_hasta_vaciar()


def cerrar(m: Mundo) -> None:
    """Los tecnicos resuelven todo y la sincronizacion cierra las solicitudes."""
    crear_tickets(m)
    for s in list(m.repos.almacen.solicitudes.values()):
        m.tecnico_resuelve_todo(s.id)
    m.avanzar(timedelta(minutes=5))
    m.sincronizar()


def caida_larga(m: Mundo) -> None:
    """GLPI cae 10 rondas seguidas: las solicitudes aprobadas pasan a `error`."""
    m.glpi.caer()
    for ronda in range(1, 11):
        m.bandeja()
        m.avanzar(espera_de_reintento(ronda))


OPERACIONES = {"crear_tickets": crear_tickets, "cerrar": cerrar, "caida_larga": caida_larga}


@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    st.lists(
        st.one_of(
            st.tuples(st.just("registrar"), st.sampled_from(sorted(REGISTRO))),
            st.tuples(st.sampled_from(["aprobar", "rechazar", "cancelar"]), st.integers(0, 6)),
            st.tuples(st.sampled_from(sorted(OPERACIONES)), st.just(0)),
        ),
        max_size=22,
    )
)
def test_P1_nunca_hay_dos_abiertas_del_mismo_colaborador_y_tipo(
    operaciones: list[tuple[str, str | int]],
) -> None:
    m = Mundo.nuevo()
    for accion, parametro in operaciones:
        existentes = sorted(m.repos.almacen.solicitudes.values(), key=lambda s: s.id.valor)
        duplicado: SolicitudDuplicada | None = None
        try:
            if accion == "registrar":
                assert isinstance(parametro, str)
                REGISTRO[parametro](m)
            elif accion in OPERACIONES:
                OPERACIONES[accion](m)
            elif existentes:
                destino = existentes[int(parametro) % len(existentes)]
                if accion == "aprobar":
                    m.aprobar("u-rrhh", destino.id)
                elif accion == "rechazar":
                    m.rechazar("u-rrhh", destino.id, "no procede")
                else:
                    pendiente = destino.estado is EstadoSolicitud.PENDIENTE_APROBACION
                    m.cancelar("u-col" if pendiente else "u-rrhh", destino.id)
        except SolicitudDuplicada as dup:
            duplicado = dup
        except ErrorDeDominio:
            pass
        if duplicado is not None:  # apunta a una solicitud que REALMENTE esta abierta (RF-09)
            assert m.repos.almacen.solicitudes[duplicado.existente_id].estado in ESTADOS_ABIERTOS
        for clave, ids in abiertas_por_clave(m).items():
            assert len(ids) == 1, f"{clave} tiene {ids} abiertas"
    assert m.repos.auditoria().verificar().valida


def test_P1_tras_un_estado_final_se_vuelve_a_registrar() -> None:
    m = Mundo.nuevo()
    for _ in range(3):
        r = m.registrar(vacaciones())
        with pytest.raises(SolicitudDuplicada):
            m.registrar(vacaciones())
        m.rechazar("u-rrhh", r.solicitud_id, "x")
    assert len(m.repos.almacen.solicitudes) == 3


# --- P10: confidencialidad de los campos restringidos --------------------------------------

centinelas = st.text(alphabet=string.ascii_letters + string.digits, min_size=10, max_size=24).map(
    lambda t: "ZQX" + t
)


def todo_lo_que_sale(m: Mundo, centinela: str) -> list[str]:
    """Cada texto que el nucleo entrega a un puerto de salida o a un rol distinto de RRHH."""
    salidas: list[str] = []
    for r in m.repos.auditoria().registros():
        salidas += [repr(r), r.contenido().decode("utf-8")]
    for t in m.glpi.tickets_remotos():
        salidas += [t.como_texto(), repr(t)]
    for ind in (m.dashboard("u-tec-ad"), m.dashboard("u-tec-inv")):
        salidas += [repr(ind), json.dumps(dataclasses.asdict(ind), default=str)]
    salidas += [repr(m.buscar("u-tec-lic", FiltroDeCuentas()))]
    for cid in list(m.repos.almacen.colaboradores):
        f = m.ficha("u-tec-ad", cid)
        salidas += [repr(f), json.dumps(dataclasses.asdict(f), default=str)]
    for d in m.repos.almacen.decisiones:
        salidas.append(repr(d))
    for c in m.repos.almacen.cuentas.values():
        salidas.append(repr(c))
    for e in m.repos.almacen.bandeja.values():
        salidas.append(repr(e))
    for s in m.repos.almacen.solicitudes.values():
        salidas.append(repr(s))  # ni siquiera el repr de la solicitud lo muestra
    assert centinela  # evita una prueba vacia
    return salidas


@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    centinelas,
    st.sampled_from(
        [
            (TipoEvento.RET, Subtipo.RENUNCIA),
            (TipoEvento.RET, Subtipo.FIN_DE_CONTRATO),
            (TipoEvento.EMG, Subtipo.FUGA_DETECTADA),
            (TipoEvento.EMG, Subtipo.DESPIDO_CON_JUSTA_CAUSA),
        ]
    ),
)
def test_P10_ninguna_salida_contiene_el_motivo_ni_la_descripcion(
    centinela: str, par: tuple[TipoEvento, Subtipo]
) -> None:
    tipo, sub = par
    m = Mundo.nuevo()
    base = (
        retiro(restringido=centinela, subtipo=sub)
        if tipo is TipoEvento.RET
        else dataclasses.replace(emergencia(subtipo=sub), restringido=centinela)
    )
    r = m.emitir(base)
    assert m.solicitud(r.solicitud_id).restringido is not None  # esta guardado (solo RRHH lo lee)
    m.correr_bandeja_hasta_vaciar()
    m.sincronizar()
    m.tecnico_resuelve_todo(r.solicitud_id)
    m.avanzar(timedelta(minutes=5))
    m.sincronizar()
    # un intento fallido tampoco puede filtrarlo en su mensaje de error
    try:
        m.emitir(base)
    except ErrorDeDominio as e:
        salidas_de_error = [str(e), repr(e), repr(e.datos)]
    else:  # pragma: no cover - el duplicado debe fallar
        raise AssertionError("se esperaba un duplicado")
    for texto in [*todo_lo_que_sale(m, centinela), *salidas_de_error]:
        assert centinela not in texto


def test_P10_el_restringido_solo_sale_por_revelar() -> None:
    m = Mundo.nuevo()
    r = m.emitir(retiro(restringido="MOTIVO-CONFIDENCIAL-1"))
    assert m.solicitud(r.solicitud_id).restringido.revelar() == "MOTIVO-CONFIDENCIAL-1"  # type: ignore[union-attr]  # existe


# --- RF-35: cada caso de uso deja su evento y la cadena verifica ------------------------------


def _registrar(m: Mundo) -> None:
    m.registrar(vacaciones())


def _emitir(m: Mundo) -> None:
    m.emitir(retiro())


def _excepcion(m: Mundo) -> None:
    m.emitir_por_excepcion(
        dataclasses.replace(vacaciones("u-admin", "col-rrhh"), justificacion="x")
    )


def _aprobar(m: Mundo) -> None:
    m.aprobar("u-rrhh", m.registrar(vacaciones()).solicitud_id)


def _rechazar(m: Mundo) -> None:
    m.rechazar("u-rrhh", m.registrar(vacaciones()).solicitud_id, "no")


def _cancelar(m: Mundo) -> None:
    m.cancelar("u-col", m.registrar(vacaciones()).solicitud_id)


def _bandeja(m: Mundo) -> None:
    m.emitir(ingreso())
    m.bandeja()


def _error(m: Mundo) -> None:
    m.emitir(ingreso())
    m.soportes.perder(m.soportes.nombres()[0])
    m.bandeja()


def _reintento(m: Mundo) -> None:
    r = m.emitir(ingreso())
    m.soportes.perder(m.soportes.nombres()[0])
    m.bandeja()
    m.reintentar("u-admin", r.solicitud_id)


def _sincronizar(m: Mundo) -> None:
    m.emitir(ingreso())
    m.correr_bandeja_hasta_vaciar()
    m.sincronizar()


def _cerrar(m: Mundo) -> None:
    r = m.emitir(ingreso())
    m.correr_bandeja_hasta_vaciar()
    m.tecnico_resuelve_todo(r.solicitud_id)
    m.sincronizar()


def _ficha(m: Mundo) -> None:
    m.ficha("u-tec-ad", "col-1")


def _emergencia(m: Mundo) -> None:
    m.registrar(vacaciones())
    m.emitir(emergencia())


def _sin_tickets(m: Mundo) -> None:
    m.aprobar("u-rrhh", m.registrar(cambio_de_departamento(destino="Finanzas")).solicitud_id)


CASOS: list[tuple[str, Callable[[Mundo], None], str, str]] = [
    ("registrar", _registrar, "solicitud.registrada", "u-col"),
    ("emitir", _emitir, "solicitud.emitida", "u-rrhh"),
    ("emitir por excepcion", _excepcion, "solicitud.emitida_por_excepcion", "u-admin"),
    ("aprobar", _aprobar, "solicitud.aprobada", "u-rrhh"),
    ("aprobar: tickets", _aprobar, "solicitud.tickets_encolados", "u-rrhh"),
    ("rechazar", _rechazar, "solicitud.rechazada", "u-rrhh"),
    ("cancelar", _cancelar, "solicitud.cancelada", "u-col"),
    ("bandeja: ticket", _bandeja, "ticket.creado", "sistema:worker"),
    ("bandeja: soporte", _bandeja, "soporte.subido", "sistema:worker"),
    ("bandeja: ejecucion", _bandeja, "solicitud.en_ejecucion", "sistema:worker"),
    ("bandeja: error", _error, "solicitud.error", "sistema:worker"),
    ("reintentar", _reintento, "solicitud.reintentada", "u-admin"),
    ("sincronizar: estado", _sincronizar, "ticket.estado_sincronizado", "sistema:worker"),
    ("sincronizar: cuenta", _cerrar, "cuenta.estado_derivado", "sistema:worker"),
    ("sincronizar: cierre", _cerrar, "solicitud.cerrada", "sistema:worker"),
    ("sincronizar: colaborador", _cerrar, "colaborador.estado_derivado", "sistema:worker"),
    ("ficha", _ficha, "ficha.consultada", "u-tec-ad"),
    ("emergencia marca otras", _emergencia, "solicitud.marcada_para_revision", "u-rrhh"),
    ("sin diferencia", _sin_tickets, "solicitud.sin_tickets", "u-rrhh"),
]


@pytest.mark.parametrize(("nombre", "accion", "evento", "actor"), CASOS, ids=[c[0] for c in CASOS])
def test_RF_35_cada_caso_de_uso_deja_su_evento_y_la_cadena_verifica(
    nombre: str, accion: Callable[[Mundo], None], evento: str, actor: str
) -> None:
    m = Mundo.nuevo()
    accion(m)
    registros = [r for r in m.repos.auditoria().registros() if r.accion == evento]
    assert registros, f"{nombre}: falta {evento}; hay {sorted(set(m.acciones_de_auditoria()))}"
    assert registros[0].actor == actor
    assert m.repos.auditoria().verificar().valida
    assert [r.secuencia for r in m.repos.auditoria().registros()] == list(
        range(1, len(m.repos.auditoria().registros()) + 1)
    )


def test_RF_35_la_ficha_fallida_no_audita() -> None:
    m = Mundo.nuevo()
    with pytest.raises(ErrorDeDominio):
        m.ficha("u-tec-ad", "no-existe")
    assert "ficha.consultada" not in m.acciones_de_auditoria()


def test_RF_35_los_actores_de_la_auditoria_nunca_son_vacios() -> None:
    m = Mundo.nuevo()
    _cerrar(m)
    assert all(r.actor for r in m.repos.auditoria().registros())
    assert SolicitudId.de(2026, 1).valor in {r.objeto for r in m.repos.auditoria().registros()}
