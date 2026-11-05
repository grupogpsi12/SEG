"""Gherkin del soporte de vinculación: invoca la validación del dominio y el worker con el GLPI simulado."""

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from jml.aplicacion.dtos import ArchivoRecibido
from jml.dominio.errores import SoporteInvalido
from jml.dominio.tipos import EstadoDeSoporte
from jml.dominio.valores import MAX_SOPORTE_BYTES
from tests.mundo import PDF_VALIDO, Mundo, ingreso

scenarios("features/soporte-pdf.feature")


@pytest.fixture
def mundo() -> Mundo:
    return Mundo.nuevo()


def _pdf(tamano: int) -> bytes:
    cabecera = b"%PDF-1.7\n"
    return cabecera + b"0" * (tamano - len(cabecera))


@given("un ingreso emitido por RRHH con un PDF válido", target_fixture="registrada")
def _(mundo: Mundo, ctx: dict[str, object]) -> object:
    r = mundo.emitir(ingreso())
    ctx["copia"] = mundo.soportes.nombres()[0]
    return r


@when("el worker crea los tickets en GLPI")
def _(mundo: Mundo) -> None:
    mundo.bandeja()


@when("GLPI corrompe el documento al recibirlo y el worker intenta crear los tickets")
def _(mundo: Mundo) -> None:
    mundo.glpi.corromper_al_subir = True
    mundo.bandeja()


@when(parsers.parse("RRHH sube un PDF de 20 MiB exactos"), target_fixture="intento")
def _(mundo: Mundo) -> dict[str, object]:
    return _subir(mundo, ArchivoRecibido("acta.pdf", _pdf(MAX_SOPORTE_BYTES)))


@when(parsers.parse("RRHH sube un PDF de 20 MiB más un byte"), target_fixture="intento")
def _(mundo: Mundo) -> dict[str, object]:
    return _subir(mundo, ArchivoRecibido("acta.pdf", _pdf(MAX_SOPORTE_BYTES + 1)))


@when(parsers.parse('RRHH sube un ejecutable llamado "{nombre}"'), target_fixture="intento")
def _(mundo: Mundo, nombre: str) -> dict[str, object]:
    return _subir(mundo, ArchivoRecibido(nombre, b"MZ\x90\x00" + b"0" * 64))


@when(parsers.parse('RRHH sube un PDF llamado "{nombre}"'), target_fixture="intento")
def _(mundo: Mundo, nombre: str) -> dict[str, object]:
    return _subir(mundo, ArchivoRecibido(nombre, PDF_VALIDO))


def _subir(mundo: Mundo, archivo: ArchivoRecibido) -> dict[str, object]:
    antes = list(mundo.soportes.nombres())
    try:
        r = mundo.emitir(ingreso(soporte=archivo))
    except SoporteInvalido as e:
        return {"error": e, "nuevas": [n for n in mundo.soportes.nombres() if n not in antes]}
    with mundo.puerto.unidad_de_trabajo() as u:
        soporte = u.soportes.obtener(r.solicitud_id)
    return {"soporte": soporte, "nuevas": [n for n in mundo.soportes.nombres() if n not in antes]}


@then("el documento queda vinculado solo a los tickets de AD y de Licencias")
def _(mundo: Mundo, registrada: object) -> None:
    with mundo.puerto.unidad_de_trabajo() as u:
        vinculados = {
            t.ticket.cola.value: bool(mundo.glpi.vinculos_de(t.id_externo or ""))
            for t in u.tickets.creados()
        }
    assert vinculados == {
        "AD": True,
        "COMUNICACIONES": False,
        "LICENCIAS": True,
        "INVENTARIO": False,
    }


@then("la copia local se borra después de verificar el hash")
def _(mundo: Mundo, ctx: dict[str, object]) -> None:
    assert not mundo.soportes.existe(str(ctx["copia"]))
    assert "soporte.subido" in mundo.acciones_de_auditoria()


@then("el soporte se acepta")
def _(intento: dict[str, object]) -> None:
    assert "error" not in intento
    assert intento["soporte"].estado is EstadoDeSoporte.PENDIENTE  # type: ignore[attr-defined]


@then("el soporte se rechaza antes de tocar el disco")
def _(intento: dict[str, object]) -> None:
    assert isinstance(intento.get("error"), SoporteInvalido)
    assert intento["nuevas"] == []


@then("el nombre guardado no conserva rutas ni caracteres de control")
def _(intento: dict[str, object]) -> None:
    nombre = intento["soporte"].nombre_original.valor  # type: ignore[attr-defined]
    assert "/" not in nombre
    assert ".." not in nombre
    assert nombre.isprintable()


@then("la copia local se conserva y el intento cuenta como fallo")
def _(mundo: Mundo, ctx: dict[str, object]) -> None:
    assert mundo.soportes.existe(str(ctx["copia"]))
