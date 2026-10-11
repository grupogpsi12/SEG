"""Ramas defensivas de los casos de uso: datos incompletos, carreras y reintentos parciales.

No son el camino normal, pero cada una protege una regla: que un fallo en una solicitud no
detenga la sincronizacion de las demas, que un reintento no recree lo ya creado, que el
estado del colaborador nunca retroceda y que la deduplicacion siga en manos de la base de datos.
"""

from collections.abc import Callable
from dataclasses import replace
from datetime import timedelta

import pytest

from jml.aplicacion.bandeja import EstadoDeEntrada, espera_de_reintento
from jml.aplicacion.casos.bandeja import ProcesarBandeja, _Conteo
from jml.aplicacion.puertos import TicketCreado
from jml.dominio.errores import DocumentoDuplicado, NoAutorizado, NoEncontrado
from jml.dominio.tickets import TicketDeCola
from jml.dominio.tipos import EstadoColaborador, EstadoSolicitud, Subtipo, TipoEvento
from jml.dominio.valores import SolicitudId
from tests.mundo import Mundo, emergencia, ingreso, vacaciones

S = EstadoSolicitud


def emitir_vac(m: Mundo) -> SolicitudId:
    return m.emitir(replace(vacaciones("u-rrhh"), justificacion="ok")).solicitud_id


# --- bandeja --------------------------------------------------------------------------------


def test_RF_38_el_reintento_no_recrea_los_tickets_que_ya_existian() -> None:
    """Creacion parcial, 10 fallos, reintento: las entradas ya enviadas no se tocan."""
    m = Mundo.nuevo()
    sid = emitir_vac(m)
    assert m.bandeja(limite=1).creadas == 1
    m.glpi.caer()
    for ronda in range(1, 11):
        m.bandeja()
        m.avanzar(espera_de_reintento(ronda))
    assert m.solicitud(sid).estado is S.ERROR
    with m.repos.unidad_de_trabajo() as u:
        enviadas = [
            e.clave for e in u.bandeja.de_solicitud(sid) if e.estado is EstadoDeEntrada.ENVIADA
        ]
    assert len(enviadas) == 1
    m.glpi.recuperar()
    m.reintentar("u-admin", sid)
    with m.repos.unidad_de_trabajo() as u:
        siguen = [
            e.clave for e in u.bandeja.de_solicitud(sid) if e.estado is EstadoDeEntrada.ENVIADA
        ]
    assert siguen == enviadas  # el reintento no reinicia lo ya enviado
    m.correr_bandeja_hasta_vaciar()
    assert m.solicitud(sid).estado is S.EN_EJECUCION
    assert len(m.glpi.creaciones_reales) == 4
    assert set(m.glpi.creaciones_reales.values()) == {1}


def test_reintentar_una_solicitud_inexistente() -> None:
    m = Mundo.nuevo()
    with pytest.raises(NoEncontrado):
        m.reintentar("u-admin", SolicitudId.de(2026, 77))


def test_una_entrada_sin_solicitud_es_un_dato_corrupto_y_se_informa() -> None:
    m = Mundo.nuevo()
    sid = emitir_vac(m)
    del m.repos.almacen.solicitudes[sid.valor]
    with pytest.raises(NoEncontrado, match="solicitud"):
        m.bandeja()
    assert m.glpi.llamadas == 0  # no se llego a GLPI con datos incompletos


def test_una_entrada_sin_colaborador_es_un_dato_corrupto_y_se_informa() -> None:
    m = Mundo.nuevo()
    emitir_vac(m)
    del m.repos.almacen.colaboradores["col-1"]
    with pytest.raises(NoEncontrado, match="colaborador"):
        m.bandeja()
    assert m.glpi.llamadas == 0


def test_una_entrada_que_ya_no_esta_pendiente_no_se_procesa() -> None:
    """Carrera: otra ejecucion la envio entre la lectura de la bandeja y su proceso."""
    m = Mundo.nuevo()
    sid = emitir_vac(m)
    with m.repos.unidad_de_trabajo() as u:
        entrada = u.bandeja.de_solicitud(sid)[0]
        u.bandeja.guardar(entrada.enviada())
    conteo = _Conteo()
    ProcesarBandeja(m._bandeja)._procesar(entrada.clave, conteo)
    ProcesarBandeja(m._bandeja)._procesar("no-existe", conteo)
    assert conteo.procesadas == 0
    assert m.glpi.llamadas == 0


# --- sincronizacion -------------------------------------------------------------------------


def test_un_fallo_en_una_solicitud_no_detiene_la_sincronizacion_de_las_demas() -> None:
    m = Mundo.nuevo()
    a = emitir_vac(m)
    b = m.emitir(ingreso()).solicitud_id
    m.correr_bandeja_hasta_vaciar()
    m.tecnico_resuelve_todo(b)
    del m.repos.almacen.colaboradores["col-1"]  # la solicitud `a` queda sin colaborador
    res = m.sincronizar()
    assert (res.resultado, res.errores) == ("error", 1)
    assert m.solicitud(b).estado is S.CERRADA  # la otra si se proceso
    assert m.solicitud(a).estado is S.EN_EJECUCION


def test_S_07_el_colaborador_nunca_retrocede_aunque_un_ticket_viejo_se_resuelva() -> None:
    """Una VAC resuelta despues de una EMG no devuelve a `activo` a un retirado."""
    m = Mundo.nuevo()
    vac = emitir_vac(m)
    m.correr_bandeja_hasta_vaciar()
    emg = m.emitir(emergencia()).solicitud_id
    m.correr_bandeja_hasta_vaciar()
    m.tecnico_resuelve_todo(emg)
    m.sincronizar()
    assert m.colaborador("col-1").estado is EstadoColaborador.RETIRADO
    m.reloj.fijar(m.reloj.ahora() + timedelta(days=30))
    m.tecnico_resuelve_todo(vac)
    m.sincronizar()
    assert m.colaborador("col-1").estado is EstadoColaborador.RETIRADO
    assert m.solicitud(vac).estado is S.CERRADA


# --- alta y decisiones ----------------------------------------------------------------------


def test_RD_01_RD_09_la_carrera_del_documento_la_decide_la_base_de_datos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si dos ingresos del mismo documento se cruzan, la restriccion unica traduce el error."""
    m = Mundo.nuevo()
    m.emitir(ingreso())
    from tests.dobles import memoria

    # el otro proceso todavia no ve el primer colaborador cuando consulta...
    monkeypatch.setattr(memoria._RepoColaboradores, "por_documento", lambda self, d: None)
    antes = m.repos.almacen.instantanea()
    with pytest.raises(DocumentoDuplicado):  # ...pero la restriccion si lo ve al guardar
        m.emitir(ingreso())
    assert m.repos.almacen.instantanea() == antes


def test_un_usuario_inexistente_no_decide() -> None:
    m = Mundo.nuevo()
    sid = m.registrar(vacaciones()).solicitud_id
    decisiones: tuple[Callable[[], object], ...] = (
        lambda: m.aprobar("fantasma", sid),
        lambda: m.rechazar("fantasma", sid, "x"),
        lambda: m.cancelar("fantasma", sid),
    )
    for decidir in decisiones:
        with pytest.raises(NoAutorizado):
            decidir()


def test_aprobar_sin_colaborador_es_un_dato_corrupto_y_no_deja_rastro() -> None:
    m = Mundo.nuevo()
    sid = m.registrar(vacaciones()).solicitud_id
    del m.repos.almacen.colaboradores["col-1"]
    antes = m.repos.almacen.instantanea()
    with pytest.raises(NoEncontrado):
        m.aprobar("u-rrhh", sid)
    assert m.repos.almacen.instantanea() == antes


def test_RF_10_aprobar_una_emergencia_pendiente_tambien_marca_las_otras() -> None:
    """Una EMG pendiente no se crea por los casos de uso, pero si existiera, al aprobarse marca."""
    m = Mundo.nuevo()
    vac = m.registrar(vacaciones()).solicitud_id
    e = m.emitir(emergencia()).solicitud_id
    with m.repos.unidad_de_trabajo() as u:
        s = u.solicitudes.obtener(e)
        assert s is not None
        u.solicitudes.guardar(replace(s, estado=S.PENDIENTE_APROBACION, tickets=()))
        otra = u.solicitudes.obtener(vac)
        assert otra is not None
        u.solicitudes.guardar(replace(otra, para_revision=False))
    m.aprobar("u-rrhh", e)
    assert m.solicitud(vac).para_revision
    assert m.solicitud(e).tipo is TipoEvento.EMG
    assert m.solicitud(e).subtipo is Subtipo.FUGA_DETECTADA


def test_R2_cualquier_error_de_dominio_en_una_solicitud_se_aisla_y_se_audita(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un dato corrupto en una solicitud no detiene la sincronizacion de las demas."""
    from jml.aplicacion.casos.sincronizar import SincronizarTickets
    from jml.dominio.errores import DatoInvalido

    m = Mundo.nuevo()
    a = emitir_vac(m)
    b = m.emitir(ingreso()).solicitud_id
    m.correr_bandeja_hasta_vaciar()
    m.tecnico_resuelve_todo(b)
    original = SincronizarTickets._solicitud

    def con_fallo(self: SincronizarTickets, sid: SolicitudId, obs: dict) -> None:  # type: ignore[type-arg]  # firma del metodo privado
        if sid == a:
            raise DatoInvalido("dato", "corrupto")
        original(self, sid, obs)

    monkeypatch.setattr(SincronizarTickets, "_solicitud", con_fallo)
    res = m.sincronizar()
    assert (res.resultado, res.errores) == ("error", 1)
    assert m.solicitud(b).estado is S.CERRADA  # la otra se proceso
    registros = [
        r for r in m.repos.auditoria().registros() if r.accion == "sincronizacion.solicitud_fallida"
    ]
    assert [(r.objeto, dict(r.datos)) for r in registros] == [
        (a.valor, {"codigo": "dato_invalido"})
    ]
    assert m.repos.auditoria().verificar().valida


def test_R1_un_ticket_creado_mientras_se_cancelaba_la_solicitud_no_se_pierde_de_vista() -> None:
    """RRHH cancela justo despues de que GLPI crea el primer ticket y antes de confirmarlo."""
    m = Mundo.nuevo()
    sid = emitir_vac(m)
    real = m.glpi.crear_ticket

    def crear_y_cancelar(ticket: TicketDeCola) -> TicketCreado:
        creado = real(ticket)
        m.cancelar("u-rrhh", sid, "se cancela en la carrera")  # aun no hay tickets confirmados
        return creado

    m.glpi.crear_ticket = crear_y_cancelar  # type: ignore[method-assign]  # carrera simulada
    res = m.bandeja(limite=1)
    assert res.creadas == 1
    assert m.solicitud(sid).estado is S.CANCELADA  # la cancelacion se respeta
    with m.repos.unidad_de_trabajo() as u:
        huerfanos = [t for t in u.tickets.creados() if t.ticket.solicitud_id == sid.valor]
        assert len(huerfanos) == 1  # y el ticket existente queda registrado para que TI lo cierre
        assert huerfanos[0].id_externo is not None
    assert "ticket.huerfano" in m.acciones_de_auditoria()
    m.glpi.crear_ticket = real  # type: ignore[method-assign]
    assert m.bandeja().procesadas == 0  # y no se crea ninguno mas
    assert len(m.glpi.creaciones_reales) == 1
    assert m.repos.auditoria().verificar().valida
