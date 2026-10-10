"""Contrato del puerto Repositorios (y su unidad de trabajo). RD-01, RD-02, RD-09, RF-14, CA-01, CA-02.

Corre contra cada fabrica de `conftest.py`. El adaptador de PostgreSQL pasara esta misma suite.
"""

from dataclasses import replace
from datetime import timedelta

import pytest

from jml.aplicacion.bandeja import EntradaDeBandeja, EstadoDeEntrada
from jml.aplicacion.dtos import FiltroDeCuentas, ResultadoDeSincronizacion
from jml.aplicacion.puertos import (
    ContenidoDeSolicitudModificado,
    DocumentoYaRegistrado,
    DuplicadoAbierto,
    UnidadDeTrabajo,
)
from jml.dominio.activos import ActivoAsignado, LicenciaAsignada
from jml.dominio.auditoria import HASH_GENESIS, EventoDeAuditoria
from jml.dominio.catalogo import DatosVacaciones
from jml.dominio.cuentas import CambioDeCuenta, Cuenta
from jml.dominio.permisos import UsuarioDelSistema
from jml.dominio.solicitud import Decision, Solicitud, TipoDeDecision
from jml.dominio.soporte import Soporte, validar_soporte
from jml.dominio.tickets import Observacion, TicketSeguido
from jml.dominio.tipos import (
    ESTADOS_ABIERTOS,
    ESTADOS_FINALES,
    EstadoColaborador,
    EstadoDeCuenta,
    EstadoDeTicket,
    EstadoSolicitud,
    Rol,
    SistemaDeCuenta,
    Subtipo,
    TipoEvento,
)
from jml.dominio.valores import CampoRestringido, Documento, SolicitudId
from tests.contratos.conftest import EntornoDeContrato
from tests.fabricas import AHORA, HOY, SENTINELA, Caso, caso, colaborador, perfil

S = EstadoSolicitud


def vac(
    numero: int, colaborador_id: str = "col-1", estado: EstadoSolicitud = S.PENDIENTE_APROBACION
) -> Solicitud:
    return Solicitud(
        id=SolicitudId.de(2026, numero),
        colaborador_id=colaborador_id,
        tipo=TipoEvento.VAC,
        subtipo=None,
        fecha_efectiva=HOY + timedelta(days=7),
        datos=DatosVacaciones(HOY + timedelta(days=14)),
        restringido=None,
        solicitante_id="u-1",
        estado=estado,
        creada_en=AHORA,
    )


def uow(e: EntornoDeContrato) -> UnidadDeTrabajo:
    return e.repos.unidad_de_trabajo()


# --- consecutivos y ciclo basico --------------------------------------------------------------


def test_los_consecutivos_son_por_anio(entorno: EntornoDeContrato) -> None:
    with uow(entorno) as u:
        assert u.solicitudes.siguiente_id(2026).valor == "SOL-2026-000001"
        assert u.solicitudes.siguiente_id(2026).valor == "SOL-2026-000002"
        assert u.solicitudes.siguiente_id(2027).valor == "SOL-2027-000001"


def test_guardar_y_obtener_devuelve_lo_mismo_incluido_el_restringido(
    entorno: EntornoDeContrato,
) -> None:
    c = caso(TipoEvento.RET, Subtipo.RENUNCIA)
    with uow(entorno) as u:
        u.solicitudes.guardar(c.solicitud)
    with uow(entorno) as u:
        leida = u.solicitudes.obtener(c.solicitud.id)
    assert leida == c.solicitud
    assert leida is not None
    assert leida.restringido == CampoRestringido(SENTINELA)
    with uow(entorno) as u:
        assert u.solicitudes.obtener(SolicitudId.de(2026, 999)) is None


# --- RD-01: duplicado abierto -----------------------------------------------------------------


@pytest.mark.parametrize("estado", sorted(ESTADOS_ABIERTOS))
def test_RD_01_un_estado_abierto_bloquea_el_duplicado(
    entorno: EntornoDeContrato, estado: EstadoSolicitud
) -> None:
    """lessons n.1: pendiente, aprobada, en_ejecucion y error son ABIERTOS."""
    with uow(entorno) as u:
        u.solicitudes.guardar(vac(1, estado=estado))
        with pytest.raises(DuplicadoAbierto) as e:
            u.solicitudes.guardar(vac(2))
    assert e.value.existente_id == SolicitudId.de(2026, 1)


@pytest.mark.parametrize("estado", sorted(ESTADOS_FINALES))
def test_RD_01_un_estado_final_no_bloquea(
    entorno: EntornoDeContrato, estado: EstadoSolicitud
) -> None:
    with uow(entorno) as u:
        u.solicitudes.guardar(vac(1, estado=estado))
        u.solicitudes.guardar(vac(2))
        assert u.solicitudes.abierta_de_tipo("col-1", TipoEvento.VAC) == vac(2)


def test_RD_01_al_cerrarse_la_primera_se_puede_registrar_otra(entorno: EntornoDeContrato) -> None:
    with uow(entorno) as u:
        u.solicitudes.guardar(vac(1, estado=S.EN_EJECUCION))
        with pytest.raises(DuplicadoAbierto):
            u.solicitudes.guardar(vac(2))
        u.solicitudes.guardar(replace(vac(1), estado=S.CERRADA))
        u.solicitudes.guardar(vac(2))


def test_RD_01_otro_tipo_u_otro_colaborador_no_bloquean(entorno: EntornoDeContrato) -> None:
    emg = caso(TipoEvento.EMG, Subtipo.FUGA_DETECTADA, numero=9).solicitud
    with uow(entorno) as u:
        u.solicitudes.guardar(vac(1))
        u.solicitudes.guardar(vac(2, colaborador_id="col-2"))
        u.solicitudes.guardar(emg)  # RF-10: la emergencia no se bloquea por otras abiertas
        assert {s.id.valor for s in u.solicitudes.abiertas_de("col-1")} == {
            "SOL-2026-000001",
            "SOL-2026-000009",
        }


def test_actualizar_la_misma_solicitud_no_es_un_duplicado(entorno: EntornoDeContrato) -> None:
    with uow(entorno) as u:
        u.solicitudes.guardar(vac(1))
        u.solicitudes.guardar(replace(vac(1), estado=S.APROBADA))
        assert u.solicitudes.obtener(SolicitudId.de(2026, 1)) is not None


def test_abiertas_y_de_colaborador(entorno: EntornoDeContrato) -> None:
    with uow(entorno) as u:
        u.solicitudes.guardar(vac(1, estado=S.CERRADA))
        u.solicitudes.guardar(vac(2))
        assert [s.id.valor for s in u.solicitudes.abiertas_de("col-1")] == ["SOL-2026-000002"]
        assert [s.id.valor for s in u.solicitudes.de_colaborador("col-1")] == [
            "SOL-2026-000001",
            "SOL-2026-000002",
        ]
        assert u.solicitudes.abierta_de_tipo("col-1", TipoEvento.RET) is None
        assert u.solicitudes.abiertas_de("nadie") == []


# --- RF-14: inmutabilidad ---------------------------------------------------------------------


def test_RF_14_no_se_cambia_el_contenido_de_una_aprobada(entorno: EntornoDeContrato) -> None:
    with uow(entorno) as u:
        u.solicitudes.guardar(vac(1, estado=S.APROBADA))
        with pytest.raises(ContenidoDeSolicitudModificado):
            u.solicitudes.guardar(
                replace(vac(1, estado=S.APROBADA), fecha_efectiva=HOY + timedelta(days=30))
            )


@pytest.mark.parametrize(
    "estado", [S.APROBADA, S.EN_EJECUCION, S.ERROR, S.CERRADA, S.RECHAZADA, S.CANCELADA]
)
def test_RF_14_lo_que_no_es_contenido_si_cambia(
    entorno: EntornoDeContrato, estado: EstadoSolicitud
) -> None:
    with uow(entorno) as u:
        u.solicitudes.guardar(vac(1, estado=estado))
        u.solicitudes.guardar(replace(vac(1, estado=estado), tickets=("k",), para_revision=True))
        leida = u.solicitudes.obtener(SolicitudId.de(2026, 1))
        assert leida is not None
        assert (leida.tickets, leida.para_revision) == (("k",), True)
        with pytest.raises(ContenidoDeSolicitudModificado):
            u.solicitudes.guardar(replace(vac(1, estado=estado), restringido=CampoRestringido("x")))


# --- RD-09: documento unico -------------------------------------------------------------------


def test_RD_09_el_documento_es_unico_entre_los_no_retirados(entorno: EntornoDeContrato) -> None:
    with uow(entorno) as u:
        u.colaboradores.guardar(colaborador(id="c1"))
        with pytest.raises(DocumentoYaRegistrado) as e:
            u.colaboradores.guardar(colaborador(id="c2"))
        assert e.value.existente_id == "c1"
        u.colaboradores.guardar(colaborador(id="c1"))  # el mismo registro se puede reescribir
        u.colaboradores.guardar(replace(colaborador(id="c1"), estado=EstadoColaborador.RETIRADO))
        u.colaboradores.guardar(
            replace(colaborador(id="c2", usuario="otro.usuario"))
        )  # ya retirado el viejo
        assert u.colaboradores.por_documento(Documento("10203040")) == colaborador(
            id="c2", usuario="otro.usuario"
        )


def test_RD_09_un_retirado_no_ocupa_el_documento(entorno: EntornoDeContrato) -> None:
    with uow(entorno) as u:
        u.colaboradores.guardar(replace(colaborador(id="c1"), estado=EstadoColaborador.RETIRADO))
        assert u.colaboradores.por_documento(Documento("10203040")) is None
        u.colaboradores.guardar(colaborador(id="c2", usuario="nuevo.usuario"))
        u.colaboradores.guardar(
            replace(colaborador(id="c3", usuario="x.y"), estado=EstadoColaborador.RETIRADO)
        )


def test_colaboradores_consultas_auxiliares(entorno: EntornoDeContrato) -> None:
    c1 = colaborador(id="c1", usuario="ana.perez")
    sin_fin = replace(c1, id_usuario_glpi="u-7")
    otro = replace(
        colaborador(id="c2", usuario="luis.diaz"),
        documento=Documento("99999"),
        fecha_fin=HOY + timedelta(days=3),
    )
    with uow(entorno) as u:
        u.colaboradores.guardar(sin_fin)
        u.colaboradores.guardar(otro)
        assert u.colaboradores.usuarios_en_uso() == {"ana.perez", "luis.diaz"}
        assert [c.id for c in u.colaboradores.con_usuario_glpi()] == ["c1"]
        assert [c.id for c in u.colaboradores.con_fin_de_contrato()] == ["c2"]
        assert u.colaboradores.obtener("c1") == sin_fin
        assert u.colaboradores.obtener("zz") is None


# --- usuarios, perfiles, tickets, cuentas, decisiones, soportes -------------------------------


def test_usuarios_y_roles(entorno: EntornoDeContrato) -> None:
    with uow(entorno) as u:
        u.usuarios.guardar(UsuarioDelSistema("u1", "c1", frozenset({Rol.RRHH})))
        u.usuarios.guardar(UsuarioDelSistema("u2", "c1", frozenset({Rol.SOLICITANTE})))
        u.usuarios.guardar(UsuarioDelSistema("u3", "c2", frozenset({Rol.TECNICO_AD}), activo=False))
        actor = u.usuarios.actor_de("u1")
        assert actor is not None
        assert (actor.usuario_id, actor.colaborador_id, actor.roles) == (
            "u1",
            "c1",
            frozenset({Rol.RRHH}),
        )
        assert u.usuarios.actor_de("u3") is None  # inactivo
        assert u.usuarios.actor_de("nadie") is None
        assert u.usuarios.roles_de_colaborador("c1") == {Rol.RRHH, Rol.SOLICITANTE}
        assert u.usuarios.roles_de_colaborador("c2") == frozenset()


def test_perfiles(entorno: EntornoDeContrato) -> None:
    with uow(entorno) as u:
        u.perfiles.guardar(perfil("TI", "Cali"))
        assert u.perfiles.obtener("TI", "Cali") == perfil("TI", "Cali")
        assert u.perfiles.obtener("TI", "Bogotá") is None


def test_tickets(entorno: EntornoDeContrato) -> None:
    c = caso(TipoEvento.RET, Subtipo.RENUNCIA)
    from jml.dominio.tickets import generar_tickets
    from jml.dominio.valores import CalendarioHabil

    ts = generar_tickets(c.solicitud, c.actual, c.nuevo, c.colaborador, CalendarioHabil(), AHORA)
    with uow(entorno) as u:
        for t in ts:
            u.tickets.guardar(TicketSeguido(t))
        u.tickets.guardar(
            TicketSeguido(ts[0], "G-1", Observacion(EstadoDeTicket.NUEVO, False, 0, AHORA))
        )
        assert len(u.tickets.de_solicitud(c.solicitud.id)) == len(ts)
        assert [t.id_externo for t in u.tickets.creados()] == ["G-1"]
        assert u.tickets.por_clave(ts[0].clave_de_idempotencia) is not None
        assert u.tickets.por_clave("no-existe") is None
        assert u.tickets.de_solicitud(SolicitudId.de(2026, 77)) == []


def test_cuentas_e_historial(entorno: EntornoDeContrato) -> None:
    cuenta = Cuenta("c1", SistemaDeCuenta.AD, EstadoDeCuenta.ACTIVA, "k", (AHORA, AHORA), AHORA)
    c1 = CambioDeCuenta(
        "c1", SistemaDeCuenta.AD, None, EstadoDeCuenta.PENDIENTE_ALTA, None, "k", AHORA
    )
    c2 = CambioDeCuenta(
        "c1",
        SistemaDeCuenta.AD,
        EstadoDeCuenta.PENDIENTE_ALTA,
        EstadoDeCuenta.ACTIVA,
        None,
        "k",
        AHORA,
    )
    with uow(entorno) as u:
        u.cuentas.guardar(cuenta)
        assert u.cuentas.obtener("c1", SistemaDeCuenta.AD) == cuenta
        assert u.cuentas.obtener("c1", SistemaDeCuenta.RED) is None
        u.cuentas.agregar_historial(c1)
        u.cuentas.agregar_historial(c2)
        assert list(u.cuentas.historial("c1")) == [c1, c2]  # solo insercion, en orden
        assert u.cuentas.historial("otro") == []


def test_decisiones_solo_se_agregan(entorno: EntornoDeContrato) -> None:
    sid = SolicitudId.de(2026, 1)
    d1 = Decision(sid, TipoDeDecision.APROBAR, None, "u1", AHORA)
    d2 = Decision(sid, TipoDeDecision.CANCELAR, "x", "u1", AHORA)
    with uow(entorno) as u:
        u.decisiones.agregar(d1)
        u.decisiones.agregar(d2)
        assert list(u.decisiones.de_solicitud(sid)) == [d1, d2]
        assert u.decisiones.de_solicitud(SolicitudId.de(2026, 2)) == []


def test_soportes(entorno: EntornoDeContrato) -> None:
    sid = SolicitudId.de(2026, 1)
    s = Soporte.pendiente(sid, validar_soporte(b"%PDF-1.4 xx", "a.pdf"), "alea-1")
    with uow(entorno) as u:
        u.soportes.guardar(s)
        assert u.soportes.obtener(sid) == s
        u.soportes.guardar(s.subido("D-1"))
        leido = u.soportes.obtener(sid)
        assert leido is not None
        assert leido.id_documento_glpi == "D-1"
        assert u.soportes.obtener(SolicitudId.de(2026, 2)) is None


# --- bandeja de salida ------------------------------------------------------------------------


def _entradas(n: int = 3) -> list[EntradaDeBandeja]:
    c = caso(TipoEvento.RET, Subtipo.RENUNCIA)
    from jml.dominio.tickets import generar_tickets
    from jml.dominio.valores import CalendarioHabil

    ts = generar_tickets(c.solicitud, c.actual, c.nuevo, c.colaborador, CalendarioHabil(), AHORA)
    return [EntradaDeBandeja.nueva(t, AHORA) for t in ts[:n]]


def test_bandeja_encolar_es_idempotente_por_clave(entorno: EntornoDeContrato) -> None:
    es = _entradas()
    with uow(entorno) as u:
        u.bandeja.encolar(es)
        u.bandeja.encolar(es)
        sid = SolicitudId.de(2026, 1)
        assert len(u.bandeja.de_solicitud(sid)) == 3


def test_bandeja_vencidas_solo_pendientes_y_con_fecha_cumplida(entorno: EntornoDeContrato) -> None:
    a, b, c = _entradas()
    with uow(entorno) as u:
        u.bandeja.encolar([a, replace(b, proximo_intento=AHORA + timedelta(minutes=5)), c])
        u.bandeja.guardar(c.enviada())
        listas = u.bandeja.vencidas(AHORA, 10)
        assert [e.clave for e in listas] == [a.clave]
        assert [e.clave for e in u.bandeja.vencidas(AHORA + timedelta(minutes=5), 10)] == sorted(
            [a.clave, b.clave],
            key=lambda k: (AHORA if k == a.clave else AHORA + timedelta(minutes=5), k),
        )
        assert len(u.bandeja.vencidas(AHORA + timedelta(hours=1), 1)) == 1  # respeta el limite


def test_bandeja_guardar_actualiza_el_estado(entorno: EntornoDeContrato) -> None:
    a = _entradas(1)[0]
    with uow(entorno) as u:
        u.bandeja.encolar([a])
        u.bandeja.guardar(a.fallo("glpi_timeout", AHORA))
        leida = u.bandeja.de_solicitud(SolicitudId.de(2026, 1))[0]
        assert (leida.intentos, leida.estado, leida.ultimo_error) == (
            1,
            EstadoDeEntrada.PENDIENTE,
            "glpi_timeout",
        )


# --- activos, licencias, sincronizaciones -----------------------------------------------------


def test_activos_se_reemplazan_en_cada_sincronizacion(entorno: EntornoDeContrato) -> None:
    a1 = ActivoAsignado("A1", "Portátil", "S1", "X", HOY, True)
    a2 = ActivoAsignado("A2", "Portátil", "S2", "Y", HOY, False)
    lic = LicenciaAsignada("L1", "Suite", "K-1")
    with uow(entorno) as u:
        u.activos.reemplazar("c1", [a1, a2], [lic])
        u.activos.reemplazar("c1", [a2], [])
        assert list(u.activos.activos_de("c1")) == [a2]
        assert list(u.activos.licencias_de("c1")) == []
        assert list(u.activos.activos_de("otro")) == []
        assert list(u.activos.licencias_de("otro")) == []


def test_sincronizaciones_ultima(entorno: EntornoDeContrato) -> None:
    r1 = ResultadoDeSincronizacion(AHORA, AHORA, "ok", 3, 0)
    r2 = ResultadoDeSincronizacion(AHORA, AHORA + timedelta(seconds=2), "error", 0, 1)
    with uow(entorno) as u:
        assert u.sincronizaciones.ultima() is None
        u.sincronizaciones.registrar(r1)
        u.sincronizaciones.registrar(r2)
        assert u.sincronizaciones.ultima() == r2


# --- unidad de trabajo atomica (CA-02) -------------------------------------------------------


class _Caida(Exception):
    pass


def _escribir_todo_y_caer(entorno: EntornoDeContrato, c: Caso) -> None:
    with uow(entorno) as u:
        u.colaboradores.guardar(c.colaborador)
        u.solicitudes.guardar(c.solicitud)
        u.decisiones.agregar(Decision(c.solicitud.id, TipoDeDecision.EMITIR, "j", "u", AHORA))
        u.bandeja.encolar(_entradas(2))
        u.auditoria.registrar("u", EventoDeAuditoria("a.b", "o", {}))
        u.cuentas.guardar(
            Cuenta("c1", SistemaDeCuenta.AD, EstadoDeCuenta.ACTIVA, "k", (AHORA, AHORA), AHORA)
        )
        u.perfiles.guardar(perfil("TI"))
        u.activos.reemplazar("c1", [ActivoAsignado("A1", "x", "S", "M", HOY, True)], [])
        u.sincronizaciones.registrar(ResultadoDeSincronizacion(AHORA, AHORA, "ok", 0, 0))
        u.solicitudes.siguiente_id(2026)
        raise _Caida


def test_CA_02_la_unidad_de_trabajo_es_atomica(entorno: EntornoDeContrato) -> None:
    """Si el ultimo paso falla, no queda rastro de ninguno de los anteriores."""
    c = caso(TipoEvento.RET, Subtipo.RENUNCIA)
    with pytest.raises(_Caida):
        _escribir_todo_y_caer(entorno, c)
    with uow(entorno) as u:
        assert u.solicitudes.obtener(c.solicitud.id) is None
        assert u.colaboradores.obtener(c.colaborador.id) is None
        assert u.decisiones.de_solicitud(c.solicitud.id) == []
        assert u.bandeja.de_solicitud(SolicitudId.de(2026, 1)) == []
        assert u.auditoria.registros() == ()
        assert u.cuentas.obtener("c1", SistemaDeCuenta.AD) is None
        assert u.perfiles.obtener("TI", "Bogotá") is None
        assert list(u.activos.activos_de("c1")) == []
        assert u.sincronizaciones.ultima() is None
        assert (
            u.solicitudes.siguiente_id(2026).valor == "SOL-2026-000001"
        )  # el consecutivo tambien vuelve


def test_la_unidad_de_trabajo_confirma_si_no_hay_error(entorno: EntornoDeContrato) -> None:
    with uow(entorno) as u:
        u.solicitudes.guardar(vac(1))
    with uow(entorno) as u:
        assert u.solicitudes.obtener(SolicitudId.de(2026, 1)) == vac(1)


def test_la_excepcion_se_propaga(entorno: EntornoDeContrato) -> None:
    with pytest.raises(_Caida), uow(entorno):
        raise _Caida


# --- auditoria dentro de la unidad de trabajo (RD-03) -----------------------------------------


def test_la_auditoria_encadena_y_verifica(entorno: EntornoDeContrato) -> None:
    with uow(entorno) as u:
        r1 = u.auditoria.registrar(
            "u1", EventoDeAuditoria("solicitud.registrada", "SOL-2026-000001", {"n": 1})
        )
        r2 = u.auditoria.registrar(
            "u1", EventoDeAuditoria("solicitud.aprobada", "SOL-2026-000001", {"n": 2})
        )
    assert (r1.secuencia, r1.hash_anterior) == (1, HASH_GENESIS)
    assert (r2.secuencia, r2.hash_anterior) == (2, r1.hash)
    with uow(entorno) as u:
        assert [r.secuencia for r in u.auditoria.registros()] == [1, 2]
        assert u.auditoria.verificar().valida
        assert r1.fecha == entorno.reloj.ahora()


def _registrar_y_caer(entorno: EntornoDeContrato) -> None:
    with uow(entorno) as u:
        u.auditoria.registrar("u", EventoDeAuditoria("b", "o", {}))
        raise _Caida


def test_un_rollback_no_deja_hueco_en_la_cadena(entorno: EntornoDeContrato) -> None:
    with uow(entorno) as u:
        u.auditoria.registrar("u", EventoDeAuditoria("a", "o", {}))
    with pytest.raises(_Caida):
        _registrar_y_caer(entorno)
    with uow(entorno) as u:
        r = u.auditoria.registrar("u", EventoDeAuditoria("c", "o", {}))
        assert r.secuencia == 2
        assert u.auditoria.verificar().valida


# --- consultas de lectura (la expectativa detallada esta en 1.11) -----------------------------


def test_consultas_sobre_un_almacen_vacio(entorno: EntornoDeContrato) -> None:
    ind = entorno.repos.indicadores(AHORA)
    assert (ind.pendientes, ind.vencidos, ind.exposicion, ind.cuentas, ind.programados) == (
        (),
        (),
        (),
        (),
        (),
    )
    assert ind.equipos.asignados == 0
    assert ind.ultima_sincronizacion is None
    pagina = entorno.repos.buscar_cuentas(FiltroDeCuentas())
    assert (pagina.filas, pagina.total, pagina.pagina) == ((), 0, 1)
    assert entorno.repos.ficha("nadie") is None


def test_buscar_ordena_y_pagina(entorno: EntornoDeContrato) -> None:
    with uow(entorno) as u:
        for i, ape in enumerate(["Zapata", "Álvarez", "Mora"]):
            u.colaboradores.guardar(
                replace(
                    colaborador(id=f"c{i}", usuario=f"u{i}.x"),
                    documento=Documento(f"1000{i}"),
                    apellidos=ape,
                )
            )
    todos = entorno.repos.buscar_cuentas(FiltroDeCuentas(tamano=2))
    assert [f.nombre_completo.split()[-1] for f in todos.filas] == ["Álvarez", "Mora"]
    assert todos.total == 3
    segunda = entorno.repos.buscar_cuentas(FiltroDeCuentas(pagina=2, tamano=2))
    assert [f.colaborador_id for f in segunda.filas] == ["c0"]
