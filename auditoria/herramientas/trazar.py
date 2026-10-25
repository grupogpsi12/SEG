"""Genera auditoria/trazabilidad.csv: requisito/amenaza -> pruebas, escenarios y evidencia.

    python auditoria/herramientas/trazar.py            # reescribe el CSV y resume huecos
    python auditoria/herramientas/trazar.py --resumen  # solo el resumen

Fuentes (todas del repositorio, nada de memoria):
  - docs/SRS.md                RF, RNF, RS, RD, RI, CA y T21 (tablas «| ID | ... |»)
  - docs/PLAN_AUDITORIA.md     N-1 a N-5 (§3.2)
  - tests/**/*.py              el nombre y el docstring de cada prueba, leidos con `ast`
  - auditoria/features/*.feature  etiquetas Gherkin (@RF-01, @T7, ...)
  - docs/evidencia/*.md y auditoria/evidencia/**/salida.txt  menciones de CA-nn

Un ID cuenta como «citado» por una prueba si aparece en su nombre o en su docstring, con
cualquier separador (RS-08, RS_08). Es una traza de NOMBRE, no una prueba de que el control
funcione: eso lo demuestran la rotura deliberada y la mutacion (plan §10).
"""

import ast
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
SALIDA = RAIZ / "auditoria" / "trazabilidad.csv"
TIPOS = ("RF", "RNF", "RS", "RD", "RI", "CA")
FILA_SRS = re.compile(r"^\|\s*((?:RF|RNF|RS|RD|RI|CA)-\d+|T\d+)\s*\|(.*)\|\s*$")
FILA_N = re.compile(r"^\|\s*(N-\d)\s*\|\s*\*\*([^*]+)\*\*")
PRIORIDAD = re.compile(r"\|\s*(Debe|Debería|Podría|Deberia|Podria)\s*$")


def _tipo(id_: str) -> str:
    return (
        "N" if id_.startswith("N-") else ("T" if re.fullmatch(r"T\d+", id_) else id_.split("-")[0])
    )


def _regex(id_: str) -> re.Pattern[str]:
    """RS-08 -> RS[-_ ]?0*8 sin cifras pegadas; T7 -> T[-_ ]?0*7; N-1 -> N[-_ ]?1."""
    m = re.fullmatch(r"([A-Z]+)-?(\d+)", id_)
    assert m, id_
    return re.compile(rf"(?<![A-Za-z0-9])({m.group(1)}[-_ ]?0*{int(m.group(2))})(?![0-9])")


def leer_srs() -> dict[str, tuple[str, str]]:
    items: dict[str, tuple[str, str]] = {}
    for linea in (RAIZ / "docs" / "SRS.md").read_text(encoding="utf-8").splitlines():
        m = FILA_SRS.match(linea)
        if not m or m.group(1) in items:
            continue
        celdas = [c.strip() for c in m.group(2).split("|")]
        prior = PRIORIDAD.search(linea)
        # RF/RNF/RS/RD/RI: la 1.ª celda es el texto; CA: «Titulo: texto»; T: la 2.ª es la amenaza
        titulo = celdas[1] if _tipo(m.group(1)) == "T" and len(celdas) > 1 else celdas[0]
        items[m.group(1)] = (re.sub(r"\s+", " ", titulo)[:140], prior.group(1) if prior else "")
    for linea in (RAIZ / "docs" / "PLAN_AUDITORIA.md").read_text(encoding="utf-8").splitlines():
        m = FILA_N.match(linea)
        if m:
            items[m.group(1)] = (m.group(2).strip()[:140], "Auditoria")
    return items


def leer_pruebas() -> list[tuple[str, str]]:
    """(ruta::nombre, texto) de cada prueba: su nombre y su docstring."""
    salida: list[tuple[str, str]] = []
    for ruta in sorted((RAIZ / "tests").rglob("*.py")):
        try:
            arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        rel = ruta.relative_to(RAIZ).as_posix()
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.FunctionDef | ast.AsyncFunctionDef) and nodo.name.startswith(
                "test"
            ):
                salida.append(
                    (f"{rel}::{nodo.name}", f"{nodo.name}\n{ast.get_docstring(nodo) or ''}")
                )
    return salida


def leer_features() -> dict[str, list[str]]:
    por_id: dict[str, list[str]] = defaultdict(list)
    for ruta in (
        sorted((RAIZ / "auditoria" / "features").glob("*.feature"))
        if (RAIZ / "auditoria" / "features").exists()
        else []
    ):
        for etiqueta in re.findall(r"@([A-Z]+-?\d+)", ruta.read_text(encoding="utf-8")):
            por_id[etiqueta].append(ruta.name)
    return por_id


def leer_evidencia() -> dict[str, str]:
    """{ruta: texto} de los documentos de evidencia y de las salidas de la auditoria."""
    textos: dict[str, str] = {}
    docs = (
        *sorted((RAIZ / "docs" / "evidencia").glob("*.md")),
        *sorted((RAIZ / "docs" / "spikes").glob("*.md")),
    )
    for ruta in docs:
        textos[ruta.relative_to(RAIZ).as_posix()] = ruta.read_text(encoding="utf-8")
    for ruta in sorted((RAIZ / "auditoria" / "evidencia").rglob("salida.txt")):
        textos[ruta.parent.relative_to(RAIZ).as_posix()] = ruta.read_text(
            encoding="utf-8", errors="replace"
        )
    return textos


def leer_plan_t() -> dict[str, tuple[str, str, str]]:
    """T1..T21 de la tabla §3.1 del plan: (control, prueba declarada, accion del plan)."""
    declarado: dict[str, tuple[str, str, str]] = {}
    for linea in (RAIZ / "docs" / "PLAN_AUDITORIA.md").read_text(encoding="utf-8").splitlines():
        celdas = [c.strip() for c in linea.strip().strip("|").split("|")]
        if len(celdas) == 8 and re.fullmatch(r"T\d+", celdas[0]):
            declarado[celdas[0]] = (celdas[4], celdas[5], celdas[7])
    return declarado


def construir() -> list[dict[str, str]]:
    items, pruebas, features, evid = leer_srs(), leer_pruebas(), leer_features(), leer_evidencia()
    plan_t = leer_plan_t()
    filas = []
    for id_, (titulo, prior) in sorted(
        items.items(), key=lambda kv: (_tipo(kv[0]), int(re.sub(r"\D", "", kv[0])))
    ):
        patron = _regex(id_)
        citadas = [nombre for nombre, texto in pruebas if patron.search(texto)]
        etiquetas = [f for et, fs in features.items() if patron.fullmatch(et) for f in fs]
        docs = sorted(ruta for ruta, texto in evid.items() if patron.search(texto))
        control, declarada, accion = plan_t.get(id_, ("", "", ""))
        filas.append(
            {
                "id": id_,
                "tipo": _tipo(id_),
                "prioridad": prior,
                "titulo": titulo,
                "n_pruebas": str(len(citadas)),
                "pruebas": ";".join(citadas[:6]) + (";…" if len(citadas) > 6 else ""),
                "escenarios_gherkin": ";".join(sorted(set(etiquetas))),
                "evidencia": ";".join(docs[:6]) + (";…" if len(docs) > 6 else ""),
                "control_declarado": control,
                "prueba_declarada_en_plan": declarada,
                "accion_del_plan": accion,
                "estado": "prueba-nombrada"
                if citadas or etiquetas
                else "solo-documento"
                if docs
                else "declarada-sin-verificar"
                if declarada
                else "sin-prueba-nombrada",
            }
        )
    return filas


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]  # consola de Windows
    filas = construir()
    if "--resumen" not in sys.argv:
        with SALIDA.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(filas[0]), lineterminator="\n")
            w.writeheader()
            w.writerows(filas)
    total: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for fila in filas:
        total[fila["tipo"]][0] += 1
        total[fila["tipo"]][1] += fila["estado"] == "prueba-nombrada"
    print("tipo   total  con prueba nombrada")
    for tipo in (*TIPOS, "T", "N"):
        t, c = total[tipo]
        print(f"{tipo:<6} {t:>5}  {c:>5}")
    por_estado: dict[str, list[str]] = defaultdict(list)
    for fila in filas:
        por_estado[fila["estado"]].append(fila["id"])
    for estado in (
        "prueba-nombrada",
        "solo-documento",
        "declarada-sin-verificar",
        "sin-prueba-nombrada",
    ):
        ids = por_estado[estado]
        lista = "(ver el CSV)" if estado == "prueba-nombrada" else " ".join(ids)
        print(f"{estado} ({len(ids)}): {lista}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
