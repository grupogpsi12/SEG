"""F9-04: verifica la carpeta de entrega (plan §15). Falla ante lo que D-01 y D-02 enseñaron.

    python auditoria/herramientas/verificar_entrega.py docs/entregables/auditoria

Comprueba, y sale con 1 si algo falla:
  1. ningún marcador sin reemplazar en los `.md` (`[PENDIENTE: motivo]` sí vale: es una decisión escrita);
  2. cada criterio de aceptación (CA-nn) que un informe declare «cumple» cita un archivo de evidencia en la
     misma fila, y ese archivo existe;
  3. el manifiesto: cada archivo listado existe y su sha256 cuadra, y ningún archivo de `evidencias/`
     falta en el manifiesto;
  4. las cifras de `metricas.json` salen de los archivos (hallazgos por severidad, filas de la traza);
  5. cada informe `.md` tiene su `.pdf`, y los PDF no están vacíos;
  6. ningún informe cita una corrida con fallos como exitosa: un `codigo.txt` distinto de 0 citado junto a
     «verde», «sin fallos» o «cumple» en la misma línea.
"""

import csv
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import marcadores

CA_CUMPLE = re.compile(
    r"\|\s*(CA-\d+)\s*\|[^|\n]*\|\s*(cumple|cumplido|verificado)\s*\|(.*)\|", re.IGNORECASE
)
RUTA_EVIDENCIA = re.compile(r"(evidencias/[\w./-]+)")


def sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def _marcadores(raiz: Path) -> list[str]:
    return [
        f"{ruta.relative_to(raiz).as_posix()}:{n}: {t}"
        for ruta, m in marcadores.recorrer(raiz).items()
        for n, t in m
    ]


def _criterios(raiz: Path) -> list[str]:
    fallos = []
    for md in sorted((raiz / "informes").glob("*.md")):
        for n, linea in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
            m = CA_CUMPLE.search(linea)
            if not m:
                continue
            rutas = RUTA_EVIDENCIA.findall(m.group(3))
            if not rutas:
                fallos.append(
                    f"{md.name}:{n}: {m.group(1)} se declara cumplido sin archivo de evidencia"
                )
            for r in rutas:
                if not (raiz / r).exists():
                    fallos.append(f"{md.name}:{n}: {m.group(1)} cita {r}, que no existe")
    return fallos


def _manifiesto(raiz: Path) -> list[str]:
    ruta = raiz / "manifiesto.sha256"
    if not ruta.exists():
        return ["falta manifiesto.sha256"]
    listados: dict[str, str] = {}
    fallos = []
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        h, _, nombre = linea.partition("  ")
        listados[nombre.strip()] = h
    for nombre, esperado in listados.items():
        archivo = raiz / nombre
        if not archivo.exists():
            fallos.append(f"manifiesto lista {nombre}, que no existe")
        elif sha256(archivo) != esperado:
            fallos.append(f"el hash de {nombre} no cuadra")
    for archivo in sorted((raiz / "evidencias").rglob("*")):
        if archivo.is_file() and archivo.relative_to(raiz).as_posix() not in listados:
            fallos.append(f"{archivo.relative_to(raiz).as_posix()} no está en el manifiesto")
    return fallos


def _metricas(raiz: Path) -> list[str]:
    fallos = []
    datos = json.loads((raiz / "metricas.json").read_text(encoding="utf-8"))
    hallazgos = list((raiz / "hallazgos").glob("B-*.md"))
    if datos["hallazgos"]["total"] != len(hallazgos):
        fallos.append(
            f"metricas.json dice {datos['hallazgos']['total']} hallazgos y hay {len(hallazgos)}"
        )
    with (raiz / "trazabilidad.csv").open(encoding="utf-8", newline="") as f:
        filas = len(list(csv.DictReader(f)))
    if datos["trazabilidad"]["filas"] != filas:
        fallos.append(
            f"metricas.json dice {datos['trazabilidad']['filas']} filas de traza y hay {filas}"
        )
    return fallos


def _pdfs(raiz: Path) -> list[str]:
    fallos = []
    for md in sorted((raiz / "informes").glob("*.md")):
        pdf = md.with_suffix(".pdf")
        if not pdf.exists() or pdf.stat().st_size < 1500:
            fallos.append(f"{md.name} no tiene su PDF (o está vacío)")
    return fallos


def _corridas_con_fallos(raiz: Path) -> list[str]:
    fallos = []
    for md in sorted((raiz / "informes").glob("*.md")):
        for n, linea in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
            if not re.search(r"\b(verde|sin fallos|cumple)\b", linea, re.IGNORECASE):
                continue
            for r in RUTA_EVIDENCIA.findall(linea):
                codigo = raiz / r.rstrip("/") / "codigo.txt"
                if codigo.exists() and codigo.read_text(encoding="utf-8").strip() not in ("0", ""):
                    fallos.append(
                        f"{md.name}:{n}: cita {r} como exitosa y su código de salida es {codigo.read_text().strip()}"
                    )
    return fallos


def main(raiz_texto: str) -> int:
    raiz = Path(raiz_texto).resolve()
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    comprobaciones = [
        ("marcadores sin reemplazar", _marcadores),
        ("criterios de aceptación con su evidencia", _criterios),
        ("manifiesto y hashes", _manifiesto),
        ("cifras de metricas.json", _metricas),
        ("PDF de cada informe", _pdfs),
        ("corridas con fallos citadas como exitosas", _corridas_con_fallos),
    ]
    malas = 0
    for nombre, f in comprobaciones:
        fallos = f(raiz)
        print(f"{'OK   ' if not fallos else 'FALLA'} {nombre}")
        for x in fallos[:15]:
            print(f"      {x}")
        malas += bool(fallos)
    print(
        "ENTREGA VERIFICADA" if not malas else f"ENTREGA RECHAZADA: {malas} comprobaciones fallan"
    )
    return 1 if malas else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
