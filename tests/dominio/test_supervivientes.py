"""Pruebas agregadas tras la segunda corrida de mutacion (docs/spikes/mutacion.md).

Cada una mata un mutante que sobrevivia porque nadie miraba ese campo, ese mensaje o ese borde.
"""

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta, tzinfo

import pytest

from jml.dominio import activos, sla
from jml.dominio.auditoria import EventoDeAuditoria, ValorAuditable, encadenar
from jml.dominio.catalogo import DatosVacaciones
from jml.dominio.colaborador import Colaborador
from jml.dominio.cuentas import derivar_cuenta
from jml.dominio.errores import (
    CampoRestringidoProhibido,
    ErrorDeDominio,
    NoAutorizado,
    TransicionInvalida,
)
from jml.dominio.perfiles import PerfilDeAcceso, nombre_de_sede
from jml.dominio.solicitud import Solicitud
from jml.dominio.tickets import Observacion, generar_tickets
from jml.dominio.tipos import (
    EstadoDeTicket,
    EstadoSolicitud,
    Subtipo,
    TipoDeEquipo,
    TipoEvento,
)
from jml.dominio.usuarios import usuario_sugerido
from jml.dominio.valores import (
    CalendarioHabil,
    CampoRestringido,
    NombreDeSoporteSaneado,
    a_utc,
    ascii_minuscula,
)
from tests.dominio.test_solicitud import EMPLEADO, FUTURO, RRHH, S, vacaciones
from tests.fabricas import AHORA, caso, colaborador, perfil

CAL = CalendarioHabil()


def datos(
    llamada: Callable[[], object], clase: type[ErrorDeDominio] = ErrorDeDominio
) -> dict[str, object]:
    with pytest.raises(clase) as exc:
        llamada()
    return dict(exc.value.datos)


# --- activos y propiedades ---------------------------------------------------------------------


def test_las_entidades_de_activos_son_congeladas_y_con_slots() -> None:
    clases: tuple[type, ...] = (activos.ActivoAsignado, activos.LicenciaAsignada)
    for clase in clases:
        assert clase.__dataclass_params__.frozen is True  # type: ignore[attr-defined]  # interno de dataclasses
        assert "__slots__" in clase.__dict__


def test_abierta_y_final_son_propiedades_no_metodos() -> None:
    for estado in EstadoSolicitud:
        s = vacaciones(estado)
        assert isinstance(s.abierta, bool)
        assert isinstance(s.final, bool)
        assert s.abierta is not s.final


# --- auditoria ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "clave",
    ["contrasena", "contraseña", "password", "token", "totp", "secret", "motivo", "descripcion"],
)
def test_cada_clave_prohibida_se_rechaza_con_su_destino(clave: str) -> None:
    assert datos(lambda: EventoDeAuditoria("a", "o", {clave: "x"}), CampoRestringidoProhibido) == {
        "destino": "auditoria"
    }


def test_el_campo_restringido_en_auditoria_dice_a_donde_no_puede_ir() -> None:
    suelto: dict[str, ValorAuditable] = {"x": CampoRestringido("s")}  # type: ignore[dict-item]  # tipo vetado a proposito
    en_tupla: dict[str, ValorAuditable] = {"x": (CampoRestringido("s"),)}  # type: ignore[dict-item]  # tipo vetado a proposito
    for malo in (suelto, en_tupla):
        assert datos(_evento_con(malo), CampoRestringidoProhibido) == {"destino": "auditoria"}


def _evento_con(contenido: dict[str, ValorAuditable]) -> Callable[[], object]:
    return lambda: EventoDeAuditoria("a", "o", contenido)


def test_los_tipos_no_auditables_dicen_cual_clave() -> None:
    esperado = {"campo": "datos.x", "motivo": "tipo no auditable"}
    assert datos(lambda: EventoDeAuditoria("a", "o", {"x": 1.5})) == esperado  # type: ignore[dict-item]
    assert datos(lambda: EventoDeAuditoria("a", "o", {"x": (1.5,)})) == esperado  # type: ignore[dict-item]


def test_la_auditoria_dice_que_campo_de_texto_esta_vacio() -> None:
    assert datos(lambda: EventoDeAuditoria(" ", "o", {}))["campo"] == "accion"
    assert datos(lambda: EventoDeAuditoria("a", " ", {}))["campo"] == "objeto"
    assert (
        datos(lambda: encadenar(None, AHORA, " ", EventoDeAuditoria("a", "o", {})))["campo"]
        == "actor"
    )


# --- colaborador -------------------------------------------------------------------------------


def test_el_colaborador_dice_que_campo_esta_vacio() -> None:
    c = colaborador()
    assert datos(lambda: replace(c, id=" "))["campo"] == "id"
    assert datos(lambda: c.con_cambio_de_departamento(" ", "x", None))["campo"] == "departamento"
    assert datos(lambda: c.con_cambio_de_departamento("x", " ", None))["campo"] == "cargo"
    assert datos(lambda: c.con_cambio_de_sede(" "))["campo"] == "sede"
    assert isinstance(c, Colaborador)


# --- cuentas -----------------------------------------------------------------------------------


def test_una_hora_sin_zona_en_la_derivacion_se_rechaza_con_su_campo() -> None:
    t = generar_tickets(*_args(TipoEvento.ING))[0]
    obs = Observacion(EstadoDeTicket.NUEVO, False, 0, AHORA)
    assert (
        datos(lambda: derivar_cuenta(None, t, None, obs, "col-1", datetime(2026, 1, 1)))["campo"]
        == "ahora"
    )


def test_los_eventos_de_cuenta_llevan_sistema_y_ticket() -> None:
    t = generar_tickets(*_args(TipoEvento.ING))[0]
    r = derivar_cuenta(
        None, t, None, Observacion(EstadoDeTicket.NUEVO, False, 0, AHORA), "col-1", AHORA
    )
    (ev,) = r.eventos
    assert ev.datos["sistema"] == "AD"
    assert ev.datos["ticket"] == t.clave_de_idempotencia
    assert ev.objeto == "col-1"


def test_el_evento_de_cuenta_inexistente_tambien_lleva_sistema_y_ticket() -> None:
    t = next(
        x for x in generar_tickets(*_args(TipoEvento.RET, Subtipo.RENUNCIA)) if x.cola.value == "AD"
    )
    r = derivar_cuenta(
        None, t, None, Observacion(EstadoDeTicket.NUEVO, False, 0, AHORA), "col-1", AHORA
    )
    assert r.eventos[0].accion == "cuenta.inexistente"
    assert dict(r.eventos[0].datos) == {"sistema": "AD", "ticket": t.clave_de_idempotencia}


def _args(
    tipo: TipoEvento, sub: Subtipo | None = None
) -> tuple[
    Solicitud, PerfilDeAcceso | None, PerfilDeAcceso | None, Colaborador, CalendarioHabil, datetime
]:
    c = caso(tipo, sub)
    return (c.solicitud, c.actual, c.nuevo, c.colaborador, CAL, AHORA)


# --- perfiles ----------------------------------------------------------------------------------


def test_el_nombre_de_sede_quita_espacios_tildes_y_pone_mayuscula_inicial() -> None:
    assert nombre_de_sede("San Andrés") == "Sanandres"
    assert nombre_de_sede("CALI") == "Cali"
    assert nombre_de_sede("bogotá") == "Bogota"


def test_el_perfil_dice_que_campo_esta_vacio_y_que_ruta_se_repite() -> None:
    p = perfil("TI")
    assert datos(lambda: replace(p, departamento=" "))["campo"] == "departamento"
    assert datos(lambda: replace(p, sede=" "))["campo"] == "sede"
    r = p.recursos[0]
    assert datos(
        lambda: PerfilDeAcceso("TI", "Cali", (), (), (), (), TipoDeEquipo.PORTATIL, (r, r))
    ) == {
        "campo": "recursos",
        "motivo": "una ruta no puede aparecer dos veces en un perfil",
    }


# --- solicitud ---------------------------------------------------------------------------------


def test_el_motivo_de_cancelar_de_rrhh_se_guarda_recortado() -> None:
    d = vacaciones(S.APROBADA).cancelar_por_rrhh(RRHH, "  se corrige  ", AHORA).decision
    assert d is not None
    assert d.justificacion == "se corrige"


def test_cerrar_con_un_solo_ticket_pendiente_ya_se_rechaza() -> None:
    with pytest.raises(ErrorDeDominio) as exc:
        vacaciones(S.EN_EJECUCION).cerrar(1)
    assert exc.value.datos == {"pendientes": 1}


def test_la_autoaprobacion_al_emitir_nombra_la_accion() -> None:
    propio = colaborador(id="col-rrhh")
    from tests.dominio.test_solicitud import emitir

    assert datos(lambda: emitir(RRHH, sujeto=propio), NoAutorizado)["accion"] == "emitir"


def test_una_hora_sin_zona_al_registrar_se_rechaza_con_su_campo() -> None:
    def registrar() -> object:
        return Solicitud.registrar_pendiente(
            id=vacaciones().id,
            actor=EMPLEADO,
            sujeto=colaborador(),
            tipo=TipoEvento.VAC,
            subtipo=None,
            fecha_efectiva=FUTURO,
            datos=DatosVacaciones(FUTURO + timedelta(days=3)),
            restringido=None,
            ahora=datetime(2026, 10, 12),
        )

    assert datos(registrar)["campo"] == "ahora"


# --- sla ---------------------------------------------------------------------------------------


def test_la_emergencia_con_hora_sin_zona_dice_el_campo() -> None:
    assert datos(lambda: sla.vence_la_emergencia(datetime(2026, 1, 1)))["campo"] == "ahora"


# --- tickets -----------------------------------------------------------------------------------


def test_los_errores_de_generacion_dicen_campo_y_motivo() -> None:
    ret = caso(TipoEvento.RET, Subtipo.RENUNCIA)
    ing = caso(TipoEvento.ING)
    cdp = caso(TipoEvento.CDP)
    csu = caso(TipoEvento.CSU)

    d = datos(lambda: generar_tickets(ret.solicitud, None, None, ret.colaborador, CAL, AHORA))
    assert d["campo"] == "perfil_actual"
    assert d["motivo"] == "obligatorio para generar los tickets de RET"
    d = datos(lambda: generar_tickets(ing.solicitud, None, None, ing.colaborador, CAL, AHORA))
    assert (d["campo"], d["motivo"]) == (
        "perfil_nuevo",
        "obligatorio para generar los tickets de ING",
    )
    d = datos(lambda: generar_tickets(cdp.solicitud, cdp.actual, None, cdp.colaborador, CAL, AHORA))
    assert (d["campo"], d["motivo"]) == (
        "perfil_nuevo",
        "obligatorio para generar los tickets de CDP",
    )
    d = datos(lambda: generar_tickets(cdp.solicitud, None, cdp.nuevo, cdp.colaborador, CAL, AHORA))
    assert (d["campo"], d["motivo"]) == (
        "perfil_actual",
        "obligatorio para generar los tickets de CDP",
    )
    vac = caso(TipoEvento.VAC)
    d = datos(lambda: generar_tickets(vac.solicitud, None, None, vac.colaborador, CAL, AHORA))
    assert (d["campo"], d["motivo"]) == (
        "perfil_actual",
        "obligatorio para generar los tickets de VAC",
    )
    d = datos(
        lambda: generar_tickets(
            cdp.solicitud, cdp.actual, perfil("TI", "Cali"), cdp.colaborador, CAL, AHORA
        )
    )
    assert d == {"campo": "perfil_nuevo", "motivo": "un cambio de departamento conserva la sede"}
    d = datos(
        lambda: generar_tickets(
            csu.solicitud, csu.actual, perfil("TI", "Cali"), csu.colaborador, CAL, AHORA
        )
    )
    assert d == {"campo": "perfil_nuevo", "motivo": "un cambio de sucursal solo cambia la sede"}
    d = datos(
        lambda: generar_tickets(
            ret.solicitud, ret.actual, None, replace(ret.colaborador, id="otro"), CAL, AHORA
        )
    )
    assert d == {"campo": "colaborador", "motivo": "no corresponde a la solicitud"}
    d = datos(
        lambda: generar_tickets(
            ret.solicitud, ret.actual, None, replace(ret.colaborador, usuario=None), CAL, AHORA
        )
    )
    assert d == {"campo": "usuario", "motivo": "el colaborador no tiene usuario sugerido asignado"}
    d = datos(
        lambda: generar_tickets(
            replace(ret.solicitud, estado=EstadoSolicitud.CERRADA),
            ret.actual,
            None,
            ret.colaborador,
            CAL,
            AHORA,
        ),
        TransicionInvalida,
    )
    assert d == {"estado": "cerrada", "accion": "generar_tickets"}


def test_una_hora_de_ahora_sin_zona_en_la_generacion_dice_el_campo() -> None:
    c = caso(TipoEvento.VAC)
    assert (
        datos(
            lambda: generar_tickets(
                c.solicitud, c.actual, None, c.colaborador, CAL, datetime(2026, 1, 1)
            )
        )["campo"]
        == "ahora"
    )


def test_la_observacion_dice_el_campo_de_cada_rechazo() -> None:
    assert datos(lambda: Observacion(EstadoDeTicket.NUEVO, False, -1, AHORA)) == {
        "campo": "documentos",
        "motivo": "no puede ser negativo",
    }
    assert (
        datos(lambda: Observacion(EstadoDeTicket.NUEVO, False, 0, datetime(2026, 1, 1)))["campo"]
        == "observada_en"
    )


# --- usuarios ----------------------------------------------------------------------------------


def test_el_recorte_del_usuario_no_se_come_las_equis_del_final() -> None:
    """El corte cae despues de una `x`: solo se pueden quitar puntos, no letras."""
    u = usuario_sugerido("Maximiliano", "Fernandezx", [])
    assert u.valor == "maximiliano.fernande"  # 20 caracteres exactos
    ocupado = usuario_sugerido("Alexxxxxxxxxxxxxxxxxxx", "Perez", ["alexxxxxxxxxxxxxxxxx"])
    assert ocupado.valor.endswith("2")
    assert ocupado.valor.startswith("alexxxxxxxxxxxxxxxx")
    assert len(ocupado.valor) <= 20


# --- valores -----------------------------------------------------------------------------------


class _SinOffset(tzinfo):
    """Una zona horaria que no sabe su desplazamiento: `a_utc` no puede fiarse de ella."""

    def utcoffset(self, dt: datetime | None) -> timedelta | None:
        return None

    def dst(self, dt: datetime | None) -> timedelta | None:
        return None

    def tzname(self, dt: datetime | None) -> str | None:
        return None


def test_una_zona_sin_desplazamiento_tampoco_es_un_instante_valido() -> None:
    assert datos(lambda: a_utc(datetime(2026, 1, 1, tzinfo=_SinOffset())))["campo"] == "fecha"
    assert a_utc(datetime(2026, 1, 1, tzinfo=UTC)).tzinfo is UTC


def test_ascii_minuscula_descarta_lo_que_no_es_ascii() -> None:
    assert ascii_minuscula("a€b") == "ab"
    assert ascii_minuscula("Ünï Çode ✓") == "uni code "


def test_el_saneado_solo_quita_espacios_y_puntos_de_los_bordes() -> None:
    assert NombreDeSoporteSaneado.sanear("Xacta.pdfX").valor == "Xacta.pdfX"
    assert NombreDeSoporteSaneado.sanear("  .acta.pdf.  ").valor == "acta.pdf"


def test_el_campo_restringido_no_se_muestra_ni_se_serializa_y_dice_por_que() -> None:
    c = CampoRestringido("secreto")
    assert repr(c) == "CampoRestringido(<oculto>)"
    assert str(c) == "CampoRestringido(<oculto>)"
    assert format(c, "") == "CampoRestringido(<oculto>)"
    assert f"{c:>50}" == "CampoRestringido(<oculto>)"
    with pytest.raises(CampoRestringidoProhibido) as e1:
        c.__reduce__()
    assert e1.value.datos == {"destino": "serializacion"}
    with pytest.raises(CampoRestringidoProhibido) as e2:
        c.__reduce_ex__(4)
    assert e2.value.datos == {"destino": "serializacion"}
