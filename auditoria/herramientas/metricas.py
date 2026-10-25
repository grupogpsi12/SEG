"""Actualiza auditoria/metricas.json (paso 9 del loop). Lo derivable se CALCULA; el resto se anota.

    python auditoria/herramientas/metricas.py                      # recalcula hallazgos y trazabilidad
    python auditoria/herramientas/metricas.py --set linea_base.pruebas_unitarias.medido=1602
    python auditoria/herramientas/metricas.py --set defectos_sembrados.detectados=3

Calculado desde los archivos (no se escribe a mano):
  - hallazgos por severidad y por estado: auditoria/hallazgos/B-*.md
  - filas de la traza y reparto por estado: auditoria/trazabilidad.csv
`--set` acepta enteros, decimales, true/false/null o texto.
"""

import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
JSON = RAIZ / "auditoria" / "metricas.json"
SEVERIDADES = {
    "Crítica": "criticos",
    "Alta": "altos",
    "Media": "medios",
    "Baja": "bajos",
    "Informativa": "informativos",
}


def hallazgos() -> dict[str, int]:
    sev: Counter[str] = Counter()
    estados: Counter[str] = Counter()
    for ruta in sorted((RAIZ / "auditoria" / "hallazgos").glob("B-*.md")):
        texto = ruta.read_text(encoding="utf-8")
        m = re.match(r"# B-\d+ · (\w+)", texto)
        e = re.search(r"\*\*Estado:\*\*\s*([^\n]+)", texto)
        if not m or not e:
            raise SystemExit(f"{ruta.name}: no tiene el formato del plan §14 (título y estado)")
        sev[SEVERIDADES.get(m.group(1), m.group(1))] += 1
        estado = e.group(1).strip()
        estados["verificados" if estado.startswith("verificado") else
                "corregidos" if estado.startswith("corregido") else
                "aceptados" if estado.startswith("aceptado") else "abiertos"] += 1  # fmt: skip
    base = {k: sev.get(k, 0) for k in SEVERIDADES.values()}
    return {
        **base,
        "total": sum(sev.values()),
        **{k: estados.get(k, 0) for k in ("abiertos", "verificados", "corregidos", "aceptados")},
    }


def trazabilidad() -> dict[str, object]:
    ruta = RAIZ / "auditoria" / "trazabilidad.csv"
    with ruta.open(encoding="utf-8", newline="") as f:
        filas = list(csv.DictReader(f))
    return {
        "filas": len(filas),
        "por_estado": dict(Counter(f["estado"] for f in filas)),
        "fuente": "auditoria/trazabilidad.csv (trazar.py)",
    }


def _valor(texto: str) -> object:
    if texto in ("null", "None"):
        return None
    if texto in ("true", "false"):
        return texto == "true"
    for tipo in (int, float):
        try:
            return tipo(texto)
        except ValueError:
            pass
    return texto


def _fijar(datos: dict[str, object], ruta: str, valor: object) -> None:
    claves = ruta.split(".")
    nodo = datos
    for c in claves[:-1]:
        nodo = nodo.setdefault(c, {})  # type: ignore[assignment]
    nodo[claves[-1]] = valor


def main() -> int:
    datos = json.loads(JSON.read_text(encoding="utf-8"))
    datos["hallazgos"] = hallazgos()
    datos["trazabilidad"] = trazabilidad()
    argv = sys.argv[1:]
    while argv:
        if argv[0] == "--set" and len(argv) > 1 and "=" in argv[1]:
            ruta, valor = argv[1].split("=", 1)
            _fijar(datos, ruta, _valor(valor))
            argv = argv[2:]
        else:
            raise SystemExit(f"argumento no reconocido: {argv[0]}")
    JSON.write_text(
        json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    print(
        json.dumps(
            {"hallazgos": datos["hallazgos"], "trazabilidad": datos["trazabilidad"]},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
