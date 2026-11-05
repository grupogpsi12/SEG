"""Anexo A (Tablas I a XVIII): compara cada hoja del Excel con su fuente en `docs/` y dice, fila por fila, si coincide.

    python auditoria/scripts/anexo-a-tablas-vs-srs.py            # imprime y escribe auditoria/evidencia/funcionales/anexo-a-tablas/

Fuente de las hojas: `auditoria/referencias/AnexoA-tablas.json` (volcado de «AnexoA. Tablas.xlsx», con su SHA-256 en
`AnexoA-tablas.sha256`). Fuente de la verdad: `docs/SRS.md` (v2.4) y `docs/decisiones.md`. El resultado es de TEXTO:
que una fila coincida con el SRS no prueba que el sistema la cumpla; eso lo comprueban las pruebas del informe.
"""

import csv
import json
import re
import sys
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
HOJAS = json.loads((RAIZ / "auditoria/referencias/AnexoA-tablas.json").read_text(encoding="utf-8"))
SRS = (RAIZ / "docs/SRS.md").read_text(encoding="utf-8")
ADR = (RAIZ / "docs/decisiones.md").read_text(encoding="utf-8")


def norm(t: str) -> str:
    t = unicodedata.normalize("NFKC", t)
    t = re.sub(r"[`*_]", "", t)
    t = t.replace("\\|", "|").replace("«", '"').replace("»", '"').replace("’", "'")
    t = re.sub(r"\s+", " ", t).strip().lower()
    return t.rstrip(".")


def tablas_md(texto: str) -> list[list[list[str]]]:
    """Todas las tablas de Markdown: lista de filas (sin la fila de guiones)."""
    tablas, actual = [], []
    for linea in [*texto.splitlines(), ""]:
        if linea.startswith("|"):
            celdas = [c.strip() for c in re.split(r"(?<!\\)\|", linea.strip())[1:-1]]
            if not all(re.fullmatch(r":?-{2,}:?", c) for c in celdas):
                actual.append(celdas)
        elif actual:
            tablas.append(actual)
            actual = []
    return tablas


TABLAS_SRS = tablas_md(SRS)
TABLAS_ADR = tablas_md(ADR)


def tabla_srs(
    encabezado: str, ocurrencia: int = 0, fuente: list[list[list[str]]] | None = None
) -> list[list[str]]:
    candidatas = [t for t in (fuente or TABLAS_SRS) if norm(t[0][0]) == norm(encabezado)]
    return candidatas[ocurrencia]


def filas_xlsx(hoja: str, encabezado_en: int = 1) -> list[list[str]]:
    return [f for f in HOJAS[hoja][encabezado_en + 1 :] if any(c.strip() for c in f)]


RESULTADOS: list[dict[str, str]] = []


def comparar(
    hoja: str,
    tabla: str,
    filas: list[list[str]],
    fuente: dict[str, list[str]],
    clave=lambda k: norm(k),
    nombre_fuente="docs/SRS.md",
) -> None:  # type: ignore[no-untyped-def]
    vistas = set()
    for f in filas:
        k = clave(f[0])
        vistas.add(k)
        origen = fuente.get(k)
        if origen is None:
            RESULTADOS.append(
                dict(
                    tabla=tabla,
                    fila=f[0],
                    estado="NO ESTÁ EN LA FUENTE",
                    detalle=f"{nombre_fuente} no tiene la fila «{f[0]}»",
                )
            )
            continue
        difieren = []
        for i, celda in enumerate(f[1:], start=1):
            if i < len(origen) and norm(celda) != norm(origen[i]):
                difieren.append((i, celda, origen[i]))
        if difieren:
            det = " || ".join(
                f"col {i}: Excel «{a[:160]}» ≠ fuente «{b[:160]}»" for i, a, b in difieren
            )
            RESULTADOS.append(dict(tabla=tabla, fila=f[0], estado="DIFIERE", detalle=det))
        else:
            RESULTADOS.append(dict(tabla=tabla, fila=f[0], estado="COINCIDE", detalle=""))
    for k, origen in fuente.items():
        if k not in vistas:
            RESULTADOS.append(
                dict(
                    tabla=tabla,
                    fila=origen[0],
                    estado="FALTA EN EL EXCEL",
                    detalle=f"{nombre_fuente} la tiene y el Excel no",
                )
            )


def por_clave(t: list[list[str]], clave=lambda k: norm(k)) -> dict[str, list[str]]:  # type: ignore[no-untyped-def]
    return {clave(f[0]): f for f in t[1:]}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    # I
    comparar(
        "TablaI Matriz funcion",
        "I",
        filas_xlsx("TablaI Matriz funcion"),
        {norm(f[0]).split(".")[0]: f for f in tabla_srs("Función")[1:]},
        clave=lambda k: norm(k).split(".")[0],
    )
    # II (ADR): el Excel dice «ADR - 01», decisiones.md dice «001»
    adr = {str(int(f[0])): f for f in tabla_srs("ADR", fuente=TABLAS_ADR)[1:]}
    comparar(
        "TablaII ADR",
        "II",
        [[str(int(re.sub(r"\D", "", f[0]))), f[1], f[2]] for f in filas_xlsx("TablaII ADR")],
        adr,
        clave=lambda k: k,
        nombre_fuente="docs/decisiones.md",
    )
    # IV a XIV
    mapa = {
        "TablaIV Users-Roles": ("IV", "Rol", 0),
        "TablaV Eventos SLAs": ("V", "Código", 0),
        "TablaVI Estados Solicitud": ("VI", "Estado", 0),
        "TablaVII Clases de Tickets": ("VII", "Clase", 0),
        "TablaVIII Acciones por Cola": ("VIII", "Evento", 0),
        "TablaIX Deshabilitación": ("IX", "Aspecto", 0),
        "TablaX Plantillas Solución ": ("X", "Cola", 0),
        "TablaXI Estados Cuentas": ("XI", "Ticket del sistema correspondiente", 0),
        "TablaXII Campos Eventos": ("XII", "Tipo", 0),
        "TablaXIII Perfiles Acceso": ("XIII", "Departamento", 0),
        "TablaXIV Recursos Compartidos": ("XIV", "Departamento", 1),
    }
    for hoja, (nombre, enc, oc) in mapa.items():
        if (
            nombre == "XIV"
        ):  # un departamento tiene varios recursos: la fila se identifica por departamento + ruta
            fuente = {norm(f[0]) + "|" + norm(f[1]): f for f in tabla_srs(enc, oc)[1:]}
            filas = [[f[0] + "|" + f[1], *f[1:]] for f in filas_xlsx(hoja)]
            fuente = {k: [k, *v[1:]] for k, v in fuente.items()}
            comparar(
                hoja, nombre, filas, fuente, clave=lambda k: k.lower().replace("`", "").strip()
            )
            continue
        comparar(
            hoja,
            nombre,
            filas_xlsx(hoja),
            por_clave(tabla_srs(enc, oc)),
            clave=(lambda k: norm(k))
            if nombre != "XI"
            else (lambda k: norm(k).replace("ticket del sistema correspondiente", "")),
        )
    # XV a XVII: los RF están repartidos por secciones del SRS; se busca por ID
    todos_rf = {}
    for t in TABLAS_SRS:
        if t and norm(t[0][0]) == "id" and len(t[0]) == 3:
            for f in t[1:]:
                todos_rf[norm(f[0])] = f
    for hoja, nombre in (
        ("TablaXV RF Autenticación", "XV"),
        ("TablaXVI RF Solicitudes", "XVI"),
        ("TablaXVII RF Tickets", "XVII"),
    ):
        filas = filas_xlsx(hoja)
        comparar(
            hoja,
            nombre,
            filas,
            {norm(f[0]): todos_rf[norm(f[0])] for f in filas if norm(f[0]) in todos_rf},
            clave=norm,
        )
    # XVIII
    ri = {norm(f[0]): f for f in tabla_srs("ID", 0)[1:]} if False else {}
    for t in TABLAS_SRS:
        if t and len(t[0]) == 4 and norm(t[0][1]) == "interfaz":
            ri = {norm(f[0]): f for f in t[1:]}
    comparar("TablaXVIII RI Interfaces", "XVIII", filas_xlsx("TablaXVIII RI Interfaces"), ri)

    destino = RAIZ / "auditoria/evidencia/funcionales/anexo-a-tablas"
    destino.mkdir(parents=True, exist_ok=True)
    with (destino / "comparacion-con-el-srs.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["tabla", "fila", "estado", "detalle"])
        w.writeheader()
        w.writerows(RESULTADOS)
    resumen: dict[str, dict[str, int]] = {}
    for r in RESULTADOS:
        resumen.setdefault(r["tabla"], {}).setdefault(r["estado"], 0)
        resumen[r["tabla"]][r["estado"]] += 1
    for tabla, c in resumen.items():
        print(f"Tabla {tabla:6} " + " · ".join(f"{k}: {v}" for k, v in c.items()))
    print()
    for r in RESULTADOS:
        if r["estado"] != "COINCIDE":
            print(f"[{r['tabla']}] {r['fila']} → {r['estado']}: {r['detalle']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
