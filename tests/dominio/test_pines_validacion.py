"""Fija el campo y el motivo exactos de cada rechazo de validacion, y los bordes numericos.

Las vistas mostraran estos mensajes y los formularios senalaran el campo (RNF-14); si cambian sin
querer se rompe la experiencia aunque la regla siga igual. Tambien fija los limites exactos.
"""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

import pytest

from jml.dominio.catalogo import (
    DatosCambioDepartamento,
    DatosCambioSucursal,
    DatosEmergencia,
    DatosIngreso,
    DatosRetiro,
    DatosVacaciones,
    validar_evento,
)
from jml.dominio.errores import DatoInvalido, ErrorDeDominio, OperacionNoPermitida
from jml.dominio.perfiles import RecursoCompartido, nombre_de_sede
from jml.dominio.soporte import Soporte, validar_soporte
from jml.dominio.tipos import (
    EstadoColaborador,
    PerfilDeRecurso,
    Subtipo,
    TipoDeVinculacion,
    TipoEvento,
)
from jml.dominio.usuarios import usuario_sugerido
from jml.dominio.valores import (
    BOGOTA,
    CalendarioHabil,
    CampoRestringido,
    CorreoUPN,
    Documento,
    FechaEfectiva,
    NombreDeSoporteSaneado,
    Sha256,
    SolicitudId,
    Usuario,
    a_utc,
    hoy_en_bogota,
    texto_no_vacio,
)
from tests.fabricas import AHORA, HOY, colaborador, datos_ingreso

R = CampoRestringido("m")
FUTURO = HOY + timedelta(days=5)


def _ingreso(**cambios: object) -> DatosIngreso:
    base = dict(
        nombres="A", apellidos="B", documento=Documento("12345"),
        vinculacion=TipoDeVinculacion.EMPLEADO, departamento="TI", cargo="x", sede="Cali",
        jefe_id=None, fecha_fin=None, requiere_equipo=False, tipo_equipo=None,
    )  # fmt: skip
    base.update(cambios)
    return DatosIngreso(**base)  # type: ignore[arg-type]  # kwargs de prueba


def _evento(
    tipo: TipoEvento,
    sub: Subtipo | None,
    fe: date,
    datos: object,
    r: CampoRestringido | None = None,
    ahora: datetime = AHORA,
) -> None:
    validar_evento(tipo, sub, fe, datos, r, ahora)  # type: ignore[arg-type]  # datos de prueba


I = _ingreso()  # noqa: E741
EMG_OK = DatosEmergencia("Seguridad", AHORA - timedelta(hours=1))

RECHAZOS: list[tuple[Callable[[], object], dict[str, object]]] = [
    # --- valores
    (lambda: FechaEfectiva(datetime(2026, 1, 1)), {"campo": "fecha_efectiva", "motivo": "debe ser una fecha, sin hora"}),
    (lambda: CalendarioHabil().sumar_dias_habiles(HOY, -1), {"campo": "dias", "motivo": "no puede ser negativo"}),
    (lambda: texto_no_vacio("x", " "), {"campo": "x", "motivo": "no puede estar vacio"}),
    (lambda: texto_no_vacio("x", "abc", 2), {"campo": "x", "motivo": "no puede superar 2 caracteres"}),
    (lambda: a_utc(datetime(2026, 1, 1)), {"campo": "fecha", "motivo": "debe incluir zona horaria"}),
    (lambda: a_utc(datetime(2026, 1, 1), "otra"), {"campo": "otra", "motivo": "debe incluir zona horaria"}),
    (lambda: hoy_en_bogota(datetime(2026, 1, 1)), {"campo": "ahora", "motivo": "debe incluir zona horaria"}),
    (lambda: SolicitudId("x"), {"campo": "solicitud_id", "motivo": "formato esperado SOL-AAAA-NNNNNN"}),
    (lambda: SolicitudId.de(999, 1), {"campo": "solicitud_id", "motivo": "anio o numero fuera de rango"}),
    (lambda: Documento("1"), {"campo": "documento", "motivo": "entre 5 y 15 letras o digitos"}),
    (lambda: CorreoUPN("x"), {"campo": "upn", "motivo": "formato usuario@dominio"}),
    (lambda: CorreoUPN("a@gmail.com"), {"campo": "upn", "motivo": "dominio no reconocido"}),
    (lambda: Usuario("A"), {"campo": "usuario", "motivo": "1 a 20 caracteres [a-z0-9.], sin punto al borde"}),
    (lambda: Sha256("x"), {"campo": "sha256", "motivo": "64 caracteres hexadecimales en minusculas"}),
    (lambda: NombreDeSoporteSaneado("a/b"), {"campo": "nombre_soporte", "motivo": "nombre no saneado"}),
    (lambda: NombreDeSoporteSaneado(".x"), {"campo": "nombre_soporte", "motivo": "nombre no saneado"}),
    (lambda: NombreDeSoporteSaneado("a\\b"), {"campo": "nombre_soporte", "motivo": "nombre no saneado"}),
    (lambda: CampoRestringido(" "), {"campo": "campo_restringido", "motivo": "no puede estar vacio"}),
    (lambda: CampoRestringido("a" * 4001), {"campo": "campo_restringido", "motivo": "no puede superar 4000 caracteres"}),
    (lambda: setattr(R, "x", 1), {"campo": "campo_restringido", "motivo": "es inmutable"}),
    # --- catalogo
    (lambda: _ingreso(vinculacion=TipoDeVinculacion.CONTRATISTA), {"campo": "fecha_fin", "motivo": "obligatoria si la vinculacion no es de empleado"}),
    (lambda: _ingreso(requiere_equipo=True), {"campo": "tipo_equipo", "motivo": "obligatorio cuando requiere equipo"}),
    (lambda: _ingreso(tipo_equipo=datos_ingreso().tipo_equipo), {"campo": "tipo_equipo", "motivo": "no aplica cuando no requiere equipo"}),
    (lambda: _ingreso(nombres=" "), {"campo": "nombres", "motivo": "no puede estar vacio"}),
    (lambda: _ingreso(apellidos=" "), {"campo": "apellidos", "motivo": "no puede estar vacio"}),
    (lambda: _ingreso(departamento=" "), {"campo": "departamento", "motivo": "no puede estar vacio"}),
    (lambda: _ingreso(cargo=" "), {"campo": "cargo", "motivo": "no puede estar vacio"}),
    (lambda: _ingreso(sede=" "), {"campo": "sede", "motivo": "no puede estar vacio"}),
    (lambda: DatosCambioDepartamento(" ", "x", None), {"campo": "departamento_nuevo", "motivo": "no puede estar vacio"}),
    (lambda: DatosCambioDepartamento("x", " ", None), {"campo": "cargo_nuevo", "motivo": "no puede estar vacio"}),
    (lambda: DatosCambioSucursal(" ", False), {"campo": "sede_nueva", "motivo": "no puede estar vacio"}),
    (lambda: DatosEmergencia(" ", AHORA), {"campo": "reportado_por", "motivo": "no puede estar vacio"}),
    (lambda: DatosEmergencia("x", datetime(2026, 1, 1)), {"campo": "hora_del_hecho", "motivo": "debe incluir zona horaria"}),
    (lambda: _evento(TipoEvento.VAC, None, FUTURO, I), {"campo": "datos", "motivo": "no corresponden a un evento VAC"}),
    (lambda: _evento(TipoEvento.RET, None, FUTURO, DatosVacaciones(FUTURO), R), {"campo": "datos", "motivo": "no corresponden a un evento RET"}),
    (lambda: _evento(TipoEvento.VAC, Subtipo.RENUNCIA, FUTURO, DatosVacaciones(FUTURO + timedelta(days=1))), {"campo": "subtipo", "motivo": "VAC no tiene subtipos"}),
    (lambda: _evento(TipoEvento.RET, Subtipo.FUGA_DETECTADA, FUTURO, DatosRetiro(), R), {"campo": "subtipo", "motivo": "no valido para RET"}),
    (lambda: _evento(TipoEvento.RET, Subtipo.RENUNCIA, FUTURO, DatosRetiro(), None), {"campo": "restringido", "motivo": "obligatorio en RET"}),
    (lambda: _evento(TipoEvento.VAC, None, FUTURO, DatosVacaciones(FUTURO + timedelta(days=1)), R), {"campo": "restringido", "motivo": "no aplica a VAC"}),
    (lambda: _evento(TipoEvento.VAC, None, HOY - timedelta(days=1), DatosVacaciones(FUTURO)), {"campo": "fecha_efectiva", "motivo": "no puede estar en el pasado"}),
    (lambda: _evento(TipoEvento.ING, None, FUTURO, _ingreso(vinculacion=TipoDeVinculacion.TEMPORAL, fecha_fin=FUTURO)), {"campo": "fecha_fin", "motivo": "debe ser posterior a la fecha de ingreso"}),
    (lambda: _evento(TipoEvento.VAC, None, FUTURO, DatosVacaciones(FUTURO)), {"campo": "fecha_regreso", "motivo": "debe ser posterior a la fecha de inicio"}),
    (lambda: _evento(TipoEvento.EMG, Subtipo.FUGA_DETECTADA, FUTURO, EMG_OK, R), {"campo": "fecha_efectiva", "motivo": "una emergencia es efectiva el dia de la emision"}),
    (lambda: _evento(TipoEvento.EMG, Subtipo.FUGA_DETECTADA, HOY, DatosEmergencia("x", AHORA + timedelta(seconds=1)), R), {"campo": "hora_del_hecho", "motivo": "no puede estar en el futuro"}),
    # --- colaborador, perfiles, soporte, usuarios
    (lambda: colaborador().con_estado(EstadoColaborador.POR_INGRESAR), {"motivo": "El colaborador no pasa de 'activo' a 'por_ingresar'"}),
    (lambda: colaborador().con_usuario_glpi(" "), {"campo": "id_usuario_glpi", "motivo": "no puede estar vacio"}),
    (lambda: RecursoCompartido("r", "s", PerfilDeRecurso.RETIRO_DE_ACCESOS, "g"), {"campo": "perfil", "motivo": "'Retiro de accesos' no se configura en la matriz (ADR-022)"}),
    (lambda: nombre_de_sede(" "), {"campo": "sede", "motivo": "no puede estar vacio"}),
    (lambda: validar_soporte(b"%PDF-x", "a.exe"), {"motivo": "la extension debe ser .pdf"}),
    (lambda: validar_soporte(b"", "a.pdf"), {"motivo": "el archivo esta vacio"}),
    (lambda: validar_soporte(b"%PDF-" + b"0" * (20 * 1024 * 1024), "a.pdf"), {"motivo": "supera los 20 MB"}),
    (lambda: validar_soporte(b"MZ", "a.pdf"), {"motivo": "el contenido no es un PDF"}),
    (lambda: usuario_sugerido("---", "x", []), {"campo": "nombres", "motivo": "no contiene letras ni digitos validos"}),
    (lambda: usuario_sugerido("x", "---", []), {"campo": "apellidos", "motivo": "no contiene letras ni digitos validos"}),
]  # fmt: skip


@pytest.mark.parametrize(("llamada", "datos"), RECHAZOS, ids=[f"{i}" for i in range(len(RECHAZOS))])
def test_cada_rechazo_dice_que_campo_y_por_que(
    llamada: Callable[[], object], datos: dict[str, object]
) -> None:
    with pytest.raises(ErrorDeDominio) as exc:
        llamada()
    obtenidos = dict(exc.value.datos)
    for clave, valor in datos.items():
        assert obtenidos[clave] == valor


def test_los_rechazos_de_soporte_y_estado_llevan_su_tipo_de_error() -> None:
    from jml.dominio.errores import SoporteInvalido

    with pytest.raises(SoporteInvalido):
        validar_soporte(b"", "a.pdf")
    with pytest.raises(OperacionNoPermitida):
        colaborador().con_estado(EstadoColaborador.POR_INGRESAR)
    s = Soporte.pendiente(SolicitudId.de(2026, 1), validar_soporte(b"%PDF-1", "a.pdf"), "n")
    with pytest.raises(OperacionNoPermitida) as e1:
        s.subido("D").subido("E")
    assert e1.value.motivo == "un soporte 'subido' no se sube"
    with pytest.raises(OperacionNoPermitida) as e2:
        s.subido("D").descartado()
    assert e2.value.motivo == "un soporte 'subido' no se descarta"


# --- bordes numericos y de formato ------------------------------------------------------------


def test_bordes_del_identificador_de_solicitud() -> None:
    assert SolicitudId.de(1000, 0).valor == "SOL-1000-000000"
    assert SolicitudId.de(9999, 999_999).valor == "SOL-9999-999999"
    for anio, numero in ((999, 0), (10_000, 0), (2026, -1), (2026, 1_000_000)):
        with pytest.raises(DatoInvalido):
            SolicitudId.de(anio, numero)


def test_bordes_del_documento_y_del_usuario() -> None:
    assert Documento("12345").valor == "12345"
    assert Documento("A" * 15).valor == "A" * 15
    for malo in ("1234", "A" * 16):
        with pytest.raises(DatoInvalido):
            Documento(malo)
    assert Usuario("a" * 20).valor == "a" * 20
    assert Usuario("a.b").valor == "a.b"
    with pytest.raises(DatoInvalido):
        Usuario("a" * 21)


def test_bordes_del_texto_y_del_campo_restringido() -> None:
    assert texto_no_vacio("x", "a" * 200) == "a" * 200
    assert texto_no_vacio("x", " ab ", 2) == "ab"
    with pytest.raises(DatoInvalido):
        texto_no_vacio("x", "a" * 201)
    assert CampoRestringido("a" * 4000).revelar() == "a" * 4000
    with pytest.raises(DatoInvalido):
        CampoRestringido("a" * 4001)


def test_bordes_del_nombre_de_soporte() -> None:
    assert NombreDeSoporteSaneado("a" * 100).valor == "a" * 100
    with pytest.raises(DatoInvalido):
        NombreDeSoporteSaneado("a" * 101)
    largo = NombreDeSoporteSaneado.sanear("b" * 150 + ".pdf").valor
    assert len(largo) == 100
    assert largo.endswith(".pdf")
    assert NombreDeSoporteSaneado.sanear(" .oculto. ").valor == "oculto"
    assert NombreDeSoporteSaneado.sanear("x" * 100).valor == "x" * 100
    assert NombreDeSoporteSaneado.sanear("x" * 101).valor == "x" * 100


def test_la_zona_horaria_de_bogota_se_llama_y_vale_menos_cinco() -> None:
    assert BOGOTA.utcoffset(None) == timedelta(hours=-5)
    assert BOGOTA.tzname(None) == "America/Bogota"
    assert hoy_en_bogota(datetime(2026, 1, 1, 4, 59, tzinfo=UTC)) == date(2025, 12, 31)
    assert hoy_en_bogota(datetime(2026, 1, 1, 5, 0, tzinfo=UTC)) == date(2026, 1, 1)


def test_el_hash_y_el_upn_aceptan_su_forma_exacta() -> None:
    assert Sha256("a" * 64).valor == "a" * 64
    with pytest.raises(DatoInvalido):
        Sha256("a" * 65)
    assert CorreoUPN("a@ad.andina.test").valor == "a@ad.andina.test"
    assert str(Usuario("ana").upn_ad()) == "ana@ad.andina.test"
    assert str(Usuario("ana").upn_m365()) == "ana@andina.example"
    assert str(Documento("ab123")) == "AB123"
    assert str(SolicitudId.de(2026, 5)) == "SOL-2026-000005"


def test_bordes_de_los_datos_del_ingreso_y_del_perfil() -> None:
    assert _ingreso(nombres="a" * 100).nombres == "a" * 100
    with pytest.raises(DatoInvalido):
        _ingreso(nombres="a" * 101)
    assert RecursoCompartido("r" * 300, "s", PerfilDeRecurso.CONSULTA, "g").ruta == "r" * 300
    with pytest.raises(DatoInvalido):
        RecursoCompartido("r" * 301, "s", PerfilDeRecurso.CONSULTA, "g")
    with pytest.raises(DatoInvalido):
        RecursoCompartido("r", "s" * 301, PerfilDeRecurso.CONSULTA, "g")
    with pytest.raises(DatoInvalido):
        RecursoCompartido("r", "s", PerfilDeRecurso.CONSULTA, "g" * 301)


def test_hoy_y_ayer_en_la_fecha_efectiva_del_evento() -> None:
    _evento(TipoEvento.VAC, None, HOY, DatosVacaciones(HOY + timedelta(days=1)))
    with pytest.raises(DatoInvalido):
        _evento(TipoEvento.VAC, None, HOY - timedelta(days=1), DatosVacaciones(HOY))
    _evento(TipoEvento.EMG, Subtipo.FUGA_DETECTADA, HOY, EMG_OK, R)
