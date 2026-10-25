"""B-02 (D-01, N-5): ningun documento declara algo con un hueco sin llenar.

`docs/evidencia/seguridad-2026-10-24.md` afirmaba «sqlmap nivel 3 sin hallazgos» y, donde debian ir
los resultados, decia literalmente `SQLMAP_RESULTADOS`. Un criterio de aceptacion (CA-12) quedaba
declarado sin su evidencia. La regla vive en `auditoria/herramientas/marcadores.py` y es la misma
que usa `verificar-entrega.py`.
"""

from pathlib import Path

import pytest
from auditoria.herramientas import marcadores

RAIZ = Path(__file__).resolve().parents[2]
DOCUMENTOS = [RAIZ / "docs", RAIZ / "tasks"]


@pytest.mark.seguridad
def test_B_02_ningun_documento_tiene_marcadores_sin_reemplazar() -> None:
    hallados = {
        ruta: m for carpeta in DOCUMENTOS for ruta, m in marcadores.recorrer(carpeta).items()
    }
    detalle = [
        f"{r.relative_to(RAIZ).as_posix()}:{n}: {t}" for r, ms in hallados.items() for n, t in ms
    ]
    assert not detalle, detalle


@pytest.mark.seguridad
@pytest.mark.parametrize(
    "texto",
    [
        "SQLMAP_RESULTADOS",
        "  RESULTADOS_DE_ZAP  ",
        "Resultado: {{resultado}}",
        "Pendiente: <<completar>>",
        "TODO escribir la conclusion",
        "Conclusion [POR COMPLETAR]",
    ],
)
def test_B_02_el_detector_reconoce_los_marcadores(texto: str) -> None:
    assert marcadores.buscar(texto), texto


@pytest.mark.seguridad
@pytest.mark.parametrize(
    "texto",
    [
        "[PENDIENTE: ventana de despliegue]",  # lo exige el plan para lo que depende de Azure
        "Se usa JML_GLPI_DE_PRUEBAS en la corrida",  # una variable dentro de una frase
        "```\nSQLMAP_RESULTADOS\n```",  # un bloque de codigo
        "Texto normal con TODOs en minuscula: todo.md",
    ],
)
def test_B_02_el_detector_respeta_lo_permitido(texto: str) -> None:
    assert marcadores.buscar(texto) == [], texto
