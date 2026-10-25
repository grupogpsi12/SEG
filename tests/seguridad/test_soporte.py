"""F3-U02 (T17, ADR-021): el soporte de vinculación se rechaza por firma, tamaño y nombre
ANTES de tocar el disco; lo que pasa se guarda con un nombre aleatorio.

Límite: 20 MiB exactos se aceptan y 20 MiB + 1 byte no (S-12).
"""

import pytest

from jml.aplicacion.dtos import ArchivoRecibido
from jml.dominio.errores import SoporteInvalido
from jml.dominio.soporte import validar_soporte
from jml.dominio.valores import MAX_SOPORTE_BYTES
from tests.mundo import PDF_VALIDO, Mundo, ingreso

pytestmark = pytest.mark.seguridad

BARRA = chr(92)  # barra invertida: evita escapes en el literal


def pdf_de(tamano: int) -> bytes:
    cabecera = b"%PDF-1.7\n"
    return cabecera + b"0" * (tamano - len(cabecera))


def test_U02_20_MiB_exactos_se_aceptan_y_20_MiB_mas_un_byte_no() -> None:
    assert validar_soporte(pdf_de(MAX_SOPORTE_BYTES), "acta.pdf").tamano == MAX_SOPORTE_BYTES
    with pytest.raises(SoporteInvalido, match="20 MB"):
        validar_soporte(pdf_de(MAX_SOPORTE_BYTES + 1), "acta.pdf")


@pytest.mark.parametrize(
    ("contenido", "nombre"),
    [
        (b"", "acta.pdf"),  # vacío
        (b"MZ\x90\x00" + b"0" * 100, "acta.pdf"),  # ejecutable de Windows con extensión .pdf
        (b"<html><script>alert(1)</script>", "acta.pdf"),  # HTML renombrado
        (b"PK\x03\x04" + b"0" * 100, "acta.pdf"),  # ZIP renombrado
        (b"%PDF" + b"0" * 100, "acta.pdf"),  # firma incompleta (falta el guion)
        (b" %PDF-1.7\n", "acta.pdf"),  # la firma no está al inicio
        (PDF_VALIDO, "acta.exe"),  # firma buena, extensión mala
        (PDF_VALIDO, "acta.pdf.exe"),  # doble extensión
        (PDF_VALIDO, "acta.pdf\x00.exe"),  # byte nulo: el cargador C leería «acta.pdf»
        (PDF_VALIDO, "acta"),  # sin extensión
        (PDF_VALIDO, ".pdf"),  # solo extensión: el nombre queda vacío y se rechaza
    ],
)
def test_U02_un_archivo_que_no_es_un_pdf_se_rechaza_por_firma_o_extension(
    contenido: bytes, nombre: str
) -> None:
    with pytest.raises(SoporteInvalido):
        validar_soporte(contenido, nombre)


@pytest.mark.parametrize(
    "original",
    [
        "../../etc/passwd.pdf",
        f"..{BARRA}..{BARRA}windows{BARRA}system32{BARRA}acta.pdf",
        "/etc/cron.d/acta.pdf",
        "acta\u200b.pdf",  # ancho cero
        "\u202egpj.exe.pdf",  # inversión de lectura (RLO)
        "acta\n.pdf",
        "a" * 500 + ".pdf",
    ],
)
def test_U02_el_nombre_original_nunca_conserva_rutas_ni_caracteres_de_control(
    original: str,
) -> None:
    nombre = validar_soporte(PDF_VALIDO, original).nombre.valor
    assert "/" not in nombre
    assert "\\" not in nombre
    assert ".." not in nombre
    assert nombre.isascii()
    assert nombre.isprintable()
    assert len(nombre) <= 100
    assert nombre.lower().endswith(".pdf")
    assert not nombre.startswith(".")


@pytest.mark.parametrize(
    "archivo",
    [
        ArchivoRecibido("acta.exe", PDF_VALIDO),
        ArchivoRecibido("acta.pdf", b"MZ" + b"0" * 50),
        ArchivoRecibido("acta.pdf", pdf_de(MAX_SOPORTE_BYTES + 1)),
    ],
)
def test_U02_un_rechazo_no_deja_nada_en_el_volumen(archivo: ArchivoRecibido) -> None:
    m = Mundo.nuevo()
    with pytest.raises(SoporteInvalido):
        m.emitir(ingreso(soporte=archivo))
    assert m.soportes.nombres() == []


def test_U02_lo_aceptado_se_guarda_con_un_nombre_aleatorio_sin_relacion_con_el_original() -> None:
    m = Mundo.nuevo()
    m.emitir(ingreso(soporte=ArchivoRecibido("acta_de_inicio.pdf", PDF_VALIDO)))
    (guardado,) = m.soportes.nombres()
    assert "acta" not in guardado
    assert "pdf" not in guardado.lower()


def test_U02_caracterizacion_un_pdf_con_carga_adicional_pasa_la_firma() -> None:
    """ADR-021 valida la FIRMA, no el contenido interno: un políglota (PDF + ZIP) la cumple.

    Es una limitación aceptada y documentada, porque la aplicación nunca abre, procesa ni sirve
    el archivo (volumen `noexec`, nombre aleatorio) y el antivirus está fuera de alcance. Si
    esta prueba empezara a fallar, el diseño cambió y hay que revisar ADR-021.
    """
    poliglota = PDF_VALIDO + b"PK\x03\x04" + b"0" * 64
    assert validar_soporte(poliglota, "acta.pdf").tamano == len(poliglota)
