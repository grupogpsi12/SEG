"""Marca ítems de `auditoria/estado-auditoria.md` desde un JSON de {ID: texto}.

    python auditoria/scripts/actualizar-estado.py <archivo.json>

Reemplaza la última celda (Estado) de cada fila cuyo ID figure en el JSON. El texto debe empezar con ✔, ◐ u ○.
"""

import json
import re
import sys
from pathlib import Path

ESTADO = Path(__file__).resolve().parents[1] / "estado-auditoria.md"


def main(origen: str) -> int:
    nuevos: dict[str, str] = json.loads(Path(origen).read_text(encoding="utf-8"))
    pendientes = set(nuevos)
    salida = []
    for linea in ESTADO.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\| (F\d-[\w…]+) \|", linea)
        if m and m.group(1) in nuevos:
            linea = linea.rstrip().rstrip("|").rsplit("|", 1)[0] + f"| {nuevos[m.group(1)]} |"
            pendientes.discard(m.group(1))
        salida.append(linea)
    ESTADO.write_text("\n".join(salida) + "\n", encoding="utf-8", newline="\n")
    if pendientes:
        print("no se encontraron:", sorted(pendientes))
        return 1
    print(f"{len(nuevos)} filas actualizadas")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
