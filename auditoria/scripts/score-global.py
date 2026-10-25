"""F8-03: puntajes DREAD, score de prioridad por hallazgo y score global (plan §14), desde `auditoria/hallazgos/`.

    python auditoria/scripts/score-global.py            # imprime y escribe auditoria/score-global.md

Score por hallazgo: `DREAD × factor` (exploit público ×1,5; requiere sesión ×0,7; requiere el host o la red interna ×0,5).
Score global: `Σ(críticas×10 + altas×5 + medias×2 + bajas×1) / (controles verificados × 10) × 100`, sobre los hallazgos
ABIERTOS o ACEPTADOS (la exposición que sigue en pie). Los controles verificados salen de `asvs-l2.csv`
(estado «verificado»). Se reporta junto a ese número: un score bajo con pocos controles probados no significa nada.
"""

import csv
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
PESOS = {"Crítica": 10, "Alta": 5, "Media": 2, "Baja": 1}
# Factor de prioridad por hallazgo, con su motivo (ancla del plan §14). Lo no listado vale 1.
FACTORES = {
    "B-01": (0.5, "exige acceso al host"),
    "B-28": (0.5, "exige interponerse en el tramo servidor→Supabase"),
    "B-29": (0.5, "exige la red interna"),
    "B-30": (0.5, "exige la red interna"),
    "B-32": (0.5, "exige un contenedor comprometido en la red interna"),
    "B-25": (0.7, "exige una sesión"),
    "B-26": (0.7, "exige una sesión"),
}


def numero(texto: str) -> float | None:
    m = re.search(r"=\s*(\d+,\d+)", texto) or re.match(r"\s*(\d+,\d+)", texto)
    return float(m.group(1).replace(",", ".")) if m else None


def leer() -> list[dict[str, object]]:
    filas = []
    for ruta in sorted((RAIZ / "auditoria" / "hallazgos").glob("B-*.md")):
        t = ruta.read_text(encoding="utf-8")
        sev = re.match(r"# (B-\d+) · (\w+)", t)
        estado = re.search(r"\*\*Estado:\*\*\s*([^\n]+)", t)
        ini = re.search(r"\*\*DREAD inherente:\*\*\s*(.*?)\s*·\s*\*\*residual:\*\*\s*([^\n]*)", t)
        assert sev, ruta.name
        assert estado, ruta.name
        assert ini, ruta.name
        e = estado.group(1).strip()
        filas.append(
            {
                "id": sev.group(1), "sev": sev.group(2), "estado": e,
                "en_pie": not (e.startswith(("verificado", "corregido"))),
                "inherente": numero(ini.group(1)), "residual": numero(ini.group(2)),
            }
        )  # fmt: skip
    return filas


def controles_verificados() -> int:
    with (RAIZ / "auditoria" / "asvs-l2.csv").open(encoding="utf-8", newline="") as f:
        return sum(1 for r in csv.DictReader(f) if r["estado"] == "verificado")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    h = leer()
    vivos = [x for x in h if x["en_pie"]]
    expo = sum(PESOS.get(str(x["sev"]), 0) for x in vivos)
    ctrl = controles_verificados()
    score = 100 * expo / (ctrl * 10)
    banda = "aceptable" if score <= 20 else "requiere mejoras" if score <= 40 else "deficiente"
    lineas = [
        "# Puntajes DREAD y score global",
        "",
        f"Generado por `auditoria/scripts/score-global.py` desde `auditoria/hallazgos/` ({len(h)} hallazgos). "
        "Un residual solo baja si hay una prueba que se rompe al quitar el control (anclas: `dread-anclas.md`).",
        "",
        "## Hallazgos ordenados por prioridad (DREAD × factor)",
        "",
        "| ID | Severidad | Estado | DREAD inherente | Factor | Prioridad | DREAD residual |",
        "|---|---|---|---|---|---|---|",
    ]
    ordenados = sorted(
        h, key=lambda x: -((x["inherente"] or 0) * FACTORES.get(str(x["id"]), (1, ""))[0])
    )  # type: ignore[operator]
    for x in ordenados:
        f, motivo = FACTORES.get(str(x["id"]), (1.0, ""))
        ini = x["inherente"]
        prioridad = f"{ini * f:.1f}" if isinstance(ini, float) else "—"
        lineas.append(
            f"| {x['id']} | {x['sev']} | {str(x['estado'])[:48]} | {str(ini).replace('.', ',') if ini is not None else 'n/a'} | "
            f"×{f}{' (' + motivo + ')' if motivo else ''} | {prioridad} | {x['residual'] if x['residual'] is not None else 'n/a'} |".replace(
                ".", ","
            )
        )
    lineas += [
        "",
        "## Score global",
        "",
        f"- Hallazgos que siguen en pie (abiertos o aceptados): **{len(vivos)}** "
        f"({', '.join(f'{k}: {sum(1 for x in vivos if x["sev"] == k)}' for k in PESOS)}; "
        f"informativos {sum(1 for x in vivos if x['sev'] == 'Informativa')} no suman).",
        f"- Exposición ponderada: **{expo}**.",
        f"- Controles verificados (ASVS L1/L2 en «verificado»): **{ctrl}**.",
        f"- **Score global = {expo} / ({ctrl} × 10) × 100 = {f'{score:.1f}'.replace('.', ',')}** → {banda} (escala: 0–20 aceptable · 21–40 requiere mejoras · 41–60 deficiente · 61–80 crítica · 81–100 exposición crítica).",
        "",
        "Se reporta junto al número de controles verificados: con 144 probados el score tiene sentido; con 10 no lo tendría.",
    ]
    texto = "\n".join(lineas) + "\n"
    (RAIZ / "auditoria" / "score-global.md").write_text(texto, encoding="utf-8", newline="\n")
    print(texto)
    return 0


if __name__ == "__main__":
    sys.exit(main())
