"""Item 1.6: generacion de tickets (RF-16, RF-17, RF-20, CA-03, CA-04, CA-10, CA-19, P4)."""

import re
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from jml.dominio.errores import DatoInvalido, TransicionInvalida
from jml.dominio.perfiles import PerfilDeAcceso
from jml.dominio.tickets import (
    COLA_A_SISTEMA,
    FRASE_DE_CONTRASENA,
    TicketDeCola,
    categoria_del_ticket,
    clave_de_idempotencia,
    generar_tickets,
)
from jml.dominio.tipos import (
    AccionDeTicket as A,
)
from jml.dominio.tipos import (
    ClaseTicket,
    Cola,
    EstadoInicialDeTicket,
    EstadoSolicitud,
    PerfilDeRecurso,
    Prioridad,
    SistemaDeCuenta,
    Subtipo,
    TipoDeVinculacion,
    TipoEvento,
)
from jml.dominio.valores import CalendarioHabil
from tests.fabricas import AHORA, SEDES, SENTINELA, Caso, caso, perfil

CAL = CalendarioHabil()
I, P, POST = ClaseTicket.CIERRE_INMEDIATO, ClaseTicket.CIERRE_PROGRAMADO, ClaseTicket.POSTERIOR  # noqa: E741
AD, COM, LIC, INV = Cola.AD, Cola.COMUNICACIONES, Cola.LICENCIAS, Cola.INVENTARIO


def generar(c: Caso) -> tuple[TicketDeCola, ...]:
    return generar_tickets(c.solicitud, c.actual, c.nuevo, c.colaborador, CAL, AHORA)


def forma(ts: tuple[TicketDeCola, ...]) -> list[tuple[Cola, ClaseTicket, A, EstadoInicialDeTicket]]:
    return [(t.cola, t.clase, t.accion, t.estado_inicial) for t in ts]


def por_cola(ts: tuple[TicketDeCola, ...], cola: Cola, clase: ClaseTicket = I) -> TicketDeCola:
    return next(t for t in ts if t.cola is cola and t.clase is clase)


NUEVO, ESPERA = EstadoInicialDeTicket.NUEVO, EstadoInicialDeTicket.EN_ESPERA

# --- la matriz evento x cola del SRS 4.4, celda por celda (CA-03, CA-04) -----------------------

MATRIZ_ESPERADA = [
    pytest.param(
        dict(tipo=TipoEvento.ING, vinculacion=TipoDeVinculacion.EMPLEADO),
        [
            (AD, I, A.ALTA, NUEVO),
            (COM, I, A.ALTA, NUEVO),
            (LIC, I, A.ALTA, NUEVO),
            (INV, I, A.EQUIPO, NUEVO),
        ],
        id="ING empleado con equipo",
    ),
    pytest.param(
        dict(tipo=TipoEvento.ING, vinculacion=TipoDeVinculacion.CONTRATISTA),
        [
            (AD, I, A.ALTA, NUEVO),
            (COM, I, A.ALTA, NUEVO),
            (LIC, I, A.ALTA, NUEVO),
            (INV, I, A.EQUIPO, NUEVO),
        ],
        id="ING contratista con equipo",
    ),
    pytest.param(
        dict(tipo=TipoEvento.ING, requiere_equipo=False),
        [(AD, I, A.ALTA, NUEVO), (COM, I, A.ALTA, NUEVO), (LIC, I, A.ALTA, NUEVO)],
        id="ING sin equipo (S-04)",
    ),
    pytest.param(
        dict(tipo=TipoEvento.VAC),
        [
            (AD, I, A.SUSPENSION, NUEVO),
            (AD, P, A.REACTIVACION, ESPERA),
            (LIC, I, A.SUSPENSION, NUEVO),
            (LIC, P, A.REACTIVACION, ESPERA),
        ],
        id="VAC: solo AD y Licencias",
    ),
    pytest.param(
        dict(tipo=TipoEvento.CDP, departamento="Finanzas", destino="TI"),
        [
            (AD, I, A.CAMBIO, NUEVO),
            (COM, I, A.CAMBIO, NUEVO),
            (LIC, I, A.CAMBIO, NUEVO),
            (INV, I, A.EQUIPO, NUEVO),
        ],
        id="CDP Finanzas->TI (cambia todo)",
    ),
    pytest.param(
        dict(tipo=TipoEvento.CDP, departamento="Operaciones", destino="Finanzas"),
        [(AD, I, A.CAMBIO, NUEVO), (LIC, I, A.CAMBIO, NUEVO)],
        id="CDP Operaciones->Finanzas (sin red ni equipo)",
    ),
    pytest.param(
        dict(tipo=TipoEvento.CDP, departamento="Finanzas", destino="Finanzas"),
        [],
        id="CDP sin diferencia: ningun ticket (S-05)",
    ),
    pytest.param(
        dict(tipo=TipoEvento.CSU, traslada_equipo=True),
        [(AD, I, A.CAMBIO, NUEVO), (COM, I, A.CAMBIO, NUEVO), (INV, I, A.EQUIPO, NUEVO)],
        id="CSU con traslado de equipo",
    ),
    pytest.param(
        dict(tipo=TipoEvento.CSU, traslada_equipo=False),
        [(AD, I, A.CAMBIO, NUEVO), (COM, I, A.CAMBIO, NUEVO)],
        id="CSU sin traslado",
    ),
    pytest.param(
        dict(tipo=TipoEvento.CSU, sede="Cali", sede_destino="Cali", traslada_equipo=False),
        [],
        id="CSU sin diferencia: ningun ticket (S-05)",
    ),
    pytest.param(
        dict(tipo=TipoEvento.RET, subtipo=Subtipo.RENUNCIA),
        [
            (AD, I, A.BAJA, NUEVO),
            (AD, POST, A.ELIMINACION, ESPERA),
            (COM, I, A.BAJA, NUEVO),
            (LIC, I, A.BAJA, NUEVO),
            (LIC, POST, A.ELIMINACION, ESPERA),
            (INV, I, A.EQUIPO, NUEVO),
        ],
        id="RET renuncia",
    ),
    pytest.param(
        dict(tipo=TipoEvento.RET, subtipo=Subtipo.FIN_DE_CONTRATO),
        [
            (AD, I, A.BAJA, NUEVO),
            (AD, POST, A.ELIMINACION, ESPERA),
            (COM, I, A.BAJA, NUEVO),
            (LIC, I, A.BAJA, NUEVO),
            (LIC, POST, A.ELIMINACION, ESPERA),
            (INV, I, A.EQUIPO, NUEVO),
        ],
        id="RET fin de contrato",
    ),
    pytest.param(
        dict(tipo=TipoEvento.EMG, subtipo=Subtipo.DESPIDO_CON_JUSTA_CAUSA),
        [
            (AD, I, A.BAJA, NUEVO),
            (AD, POST, A.ELIMINACION, ESPERA),
            (COM, I, A.BAJA, NUEVO),
            (LIC, I, A.BAJA, NUEVO),
            (LIC, POST, A.ELIMINACION, ESPERA),
            (INV, I, A.EQUIPO, NUEVO),
        ],
        id="EMG despido",
    ),
    pytest.param(
        dict(tipo=TipoEvento.EMG, subtipo=Subtipo.FUGA_DETECTADA),
        [
            (AD, I, A.BAJA, NUEVO),
            (AD, POST, A.ELIMINACION, ESPERA),
            (COM, I, A.BAJA, NUEVO),
            (LIC, I, A.BAJA, NUEVO),
            (LIC, POST, A.ELIMINACION, ESPERA),
            (INV, I, A.EQUIPO, NUEVO),
        ],
        id="EMG fuga detectada",
    ),
]


@pytest.mark.parametrize(("params", "esperado"), MATRIZ_ESPERADA)
def test_matriz_evento_x_cola_celda_por_celda(
    params: dict[str, object], esperado: list[object]
) -> None:
    ts = generar(caso(**params))  # type: ignore[arg-type]  # parametros nombrados de prueba
    assert forma(ts) == esperado


# --- prioridades, clases y vencimientos (S-02, S-03, S-16, S-17) --------------------------------


def test_prioridades_por_tipo_SRS_4_1() -> None:
    esperadas = {
        TipoEvento.ING: Prioridad.MEDIA,
        TipoEvento.VAC: Prioridad.MEDIA,
        TipoEvento.CDP: Prioridad.MEDIA,
        TipoEvento.CSU: Prioridad.MEDIA,
        TipoEvento.RET: Prioridad.ALTA,
        TipoEvento.EMG: Prioridad.MUY_ALTA,
    }
    for tipo, prioridad in esperadas.items():
        sub = {TipoEvento.RET: Subtipo.RENUNCIA, TipoEvento.EMG: Subtipo.FUGA_DETECTADA}.get(tipo)
        for t in generar(caso(tipo, sub)):
            if t.clase is not POST:
                assert t.prioridad is prioridad


def test_los_posteriores_son_prioridad_media_S_17() -> None:
    for sub, tipo in ((Subtipo.RENUNCIA, TipoEvento.RET), (Subtipo.FUGA_DETECTADA, TipoEvento.EMG)):
        posteriores = [t for t in generar(caso(tipo, sub)) if t.clase is POST]
        assert len(posteriores) == 2
        assert {t.prioridad for t in posteriores} == {Prioridad.MEDIA}


def test_ING_vence_a_las_0000_de_bogota_del_dia_de_ingreso_S_02() -> None:
    c = caso(TipoEvento.ING, dias=7)
    esperado = datetime(2026, 10, 19, 5, 0, tzinfo=UTC)  # 00:00 -05
    assert {t.vence_en for t in generar(c)} == {esperado}


def test_VAC_suspension_el_dia_de_inicio_y_reactivacion_el_dia_de_regreso_S_16() -> None:
    ts = generar(caso(TipoEvento.VAC, dias=7))
    inicio, regreso = date(2026, 10, 19), date(2026, 11, 2)
    susp = por_cola(ts, AD, I)
    react = por_cola(ts, AD, P)
    assert susp.vence_en == datetime(2026, 10, 20, 4, 59, 59, tzinfo=UTC)  # 23:59:59 -05 del 19
    assert react.vence_en == datetime(2026, 11, 3, 4, 59, 59, tzinfo=UTC)
    assert react.activo_desde == datetime(2026, 11, 2, 5, 0, tzinfo=UTC)
    assert susp.activo_desde == susp.emitido_en == AHORA
    assert regreso > inicio


def test_CDP_y_CSU_vencen_1_dia_habil_despues_S_01() -> None:
    # fecha efectiva viernes 16-oct-2026 (dias=4) -> lunes 19 a las 23:59:59
    cdp = generar(caso(TipoEvento.CDP, dias=4))
    assert {t.vence_en for t in cdp} == {datetime(2026, 10, 20, 4, 59, 59, tzinfo=UTC)}
    # martes 13 -> miercoles 14
    csu = generar(caso(TipoEvento.CSU, dias=1))
    assert {t.vence_en for t in csu} == {datetime(2026, 10, 15, 4, 59, 59, tzinfo=UTC)}


def test_el_calendario_con_festivos_corre_el_vencimiento_S_01() -> None:
    c = caso(TipoEvento.CDP, dias=4)  # viernes 16
    festivo = CalendarioHabil(frozenset({date(2026, 10, 19)}))
    ts = generar_tickets(c.solicitud, c.actual, c.nuevo, c.colaborador, festivo, AHORA)
    assert {t.vence_en for t in ts} == {datetime(2026, 10, 21, 4, 59, 59, tzinfo=UTC)}


def test_RET_vence_al_final_del_ultimo_dia_laborado_y_el_posterior_a_los_90_dias_S_03() -> None:
    ts = generar(caso(TipoEvento.RET, Subtipo.RENUNCIA, dias=20))  # ultimo dia 1-nov-2026
    baja = por_cola(ts, AD, I)
    assert baja.vence_en == datetime(2026, 11, 2, 4, 59, 59, tzinfo=UTC)
    post = por_cola(ts, AD, POST)
    assert post.vence_en == datetime(2027, 1, 31, 4, 59, 59, tzinfo=UTC)
    assert post.activo_desde == datetime(2027, 1, 30, 5, 0, tzinfo=UTC)


def test_EMG_vence_en_1_hora_y_el_posterior_cuenta_desde_la_emision_S_03() -> None:
    ts = generar(caso(TipoEvento.EMG, Subtipo.FUGA_DETECTADA))
    assert por_cola(ts, AD, I).vence_en == AHORA + timedelta(hours=1)
    # emision 12-oct-2026 (Bogota) + 90 dias = 10-ene-2027
    assert por_cola(ts, AD, POST).vence_en == datetime(2027, 1, 11, 4, 59, 59, tzinfo=UTC)


def test_S_22_un_retiro_futuro_crea_la_baja_como_nuevo_con_vencimiento_en_su_fecha() -> None:
    """Precedente de CA-04 (la suspension de VAC es `Nuevo` aunque las vacaciones sean futuras)."""
    ts = generar(caso(TipoEvento.RET, Subtipo.RENUNCIA, dias=200))
    baja = por_cola(ts, AD, I)
    assert baja.estado_inicial is NUEVO
    assert baja.activo_desde == baja.emitido_en
    assert baja.vence_en > baja.emitido_en + timedelta(days=199)


def test_los_posteriores_no_bloquean_el_cierre_RF_26() -> None:
    for t in generar(caso(TipoEvento.RET, Subtipo.RENUNCIA)):
        assert t.bloquea_el_cierre is (t.clase is not POST)


# --- contenido de las listas de verificacion --------------------------------------------------


def texto(t: TicketDeCola) -> str:
    return "\n".join(t.lista_de_verificacion)


def test_ING_AD_lleva_usuario_grupos_recursos_y_soporte_CA_19() -> None:
    c = caso(TipoEvento.ING)
    t = por_cola(generar(c), AD)
    txt = texto(t)
    assert "Verificar el soporte de vinculación adjunto" in txt
    assert "maria.gomez (maria.gomez@ad.andina.test)" in txt
    assert "GG-Finanzas" in txt
    assert "GG-Sede-Bogota" in txt
    p = perfil("Finanzas")
    for r in p.recursos:  # ruta, serie, perfil y grupo de CADA recurso
        linea = next(x for x in t.lista_de_verificacion if r.ruta in x)
        assert f"serie: {r.serie}" in linea
        assert f"perfil: {r.perfil.value}" in linea
        assert f"grupo: {r.grupo}" in linea
    assert "expiración" not in txt  # empleado: sin fecha de fin
    assert t.adjunta_soporte is True


def test_ING_contratista_fija_fecha_de_expiracion_S_21() -> None:
    t = por_cola(generar(caso(TipoEvento.ING, vinculacion=TipoDeVinculacion.CONTRATISTA)), AD)
    assert "Fijar la fecha de expiración de la cuenta: 2027-05-07." in texto(t)


def test_el_soporte_se_adjunta_solo_a_AD_y_Licencias_RF_40() -> None:
    adjuntan = {t.cola for t in generar(caso(TipoEvento.ING)) if t.adjunta_soporte}
    assert adjuntan == {AD, LIC}
    assert "soporte" in texto(por_cola(generar(caso(TipoEvento.ING)), LIC)).lower()
    for tipo, sub in ((TipoEvento.VAC, None), (TipoEvento.RET, Subtipo.RENUNCIA)):
        assert not any(t.adjunta_soporte for t in generar(caso(tipo, sub)))


def test_ING_otras_colas() -> None:
    ts = generar(caso(TipoEvento.ING))
    assert "NET-WIFI-CORP" in texto(por_cola(ts, COM))
    assert "NET-VLAN-Bogota" in texto(por_cola(ts, COM))
    lic = texto(por_cola(ts, LIC))
    assert "maria.gomez@andina.example" in lic
    assert "M365-Finanzas" in lic
    assert "Software contable" in lic
    assert "Escritorio" in texto(por_cola(ts, INV))
    assert "acta de entrega" in texto(por_cola(ts, INV))


def test_VAC_no_cambia_contrasena_ni_grupos_y_programa_la_reactivacion() -> None:
    ts = generar(caso(TipoEvento.VAC))
    assert "No cambiar la contraseña ni quitar los grupos" in texto(por_cola(ts, AD, I))
    assert "Habilitar la cuenta maria.gomez" in texto(por_cola(ts, AD, P))
    assert "Desbloquear" in texto(por_cola(ts, LIC, P))
    assert por_cola(ts, AD, P).estado_inicial is ESPERA
    assert por_cola(ts, AD, I).estado_inicial is NUEVO


def test_CDP_lista_la_diferencia_de_grupos_y_recursos_CA_19() -> None:
    t = por_cola(generar(caso(TipoEvento.CDP, departamento="Finanzas", destino="TI")), AD)
    txt = texto(t)
    assert "Quitar los grupos de AD del perfil anterior: " in txt
    assert "GG-Finanzas" in txt
    assert "Agregar los grupos de AD del perfil nuevo: " in txt
    assert "GG-TI" in txt
    retiros = [x for x in t.lista_de_verificacion if "Retiro de accesos" in x and "|" in x]
    assert len(retiros) == 2  # Contabilidad y Presupuesto
    assert all("Contabilidad" in x or "Presupuesto" in x for x in retiros)
    nuevos = [x for x in t.lista_de_verificacion if "perfil: Edición" in x]
    assert any(r"\TI |" in x for x in nuevos)
    assert any("comun" in x and "FS-Comun-RW" in x for x in nuevos)  # Consulta -> Edicion


def test_CDP_no_retira_una_ruta_que_sigue_vigente() -> None:
    t = por_cola(generar(caso(TipoEvento.CDP, departamento="Comercial", destino="Operaciones")), AD)
    retiros = [x for x in t.lista_de_verificacion if "perfil: Retiro de accesos" in x]
    assert len(retiros) == 1
    assert "Comercial" in retiros[0]
    assert not any("comun" in x for x in retiros)


def test_CDP_cambio_de_equipo_nombra_los_tipos() -> None:
    t = por_cola(generar(caso(TipoEvento.CDP, departamento="Finanzas", destino="TI")), INV)
    assert "Escritorio" in texto(t)
    assert "Portátil" in texto(t)


def test_CSU_solo_toca_los_grupos_de_sede() -> None:
    ts = generar(caso(TipoEvento.CSU, sede="Bogotá", sede_destino="Medellín", traslada_equipo=True))
    assert "GG-Sede-Bogota" in texto(por_cola(ts, AD))
    assert "GG-Sede-Medellin" in texto(por_cola(ts, AD))
    assert "NET-VLAN-Bogota" in texto(por_cola(ts, COM))
    assert "NET-VLAN-Medellin" in texto(por_cola(ts, COM))
    assert "Medellín" in texto(por_cola(ts, INV))
    assert not [x for x in texto(por_cola(ts, AD)).splitlines() if "|" in x]  # sin recursos


@pytest.mark.parametrize(
    ("tipo", "sub"),
    [(TipoEvento.RET, Subtipo.RENUNCIA), (TipoEvento.EMG, Subtipo.FUGA_DETECTADA)],
)
def test_RET_y_EMG_retiran_acceso_en_todos_los_recursos_CA_19(
    tipo: TipoEvento, sub: Subtipo
) -> None:
    c = caso(tipo, sub)
    ad = por_cola(generar(c), AD)
    recursos = [x for x in ad.lista_de_verificacion if x.startswith("  - ")]
    assert len(recursos) == len(perfil("Finanzas").recursos)
    assert all("perfil: Retiro de accesos" in x for x in recursos)
    assert "Mover la cuenta a la OU Deshabilitados." in ad.lista_de_verificacion
    assert FRASE_DE_CONTRASENA in ad.lista_de_verificacion
    assert "Dar al jefe directo perfil Consulta sobre la carpeta personal por 30 días." in texto(ad)
    assert "Deshabilitar la cuenta maria.gomez" in texto(ad)
    assert "Quitar todos los grupos de red" in texto(por_cola(generar(c), COM))
    lic = texto(por_cola(generar(c), LIC))
    assert "Bloquear el inicio de sesión" in lic
    assert "Liberar las licencias" in lic


def test_RET_sin_jefe_no_agrega_el_acceso_del_jefe() -> None:
    c = caso(TipoEvento.RET, Subtipo.RENUNCIA)
    sin_jefe = replace(c.colaborador, jefe_id=None)
    ts = generar_tickets(c.solicitud, c.actual, c.nuevo, sin_jefe, CAL, AHORA)
    assert "jefe directo" not in texto(por_cola(ts, AD))


def test_EMG_marca_la_ejecucion_inmediata_e_inventario_recupera() -> None:
    ts = generar(caso(TipoEvento.EMG, Subtipo.FUGA_DETECTADA))
    for cola in (AD, COM, LIC, INV):
        assert texto(por_cola(ts, cola)).startswith("Emergencia: ejecutar de inmediato.")
    assert "Recuperar el equipo" in texto(por_cola(ts, INV))
    ret = generar(caso(TipoEvento.RET, Subtipo.RENUNCIA))
    assert "Recibir el equipo" in texto(por_cola(ret, INV))
    assert "paz y salvo" in texto(por_cola(ret, INV))
    assert "Emergencia" not in "\n".join(t.titulo + texto(t) for t in ret)


def test_el_posterior_elimina_la_cuenta_y_la_identidad() -> None:
    ts = generar(caso(TipoEvento.RET, Subtipo.RENUNCIA))
    assert "Eliminar la cuenta maria.gomez" in texto(por_cola(ts, AD, POST))
    assert "Eliminar la identidad maria.gomez@andina.example" in texto(por_cola(ts, LIC, POST))


# --- identidad de los tickets -----------------------------------------------------------------


def test_clave_de_idempotencia_determinista() -> None:
    assert (
        clave_de_idempotencia("SOL-2026-000001", AD, I, 1)
        == "SOL-2026-000001:AD:cierre_inmediato:1"
    )
    ts = generar(caso(TipoEvento.RET, Subtipo.RENUNCIA))
    claves = [t.clave_de_idempotencia for t in ts]
    assert len(claves) == len(set(claves))
    assert generar(caso(TipoEvento.RET, Subtipo.RENUNCIA)) == ts  # pura: mismo resultado


def test_categoria_y_sistema_por_cola() -> None:
    assert categoria_del_ticket(TipoEvento.ING, AD, A.ALTA) == "JML/ING/AD/alta"
    assert COLA_A_SISTEMA == {
        AD: SistemaDeCuenta.AD,
        COM: SistemaDeCuenta.RED,
        LIC: SistemaDeCuenta.M365,
        INV: None,
        Cola.REVISION_MANUAL: None,
    }
    t = por_cola(generar(caso(TipoEvento.ING)), COM)
    assert t.sistema is SistemaDeCuenta.RED
    assert t.categoria == "JML/ING/COMUNICACIONES/alta"
    assert por_cola(generar(caso(TipoEvento.ING)), INV).sistema is None


def test_el_orden_es_por_cola_y_luego_por_clase() -> None:
    ts = generar(caso(TipoEvento.RET, Subtipo.RENUNCIA))
    assert [(t.cola, t.clase) for t in ts] == [
        (AD, I),
        (AD, POST),
        (COM, I),
        (LIC, I),
        (LIC, POST),
        (INV, I),
    ]


def test_datos_tecnicos_RF_20() -> None:
    t = por_cola(generar(caso(TipoEvento.ING)), AD)
    assert t.datos.colaborador == "María José Gómez Ramírez"
    assert t.datos.usuario == "maria.gomez"
    assert t.datos.perfil == "Finanzas / Bogotá"
    assert t.datos.fecha_efectiva == date(2026, 10, 19)
    assert t.datos.solicitud == "SOL-2026-000001"
    assert t.titulo.startswith("SOL-2026-000001")


# --- errores de entrada ------------------------------------------------------------------------


def test_solo_se_generan_tickets_de_una_solicitud_aprobada() -> None:
    c = caso(TipoEvento.VAC)
    for estado in set(EstadoSolicitud) - {EstadoSolicitud.APROBADA}:
        with pytest.raises(TransicionInvalida):
            generar_tickets(
                replace(c.solicitud, estado=estado), None, None, c.colaborador, CAL, AHORA
            )


def test_perfiles_obligatorios_segun_el_tipo() -> None:
    for tipo, sub in ((TipoEvento.RET, Subtipo.RENUNCIA), (TipoEvento.EMG, Subtipo.FUGA_DETECTADA)):
        c = caso(tipo, sub)
        with pytest.raises(DatoInvalido, match="perfil_actual"):
            generar_tickets(c.solicitud, None, None, c.colaborador, CAL, AHORA)
    c = caso(TipoEvento.ING)
    with pytest.raises(DatoInvalido, match="perfil_nuevo"):
        generar_tickets(c.solicitud, None, None, c.colaborador, CAL, AHORA)
    for tipo in (TipoEvento.CDP, TipoEvento.CSU):
        c = caso(tipo)
        with pytest.raises(DatoInvalido, match="perfil_actual"):
            generar_tickets(c.solicitud, None, c.nuevo, c.colaborador, CAL, AHORA)
        with pytest.raises(DatoInvalido, match="perfil_nuevo"):
            generar_tickets(c.solicitud, c.actual, None, c.colaborador, CAL, AHORA)
    c = caso(TipoEvento.VAC)
    with pytest.raises(DatoInvalido, match="perfil_actual"):
        generar_tickets(c.solicitud, None, None, c.colaborador, CAL, AHORA)


def test_los_perfiles_deben_ser_coherentes_con_el_evento() -> None:
    c = caso(TipoEvento.CDP)
    with pytest.raises(DatoInvalido, match="conserva la sede"):
        generar_tickets(c.solicitud, c.actual, perfil("TI", "Cali"), c.colaborador, CAL, AHORA)
    c = caso(TipoEvento.CSU, sede_destino="Cali")
    with pytest.raises(DatoInvalido, match="solo cambia la sede"):
        generar_tickets(c.solicitud, c.actual, perfil("TI", "Cali"), c.colaborador, CAL, AHORA)
    with pytest.raises(DatoInvalido, match="solo cambia la sede"):
        generar_tickets(
            c.solicitud, c.actual, perfil("Finanzas", "Medellín"), c.colaborador, CAL, AHORA
        )


def test_el_colaborador_debe_ser_el_de_la_solicitud_y_tener_usuario() -> None:
    c = caso(TipoEvento.RET, Subtipo.RENUNCIA)
    with pytest.raises(DatoInvalido, match="colaborador"):
        generar_tickets(c.solicitud, c.actual, None, replace(c.colaborador, id="otro"), CAL, AHORA)
    with pytest.raises(DatoInvalido, match="usuario"):
        generar_tickets(
            c.solicitud, c.actual, None, replace(c.colaborador, usuario=None), CAL, AHORA
        )


# --- confidencialidad y contrasenas (CA-10, T7, T9, P4) ----------------------------------------

PROHIBIDO = re.compile(r"password|contrase[ñn]a\s*[:=]|clave\s*[:=]|pwd|secret", re.IGNORECASE)


def verificar_texto(t: TicketDeCola) -> None:
    todo = t.como_texto()
    assert SENTINELA not in todo
    assert not PROHIBIDO.search(todo)
    # la unica mencion de contrasena permitida es la frase de SRS 4.5
    sin_frase = todo.replace(FRASE_DE_CONTRASENA, "")
    assert "contraseña" not in sin_frase.replace(
        "No cambiar la contraseña ni quitar los grupos", ""
    )
    for subtipo in Subtipo:  # el subtipo no es dato tecnico (RF-20)
        assert subtipo.value not in todo


CASOS_P4 = st.sampled_from(
    [
        (TipoEvento.ING, None),
        (TipoEvento.VAC, None),
        (TipoEvento.CDP, None),
        (TipoEvento.CSU, None),
        (TipoEvento.RET, Subtipo.RENUNCIA),
        (TipoEvento.RET, Subtipo.FIN_DE_CONTRATO),
        (TipoEvento.EMG, Subtipo.DESPIDO_CON_JUSTA_CAUSA),
        (TipoEvento.EMG, Subtipo.FUGA_DETECTADA),
    ]
)
DEPTOS = st.sampled_from(["Gerencia", "RRHH", "Finanzas", "Comercial", "TI", "Operaciones"])

PERMITIDOS_P4 = {
    TipoEvento.ING: {(AD, I), (COM, I), (LIC, I), (INV, I)},
    TipoEvento.VAC: {(AD, I), (AD, P), (LIC, I), (LIC, P)},
    TipoEvento.CDP: {(AD, I), (COM, I), (LIC, I), (INV, I)},
    TipoEvento.CSU: {(AD, I), (COM, I), (INV, I)},
    TipoEvento.RET: {(AD, I), (AD, POST), (COM, I), (LIC, I), (LIC, POST), (INV, I)},
    TipoEvento.EMG: {(AD, I), (AD, POST), (COM, I), (LIC, I), (LIC, POST), (INV, I)},
}


@given(
    CASOS_P4,
    DEPTOS,
    DEPTOS,
    st.sampled_from(SEDES),
    st.sampled_from(SEDES),
    st.sampled_from(list(TipoDeVinculacion)),
    st.booleans(),
    st.booleans(),
    st.integers(0, 400),
)
def test_P4_generacion_de_tickets(
    par: tuple[TipoEvento, Subtipo | None],
    depto: str,
    destino: str,
    sede: str,
    sede_destino: str,
    vinculacion: TipoDeVinculacion,
    equipo: bool,
    traslada: bool,
    dias: int,
) -> None:
    tipo, sub = par
    c = caso(
        tipo,
        sub,
        departamento=depto,
        destino=destino,
        sede=sede,
        sede_destino=sede_destino,
        vinculacion=vinculacion,
        requiere_equipo=equipo,
        traslada_equipo=traslada,
        dias=dias,
    )
    ts = generar(c)
    assert generar(c) == ts  # determinista
    claves = [t.clave_de_idempotencia for t in ts]
    assert len(claves) == len(set(claves))
    assert {(t.cola, t.clase) for t in ts} <= PERMITIDOS_P4[
        tipo
    ]  # nunca una celda fuera de la matriz
    for t in ts:
        verificar_texto(t)
        assert t.vence_en.tzinfo is UTC
        assert t.emitido_en == AHORA
        assert t.lista_de_verificacion
        assert t.activo_desde >= AHORA or t.clase is I
        assert (t.estado_inicial is NUEVO) is (t.clase is I)
        assert t.clave_de_idempotencia.startswith(t.solicitud_id)
        if t.clase is not I:
            assert t.activo_desde > AHORA
    if tipo is TipoEvento.ING:
        assert {t.cola for t in ts} >= {AD, COM, LIC}
        assert (INV in {t.cola for t in ts}) is equipo
    if tipo in (TipoEvento.RET, TipoEvento.EMG):
        assert len(ts) == 6
        assert sum(1 for t in ts if t.clase is POST) == 2
    # los recursos de un perfil se listan completos en el ING
    if tipo is TipoEvento.ING:
        ad = por_cola(ts, AD)
        for r in perfil(depto, sede).recursos:
            assert any(
                r.ruta in x and r.grupo in x and r.serie in x for x in ad.lista_de_verificacion
            )
        assert all(
            r.perfil is not PerfilDeRecurso.RETIRO_DE_ACCESOS for r in perfil(depto, sede).recursos
        )


def test_el_centinela_nunca_llega_al_ticket_aunque_la_solicitud_lo_tenga_CA_10() -> None:
    for tipo, sub in ((TipoEvento.RET, Subtipo.RENUNCIA), (TipoEvento.EMG, Subtipo.FUGA_DETECTADA)):
        c = caso(tipo, sub)
        assert c.solicitud.restringido is not None
        assert c.solicitud.restringido.revelar() == SENTINELA
        for t in generar(c):
            assert SENTINELA not in repr(t)
            assert SENTINELA not in t.como_texto()


def test_perfil_de_acceso_usado_es_el_de_la_matriz() -> None:
    assert isinstance(perfil("TI"), PerfilDeAcceso)
