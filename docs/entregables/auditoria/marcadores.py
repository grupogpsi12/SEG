"""Detecta marcadores sin reemplazar en los documentos (plan §10; D-01, B-02).

Una sola regla, usada por la prueba `tests/seguridad/test_documentos.py` (CI) y por
`verificar-entrega.py`. Un marcador es un hueco que alguien dejó para llenar después: un documento
que lo conserva puede declarar «cumplido» algo sin su evidencia (así pasó con CA-12).

NO son marcadores: `[PENDIENTE: motivo]` (el plan lo exige para lo que depende de Azure), el texto
dentro de bloques de código ``` ``` y los nombres de variables que aparecen dentro de una frase.

    python auditoria/herramientas/marcadores.py docs   # lista los marcadores y sale 1 si hay
"""

import re
import sys
from pathlib import Path

# Una línea que es SOLO un token EN_MAYUSCULAS_CON_GUION_BAJO (SQLMAP_RESULTADOS).
_TOKEN_SOLO = re.compile(r"^[A-Z][A-Z0-9]+(?:_[A-Z0-9]+)+$")
_OTROS = (
    re.compile(r"\{\{[^}\n]+\}\}"),  # {{valor}}
    re.compile(r"<<[A-Za-z_ ]+>>"),  # <<completar>>
    re.compile(r"\b(?:TODO|TBD|FIXME|XXX|LOREM IPSUM|PLACEHOLDER)\b"),
    re.compile(r"\[(?:POR )?COMPLETAR[^\]]*\]", re.IGNORECASE),
)


def buscar(texto: str) -> list[tuple[int, str]]:
    """[(número de línea, línea)] de cada marcador, ignorando los bloques de código."""
    hallazgos: list[tuple[int, str]] = []
    en_codigo = False
    for n, linea in enumerate(texto.splitlines(), start=1):
        if linea.lstrip().startswith("```"):
            en_codigo = not en_codigo
            continue
        if en_codigo:
            continue
        limpia = linea.strip()
        if _TOKEN_SOLO.fullmatch(limpia) or any(p.search(linea) for p in _OTROS):
            hallazgos.append((n, limpia))
    return hallazgos


def recorrer(carpeta: Path) -> dict[Path, list[tuple[int, str]]]:
    encontrados: dict[Path, list[tuple[int, str]]] = {}
    for ruta in sorted(carpeta.rglob("*.md")):
        marcas = buscar(ruta.read_text(encoding="utf-8", errors="replace"))
        if marcas:
            encontrados[ruta] = marcas
    return encontrados


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    raiz = Path(sys.argv[1] if len(sys.argv) > 1 else "docs")
    hay = recorrer(raiz)
    for ruta, marcas in hay.items():
        for n, linea in marcas:
            print(f"{ruta.as_posix()}:{n}: {linea}")
    print(f"{sum(len(m) for m in hay.values())} marcador(es) en {len(hay)} archivo(s)")
    sys.exit(1 if hay else 0)
