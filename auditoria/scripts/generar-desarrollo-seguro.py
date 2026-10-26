"""Entregables de «Desarrollo Seguro»: regenera las figuras y los cuatro PDF de `docs/Desarrollo Seguro/`.

    uv run python auditoria/scripts/generar-desarrollo-seguro.py

Los textos son los `.md` de esa carpeta (no se modifican); las figuras las dibuja `figuras-desarrollo-seguro.py`.
"""

import importlib.util
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
CARPETA = RAIZ / "docs" / "Desarrollo Seguro"
ENTREGABLES = [
    "1-Resultados-de-pruebas-funcionales",
    "2-Resultados-de-pruebas-de-vulnerabilidades",
    "3-Analisis-de-captura-de-trafico",
    "4-Propuesta-de-controles-de-seguridad",
]


def cargar(nombre: str):  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(
        nombre.replace("-", "_"), RAIZ / "auditoria" / "scripts" / f"{nombre}.py"
    )
    assert spec is not None
    assert spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    cargar("figuras-desarrollo-seguro").main()
    pdf = cargar("generar-entrega")
    for nombre in ENTREGABLES:
        fuente = CARPETA / f"{nombre}.md"
        if not fuente.exists():
            print(f"falta {fuente.name}: se omite")
            continue
        texto = fuente.read_text(encoding="utf-8")
        titulo = texto.splitlines()[0].lstrip("# ").strip()  # con tildes, no el nombre del archivo
        pdf.md_a_pdf(
            texto,
            CARPETA / f"{nombre}.pdf",
            titulo,
            None,
            CARPETA,
            pie_prefijo="SSGUI · Desarrollo Seguro",
        )
        print(f"{nombre}.pdf: {(CARPETA / f'{nombre}.pdf').stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
