"""Fija los valores exactos que otras capas leen: enumeraciones, codigos y datos de los errores,
forma de las entidades (congeladas, con slots), valores por defecto y eventos de auditoria.

Estos textos cruzan fronteras (se guardan en la base de datos, viajan a la auditoria o se
traducen en las vistas), asi que cambiarlos sin querer es un error aunque ningun otro test lo note.
La mutacion los detecto como supervivientes (docs/spikes/mutacion.md).
"""

import dataclasses
import importlib
import inspect
import pkgutil
from collections.abc import Callable
from datetime import date, datetime, timedelta
from enum import Enum

import pytest

import jml.dominio as dominio
from jml.dominio import errores as e
from jml.dominio.colaborador import Colaborador
from jml.dominio.cuentas import Cuenta
from jml.dominio.permisos import Relacion, UsuarioDelSistema
from jml.dominio.solicitud import Accion, ResultadoSolicitud, Solicitud, TipoDeDecision
from jml.dominio.soporte import Soporte
from jml.dominio.tickets import TicketSeguido
from jml.dominio.tipos import (
    AccionDeTicket,
    ClaseTicket,
    Cola,
    EstadoColaborador,
    EstadoDeCuenta,
    EstadoDeSoporte,
    EstadoDeTicket,
    EstadoInicialDeTicket,
    EstadoSolicitud,
    MarcaDeCuenta,
    PerfilDeRecurso,
    Prioridad,
    Rol,
    SistemaDeCuenta,
    Subtipo,
    TipoDeEquipo,
    TipoDeVinculacion,
    TipoEvento,
)
from tests.fabricas import AHORA, colaborador

# --- enumeraciones ----------------------------------------------------------------------------

VALORES: dict[type[Enum], dict[str, object]] = {
    TipoEvento: {
        "ING": "ING",
        "VAC": "VAC",
        "CDP": "CDP",
        "CSU": "CSU",
        "RET": "RET",
        "EMG": "EMG",
    },
    Subtipo: {
        "RENUNCIA": "renuncia",
        "FIN_DE_CONTRATO": "fin_de_contrato",
        "DESPIDO_CON_JUSTA_CAUSA": "despido_con_justa_causa",
        "FUGA_DETECTADA": "fuga_detectada",
    },
    EstadoSolicitud: {
        "PENDIENTE_APROBACION": "pendiente_aprobacion",
        "APROBADA": "aprobada",
        "EN_EJECUCION": "en_ejecucion",
        "ERROR": "error",
        "CERRADA": "cerrada",
        "RECHAZADA": "rechazada",
        "CANCELADA": "cancelada",
    },
    Cola: {
        "AD": "AD",
        "COMUNICACIONES": "COMUNICACIONES",
        "LICENCIAS": "LICENCIAS",
        "INVENTARIO": "INVENTARIO",
        "REVISION_MANUAL": "REVISION_MANUAL",
    },
    ClaseTicket: {
        "CIERRE_INMEDIATO": "cierre_inmediato",
        "CIERRE_PROGRAMADO": "cierre_programado",
        "POSTERIOR": "posterior",
    },
    AccionDeTicket: {
        "ALTA": "alta",
        "SUSPENSION": "suspension",
        "REACTIVACION": "reactivacion",
        "CAMBIO": "cambio",
        "BAJA": "baja",
        "ELIMINACION": "eliminacion",
        "EQUIPO": "equipo",
    },
    EstadoInicialDeTicket: {"NUEVO": "Nuevo", "EN_ESPERA": "En espera"},
    EstadoDeTicket: {"NUEVO": 1, "EN_ESPERA": 2, "EN_CURSO": 3, "RESUELTO": 4, "CERRADO": 5},
    SistemaDeCuenta: {"AD": "AD", "RED": "Red", "M365": "M365"},
    EstadoDeCuenta: {
        "PENDIENTE_ALTA": "pendiente_alta",
        "ACTIVA": "activa",
        "PENDIENTE_SUSPENSION": "pendiente_suspension",
        "SUSPENDIDA": "suspendida",
        "PENDIENTE_BAJA": "pendiente_baja",
        "DESHABILITADA": "deshabilitada",
        "ELIMINADA": "eliminada",
    },
    MarcaDeCuenta: {
        "CAMBIO_PENDIENTE": "cambio_pendiente",
        "REABIERTO": "reabierto",
        "CIERRE_SIN_SOLUCION": "cierre_sin_solucion",
    },
    PerfilDeRecurso: {
        "CONSULTA": "Consulta",
        "EDICION": "Edición",
        "RETIRO_DE_ACCESOS": "Retiro de accesos",
    },
    Prioridad: {"MEDIA": "Media", "ALTA": "Alta", "MUY_ALTA": "Muy alta"},
    Rol: {
        "SOLICITANTE": "solicitante",
        "RRHH": "rrhh",
        "TECNICO_AD": "tecnico_ad",
        "TECNICO_COMUNICACIONES": "tecnico_comunicaciones",
        "TECNICO_LICENCIAS": "tecnico_licencias",
        "TECNICO_INVENTARIO": "tecnico_inventario",
        "AUDITOR": "auditor",
        "ADMINISTRADOR": "administrador",
    },
    TipoDeVinculacion: {
        "EMPLEADO": "empleado",
        "CONTRATISTA": "contratista",
        "PRACTICANTE": "practicante",
        "TEMPORAL": "temporal",
    },
    TipoDeEquipo: {"PORTATIL": "Portátil", "ESCRITORIO": "Escritorio"},
    EstadoColaborador: {
        "POR_INGRESAR": "por_ingresar",
        "ACTIVO": "activo",
        "SUSPENDIDO": "suspendido",
        "RETIRADO": "retirado",
    },
    EstadoDeSoporte: {"PENDIENTE": "pendiente", "SUBIDO": "subido", "DESCARTADO": "descartado"},
    Accion: {
        "APROBAR": "aprobar",
        "RECHAZAR": "rechazar",
        "CANCELAR_SOLICITANTE": "cancelar_solicitante",
        "CANCELAR_RRHH": "cancelar_rrhh",
        "INICIAR_EJECUCION": "iniciar_ejecucion",
        "FALLAR_EMISION": "fallar_emision",
        "REINTENTAR": "reintentar",
        "CERRAR": "cerrar",
    },
    TipoDeDecision: {
        "APROBAR": "aprobar",
        "RECHAZAR": "rechazar",
        "EMITIR": "emitir",
        "EMITIR_POR_EXCEPCION": "emitir_por_excepcion",
        "CANCELAR": "cancelar",
    },
    Relacion: {
        "SI_MISMO": "si_mismo",
        "SUBORDINADO_DIRECTO": "subordinado_directo",
        "TERCERO": "tercero",
    },
}


@pytest.mark.parametrize("enum", list(VALORES), ids=lambda c: c.__name__)
def test_los_valores_de_las_enumeraciones_son_estables(enum: type[Enum]) -> None:
    """Se guardan en la base de datos y en la auditoria: cambiarlos rompe los datos existentes."""
    assert {m.name: m.value for m in enum} == VALORES[enum]


# --- forma de las entidades -------------------------------------------------------------------


def _clases_de_datos() -> list[type]:
    clases = []
    for mod in pkgutil.iter_modules(dominio.__path__):
        modulo = importlib.import_module(f"jml.dominio.{mod.name}")
        for _, c in inspect.getmembers(modulo, inspect.isclass):
            if dataclasses.is_dataclass(c) and c.__module__ == modulo.__name__:
                clases.append(c)
    return clases


@pytest.mark.parametrize("clase", _clases_de_datos(), ids=lambda c: c.__name__)
def test_toda_entidad_y_objeto_de_valor_es_congelado_y_con_slots(clase: type) -> None:
    """RF-14, RD-11: las operaciones devuelven valores nuevos; nada se muta por accidente."""
    params = clase.__dataclass_params__  # type: ignore[attr-defined]  # atributo interno de dataclasses
    assert params.frozen is True
    assert "__slots__" in clase.__dict__


def test_hay_entidades_que_comprobar() -> None:
    nombres = {c.__name__ for c in _clases_de_datos()}
    assert {"Solicitud", "Cuenta", "TicketDeCola", "Colaborador", "RegistroDeAuditoria"} <= nombres


# --- valores por defecto ----------------------------------------------------------------------


def _por_defecto(clase: type) -> dict[str, object]:
    return {
        f.name: f.default for f in dataclasses.fields(clase) if f.default is not dataclasses.MISSING
    }


@pytest.mark.parametrize(
    ("clase", "esperado"),
    [
        (Colaborador, {"usuario": None, "id_usuario_glpi": None}),
        (UsuarioDelSistema, {"activo": True}),
        (Solicitud, {"solicitud_origen_id": None, "tickets": (), "para_revision": False}),
        (Cuenta, {"marca": None}),
        (Soporte, {"estado": EstadoDeSoporte.PENDIENTE, "id_documento_glpi": None}),
        (TicketSeguido, {"id_externo": None, "observacion": None, "reabierto": False}),
    ],
)
def test_valores_por_defecto(clase: type, esperado: dict[str, object]) -> None:
    assert _por_defecto(clase) == esperado


# --- errores: codigos, atributos y mensajes ---------------------------------------------------

ERRORES = [
    (e.ErrorDeDominio("m", a=1), "error_de_dominio", "m", {"a": 1}),
    (e.DatoInvalido("c", "mot"), "dato_invalido", "c: mot", {"campo": "c", "motivo": "mot"}),
    (
        e.TransicionInvalida("cerrada", "aprobar"),
        "transicion_invalida",
        "No se puede 'aprobar' desde 'cerrada'",
        {"estado": "cerrada", "accion": "aprobar"},
    ),
    (
        e.SolicitudDuplicada("SOL-1"),
        "solicitud_duplicada",
        "Ya existe una solicitud abierta: SOL-1",
        {"existente_id": "SOL-1"},
    ),
    (
        e.DocumentoDuplicado("c1"),
        "documento_duplicado",
        "El documento ya existe y no esta retirado: c1",
        {"existente_id": "c1"},
    ),
    (
        e.NoAutorizado("emitir", "porque si"),
        "no_autorizado",
        "No autorizado para 'emitir': porque si",
        {"accion": "emitir", "motivo": "porque si"},
    ),
    (
        e.AutoAprobacionProhibida("aprobar"),
        "auto_aprobacion_prohibida",
        "No autorizado para 'aprobar': quien decide no puede ser el sujeto de la solicitud",
        {
            "accion": "aprobar",
            "motivo": "quien decide no puede ser el sujeto de la solicitud",
        },
    ),
    (
        e.RolesIncompatibles("rrhh", "auditor"),
        "roles_incompatibles",
        "Roles incompatibles: rrhh y auditor",
        {"uno": "rrhh", "otro": "auditor"},
    ),
    (
        e.JustificacionRequerida("rechazar"),
        "justificacion_requerida",
        "La accion 'rechazar' exige una justificacion",
        {"accion": "rechazar"},
    ),
    (
        e.SolicitudInmutable("aprobada"),
        "solicitud_inmutable",
        "El contenido no se modifica en estado 'aprobada' (RF-14)",
        {"estado": "aprobada"},
    ),
    (
        e.CancelacionNoPermitida("hay tickets"),
        "cancelacion_no_permitida",
        "No se puede cancelar: hay tickets",
        {"motivo": "hay tickets"},
    ),
    (
        e.CierreNoPermitido(2),
        "cierre_no_permitido",
        "Hay 2 tickets de cierre sin resolver",
        {"pendientes": 2},
    ),
    (
        e.ColaboradorNoElegible("VAC", "retirado"),
        "colaborador_no_elegible",
        "Un evento VAC no aplica a un colaborador 'retirado'",
        {"tipo": "VAC", "estado": "retirado"},
    ),
    (
        e.SoporteInvalido("firma"),
        "soporte_invalido",
        "Soporte de vinculacion invalido: firma",
        {"motivo": "firma"},
    ),
    (
        e.CampoRestringidoProhibido("log"),
        "campo_restringido_prohibido",
        "Un campo restringido no puede ir a log",
        {"destino": "log"},
    ),
    (e.OperacionNoPermitida("no"), "operacion_no_permitida", "no", {"motivo": "no"}),
    (
        e.NoEncontrado("solicitud", "SOL-9"),
        "no_encontrado",
        "No existe solicitud: SOL-9",
        {"entidad": "solicitud", "referencia": "SOL-9"},
    ),
]


@pytest.mark.parametrize(
    "error", ERRORES, ids=lambda x: type(x[0]).__name__ if isinstance(x, tuple) else ""
)
def test_cada_error_tiene_codigo_mensaje_y_datos_estables(
    error: tuple[e.ErrorDeDominio, str, str, dict[str, object]],
) -> None:
    instancia, codigo, mensaje, datos = error
    assert instancia.codigo == codigo
    assert type(instancia).codigo == codigo
    assert instancia.mensaje == mensaje
    assert str(instancia) == mensaje
    assert instancia.datos == datos


def test_cada_atributo_de_los_errores_se_conserva() -> None:
    assert e.DatoInvalido("c", "m").campo == "c"
    assert e.DatoInvalido("c", "m").motivo == "m"
    assert e.TransicionInvalida("a", "b").estado == "a"
    assert e.TransicionInvalida("a", "b").accion == "b"
    assert e.SolicitudDuplicada("x").existente_id == "x"
    assert e.DocumentoDuplicado("x").existente_id == "x"
    assert (e.NoAutorizado("a", "m").accion, e.NoAutorizado("a", "m").motivo) == ("a", "m")
    assert e.AutoAprobacionProhibida("a").accion == "a"
    assert (e.RolesIncompatibles("u", "o").uno, e.RolesIncompatibles("u", "o").otro) == ("u", "o")
    assert e.JustificacionRequerida("a").accion == "a"
    assert e.SolicitudInmutable("s").estado == "s"
    assert e.CancelacionNoPermitida("m").motivo == "m"
    assert e.CierreNoPermitido(3).pendientes == 3
    assert (e.ColaboradorNoElegible("t", "s").tipo, e.ColaboradorNoElegible("t", "s").estado) == (
        "t",
        "s",
    )
    assert e.SoporteInvalido("m").motivo == "m"
    assert e.CampoRestringidoProhibido("d").destino == "d"
    assert e.OperacionNoPermitida("m").motivo == "m"
    assert (e.NoEncontrado("a", "b").entidad, e.NoEncontrado("a", "b").referencia) == ("a", "b")


def test_los_codigos_son_los_que_las_vistas_traduciran() -> None:
    assert sorted(c.codigo for c in vars(e).values() if inspect.isclass(c) and issubclass(c, e.ErrorDeDominio)) == sorted(
        [
            "error_de_dominio", "dato_invalido", "transicion_invalida", "solicitud_duplicada",
            "documento_duplicado", "no_autorizado", "auto_aprobacion_prohibida",
            "roles_incompatibles", "justificacion_requerida", "solicitud_inmutable",
            "cancelacion_no_permitida", "cierre_no_permitido", "colaborador_no_elegible",
            "soporte_invalido", "campo_restringido_prohibido", "operacion_no_permitida",
            "no_encontrado",
        ]
    )  # fmt: skip


# --- eventos de auditoria de las operaciones de Solicitud --------------------------------------


def _resultado(operacion: str) -> ResultadoSolicitud:
    from jml.dominio.tipos import EstadoSolicitud as S
    from tests.dominio.test_solicitud import (
        ADMIN,
        EMPLEADO,
        RRHH,
        emitir,
        registrar_vac,
        vacaciones,
    )

    operaciones: dict[str, Callable[[], ResultadoSolicitud]] = {
        "registrada": registrar_vac,
        "emitida": lambda: emitir(RRHH),
        "aprobada": lambda: vacaciones().aprobar(RRHH, None, AHORA),
        "rechazada": lambda: vacaciones().rechazar(RRHH, "x", AHORA),
        "cancelada_sol": lambda: vacaciones().cancelar_por_solicitante(EMPLEADO, AHORA),
        "cancelada_rrhh": lambda: vacaciones(S.APROBADA).cancelar_por_rrhh(RRHH, None, AHORA),
        "en_ejecucion": lambda: vacaciones(S.APROBADA).iniciar_ejecucion(frozenset()),
        "error": lambda: vacaciones(S.APROBADA).fallar_emision("glpi_500"),
        "reintentada": lambda: vacaciones(S.ERROR).reintentar(ADMIN),
        "cerrada": lambda: vacaciones(S.EN_EJECUCION).cerrar(0),
        "revision": lambda: vacaciones().marcar_para_revision(),
    }
    return operaciones[operacion]()


@pytest.mark.parametrize(
    ("operacion", "acciones", "estado"),
    [
        ("registrada", ["solicitud.registrada"], "pendiente_aprobacion"),
        ("emitida", ["solicitud.registrada", "solicitud.emitida"], "aprobada"),
        ("aprobada", ["solicitud.aprobada"], "aprobada"),
        ("rechazada", ["solicitud.rechazada"], "rechazada"),
        ("cancelada_sol", ["solicitud.cancelada"], "cancelada"),
        ("cancelada_rrhh", ["solicitud.cancelada"], "cancelada"),
        ("en_ejecucion", ["solicitud.en_ejecucion"], "en_ejecucion"),
        ("error", ["solicitud.error"], "error"),
        ("reintentada", ["solicitud.reintentada"], "aprobada"),
        ("cerrada", ["solicitud.cerrada"], "cerrada"),
        ("revision", ["solicitud.marcada_para_revision"], "pendiente_aprobacion"),
    ],
)
def test_RF_35_los_eventos_de_auditoria_de_cada_operacion(
    operacion: str, acciones: list[str], estado: str
) -> None:
    r = _resultado(operacion)
    assert [ev.accion for ev in r.eventos] == acciones
    for ev in r.eventos:
        assert ev.objeto == "SOL-2026-000001"
        assert ev.datos["tipo"] == "VAC"
        assert ev.datos["estado"] == r.solicitud.estado.value
        assert ev.datos["colaborador_id"] == "col-1"
    assert r.solicitud.estado.value == estado


def test_RF_35_los_eventos_llevan_su_via_y_sus_marcas_pero_nunca_la_justificacion() -> None:
    assert _resultado("registrada").eventos[0].datos["via"] == "solicitante"
    emitida = _resultado("emitida").eventos
    assert emitida[0].datos["via"] == "rrhh"
    assert emitida[1].datos["justificada"] is True
    assert _resultado("rechazada").eventos[0].datos["justificada"] is True
    assert _resultado("error").eventos[0].datos["codigo"] == "glpi_500"
    for op in ("emitida", "rechazada"):
        for ev in _resultado(op).eventos:
            assert "justificacion" not in ev.datos


def test_la_emision_por_excepcion_deja_su_evento_propio() -> None:
    from jml.dominio.catalogo import DatosVacaciones
    from jml.dominio.valores import SolicitudId
    from tests.dominio.test_solicitud import ADMIN, FUTURO

    r = Solicitud.emitir_por_excepcion(
        id=SolicitudId.de(2026, 1), actor=ADMIN, sujeto=colaborador(id="col-rrhh"),
        sujeto_es_rrhh=True, tipo=TipoEvento.VAC, subtipo=None, fecha_efectiva=FUTURO,
        datos=DatosVacaciones(FUTURO + timedelta(days=3)), restringido=None,
        justificacion="x", ahora=AHORA,
    )  # fmt: skip
    assert [ev.accion for ev in r.eventos] == [
        "solicitud.registrada",
        "solicitud.emitida_por_excepcion",
    ]
    assert r.eventos[0].datos["via"] == "administrador"
    assert r.eventos[1].datos["justificada"] is True


# --- mensajes de las negativas del dominio ----------------------------------------------------


def _datos(exc: pytest.ExceptionInfo[e.ErrorDeDominio]) -> dict[str, object]:
    return dict(exc.value.datos)


def test_las_negativas_de_la_solicitud_dicen_que_accion_y_por_que() -> None:
    from tests.dominio import test_solicitud as t

    casos: list[tuple[Callable[[], object], type[e.ErrorDeDominio], dict[str, object]]] = [
        (lambda: t.emitir(t.EMPLEADO), e.NoAutorizado, {"accion": "emitir", "motivo": "solo RRHH emite directamente"}),
        (lambda: t.vacaciones().aprobar(t.EMPLEADO, None, AHORA), e.NoAutorizado, {"accion": "aprobar", "motivo": "solo RRHH decide"}),
        (lambda: t.vacaciones().rechazar(t.EMPLEADO, "x", AHORA), e.NoAutorizado, {"accion": "rechazar", "motivo": "solo RRHH decide"}),
        (lambda: t.vacaciones(t.S.APROBADA).cancelar_por_rrhh(t.EMPLEADO, None, AHORA), e.NoAutorizado, {"accion": "cancelar", "motivo": "solo RRHH decide"}),
        (lambda: t.vacaciones().cancelar_por_solicitante(t.TERCERO, AHORA), e.NoAutorizado, {"accion": "cancelar", "motivo": "solo quien registro la solicitud puede cancelarla"}),
        (lambda: t.vacaciones(t.S.ERROR).reintentar(t.RRHH), e.NoAutorizado, {"accion": "reintentar", "motivo": "solo el Administrador reintenta"}),
        (lambda: t.vacaciones().rechazar(t.RRHH, " ", AHORA), e.JustificacionRequerida, {"accion": "rechazar"}),
        (lambda: t.emitir(t.RRHH, " "), e.JustificacionRequerida, {"accion": "emitir"}),
        (lambda: t.vacaciones(t.S.APROBADA).registrar_ticket_creado("k").iniciar_ejecucion(frozenset({"k", "z"})), e.OperacionNoPermitida, {"motivo": "faltan tickets por crear en GLPI"}),
        (lambda: t.vacaciones(t.S.APROBADA).registrar_ticket_creado("k").cancelar_por_rrhh(t.RRHH, None, AHORA), e.CancelacionNoPermitida, {"motivo": "ya se creo al menos un ticket en GLPI"}),
        (lambda: t.vacaciones(t.S.CERRADA).registrar_ticket_creado("k"), e.TransicionInvalida, {"estado": "cerrada", "accion": "registrar_ticket_creado"}),
        (lambda: t.vacaciones(t.S.CERRADA).marcar_para_revision(), e.TransicionInvalida, {"estado": "cerrada", "accion": "marcar_para_revision"}),
        (lambda: t.registrar_vac(t.TERCERO), e.NoAutorizado, {"accion": "registrar", "motivo": "un VAC no lo registra este rol sobre este sujeto"}),
    ]  # fmt: skip
    for llamada, clase, datos in casos:
        with pytest.raises(clase) as exc:
            llamada()
        assert dict(exc.value.datos) == datos


def test_la_emision_por_excepcion_explica_la_negativa() -> None:
    from jml.dominio.catalogo import DatosVacaciones
    from jml.dominio.valores import SolicitudId
    from tests.dominio.test_solicitud import ADMIN, FUTURO, RRHH

    with pytest.raises(e.NoAutorizado) as exc:
        Solicitud.emitir_por_excepcion(
            id=SolicitudId.de(2026, 1), actor=ADMIN, sujeto=colaborador(), sujeto_es_rrhh=False,
            tipo=TipoEvento.VAC, subtipo=None, fecha_efectiva=FUTURO,
            datos=DatosVacaciones(FUTURO + timedelta(days=3)), restringido=None,
            justificacion="x", ahora=AHORA,
        )  # fmt: skip
    assert dict(exc.value.datos) == {
        "accion": "emitir_por_excepcion",
        "motivo": "solo el Administrador, y solo sobre una persona de RRHH",
    }
    with pytest.raises(e.JustificacionRequerida) as exc2:
        Solicitud.emitir_por_excepcion(
            id=SolicitudId.de(2026, 1), actor=ADMIN, sujeto=colaborador(id="col-rrhh"),
            sujeto_es_rrhh=True, tipo=TipoEvento.VAC, subtipo=None, fecha_efectiva=FUTURO,
            datos=DatosVacaciones(FUTURO + timedelta(days=3)), restringido=None,
            justificacion=" ", ahora=AHORA,
        )  # fmt: skip
    assert exc2.value.accion == "emitir_por_excepcion"
    assert RRHH.usuario_id == "u-rrhh"


def test_la_aprobacion_sin_justificacion_es_valida_y_la_cancelacion_tambien() -> None:
    from tests.dominio.test_solicitud import EMPLEADO, RRHH, S, vacaciones

    assert _resultado("aprobada").decision is not None
    rrhh = vacaciones(S.APROBADA).cancelar_por_rrhh(RRHH, "  ", AHORA).decision
    assert rrhh is not None
    assert rrhh.justificacion is None
    sol = vacaciones().cancelar_por_solicitante(EMPLEADO, AHORA).decision
    assert sol is not None
    assert sol.justificacion is None


def test_la_fecha_de_la_decision_es_el_instante_dado_en_utc() -> None:
    from tests.dominio.test_solicitud import RRHH, vacaciones

    otra_zona = AHORA.astimezone(__import__("jml.dominio.valores", fromlist=["BOGOTA"]).BOGOTA)
    r = vacaciones().aprobar(RRHH, None, otra_zona)
    assert r.decision is not None
    assert r.decision.fecha == AHORA
    assert r.decision.fecha.utcoffset() == timedelta(0)
    assert isinstance(r.solicitud.creada_en, datetime)
    assert date(2026, 10, 12) == AHORA.date()
