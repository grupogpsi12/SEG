"""Bandeja de salida: reintentos, idempotencia y paso a `error` (RF-18, RF-21, RF-38, RF-40, CA-07, P8)."""

from dataclasses import replace
from datetime import timedelta

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from jml.aplicacion.bandeja import (
    ESPERAS_DE_REINTENTO,
    MAX_INTENTOS,
    EntradaDeBandeja,
    EstadoDeEntrada,
    espera_de_reintento,
)
from jml.dominio.errores import (
    CancelacionNoPermitida,
    DatoInvalido,
    NoAutorizado,
    TransicionInvalida,
)
from jml.dominio.tipos import EstadoDeSoporte, EstadoDeTicket, EstadoSolicitud
from tests.dobles.glpi import Fallo
from tests.mundo import Mundo, ingreso, retiro, vacaciones

S = EstadoSolicitud


def emitir_vac(m: Mundo):  # type: ignore[no-untyped-def]  # devuelve SolicitudRegistrada
    return m.emitir(replace(vacaciones("u-rrhh"), justificacion="ok"))


def entradas(m: Mundo, sid) -> list[EntradaDeBandeja]:  # type: ignore[no-untyped-def]  # sid: SolicitudId
    with m.repos.unidad_de_trabajo() as u:
        return list(u.bandeja.de_solicitud(sid))


# --- politica de espera (S-13) --------------------------------------------------------------


def test_S_13_esperas_crecientes_y_tope_de_15_minutos() -> None:
    esperado = [30, 60, 120, 300, 600, 900, 900, 900, 900, 900, 900, 900]
    assert [espera_de_reintento(n).total_seconds() for n in range(1, 13)] == esperado
    assert ESPERAS_DE_REINTENTO[-1] == timedelta(minutes=15)
    with pytest.raises(DatoInvalido):
        espera_de_reintento(0)


def test_la_espera_es_funcion_pura_del_numero_de_intento() -> None:
    assert espera_de_reintento(3) == espera_de_reintento(3)
    assert MAX_INTENTOS == 10  # RF-18


# --- camino feliz -----------------------------------------------------------------------------


def test_RNF_07_la_bandeja_crea_los_tickets_y_la_solicitud_pasa_a_en_ejecucion() -> None:
    m = Mundo.nuevo()
    r = emitir_vac(m)
    res = m.bandeja()
    assert (res.procesadas, res.creadas, res.reintentos_programados) == (4, 4, 0)
    assert res.solicitudes_en_ejecucion == (r.solicitud_id,)
    s = m.solicitud(r.solicitud_id)
    assert s.estado is S.EN_EJECUCION
    assert len(s.tickets) == 4
    assert all(n == 1 for n in m.glpi.creaciones_reales.values())
    with m.repos.unidad_de_trabajo() as u:
        assert {e.estado for e in u.bandeja.de_solicitud(r.solicitud_id)} == {
            EstadoDeEntrada.ENVIADA
        }
        assert all(t.id_externo is not None for t in u.tickets.de_solicitud(r.solicitud_id))
    assert m.acciones_de_auditoria().count("ticket.creado") == 4
    assert m.repos.auditoria().verificar().valida


def test_RF_17_los_programados_nacen_en_espera_en_glpi() -> None:
    m = Mundo.nuevo()
    r = emitir_vac(m)
    m.bandeja()
    with m.repos.unidad_de_trabajo() as u:
        por_clave = {t.ticket.clave_de_idempotencia: t for t in u.tickets.creados()}
    ids = {clave: t.id_externo or "" for clave, t in por_clave.items()}
    estados = {clave: m.glpi.leer_tickets([i])[i].estado for clave, i in ids.items()}
    assert sorted(v.name for v in estados.values()) == ["EN_ESPERA", "EN_ESPERA", "NUEVO", "NUEVO"]
    assert r.solicitud_id.valor in next(iter(estados))


def test_RF_21_se_asegura_el_usuario_de_glpi_una_vez() -> None:
    m = Mundo.nuevo()
    emitir_vac(m)
    m.bandeja()
    assert m.colaborador("col-1").id_usuario_glpi == "u-col-1"


def test_la_bandeja_vacia_no_hace_nada() -> None:
    m = Mundo.nuevo()
    res = m.bandeja()
    assert (res.procesadas, res.creadas) == (0, 0)
    assert m.glpi.llamadas == 0


# --- soporte (RF-40, CA-18, RD-12) ---------------------------------------------------------


def test_RF_40_el_soporte_se_sube_una_vez_se_vincula_a_AD_y_Licencias_y_se_borra_la_copia() -> None:
    m = Mundo.nuevo()
    r = m.emitir(ingreso())
    nombre = m.soportes.nombres()[0]
    m.bandeja()
    assert m.glpi.subidas_reales == 1
    assert m.glpi.documentos_subidos() == 1
    with m.repos.unidad_de_trabajo() as u:
        soporte = u.soportes.obtener(r.solicitud_id)
        assert soporte is not None
        assert (soporte.estado, soporte.id_documento_glpi) == (EstadoDeSoporte.SUBIDO, "D-0001")
        vinculados = {
            t.ticket.cola.value: m.glpi.vinculos_de(t.id_externo or "") for t in u.tickets.creados()
        }
    assert vinculados == {
        "AD": {"D-0001"},
        "COMUNICACIONES": set(),
        "LICENCIAS": {"D-0001"},
        "INVENTARIO": set(),
    }
    assert not m.soportes.existe(nombre)  # copia local borrada tras verificar el hash
    assert "soporte.subido" in m.acciones_de_auditoria()
    assert m.acciones_de_auditoria().count("soporte.subido") == 1


def test_el_hash_distinto_mantiene_la_copia_y_cuenta_como_fallo() -> None:
    m = Mundo.nuevo()
    r = m.emitir(ingreso())
    nombre = m.soportes.nombres()[0]
    m.glpi.corromper_al_subir = True
    res = m.bandeja()
    assert res.creadas == 2  # COM e INVENTARIO no llevan soporte
    assert m.soportes.existe(nombre)
    with m.repos.unidad_de_trabajo() as u:
        assert u.soportes.obtener(r.solicitud_id).estado is EstadoDeSoporte.PENDIENTE  # type: ignore[union-attr]  # existe
    fallidas = [e for e in entradas(m, r.solicitud_id) if e.estado is EstadoDeEntrada.PENDIENTE]
    assert len(fallidas) == 2
    assert {e.ultimo_error for e in fallidas} == {"glpi_rechazo"}


def test_RD_12_si_la_copia_se_pierde_antes_de_subirse_la_solicitud_pasa_a_error() -> None:
    m = Mundo.nuevo()
    r = m.emitir(ingreso())
    m.soportes.perder(m.soportes.nombres()[0])
    res = m.bandeja()
    assert r.solicitud_id in res.solicitudes_en_error
    assert m.solicitud(r.solicitud_id).estado is S.ERROR
    assert "solicitud.error" in m.acciones_de_auditoria()
    # nada de lo que dependia del soporte llego a GLPI con el soporte inexistente
    assert m.glpi.documentos_subidos() == 0


def test_RD_12_tras_el_error_RRHH_cancela_y_registra_de_nuevo_S_19() -> None:
    m = Mundo.nuevo()
    r = m.emitir(ingreso())
    m.soportes.perder(m.soportes.nombres()[0])
    m.bandeja()
    # el reintento del Administrador no puede recuperar un archivo perdido
    m.reintentar("u-admin", r.solicitud_id)
    m.bandeja()
    assert m.solicitud(r.solicitud_id).estado is S.ERROR
    m.cancelar(
        "u-rrhh", r.solicitud_id, "se perdio el soporte"
    )  # `error` es abierto: hay que cancelar
    nueva = m.emitir(ingreso())
    assert nueva.colaborador_id == r.colaborador_id
    assert nueva.estado is S.APROBADA


# --- reintentos con espera (RF-18) ------------------------------------------------------------


def test_un_error_programa_el_reintento_con_espera_de_30_segundos() -> None:
    m = Mundo.nuevo()
    r = emitir_vac(m)
    m.glpi.programar(Fallo.ANTES)
    res = m.bandeja(limite=1)
    assert (res.creadas, res.reintentos_programados) == (0, 1)
    pendiente = next(e for e in entradas(m, r.solicitud_id) if e.intentos == 1)
    assert pendiente.proximo_intento == m.reloj.ahora() + timedelta(seconds=30)
    assert pendiente.ultimo_error == "glpi_no_disponible"
    m.avanzar(timedelta(seconds=29))
    assert m.bandeja(limite=1).procesadas <= 1  # los otros siguen pendientes de ahora
    m.avanzar(timedelta(seconds=1))
    m.correr_bandeja_hasta_vaciar()
    assert m.solicitud(r.solicitud_id).estado is S.EN_EJECUCION


def test_B_20_una_respuesta_inesperada_de_glpi_es_un_fallo_de_esa_entrada_y_no_frena_la_bandeja(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un `KeyError` al leer la respuesta de GLPI no es un `ErrorDeSistemaDeTickets`. Sin captura,
    la entrada quedaba primera en la cola sin sumar intentos y bloqueaba a todas las demas."""
    m = Mundo.nuevo()
    r = emitir_vac(m)
    original = m.glpi.crear_ticket
    llamadas: list[str] = []

    def roto(ticket):  # type: ignore[no-untyped-def]  # doble de prueba
        if not llamadas:
            llamadas.append(ticket.clave_de_idempotencia)
            raise KeyError("id")
        return original(ticket)

    monkeypatch.setattr(m.glpi, "crear_ticket", roto)
    res = m.bandeja()
    assert res.reintentos_programados == 1
    assert res.creadas == len(entradas(m, r.solicitud_id)) - 1  # las demas siguieron
    fallida = next(e for e in entradas(m, r.solicitud_id) if e.intentos == 1)
    assert fallida.clave == llamadas[0]
    assert fallida.ultimo_error == "error_inesperado"


def test_CA_07_tras_10_fallos_la_solicitud_pasa_a_error_con_las_esperas_de_S_13() -> None:
    m = Mundo.nuevo()
    r = emitir_vac(m)
    m.glpi.caer()  # GLPI detenido
    intentos_esperados = []
    for ronda in range(1, MAX_INTENTOS + 1):
        res = m.bandeja()
        if ronda < MAX_INTENTOS:
            assert res.solicitudes_en_error == ()
            primera = entradas(m, r.solicitud_id)[0]
            intentos_esperados.append(primera.intentos)
            # la espera hasta el siguiente intento es la de la tabla
            m.avanzar(espera_de_reintento(ronda) - timedelta(seconds=1))
            assert m.bandeja().procesadas == 0  # todavia no
            m.avanzar(timedelta(seconds=1))
        else:
            assert res.solicitudes_en_error == (r.solicitud_id,)
    assert intentos_esperados == list(range(1, MAX_INTENTOS))
    assert m.solicitud(r.solicitud_id).estado is S.ERROR
    assert any(e.estado is EstadoDeEntrada.FALLIDA for e in entradas(m, r.solicitud_id))
    assert m.glpi.tickets_remotos() == []  # nunca llego a crearse nada


def test_CA_07_el_administrador_reintenta_y_los_tickets_se_crean_sin_duplicados() -> None:
    m = Mundo.nuevo()
    r = emitir_vac(m)
    m.glpi.caer()
    for ronda in range(1, MAX_INTENTOS + 1):
        m.bandeja()
        m.avanzar(espera_de_reintento(ronda))
    assert m.solicitud(r.solicitud_id).estado is S.ERROR
    m.glpi.recuperar()
    m.reintentar("u-admin", r.solicitud_id)
    assert m.solicitud(r.solicitud_id).estado is S.APROBADA
    m.correr_bandeja_hasta_vaciar()
    assert m.solicitud(r.solicitud_id).estado is S.EN_EJECUCION
    assert len(m.glpi.tickets_remotos()) == 4
    assert set(m.glpi.creaciones_reales.values()) == {1}


def test_RNF_02_con_glpi_caido_se_sigue_aprobando_y_al_recuperarse_no_hay_duplicados() -> None:
    m = Mundo.nuevo()
    m.glpi.caer()
    a = m.registrar(vacaciones())
    assert (
        m.aprobar("u-rrhh", a.solicitud_id).tickets_encolados == 4
    )  # la aplicacion sigue operando
    m.bandeja()
    m.glpi.recuperar()
    m.avanzar(timedelta(minutes=1))
    m.correr_bandeja_hasta_vaciar()
    assert m.solicitud(a.solicitud_id).estado is S.EN_EJECUCION
    assert set(m.glpi.creaciones_reales.values()) == {1}
    assert len(m.glpi.creaciones_reales) == 4


def test_el_timeout_despues_de_crear_no_duplica_el_ticket_RF_18() -> None:
    m = Mundo.nuevo()
    r = emitir_vac(m)
    m.glpi.programar(
        Fallo.ANTES, Fallo.DESPUES
    )  # 1.º cae el usuario; 2.º crea y pierde la respuesta
    m.correr_bandeja_hasta_vaciar()
    assert set(m.glpi.creaciones_reales.values()) == {1}
    assert m.solicitud(r.solicitud_id).estado is S.EN_EJECUCION


def test_una_respuesta_duplicada_tampoco_duplica() -> None:
    m = Mundo.nuevo()
    emitir_vac(m)
    m.glpi.programar(Fallo.DUPLICADA, Fallo.DUPLICADA)
    m.correr_bandeja_hasta_vaciar()
    assert set(m.glpi.creaciones_reales.values()) == {1}


def test_con_una_creacion_parcial_la_solicitud_sigue_aprobada_y_no_se_cancela() -> None:
    m = Mundo.nuevo()
    r = emitir_vac(m)
    assert m.bandeja(limite=1).creadas == 1
    m.glpi.caer()
    m.bandeja()
    s = m.solicitud(r.solicitud_id)
    assert (s.estado, len(s.tickets)) == (S.APROBADA, 1)
    with pytest.raises(CancelacionNoPermitida):
        m.cancelar("u-rrhh", r.solicitud_id)


def test_una_entrada_de_una_solicitud_en_error_espera_el_reintento() -> None:
    m = Mundo.nuevo()
    r = emitir_vac(m)
    m.glpi.caer()
    for ronda in range(1, MAX_INTENTOS + 1):
        m.bandeja()
        m.avanzar(espera_de_reintento(ronda))
    antes = m.glpi.llamadas
    m.glpi.recuperar()
    assert m.bandeja().procesadas == 0  # la solicitud esta en `error`
    assert m.glpi.llamadas == antes
    assert m.solicitud(r.solicitud_id).estado is S.ERROR


def test_RF_38_solo_el_administrador_reintenta_y_solo_si_esta_en_error() -> None:
    m = Mundo.nuevo()
    r = emitir_vac(m)
    with pytest.raises(NoAutorizado):
        m.reintentar("u-rrhh", r.solicitud_id)
    with pytest.raises(TransicionInvalida):
        m.reintentar("u-admin", r.solicitud_id)  # esta `aprobada`, no en `error`
    with pytest.raises(NoAutorizado):
        m.reintentar("fantasma", r.solicitud_id)


def test_lo_cancelado_no_llega_a_glpi() -> None:
    m = Mundo.nuevo()
    a = m.registrar(vacaciones())
    m.aprobar("u-rrhh", a.solicitud_id)
    m.cancelar("u-rrhh", a.solicitud_id)
    m.bandeja()
    assert m.glpi.llamadas == 0


def test_una_entrada_cuya_solicitud_ya_no_esta_aprobada_se_descarta() -> None:
    """Defensa: si la solicitud se cancela entre la lectura de la bandeja y su proceso."""
    m = Mundo.nuevo()
    a = m.registrar(vacaciones())
    m.aprobar("u-rrhh", a.solicitud_id)
    with m.repos.unidad_de_trabajo() as u:
        s = u.solicitudes.obtener(a.solicitud_id)
        assert s is not None
        u.solicitudes.guardar(replace(s, estado=S.CANCELADA))
    assert m.bandeja().procesadas == 0
    assert {e.estado for e in entradas(m, a.solicitud_id)} == {EstadoDeEntrada.DESCARTADA}


# --- P8 ---------------------------------------------------------------------------------------


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(st.lists(st.sampled_from(list(Fallo)), max_size=14))
def test_P8_con_cualquier_calendario_de_fallos_existe_exactamente_un_ticket_por_clave(
    fallos: list[Fallo],
) -> None:
    m = Mundo.nuevo()
    r = m.emitir(ingreso())
    m.glpi.programar(*fallos)
    for _ in range(40):
        m.bandeja()
        if m.solicitud(r.solicitud_id).estado is S.ERROR:
            m.reintentar("u-admin", r.solicitud_id)
        m.avanzar(timedelta(minutes=15))
    assert m.solicitud(r.solicitud_id).estado is S.EN_EJECUCION
    assert len(m.glpi.creaciones_reales) == 4
    assert set(m.glpi.creaciones_reales.values()) == {1}  # nunca dos con la misma clave
    assert m.glpi.documentos_subidos() == 1  # y el soporte se subio una sola vez
    with m.repos.unidad_de_trabajo() as u:
        assert all(t.id_externo is not None for t in u.tickets.de_solicitud(r.solicitud_id))
    assert m.repos.auditoria().verificar().valida


@settings(max_examples=20, deadline=None)
@given(st.integers(MAX_INTENTOS, MAX_INTENTOS + 6))
def test_P8_con_10_o_mas_fallos_seguidos_la_solicitud_queda_en_error(rondas: int) -> None:
    m = Mundo.nuevo()
    r = emitir_vac(m)
    m.glpi.caer()
    for _ in range(rondas):
        m.bandeja()
        m.avanzar(timedelta(minutes=15))
    assert m.solicitud(r.solicitud_id).estado is S.ERROR
    assert m.glpi.creaciones_reales == {}


@settings(max_examples=20, deadline=None)
@given(st.integers(0, MAX_INTENTOS - 2))
def test_P8_con_recuperacion_antes_del_limite_todos_los_tickets_existen(caidas: int) -> None:
    m = Mundo.nuevo()
    r = emitir_vac(m)
    m.glpi.caer()
    for _ in range(caidas):
        m.bandeja()
        m.avanzar(timedelta(minutes=15))
    m.glpi.recuperar()
    for _ in range(3):
        m.bandeja()
        m.avanzar(timedelta(minutes=15))
    assert m.solicitud(r.solicitud_id).estado is S.EN_EJECUCION
    assert set(m.glpi.creaciones_reales.values()) == {1}
    assert len(m.glpi.creaciones_reales) == 4


def test_los_estados_de_glpi_se_ven_en_la_sincronizacion_pero_la_bandeja_no_los_toca() -> None:
    m = Mundo.nuevo()
    emitir_vac(m)
    m.bandeja()
    gid = next(iter(m.glpi._remotos))
    assert m.glpi._remotos[gid].estado in (EstadoDeTicket.NUEVO, EstadoDeTicket.EN_ESPERA)


def test_una_solicitud_RET_tambien_pasa_por_la_bandeja() -> None:
    m = Mundo.nuevo()
    r = m.emitir(retiro())
    res = m.bandeja()
    assert res.creadas == 6
    assert m.solicitud(r.solicitud_id).estado is S.EN_EJECUCION
