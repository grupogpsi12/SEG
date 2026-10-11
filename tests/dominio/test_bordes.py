"""Bordes de la derivacion de cuentas, de la diferencia de perfiles y del texto de los tickets.

Cada prueba fija un borde donde un `<` por `<=`, un `or` por `and` o un valor por defecto
cambiado seguia dejando todas las demas pruebas en verde (docs/spikes/mutacion.md).
"""

import dataclasses
from datetime import timedelta

from jml.dominio.cuentas import Cuenta
from jml.dominio.perfiles import DiferenciaDePerfiles, aplicar, diferencia
from jml.dominio.tickets import DatosTecnicos, Observacion, TicketDeCola
from jml.dominio.tipos import (
    EstadoDeCuenta,
    EstadoDeTicket,
    MarcaDeCuenta,
    PerfilDeRecurso,
    Subtipo,
    TipoDeEquipo,
    TipoEvento,
)
from tests.dominio.test_resolucion_cuentas import (
    AD,
    TARDE,
    I,
    P,
    cuenta_de,
    derivar,
    elegir,
    obs,
)
from tests.fabricas import AHORA, caso, perfil

E, M, ET = EstadoDeCuenta, MarcaDeCuenta, EstadoDeTicket


# --- cuentas ---------------------------------------------------------------------------------


def test_dos_observaciones_con_la_misma_hora_pero_distinto_contenido_si_se_aplican() -> None:
    """Solo una observacion ESTRICTAMENTE mas vieja se ignora (RF-25)."""
    t = elegir(caso(TipoEvento.RET, Subtipo.RENUNCIA), AD, I)
    previa = obs(ET.EN_CURSO, False, minutos=3)
    misma_hora = obs(ET.RESUELTO, True, minutos=3)
    r = derivar(cuenta_de(t, E.ACTIVA), t, previa, misma_hora, TARDE)
    assert r.cuenta is not None
    assert r.cuenta.estado is E.DESHABILITADA


def test_un_ticket_con_el_mismo_orden_que_el_que_gobierna_no_es_mas_antiguo_S_10() -> None:
    a = elegir(caso(TipoEvento.RET, Subtipo.RENUNCIA, numero=1), AD, I)
    b = dataclasses.replace(
        elegir(caso(TipoEvento.RET, Subtipo.RENUNCIA, numero=2), AD, I),
        emitido_en=a.emitido_en,
        vence_en=a.vence_en,
    )
    gobierna = cuenta_de(a, E.PENDIENTE_BAJA)
    r = derivar(gobierna, b, None, obs(ET.RESUELTO, True), TARDE)
    assert r.cuenta is not None
    assert (r.cuenta.estado, r.cuenta.ticket_origen) == (E.DESHABILITADA, b.clave_de_idempotencia)


def test_un_programado_cuenta_como_pendiente_justo_en_su_fecha() -> None:
    t = elegir(caso(TipoEvento.VAC), AD, P)
    base = dataclasses.replace(
        cuenta_de(t, E.SUSPENDIDA), ticket_origen="susp", orden_origen=(AHORA, AHORA)
    )
    antes = derivar(base, t, None, obs(ET.NUEVO, False), t.activo_desde - timedelta(seconds=1))
    justo = derivar(base, t, None, obs(ET.NUEVO, False), t.activo_desde)
    assert antes.cuenta == base
    assert justo.cuenta is not None
    assert justo.cuenta.ticket_origen == t.clave_de_idempotencia


def test_un_cambio_abierto_conserva_el_estado_actual_de_la_cuenta() -> None:
    t = elegir(caso(TipoEvento.CDP), AD, I)
    suspendida = dataclasses.replace(
        cuenta_de(t, E.SUSPENDIDA),
        ticket_origen="otro",
        orden_origen=(AHORA - timedelta(days=2),) * 2,
    )
    r = derivar(suspendida, t, None, obs(ET.EN_CURSO, False), TARDE)
    assert r.cuenta is not None
    assert (r.cuenta.estado, r.cuenta.marca) == (E.SUSPENDIDA, M.CAMBIO_PENDIENTE)


def _con(
    t: TicketDeCola, estado: EstadoDeCuenta, desde_hace: int = 0, marca: MarcaDeCuenta | None = None
) -> Cuenta:
    return dataclasses.replace(
        cuenta_de(t, estado, marca), desde=TARDE - timedelta(days=desde_hace)
    )


def test_desde_solo_cambia_cuando_cambia_el_estado_o_el_ticket_de_origen() -> None:
    t = elegir(caso(TipoEvento.CDP), AD, I)
    gobernada = _con(t, E.ACTIVA, desde_hace=10)
    # mismo estado y mismo ticket, solo cambia la marca: conserva la fecha
    solo_marca = derivar(
        gobernada, t, obs(ET.EN_CURSO, False), obs(ET.RESUELTO, False, minutos=1), TARDE
    )
    assert solo_marca.cuenta is not None
    assert solo_marca.cuenta.marca is M.CIERRE_SIN_SOLUCION
    assert solo_marca.cuenta.desde == gobernada.desde
    # cambia el estado: toma la hora de la observacion
    ret = elegir(caso(TipoEvento.RET, Subtipo.RENUNCIA), AD, I)
    con_estado = derivar(_con(ret, E.ACTIVA, 10), ret, None, obs(ET.EN_CURSO, False), TARDE)
    assert con_estado.cuenta is not None
    assert con_estado.cuenta.desde == TARDE
    # mismo estado pero OTRO ticket de origen: tambien la toma
    nueva_origen = derivar(
        _con(t, E.ACTIVA, 10),
        dataclasses.replace(
            t, clave_de_idempotencia="otra", emitido_en=t.emitido_en + timedelta(hours=1)
        ),
        None,
        obs(ET.EN_CURSO, False),
        TARDE,
    )
    assert nueva_origen.cuenta is not None
    assert nueva_origen.cuenta.estado is E.ACTIVA
    assert nueva_origen.cuenta.desde == TARDE
    assert nueva_origen.cuenta.ticket_origen == "otra"


def test_una_cuenta_nueva_toma_la_hora_de_la_observacion() -> None:
    t = elegir(caso(TipoEvento.ING), AD, I)
    r = derivar(None, t, None, obs(ET.NUEVO, False), TARDE)
    assert r.cuenta is not None
    assert r.cuenta.desde == TARDE


# --- perfiles ---------------------------------------------------------------------------------


def test_aplicar_la_diferencia_real_de_un_cdp_reconstruye_el_perfil_nuevo() -> None:
    a, b = perfil("Finanzas"), perfil("TI")
    d = diferencia(a, b)
    assert d.recursos_a_retirar  # hay retiros que aplicar
    assert aplicar(d, a) == b
    assert aplicar(d, a).tipo_equipo is TipoDeEquipo.PORTATIL  # cambia de escritorio a portatil
    assert {r.ruta for r in aplicar(d, a).recursos} == {r.ruta for r in b.recursos}


def test_aplicar_sin_cambio_de_equipo_conserva_el_de_la_base() -> None:
    a, b = perfil("Comercial"), perfil("Gerencia")  # ambos portatil
    d = diferencia(a, b)
    assert d.equipo_nuevo is None
    assert aplicar(d, a).tipo_equipo is TipoDeEquipo.PORTATIL


def _vacia(**cambios: object) -> DiferenciaDePerfiles:
    base = diferencia(perfil("TI"), perfil("TI"))
    return dataclasses.replace(base, **cambios)  # type: ignore[arg-type]  # kwargs de prueba


def test_cada_campo_de_la_diferencia_basta_para_que_no_este_vacia() -> None:
    assert _vacia().esta_vacia
    uno = ("g",)
    recurso = diferencia(perfil("Finanzas"), perfil("TI")).recursos_a_retirar
    unicos: list[dict[str, object]] = [
        {"grupos_ad_agregar": uno}, {"grupos_ad_quitar": uno},
        {"recursos_a_aplicar": recurso}, {"recursos_a_retirar": recurso},
        {"grupos_red_agregar": uno}, {"grupos_red_quitar": uno},
        {"grupos_m365_agregar": uno}, {"grupos_m365_quitar": uno},
        {"licencias_agregar": uno}, {"licencias_quitar": uno},
        {"equipo_nuevo": TipoDeEquipo.ESCRITORIO},
    ]  # fmt: skip
    for cambio in unicos:
        d = _vacia(**cambio)
        assert not d.esta_vacia, cambio
    # y cada familia enciende SOLO su propia bandera
    assert _vacia(grupos_ad_quitar=uno).cambia_ad
    assert not _vacia(grupos_ad_quitar=uno).cambia_red
    assert not _vacia(grupos_ad_quitar=uno).cambia_m365
    assert _vacia(recursos_a_aplicar=recurso).cambia_ad
    assert _vacia(recursos_a_retirar=recurso).cambia_ad
    assert _vacia(grupos_red_quitar=uno).cambia_red
    for campo in (
        "grupos_m365_agregar",
        "grupos_m365_quitar",
        "licencias_agregar",
        "licencias_quitar",
    ):
        d = _vacia(**{campo: uno})
        assert d.cambia_m365
        assert not d.cambia_ad
        assert not d.cambia_red
    for campo in ("grupos_ad_agregar", "grupos_ad_quitar"):
        assert _vacia(**{campo: uno}).cambia_ad
    for campo in ("grupos_red_agregar", "grupos_red_quitar"):
        assert _vacia(**{campo: uno}).cambia_red


def test_un_perfil_con_recurso_cuyo_perfil_pasa_de_consulta_a_edicion_se_reaplica() -> None:
    d = diferencia(perfil("Finanzas"), perfil("TI"))
    comun = [a for a in d.recursos_a_aplicar if a.ruta.endswith("comun")]
    assert [a.perfil for a in comun] == [PerfilDeRecurso.EDICION]
    assert not [a for a in d.recursos_a_retirar if a.ruta.endswith("comun")]


# --- tickets ----------------------------------------------------------------------------------


def test_el_texto_del_ticket_muestra_un_guion_si_aun_no_hay_usuario() -> None:
    t = elegir(caso(TipoEvento.VAC), AD, I)
    sin = dataclasses.replace(
        t, datos=DatosTecnicos("Ana", None, "TI / Cali", t.datos.fecha_efectiva, "SOL-2026-000001")
    )
    assert "Usuario: -" in sin.como_texto()
    con = dataclasses.replace(
        t,
        datos=DatosTecnicos("Ana", "ana.x", "TI / Cali", t.datos.fecha_efectiva, "SOL-2026-000001"),
    )
    assert "Usuario: ana.x" in con.como_texto()
    assert "Usuario: -" not in con.como_texto()
    texto = con.como_texto()
    for parte in (
        "Colaborador: Ana",
        "Perfil: TI / Cali",
        "Solicitud: SOL-2026-000001",
        "Prioridad: Media",
        t.categoria,
        t.titulo,
    ):
        assert parte in texto


def test_la_observacion_rechaza_documentos_negativos_y_normaliza_la_hora() -> None:
    import pytest

    from jml.dominio.errores import DatoInvalido

    with pytest.raises(DatoInvalido) as e:
        Observacion(ET.NUEVO, False, -1, AHORA)
    assert e.value.campo == "documentos"
    from jml.dominio.valores import BOGOTA

    assert Observacion(ET.NUEVO, False, 0, AHORA.astimezone(BOGOTA)).observada_en == AHORA
