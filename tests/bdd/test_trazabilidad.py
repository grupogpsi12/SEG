"""F4-04: cada etiqueta de Gherkin se traza a algo real y ninguna amenaza se queda sin escenario.

Las etiquetas son los identificadores de verdad: `@RF-01`, `@RS-13`, `@CA-14`, `@T1`, `@A07-2025`.
Una etiqueta que no existe en el SRS o en el plan es una traza rota, y se detecta aquí.
"""

import re
from collections import defaultdict
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
FEATURES = sorted((RAIZ / "tests" / "bdd" / "features").glob("*.feature"))
SRS = (RAIZ / "docs" / "SRS.md").read_text(encoding="utf-8")

# etiquetas de ejecución (marcadores de pytest), no identificadores de trazabilidad
DE_EJECUCION = {"integracion", "requiere-stack", "requiere-red", "pendiente-F7", "pendiente-F6"}
AMENAZAS = {f"T{n}" for n in range(1, 22)}
NUEVAS = {f"N-{n}" for n in range(1, 6)}
OWASP = {f"A{n:02d}-2025" for n in range(1, 11)}


def _etiquetas(texto: str) -> list[str]:
    return re.findall(r"(?<!\S)@([\w.-]+)", texto)


def _escenarios() -> list[tuple[str, str, set[str]]]:
    """(archivo, título, etiquetas heredadas de la característica + propias) de cada escenario."""
    salida: list[tuple[str, str, set[str]]] = []
    for ruta in FEATURES:
        lineas = ruta.read_text(encoding="utf-8").splitlines()
        de_la_caracteristica: set[str] = set()
        pendientes: list[str] = []
        en_caracteristica = False
        for linea in lineas:
            texto = linea.strip()
            if texto.startswith("@"):
                pendientes += _etiquetas(texto)
            elif texto.startswith("Característica:"):
                de_la_caracteristica, pendientes, en_caracteristica = set(pendientes), [], True
            elif texto.startswith(("Escenario:", "Esquema del escenario:")) and en_caracteristica:
                titulo = texto.split(":", 1)[1].strip()
                salida.append((ruta.name, titulo, de_la_caracteristica | set(pendientes)))
                pendientes = []
    return salida


ESCENARIOS = _escenarios()


def _existe(etiqueta: str) -> bool:
    if etiqueta in DE_EJECUCION or etiqueta in AMENAZAS | NUEVAS | OWASP:
        return True
    if re.fullmatch(r"(RF|RNF|RD|RS|RI|CA)-\d+", etiqueta):
        return re.search(rf"^\| {re.escape(etiqueta)} \|", SRS, re.MULTILINE) is not None
    return bool(re.fullmatch(r"WSTG-[A-Z]+|CWE-\d+", etiqueta))


def test_hay_doce_caracteristicas_mas_la_de_postgresql() -> None:
    nombres = {f.stem for f in FEATURES}
    assert nombres >= {
        "ingreso", "autorizacion", "inmutabilidad", "restringidos", "cabeceras", "borde",
        "soporte-pdf", "cuentas-derivadas", "resiliencia", "supabase-aislada",
        "cadena-de-suministro", "secretos-y-logs",
    }  # fmt: skip


def test_F4_04_ninguna_etiqueta_sin_trazar() -> None:
    rotas = {
        (archivo, e) for archivo, _, etiquetas in ESCENARIOS for e in etiquetas if not _existe(e)
    }
    assert rotas == set()


def test_F4_04_ninguna_amenaza_sin_escenario() -> None:
    cubiertas = set().union(*(etiquetas for _, _, etiquetas in ESCENARIOS))
    assert (AMENAZAS | NUEVAS) - cubiertas == set()


@pytest.mark.parametrize("archivo", [f.name for f in FEATURES])
def test_cada_caracteristica_tiene_camino_feliz_o_borde_y_un_caso_adversarial(archivo: str) -> None:
    titulos = [t for a, t, _ in ESCENARIOS if a == archivo]
    assert any(t.startswith("Adversarial") for t in titulos), titulos
    assert any(t.startswith(("Camino feliz", "Borde")) for t in titulos), titulos


def test_los_escenarios_de_bloqueo_se_nombran_con_su_control_positivo() -> None:
    """Un escenario de baneo, 403 o 429 declara su control positivo en el título."""
    sin_control = [
        (a, t)
        for a, t, _ in ESCENARIOS
        if re.search(r"baneo|bloquea", t, re.IGNORECASE) and "control positivo" not in t.lower()
    ]
    assert sin_control == []


def test_resumen_de_escenarios_por_amenaza() -> None:
    por_amenaza: dict[str, int] = defaultdict(int)
    for _, _, etiquetas in ESCENARIOS:
        for e in etiquetas & (AMENAZAS | NUEVAS):
            por_amenaza[e] += 1
    assert len(por_amenaza) == len(AMENAZAS | NUEVAS)


def test_S_37_toda_omision_de_un_escenario_cita_su_supuesto() -> None:
    """S-37 y S-38: un `skip` de Gherkin dice por qué (stack, red o F7) y no se confunde con un pase."""
    sin_id = [
        f"{ruta.name}:{n}"
        for ruta in (RAIZ / "tests" / "bdd").glob("test_*.py")
        if ruta.name != "test_trazabilidad.py"
        for n, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), 1)
        if "pytest" + ".skip(" in linea and not re.search(r"S-3[78]", linea)
    ]
    assert sin_id == []


def test_S_38_los_escenarios_pendientes_de_F7_estan_marcados() -> None:
    """Un escenario omitido a la espera de F7 lleva la etiqueta `@pendiente-F7` en su `.feature`."""
    fuentes = "".join(f.read_text(encoding="utf-8") for f in FEATURES)
    omitidos_en_codigo = len(
        re.findall(
            r"S-38 \[PENDIENTE: F7\]",
            "".join(
                p.read_text(encoding="utf-8") for p in (RAIZ / "tests" / "bdd").glob("test_*.py")
            ),
        )
    )
    assert omitidos_en_codigo > 0
    assert fuentes.count("@pendiente-F7") >= 2
