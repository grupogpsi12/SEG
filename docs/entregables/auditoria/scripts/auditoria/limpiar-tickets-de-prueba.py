"""Purga de GLPI (instancia DESECHABLE del laboratorio) los tickets que dejaron las corridas de la auditoria.

    docker exec -i jml-worker-1 python - [DESDE] < auditoria/scripts/limpiar-tickets-de-prueba.py

Por que: tras restaurar la base de la aplicacion, los consecutivos SOL-2026-nnnnnn se repiten, pero GLPI conserva los tickets de la
corrida anterior con el mismo `externalid`. Una prueba que espera «tickets de la solicitud X» los encuentra viejos y pasa sin que la
aplicacion cree nada (B-37). Se borran los tickets cuya solicitud es >= DESDE (por defecto 22: las 21 primeras son del conjunto base).
Solo usa la cuenta de servicio de GLPI; no imprime tokens.
"""

import re
import sys
from pathlib import Path

import httpx

BASE = "http://glpi/apirest.php"
DESDE = int(sys.argv[1]) if len(sys.argv) > 1 else 22


def main() -> None:
    app = Path("/run/secrets/glpi_app_token").read_text(encoding="utf-8").strip()
    usuario = Path("/run/secrets/glpi_user_token").read_text(encoding="utf-8").strip()
    with httpx.Client(timeout=30) as c:
        s = c.get(
            f"{BASE}/initSession",
            headers={"App-Token": app, "Authorization": f"user_token {usuario}"},
        )
        s.raise_for_status()
        h = {"App-Token": app, "Session-Token": s.json()["session_token"]}
        borrados = 0
        while True:
            pagina = c.get(
                f"{BASE}/Ticket",
                headers=h,
                params={"searchText[externalid]": "SOL-2026-", "range": "0-199"},
            ).json()
            if not isinstance(pagina, list):
                break
            sobrantes = []
            for t in pagina:
                m = re.match(r"SOL-2026-(\d{6})", str(t.get("externalid", "")))
                if m and int(m.group(1)) >= DESDE:
                    sobrantes.append(t["id"])
            if not sobrantes:
                break
            for ticket_id in sobrantes:
                c.delete(
                    f"{BASE}/Ticket/{ticket_id}", headers=h, params={"force_purge": "true"}
                ).raise_for_status()
                borrados += 1
        print(f"tickets purgados (solicitud >= SOL-2026-{DESDE:06d}): {borrados}")
        c.get(f"{BASE}/killSession", headers=h)


main()
