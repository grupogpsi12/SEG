"""Item 1.3: objetos de valor y errores tipados."""

import copy
import dataclasses
import json
import pickle
from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from jml.dominio import errores
from jml.dominio.errores import CampoRestringidoProhibido, DatoInvalido, ErrorDeDominio
from jml.dominio.tipos import ESTADOS_ABIERTOS, ESTADOS_FINALES, EstadoSolicitud
from jml.dominio.valores import (
    BOGOTA,
    MAX_SOPORTE_BYTES,
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
    ascii_minuscula,
    fin_del_dia,
    hoy_en_bogota,
    inicio_del_dia,
    texto_no_vacio,
)


def test_estados_abiertos_incluyen_error_y_en_ejecucion_RD_01() -> None:
    """RD-01 / lessons n.1: contar error o en_ejecucion como finales es el error n.1."""
    assert {
        EstadoSolicitud.PENDIENTE_APROBACION,
        EstadoSolicitud.APROBADA,
        EstadoSolicitud.EN_EJECUCION,
        EstadoSolicitud.ERROR,
    } == ESTADOS_ABIERTOS
    assert {
        EstadoSolicitud.CERRADA,
        EstadoSolicitud.RECHAZADA,
        EstadoSolicitud.CANCELADA,
    } == ESTADOS_FINALES


def test_ningun_error_de_dominio_es_value_error() -> None:
    for nombre in dir(errores):
        objeto = getattr(errores, nombre)
        if isinstance(objeto, type) and issubclass(objeto, ErrorDeDominio):
            assert not issubclass(objeto, ValueError)
    assert not issubclass(DatoInvalido, ValueError)


def test_los_codigos_de_error_son_unicos_y_estables() -> None:
    codigos = [
        c.codigo
        for c in vars(errores).values()
        if isinstance(c, type) and issubclass(c, ErrorDeDominio)
    ]
    assert len(codigos) == len(set(codigos))
    assert DatoInvalido.codigo == "dato_invalido"


def test_solicitud_id_valido_e_invalido() -> None:
    assert str(SolicitudId.de(2026, 42)) == "SOL-2026-000042"
    assert SolicitudId("SOL-2026-000042").valor == "SOL-2026-000042"
    for malo in ["", "SOL-26-000042", "SOL-2026-42", "sol-2026-000042", "SOL-2026-0000421"]:
        with pytest.raises(DatoInvalido):
            SolicitudId(malo)
    with pytest.raises(DatoInvalido):
        SolicitudId.de(2026, 1_000_000)
    with pytest.raises(DatoInvalido):
        SolicitudId.de(999, 1)
    with pytest.raises(DatoInvalido):
        SolicitudId.de(2026, -1)


def test_documento_se_normaliza_y_valida() -> None:
    assert Documento(" ab12345 ").valor == "AB12345"
    for malo in ["1234", "1" * 16, "12 345", "123-456", ""]:
        with pytest.raises(DatoInvalido):
            Documento(malo)


def test_usuario_y_upn() -> None:
    u = Usuario("maria.gomez")
    assert str(u.upn_ad()) == "maria.gomez@ad.andina.test"
    assert str(u.upn_m365()) == "maria.gomez@andina.example"
    assert str(u) == "maria.gomez"
    assert Usuario("a").valor == "a"
    assert Usuario("a" * 20).valor == "a" * 20
    for malo in ["", "a" * 21, ".ab", "ab.", "Ab", "a b", "a..b", "ñu"]:
        with pytest.raises(DatoInvalido):
            Usuario(malo)


def test_upn_rechaza_dominios_ajenos() -> None:
    assert str(CorreoUPN("a.b@andina.example")) == "a.b@andina.example"
    for malo in ["a.b@gmail.com", "sin-arroba", "A@andina.example", "@andina.example"]:
        with pytest.raises(DatoInvalido):
            CorreoUPN(malo)


def test_sha256() -> None:
    assert Sha256.de_bytes(b"").valor == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )
    assert str(Sha256.de_bytes(b"x")) == Sha256.de_bytes(b"x").valor
    for malo in ["", "ABC", "g" * 64, "a" * 63, "A" * 64]:
        with pytest.raises(DatoInvalido):
            Sha256(malo)


@pytest.mark.parametrize(
    ("original", "esperado"),
    [
        ("acta.pdf", "acta.pdf"),
        ("C:\\Users\\x\\acta de inicio.pdf", "acta de inicio.pdf"),
        ("../../etc/passwd.pdf", "passwd.pdf"),
        ("acción ñandú.pdf", "accion nandu.pdf"),
        ("a<b>|c?.pdf", "a_b__c_.pdf"),
        (".htaccess", "htaccess"),
        ("", "soporte.pdf"),
        ("...", "soporte.pdf"),
        ("dir/", "soporte.pdf"),
    ],
)
def test_nombre_de_soporte_saneado_RF_39(original: str, esperado: str) -> None:
    assert NombreDeSoporteSaneado.sanear(original).valor == esperado


def test_nombre_de_soporte_largo_conserva_la_extension() -> None:
    nombre = NombreDeSoporteSaneado.sanear("a" * 300 + ".pdf").valor
    assert len(nombre) == 100
    assert nombre.endswith(".pdf")
    assert len(NombreDeSoporteSaneado.sanear("b" * 300).valor) == 100
    assert str(NombreDeSoporteSaneado.sanear("x.pdf")) == "x.pdf"


def test_nombre_de_soporte_directo_rechaza_lo_no_saneado() -> None:
    for malo in ["", "a/b.pdf", "a\\b.pdf", ".oculto", "x" * 101, "a<b.pdf"]:
        with pytest.raises(DatoInvalido):
            NombreDeSoporteSaneado(malo)


def test_limite_de_soporte_S_12() -> None:
    """S-12: 20 MiB exactos."""
    assert MAX_SOPORTE_BYTES == 20 * 1024 * 1024


def test_fecha_efectiva_rechaza_datetime() -> None:
    assert FechaEfectiva(date(2026, 10, 12)).mas_dias(3).valor == date(2026, 10, 15)
    with pytest.raises(DatoInvalido):
        FechaEfectiva(datetime(2026, 10, 12, 1, 0))


def test_limites_del_dia_en_bogota_S_02() -> None:
    """S-02: 00:00 y 23:59:59 America/Bogota, guardados en UTC."""
    f = FechaEfectiva(date(2026, 10, 12))
    assert f.inicio_del_dia() == datetime(2026, 10, 12, 5, 0, 0, tzinfo=UTC)
    assert f.fin_del_dia() == datetime(2026, 10, 13, 4, 59, 59, tzinfo=UTC)
    assert inicio_del_dia(date(2026, 1, 1)).tzinfo == UTC
    assert fin_del_dia(date(2026, 1, 1)).tzinfo == UTC


def test_hoy_en_bogota_cruza_la_medianoche_S_02() -> None:
    assert hoy_en_bogota(datetime(2026, 10, 12, 4, 59, tzinfo=UTC)) == date(2026, 10, 11)
    assert hoy_en_bogota(datetime(2026, 10, 12, 5, 0, tzinfo=UTC)) == date(2026, 10, 12)


def test_instantes_sin_zona_se_rechazan() -> None:
    with pytest.raises(DatoInvalido):
        a_utc(datetime(2026, 1, 1))
    with pytest.raises(DatoInvalido):
        hoy_en_bogota(datetime(2026, 1, 1))
    mismo = a_utc(datetime(2026, 1, 1, 0, 0, tzinfo=BOGOTA))
    assert mismo == datetime(2026, 1, 1, 5, 0, tzinfo=UTC)
    assert mismo.tzinfo == UTC
    assert a_utc(datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=2)))).hour == 22


def test_calendario_habil_S_01() -> None:
    cal = CalendarioHabil()
    viernes, sabado, lunes = date(2026, 10, 9), date(2026, 10, 10), date(2026, 10, 12)
    assert cal.es_habil(viernes)
    assert not cal.es_habil(sabado)
    assert cal.sumar_dias_habiles(viernes, 1) == lunes
    assert cal.sumar_dias_habiles(sabado, 1) == lunes
    assert cal.sumar_dias_habiles(viernes, 0) == viernes
    assert cal.sumar_dias_habiles(lunes, 5) == date(2026, 10, 19)
    con_festivo = CalendarioHabil(frozenset({lunes}))
    assert not con_festivo.es_habil(lunes)
    assert con_festivo.sumar_dias_habiles(viernes, 1) == date(2026, 10, 13)
    with pytest.raises(DatoInvalido):
        cal.sumar_dias_habiles(viernes, -1)


def test_texto_no_vacio() -> None:
    assert texto_no_vacio("x", "  hola ") == "hola"
    with pytest.raises(DatoInvalido):
        texto_no_vacio("x", "   ")
    with pytest.raises(DatoInvalido):
        texto_no_vacio("x", "a" * 201)
    assert texto_no_vacio("x", "a" * 200) == "a" * 200
    assert texto_no_vacio("x", "a" * 5, maximo=5) == "a" * 5
    with pytest.raises(DatoInvalido):
        texto_no_vacio("x", "a" * 6, maximo=5)


def test_ascii_minuscula() -> None:
    assert ascii_minuscula("MUÑOZ Ángel Ünal") == "munoz angel unal"


# --- CampoRestringido (RD-05, CA-10) -----------------------------------------------------------

SENTINELA = "SENTINELA-MOTIVO-ÚNICO-7731"


def test_campo_restringido_no_se_imprime_ni_formatea_RD_05() -> None:
    c = CampoRestringido(SENTINELA)
    for salida in (repr(c), str(c), f"{c}", f"{c!r}", "%s" % c, format(c, ">40")):  # noqa: UP031
        assert SENTINELA not in salida
    assert c.revelar() == SENTINELA


def test_campo_restringido_no_se_serializa_RD_05() -> None:
    c = CampoRestringido(SENTINELA)
    with pytest.raises(TypeError):
        json.dumps({"x": c})
    with pytest.raises(CampoRestringidoProhibido):
        pickle.dumps(c)
    with pytest.raises(CampoRestringidoProhibido):
        c.__reduce__()
    assert copy.copy(c) is c
    assert copy.deepcopy(c) is c


def test_campo_restringido_en_dataclass_no_aparece_en_repr_ni_asdict_json() -> None:
    @dataclasses.dataclass(frozen=True, slots=True)
    class Contenedor:
        motivo: CampoRestringido
        otro: str

    cont = Contenedor(CampoRestringido(SENTINELA), "visible")
    assert SENTINELA not in repr(cont)
    assert SENTINELA not in str(cont)
    with pytest.raises(TypeError):
        json.dumps(dataclasses.asdict(cont))


def test_campo_restringido_es_inmutable_y_valida() -> None:
    c = CampoRestringido(f"  {SENTINELA}  ")
    assert c.revelar() == SENTINELA
    with pytest.raises(DatoInvalido):
        c.otro = "x"
    with pytest.raises(DatoInvalido):
        CampoRestringido("   ")
    with pytest.raises(DatoInvalido):
        CampoRestringido("a" * 4001)
    assert CampoRestringido("a" * 4000).revelar() == "a" * 4000
    assert CampoRestringido("a") == CampoRestringido("a")
    assert CampoRestringido("a") != CampoRestringido("b")
    assert CampoRestringido("a") != "a"
    assert hash(CampoRestringido("a")) == hash(CampoRestringido("a"))


def test_errores_tipados_exponen_datos() -> None:
    e = errores.SolicitudDuplicada("SOL-2026-000001")
    assert e.existente_id == "SOL-2026-000001"
    assert e.datos["existente_id"] == "SOL-2026-000001"
    t = errores.TransicionInvalida("cerrada", "aprobar")
    assert (t.estado, t.accion) == ("cerrada", "aprobar")
    assert errores.AutoAprobacionProhibida("aprobar").accion == "aprobar"
    assert isinstance(errores.AutoAprobacionProhibida("x"), errores.NoAutorizado)
    assert errores.DocumentoDuplicado("c1").existente_id == "c1"
    assert errores.RolesIncompatibles("a", "b").otro == "b"
    assert errores.JustificacionRequerida("rechazar").accion == "rechazar"
    assert errores.SolicitudInmutable("aprobada").estado == "aprobada"
    assert errores.CancelacionNoPermitida("m").motivo == "m"
    assert errores.CierreNoPermitido(2).pendientes == 2
    assert errores.ColaboradorNoElegible("VAC", "retirado").tipo == "VAC"
    assert errores.SoporteInvalido("firma").motivo == "firma"
    assert errores.CampoRestringidoProhibido("log").destino == "log"
    assert errores.OperacionNoPermitida("m").motivo == "m"
    assert errores.NoEncontrado("solicitud", "x").referencia == "x"
    assert errores.NoAutorizado("a", "m").motivo == "m"
