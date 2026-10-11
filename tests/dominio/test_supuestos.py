"""Item 1.2: todo supuesto tiene un ID y una prueba que lo nombra (lessons.md n.º 17)."""

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
REGISTRO = RAIZ / "docs" / "supuestos-nucleo.md"
ID = re.compile(r"S[-_](\d{2})(?!\d)")


def _ids_del_registro() -> set[str]:
    filas = re.findall(r"^\| (S-\d{2}) \|", REGISTRO.read_text(encoding="utf-8"), re.MULTILINE)
    return set(filas)


def _texto_de(carpeta: Path) -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(carpeta.rglob("*.py")))


def _ids_citados(texto: str) -> set[str]:
    return {f"S-{n}" for n in ID.findall(texto)}


def test_el_registro_tiene_los_supuestos_sin_huecos() -> None:
    esperados = {f"S-{n:02d}" for n in range(1, 36)}
    assert _ids_del_registro() == esperados


def test_cada_supuesto_del_registro_lo_nombra_alguna_prueba() -> None:
    nombradas = _ids_citados(_texto_de(RAIZ / "tests"))
    sin_prueba = _ids_del_registro() - nombradas
    assert not sin_prueba, f"supuestos sin prueba que los nombre: {sorted(sin_prueba)}"


def test_ningun_id_citado_en_el_codigo_falta_en_el_registro() -> None:
    citados = _ids_citados(_texto_de(RAIZ / "src")) | _ids_citados(_texto_de(RAIZ / "tests"))
    huerfanos = citados - _ids_del_registro()
    assert not huerfanos, (
        f"IDs usados sin registrar en docs/supuestos-nucleo.md: {sorted(huerfanos)}"
    )


def test_el_registro_dice_donde_esta_la_prueba_de_cada_supuesto() -> None:
    texto = REGISTRO.read_text(encoding="utf-8")
    fuente = _texto_de(RAIZ / "tests")
    for linea in texto.splitlines():
        if not re.match(r"^\| S-\d{2} \|", linea):
            continue
        nombres = re.findall(r"`(test_[A-Za-z0-9_]+)`", linea)
        assert nombres, f"{linea[:8]} no indica su prueba"
        for nombre in nombres:
            assert f"def {nombre}(" in fuente, f"{nombre} no existe"
