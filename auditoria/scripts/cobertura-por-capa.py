"""Cobertura de RAMAS por capa y por módulo de seguridad, desde el `.coverage` del directorio actual.

    cd <repositorio o worktree> && python auditoria/scripts/cobertura-por-capa.py [--json salida.json]

Plan §11: dominio ≥ 95 %, aplicación ≥ 90 %, módulos de seguridad ≥ 95 %. Muestra tres números por
grupo: ramas cubiertas/total, líneas cubiertas/total y el porcentaje combinado que reporta coverage.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

GRUPOS = {
    "dominio": ["src/jml/dominio/*"],
    "aplicacion": ["src/jml/aplicacion/*"],
    "adaptadores": ["src/jml/adaptadores/*"],
    "TOTAL": ["src/*"],
    # Módulos que sostienen un control de seguridad (plan §11, fila 3)
    "seguridad:ingreso": [
        "src/jml/aplicacion/casos/ingreso.py",
        "src/jml/adaptadores/entrada/web/ingreso.py",
        "src/jml/adaptadores/salida/identidad/supabase.py",
    ],
    "seguridad:permisos": ["src/jml/dominio/permisos.py", "src/jml/dominio/usuarios.py"],
    "seguridad:auditoria": [
        "src/jml/dominio/auditoria.py",
        "src/jml/aplicacion/casos/auditoria.py",
    ],
    "seguridad:soportes": ["src/jml/dominio/soporte.py", "src/jml/adaptadores/salida/soportes.py"],
    "seguridad:filtro-de-logs": ["src/jml/adaptadores/registro.py"],
    "seguridad:csv-y-vistas-tecnicas": ["src/jml/adaptadores/entrada/web/tecnicos.py"],
    "seguridad:middleware": ["src/jml/adaptadores/entrada/web/middleware.py"],
}
SEGURIDAD = [g for g in GRUPOS if g.startswith("seguridad:")]


def medir(patrones: list[str]) -> dict[str, float]:
    with tempfile.TemporaryDirectory() as tmp:
        salida = Path(tmp) / "c.json"
        cmd = [sys.executable, "-m", "coverage", "json", "-q", "-o", str(salida)]
        cmd += ["--include=" + ",".join(patrones)]
        r = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if r.returncode != 0:
            raise SystemExit(
                f"coverage json falló para {patrones}: {(r.stdout + r.stderr).strip()}"
            )
        t = json.loads(salida.read_text(encoding="utf-8"))["totals"]
    ramas, cubiertas = t["num_branches"], t["covered_branches"]
    return {
        "ramas_total": ramas,
        "ramas_cubiertas": cubiertas,
        "ramas_pct": round(100 * cubiertas / ramas, 2) if ramas else 100.0,
        "lineas_total": t["num_statements"],
        "lineas_cubiertas": t["covered_lines"],
        "combinado_pct": round(t["percent_covered"], 2),
    }


def main() -> int:
    resultado = {g: medir(p) for g, p in GRUPOS.items()}
    print(f"{'grupo':<34}{'ramas':>14}{'ramas %':>9}{'líneas':>14}{'comb. %':>9}")
    for g, m in resultado.items():
        ramas = f"{m['ramas_cubiertas']}/{m['ramas_total']}"
        lineas = f"{m['lineas_cubiertas']}/{m['lineas_total']}"
        print(f"{g:<34}{ramas:>14}{m['ramas_pct']:>9}{lineas:>14}{m['combinado_pct']:>9}")
    if "--json" in sys.argv:
        Path(sys.argv[sys.argv.index("--json") + 1]).write_text(
            json.dumps(resultado, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    metas = {"dominio": 95.0, "aplicacion": 90.0} | dict.fromkeys(SEGURIDAD, 95.0)
    bajo = [g for g, meta in metas.items() if resultado[g]["combinado_pct"] < meta]
    print("\nPor debajo de la meta:", ", ".join(bajo) if bajo else "ninguno")
    return 0


if __name__ == "__main__":
    sys.exit(main())
