"""Catalogo de campos (4.8) y permisos (3.3, 4.1): RF-03, RF-05, RF-07, RF-08, RF-13, RF-15."""

import dataclasses
import itertools
from datetime import date, datetime, timedelta

import pytest

from jml.dominio.catalogo import (
    DATOS_POR_TIPO,
    SUBTIPOS_POR_TIPO,
    DatosCambioDepartamento,
    DatosCambioSucursal,
    DatosEmergencia,
    DatosIngreso,
    DatosRetiro,
    DatosVacaciones,
    validar_evento,
)
from jml.dominio.errores import DatoInvalido, RolesIncompatibles
from jml.dominio.permisos import (
    Actor,
    Relacion,
    puede_consultar_auditoria,
    puede_decidir,
    puede_emitir_directo,
    puede_emitir_por_excepcion,
    puede_registrar_como_solicitante,
    puede_reintentar_emision,
    puede_ver_dashboard,
    puede_ver_restringidos,
    relacion_con,
    validar_roles,
)
from jml.dominio.tipos import (
    Rol,
    Subtipo,
    TipoDeEquipo,
    TipoDeVinculacion,
    TipoEvento,
)
from jml.dominio.valores import CampoRestringido, Documento
from tests.fabricas import AHORA, HOY, datos_ingreso

R = CampoRestringido("motivo cualquiera")


# --- catalogo ---------------------------------------------------------------------------------


def test_campos_del_catalogo_coinciden_con_el_SRS_4_8() -> None:
    campos = {t: {f.name for f in dataclasses.fields(c)} for t, c in DATOS_POR_TIPO.items()}
    assert campos[TipoEvento.ING] >= {
        "nombres", "apellidos", "documento", "vinculacion", "departamento", "cargo", "sede",
        "jefe_id", "fecha_fin", "requiere_equipo", "tipo_equipo",
    }  # fmt: skip
    assert campos[TipoEvento.VAC] == {"fecha_regreso"}
    assert campos[TipoEvento.CDP] == {"departamento_nuevo", "cargo_nuevo", "jefe_nuevo_id"}
    assert campos[TipoEvento.CSU] == {"sede_nueva", "traslada_equipo"}
    assert campos[TipoEvento.RET] == set()
    assert campos[TipoEvento.EMG] == {"reportado_por", "hora_del_hecho"}


def test_los_datos_no_incluyen_campos_restringidos_RD_05() -> None:
    for clase in DATOS_POR_TIPO.values():
        nombres = {f.name for f in dataclasses.fields(clase)}
        assert not nombres & {"motivo", "descripcion"}


def test_ingreso_exige_fecha_fin_si_no_es_empleado_RF_07() -> None:
    for v in (
        TipoDeVinculacion.CONTRATISTA,
        TipoDeVinculacion.PRACTICANTE,
        TipoDeVinculacion.TEMPORAL,
    ):
        with pytest.raises(DatoInvalido, match="fecha_fin"):
            DatosIngreso(
                "A", "B", Documento("12345"), v, "TI", "x", "Cali", None, None, False, None
            )
    DatosIngreso(
        "A", "B", Documento("12345"), TipoDeVinculacion.EMPLEADO, "TI", "x", "Cali", None, None,
        False, None,
    )  # fmt: skip


def test_ingreso_coherencia_de_equipo() -> None:
    with pytest.raises(DatoInvalido, match="tipo_equipo"):
        DatosIngreso("A", "B", Documento("12345"), TipoDeVinculacion.EMPLEADO, "TI", "x", "Cali",
                     None, None, True, None)  # fmt: skip
    with pytest.raises(DatoInvalido, match="tipo_equipo"):
        DatosIngreso("A", "B", Documento("12345"), TipoDeVinculacion.EMPLEADO, "TI", "x", "Cali",
                     None, None, False, TipoDeEquipo.PORTATIL)  # fmt: skip


@pytest.mark.parametrize("campo", ["nombres", "apellidos", "departamento", "cargo", "sede"])
def test_ingreso_rechaza_textos_vacios(campo: str) -> None:
    base = dict(
        nombres="A", apellidos="B", departamento="TI", cargo="x", sede="Cali",
    )  # fmt: skip
    base[campo] = "  "
    with pytest.raises(DatoInvalido, match=campo):
        DatosIngreso(
            documento=Documento("12345"), vinculacion=TipoDeVinculacion.EMPLEADO, jefe_id=None,
            fecha_fin=None, requiere_equipo=False, tipo_equipo=None, **base,
        )  # fmt: skip


def test_otros_datos_rechazan_vacios() -> None:
    with pytest.raises(DatoInvalido):
        DatosCambioDepartamento(" ", "x", None)
    with pytest.raises(DatoInvalido):
        DatosCambioDepartamento("x", " ", None)
    with pytest.raises(DatoInvalido):
        DatosCambioSucursal(" ", False)
    with pytest.raises(DatoInvalido):
        DatosEmergencia(" ", AHORA)
    with pytest.raises(DatoInvalido):
        DatosEmergencia("Seguridad", datetime(2026, 1, 1))


def _valido(tipo: TipoEvento) -> tuple[Subtipo | None, date, object, CampoRestringido | None]:
    fe = HOY + timedelta(days=5)
    match tipo:
        case TipoEvento.ING:
            return None, fe, datos_ingreso(), None
        case TipoEvento.VAC:
            return None, fe, DatosVacaciones(fe + timedelta(days=10)), None
        case TipoEvento.CDP:
            return None, fe, DatosCambioDepartamento("TI", "Dev", None), None
        case TipoEvento.CSU:
            return None, fe, DatosCambioSucursal("Cali", True), None
        case TipoEvento.RET:
            return Subtipo.RENUNCIA, fe, DatosRetiro(), R
        case TipoEvento.EMG:
            return (
                Subtipo.FUGA_DETECTADA,
                HOY,
                DatosEmergencia("Seguridad", AHORA - timedelta(hours=1)),
                R,
            )


@pytest.mark.parametrize("tipo", list(TipoEvento))
def test_cada_tipo_valido_pasa_la_validacion_RF_07(tipo: TipoEvento) -> None:
    sub, fe, datos, r = _valido(tipo)
    validar_evento(tipo, sub, fe, datos, r, AHORA)  # type: ignore[arg-type]  # `datos` es object


@pytest.mark.parametrize(("tipo", "otro"), list(itertools.permutations(TipoEvento, 2)))
def test_datos_de_otro_tipo_se_rechazan(tipo: TipoEvento, otro: TipoEvento) -> None:
    sub, fe, _, r = _valido(tipo)
    _, _, datos_otro, _ = _valido(otro)
    with pytest.raises(DatoInvalido, match="datos"):
        validar_evento(tipo, sub, fe, datos_otro, r, AHORA)  # type: ignore[arg-type]


def test_subtipos_RET_y_EMG() -> None:
    assert SUBTIPOS_POR_TIPO[TipoEvento.RET] == {Subtipo.RENUNCIA, Subtipo.FIN_DE_CONTRATO}
    assert SUBTIPOS_POR_TIPO[TipoEvento.EMG] == {
        Subtipo.DESPIDO_CON_JUSTA_CAUSA,
        Subtipo.FUGA_DETECTADA,
    }
    for t in (TipoEvento.ING, TipoEvento.VAC, TipoEvento.CDP, TipoEvento.CSU):
        _sub, fe, datos, r = _valido(t)
        with pytest.raises(DatoInvalido, match="subtipo"):
            validar_evento(t, Subtipo.RENUNCIA, fe, datos, r, AHORA)  # type: ignore[arg-type]
    _sub, fe, datos, r = _valido(TipoEvento.RET)
    for malo in (None, Subtipo.FUGA_DETECTADA):
        with pytest.raises(DatoInvalido, match="subtipo"):
            validar_evento(TipoEvento.RET, malo, fe, datos, r, AHORA)  # type: ignore[arg-type]
    _sub, fe, datos, r = _valido(TipoEvento.EMG)
    for malo in (None, Subtipo.RENUNCIA):
        with pytest.raises(DatoInvalido, match="subtipo"):
            validar_evento(TipoEvento.EMG, malo, fe, datos, r, AHORA)  # type: ignore[arg-type]


def test_restringido_obligatorio_solo_en_RET_y_EMG() -> None:
    for t in (TipoEvento.RET, TipoEvento.EMG):
        sub, fe, datos, _ = _valido(t)
        with pytest.raises(DatoInvalido, match="restringido"):
            validar_evento(t, sub, fe, datos, None, AHORA)  # type: ignore[arg-type]
    for t in (TipoEvento.ING, TipoEvento.VAC, TipoEvento.CDP, TipoEvento.CSU):
        sub, fe, datos, _ = _valido(t)
        with pytest.raises(DatoInvalido, match="restringido"):
            validar_evento(t, sub, fe, datos, R, AHORA)  # type: ignore[arg-type]


def test_fecha_efectiva_pasada_se_rechaza_pero_hoy_y_futuro_pasan_RF_08_S_15() -> None:
    sub, _, datos, r = _valido(TipoEvento.RET)
    with pytest.raises(DatoInvalido, match="pasado"):
        validar_evento(TipoEvento.RET, sub, HOY - timedelta(days=1), datos, r, AHORA)  # type: ignore[arg-type]
    validar_evento(TipoEvento.RET, sub, HOY, datos, r, AHORA)  # type: ignore[arg-type]
    validar_evento(TipoEvento.RET, sub, HOY + timedelta(days=300), datos, r, AHORA)  # type: ignore[arg-type]


def test_reglas_de_fechas_cruzadas() -> None:
    fe = HOY + timedelta(days=3)
    datos = datos_ingreso(TipoDeVinculacion.CONTRATISTA, fecha_fin=fe)
    with pytest.raises(DatoInvalido, match="fecha_fin"):  # fin == ingreso
        validar_evento(TipoEvento.ING, None, fe, datos, None, AHORA)
    validar_evento(
        TipoEvento.ING, None, fe, datos_ingreso(TipoDeVinculacion.CONTRATISTA, fecha_fin=fe + timedelta(days=1)),
        None, AHORA,
    )  # fmt: skip
    with pytest.raises(DatoInvalido, match="fecha_regreso"):  # regreso == inicio
        validar_evento(TipoEvento.VAC, None, fe, DatosVacaciones(fe), None, AHORA)
    validar_evento(TipoEvento.VAC, None, fe, DatosVacaciones(fe + timedelta(days=1)), None, AHORA)


def test_emergencia_es_efectiva_hoy_y_el_hecho_no_es_futuro_S_15() -> None:
    d = DatosEmergencia("Seguridad", AHORA - timedelta(minutes=1))
    with pytest.raises(DatoInvalido, match="fecha_efectiva"):
        validar_evento(TipoEvento.EMG, Subtipo.FUGA_DETECTADA, HOY + timedelta(days=1), d, R, AHORA)
    futuro = DatosEmergencia("Seguridad", AHORA + timedelta(minutes=1))
    with pytest.raises(DatoInvalido, match="hora_del_hecho"):
        validar_evento(TipoEvento.EMG, Subtipo.FUGA_DETECTADA, HOY, futuro, R, AHORA)
    justo = DatosEmergencia("Seguridad", AHORA)
    validar_evento(TipoEvento.EMG, Subtipo.FUGA_DETECTADA, HOY, justo, R, AHORA)


# --- roles incompatibles (3.3) -----------------------------------------------------------------

TECNICOS = [
    Rol.TECNICO_AD,
    Rol.TECNICO_COMUNICACIONES,
    Rol.TECNICO_LICENCIAS,
    Rol.TECNICO_INVENTARIO,
]


def _compatibles(a: Rol, b: Rol) -> bool:
    """Tabla del SRS 3.3 escrita a mano, independiente de la implementacion."""
    pares_malos = {
        Rol.RRHH,
        *TECNICOS,
        Rol.ADMINISTRADOR,
        Rol.AUDITOR,
    }  # RRHH incompatible con estos
    if Rol.AUDITOR in (a, b):
        return False
    if Rol.RRHH in (a, b):
        otro = b if a is Rol.RRHH else a
        return otro not in pares_malos
    if Rol.ADMINISTRADOR in (a, b):
        otro = b if a is Rol.ADMINISTRADOR else a
        return otro not in {Rol.RRHH, *TECNICOS}
    return True


@pytest.mark.parametrize(("a", "b"), list(itertools.combinations(Rol, 2)))
def test_roles_incompatibles_RF_05(a: Rol, b: Rol) -> None:
    if _compatibles(a, b):
        validar_roles(frozenset({a, b}))
    else:
        with pytest.raises(RolesIncompatibles):
            validar_roles(frozenset({a, b}))
        with pytest.raises(RolesIncompatibles):
            Actor("u", "c", frozenset({a, b}))


def test_un_solo_rol_y_varios_tecnicos_son_validos() -> None:
    for r in Rol:
        validar_roles(frozenset({r}))
    validar_roles(frozenset(TECNICOS))
    validar_roles(frozenset({Rol.SOLICITANTE, Rol.RRHH}))
    validar_roles(frozenset({Rol.SOLICITANTE, Rol.ADMINISTRADOR}))
    validar_roles(frozenset())


# --- quien registra que: rol x tipo x sujeto (4.1, RF-15) --------------------------------------

RELACIONES = list(Relacion)


def _esperado_solicitante(tipo: TipoEvento, sub: Subtipo | None, rel: Relacion) -> bool:
    if rel is Relacion.SI_MISMO:
        return tipo is TipoEvento.VAC or (tipo is TipoEvento.RET and sub is Subtipo.RENUNCIA)
    if rel is Relacion.SUBORDINADO_DIRECTO:
        return tipo in (TipoEvento.CDP, TipoEvento.CSU)
    return False


SUBTIPOS_DE = {
    TipoEvento.RET: [Subtipo.RENUNCIA, Subtipo.FIN_DE_CONTRATO],
    TipoEvento.EMG: [Subtipo.DESPIDO_CON_JUSTA_CAUSA, Subtipo.FUGA_DETECTADA],
}


@pytest.mark.parametrize("rol", list(Rol))
@pytest.mark.parametrize("tipo", list(TipoEvento))
@pytest.mark.parametrize("rel", RELACIONES)
def test_matriz_rol_tipo_sujeto_del_registro_pendiente(
    rol: Rol, tipo: TipoEvento, rel: Relacion
) -> None:
    actor = Actor("u", "c", frozenset({rol}))
    for sub in SUBTIPOS_DE.get(tipo, [None]):
        esperado = rol is Rol.SOLICITANTE and _esperado_solicitante(tipo, sub, rel)
        assert puede_registrar_como_solicitante(actor, tipo, sub, rel) is esperado


@pytest.mark.parametrize("rol", list(Rol))
@pytest.mark.parametrize("rel", RELACIONES)
def test_matriz_rol_sujeto_de_la_emision_directa_RF_13_RF_15(rol: Rol, rel: Relacion) -> None:
    actor = Actor("u", "c", frozenset({rol}))
    assert puede_emitir_directo(actor, rel) is (rol is Rol.RRHH and rel is not Relacion.SI_MISMO)


@pytest.mark.parametrize("rol", list(Rol))
def test_emision_por_excepcion_solo_admin_y_sujeto_rrhh_S_08(rol: Rol) -> None:
    actor = Actor("u", "c", frozenset({rol}))
    assert puede_emitir_por_excepcion(actor, True) is (rol is Rol.ADMINISTRADOR)
    assert puede_emitir_por_excepcion(actor, False) is False


def test_solicitante_con_rrhh_registra_su_vacacion_pero_no_emite_sobre_si_RF_15() -> None:
    a = Actor("u", "c", frozenset({Rol.SOLICITANTE, Rol.RRHH}))
    assert puede_registrar_como_solicitante(a, TipoEvento.VAC, None, Relacion.SI_MISMO)
    assert not puede_emitir_directo(a, Relacion.SI_MISMO)
    assert puede_emitir_directo(a, Relacion.TERCERO)


def test_relacion_con_el_sujeto() -> None:
    jefe = Actor("u1", "jefe-1", frozenset({Rol.SOLICITANTE}))
    assert relacion_con(jefe, "jefe-1", None) is Relacion.SI_MISMO
    assert relacion_con(jefe, "col-1", "jefe-1") is Relacion.SUBORDINADO_DIRECTO
    assert relacion_con(jefe, "col-1", "otro") is Relacion.TERCERO
    assert relacion_con(jefe, "col-1", None) is Relacion.TERCERO
    sin_colaborador = Actor("u2", None, frozenset({Rol.ADMINISTRADOR}))
    assert relacion_con(sin_colaborador, "col-1", None) is Relacion.TERCERO


def test_visibilidad_por_rol() -> None:
    for r in Rol:
        roles = frozenset({r})
        assert puede_ver_restringidos(roles) is (r is Rol.RRHH)
        assert puede_ver_dashboard(roles) is (r in TECNICOS)
        assert puede_consultar_auditoria(roles) is (r is Rol.AUDITOR)
        assert puede_reintentar_emision(roles) is (r is Rol.ADMINISTRADOR)
        assert puede_decidir(Actor("u", "c", roles)) is (r is Rol.RRHH)
