"""Contrato del puerto SistemaDeTickets (GLPI). RF-18, RF-21, RF-22, RF-23, RF-40, CA-07.

La prueba clave: con cualquier calendario de fallos, existe EXACTAMENTE un ticket por clave
(incluido el timeout DESPUES de crear, donde el ticket existe pero la respuesta se perdio).
"""

from datetime import timedelta

import pytest

from jml.aplicacion.puertos import GlpiNoDisponible, GlpiRechazo, TiempoAgotado
from jml.dominio.activos import ActivoAsignado, LicenciaAsignada
from jml.dominio.tickets import TicketDeCola, generar_tickets
from jml.dominio.tipos import ClaseTicket, Cola, EstadoDeTicket, Subtipo, TipoEvento
from jml.dominio.valores import CalendarioHabil, NombreDeSoporteSaneado, Sha256
from tests.contratos.conftest import EntornoDeContrato
from tests.fabricas import AHORA, HOY, caso, colaborador

PDF = b"%PDF-1.7 contenido del soporte"
NOMBRE = NombreDeSoporteSaneado.sanear("acta.pdf")


def un_ticket(
    tipo: TipoEvento = TipoEvento.RET, clase: ClaseTicket = ClaseTicket.CIERRE_INMEDIATO
) -> TicketDeCola:
    sub = {TipoEvento.RET: Subtipo.RENUNCIA}.get(tipo)
    c = caso(tipo, sub)
    ts = generar_tickets(c.solicitud, c.actual, c.nuevo, c.colaborador, CalendarioHabil(), AHORA)
    return next(t for t in ts if t.cola is Cola.AD and t.clase is clase)


def test_crear_ticket_devuelve_un_id_y_es_idempotente(entorno: EntornoDeContrato) -> None:
    t = un_ticket()
    primero = entorno.glpi.crear_ticket(t)
    segundo = entorno.glpi.crear_ticket(t)
    assert primero.ya_existia is False
    assert segundo.ya_existia is True
    assert primero.id_externo == segundo.id_externo
    assert entorno.tecnico.creaciones(t.clave_de_idempotencia) == 1


def test_claves_distintas_crean_tickets_distintos(entorno: EntornoDeContrato) -> None:
    c = caso(TipoEvento.RET, Subtipo.RENUNCIA)
    ts = generar_tickets(c.solicitud, c.actual, c.nuevo, c.colaborador, CalendarioHabil(), AHORA)
    ids = {entorno.glpi.crear_ticket(t).id_externo for t in ts}
    assert len(ids) == len(ts)


def test_el_timeout_despues_de_crear_no_duplica_RF_18(entorno: EntornoDeContrato) -> None:
    """El ticket existe en GLPI pero la respuesta se perdio: reintentar no lo duplica."""
    t = un_ticket()
    entorno.inyector.timeout_despues_de_crear()
    with pytest.raises(TiempoAgotado):
        entorno.glpi.crear_ticket(t)
    reintento = entorno.glpi.crear_ticket(t)
    assert reintento.ya_existia is True
    assert entorno.tecnico.creaciones(t.clave_de_idempotencia) == 1


def test_un_error_antes_de_crear_no_deja_nada(entorno: EntornoDeContrato) -> None:
    t = un_ticket()
    entorno.inyector.error_antes_de_crear()
    with pytest.raises(GlpiNoDisponible):
        entorno.glpi.crear_ticket(t)
    assert entorno.tecnico.creaciones(t.clave_de_idempotencia) == 0
    assert entorno.glpi.crear_ticket(t).ya_existia is False
    assert entorno.tecnico.creaciones(t.clave_de_idempotencia) == 1


def test_una_respuesta_duplicada_no_duplica(entorno: EntornoDeContrato) -> None:
    t = un_ticket()
    entorno.inyector.respuesta_duplicada()
    entorno.glpi.crear_ticket(t)
    assert entorno.tecnico.creaciones(t.clave_de_idempotencia) == 1


def test_una_caida_larga_y_la_recuperacion(entorno: EntornoDeContrato) -> None:
    t = un_ticket()
    entorno.inyector.caida(3)
    for _ in range(3):
        with pytest.raises(GlpiNoDisponible):
            entorno.glpi.crear_ticket(t)
    entorno.glpi.crear_ticket(t)
    assert entorno.tecnico.creaciones(t.clave_de_idempotencia) == 1


def test_leer_tickets_refleja_lo_que_hace_el_tecnico_RF_22(entorno: EntornoDeContrato) -> None:
    t = un_ticket()
    gid = entorno.glpi.crear_ticket(t).id_externo
    obs = entorno.glpi.leer_tickets([gid])[gid]
    # S-34: en GLPI la regla de enrutamiento asigna el grupo y el ticket pasa de «Nuevo» a
    # «En curso». El nucleo solo distingue «antes» y «desde» Resuelto (RF-24).
    assert obs.estado in (EstadoDeTicket.NUEVO, EstadoDeTicket.EN_CURSO)
    assert (obs.tiene_solucion, obs.documentos) == (False, 0)
    assert obs.observada_en == entorno.reloj.ahora()
    entorno.tecnico.resolver(gid, con_solucion=True, documentos=2)
    resuelto = entorno.glpi.leer_tickets([gid])[gid]
    assert (resuelto.estado, resuelto.tiene_solucion, resuelto.documentos) == (
        EstadoDeTicket.RESUELTO,
        True,
        2,
    )
    entorno.tecnico.reabrir(gid)
    assert entorno.glpi.leer_tickets([gid])[gid].estado < EstadoDeTicket.RESUELTO


def test_un_ticket_resuelto_sin_solucion_se_ve_asi(entorno: EntornoDeContrato) -> None:
    gid = entorno.glpi.crear_ticket(un_ticket()).id_externo
    entorno.tecnico.resolver(gid, con_solucion=False)
    obs = entorno.glpi.leer_tickets([gid])[gid]
    assert obs.estado >= EstadoDeTicket.RESUELTO
    assert obs.tiene_solucion is False


def test_un_ticket_programado_nace_en_espera_RF_17(entorno: EntornoDeContrato) -> None:
    posterior = un_ticket(clase=ClaseTicket.POSTERIOR)
    gid = entorno.glpi.crear_ticket(posterior).id_externo
    assert entorno.glpi.leer_tickets([gid])[gid].estado is EstadoDeTicket.EN_ESPERA


def test_leer_tickets_omite_los_desconocidos_y_acepta_lotes(entorno: EntornoDeContrato) -> None:
    gid = entorno.glpi.crear_ticket(un_ticket()).id_externo
    leidos = entorno.glpi.leer_tickets([gid, "no-existe"])
    assert set(leidos) == {gid}
    assert entorno.glpi.leer_tickets([]) == {}


def test_la_lectura_falla_si_glpi_esta_caido(entorno: EntornoDeContrato) -> None:
    gid = entorno.glpi.crear_ticket(un_ticket()).id_externo
    entorno.inyector.caida(1)
    with pytest.raises(GlpiNoDisponible):
        entorno.glpi.leer_tickets([gid])


# --- documentos (RF-40, CA-18) ----------------------------------------------------------------


def test_subir_el_mismo_contenido_dos_veces_da_el_mismo_documento(
    entorno: EntornoDeContrato,
) -> None:
    uno = entorno.glpi.subir_documento(NOMBRE, PDF)
    dos = entorno.glpi.subir_documento(NOMBRE, PDF)
    otro = entorno.glpi.subir_documento(NOMBRE, PDF + b"x")
    assert uno == dos
    assert otro != uno


def test_el_hash_del_documento_coincide_con_el_del_contenido(entorno: EntornoDeContrato) -> None:
    doc = entorno.glpi.subir_documento(NOMBRE, PDF)
    assert entorno.glpi.hash_de_documento(doc) == Sha256.de_bytes(PDF)


def test_vincular_un_documento_a_dos_tickets_es_idempotente(entorno: EntornoDeContrato) -> None:
    c = caso(TipoEvento.RET, Subtipo.RENUNCIA)
    ts = generar_tickets(c.solicitud, c.actual, c.nuevo, c.colaborador, CalendarioHabil(), AHORA)
    ids = [entorno.glpi.crear_ticket(t).id_externo for t in ts[:2]]
    doc = entorno.glpi.subir_documento(NOMBRE, PDF)
    for gid in ids:
        entorno.glpi.vincular_documento(doc, gid)
        entorno.glpi.vincular_documento(doc, gid)
    assert entorno.glpi.hash_de_documento(doc) == Sha256.de_bytes(PDF)


def test_vincular_a_algo_inexistente_se_rechaza(entorno: EntornoDeContrato) -> None:
    gid = entorno.glpi.crear_ticket(un_ticket()).id_externo
    doc = entorno.glpi.subir_documento(NOMBRE, PDF)
    with pytest.raises(GlpiRechazo):
        entorno.glpi.vincular_documento("no-existe", gid)
    with pytest.raises(GlpiRechazo):
        entorno.glpi.vincular_documento(doc, "no-existe")
    with pytest.raises(GlpiRechazo):
        entorno.glpi.hash_de_documento("no-existe")


# --- usuarios, activos y licencias (RF-21, RF-23) ---------------------------------------------


def test_asegurar_usuario_es_idempotente(entorno: EntornoDeContrato) -> None:
    c = colaborador()
    assert entorno.glpi.asegurar_usuario(c) == entorno.glpi.asegurar_usuario(c)
    assert entorno.glpi.asegurar_usuario(c) != entorno.glpi.asegurar_usuario(colaborador(id="otro"))


def test_leer_activos_y_licencias(entorno: EntornoDeContrato) -> None:
    uid = entorno.glpi.asegurar_usuario(colaborador())
    assert list(entorno.glpi.leer_activos(uid)) == []
    activo = ActivoAsignado("A1", "Portátil", "SN-1", "ThinkPad", HOY - timedelta(days=3), True)
    lic = LicenciaAsignada("L1", "Suite ofimática", "K-001")
    # GLPI real asigna sus propios ids: la expectativa (lo leido == lo asignado) no cambia.
    activo = entorno.tecnico.asignar_activo(uid, activo)
    lic = entorno.tecnico.asignar_licencia(uid, lic)
    assert list(entorno.glpi.leer_activos(uid)) == [activo]
    assert list(entorno.glpi.leer_licencias(uid)) == [lic]
    assert list(entorno.glpi.leer_activos("otro")) == []
