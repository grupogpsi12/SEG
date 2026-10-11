"""CA-17 / RNF-10: refuerzo de import-linter. Cualquier import externo falla, no solo los listados.

Tambien prohibe las llamadas no deterministas (datetime.now, uuid4, random): el tiempo y los
identificadores entran por puertos o generadores inyectados.
"""

import ast
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2] / "src" / "jml"
PROHIBIDAS = {"now", "utcnow", "today", "uuid4", "uuid1", "random", "randint", "urandom"}


def _archivos(capa: str) -> list[Path]:
    return sorted((RAIZ / capa).rglob("*.py"))


def _modulos_importados(ruta: Path) -> set[str]:
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    modulos: set[str] = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            modulos.update(a.name for a in nodo.names)
        elif isinstance(nodo, ast.ImportFrom) and nodo.level == 0 and nodo.module:
            modulos.add(nodo.module)
    return modulos


@pytest.mark.parametrize(
    ("capa", "permitidos"), [("dominio", ()), ("aplicacion", ("jml.dominio",))]
)
def test_capa_solo_importa_lo_permitido(capa: str, permitidos: tuple[str, ...]) -> None:
    for ruta in _archivos(capa):
        for modulo in _modulos_importados(ruta):
            raiz = modulo.split(".")[0]
            propio = modulo == f"jml.{capa}" or modulo.startswith(f"jml.{capa}.")
            ok = (
                raiz in sys.stdlib_module_names
                or propio
                or any(modulo == p or modulo.startswith(p + ".") for p in permitidos)
            )
            assert ok, f"{ruta.name} importa {modulo}"


@pytest.mark.parametrize("capa", ["dominio", "aplicacion"])
def test_no_hay_llamadas_no_deterministas(capa: str) -> None:
    for ruta in _archivos(capa):
        for nodo in ast.walk(ast.parse(ruta.read_text(encoding="utf-8"))):
            if isinstance(nodo, ast.Call):
                f = nodo.func
                nombre = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
                assert nombre not in PROHIBIDAS, f"{ruta.name}: llamada a {nombre}()"


def test_no_hay_pruebas_omitidas_sin_id_de_supuesto() -> None:
    """Item 1.13: `skip`/`xfail` solo con el ID de un supuesto abierto (S-nn)."""
    import re

    raiz = Path(__file__).resolve().parents[1]
    for ruta in raiz.rglob("test_*.py"):
        if ruta.name == "test_pureza.py":
            continue
        for n, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), start=1):
            if re.search(r"pytest\.mark\.(skip|skipif|xfail)|pytest\.(skip|xfail)\(", linea):
                assert re.search(r"S-\d{2}", linea), f"{ruta.name}:{n} omite una prueba sin ID"
