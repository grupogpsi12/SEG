"""RI-02 (Anexo A): perfil real de la cuenta de servicio de GLPI, leído por la propia cuenta del worker (solo lecturas).

    docker exec -i jml-worker-1 python - < auditoria/scripts/sonda-perfil-glpi.py

Imprime el nombre del perfil y los derechos sobre algunos tipos (R leer · U actualizar · C crear · D borrar · P purgar).
No imprime tokens. Se ejecuta dentro del contenedor del worker porque ahí viven los secretos (`/run/secrets`).
"""

from pathlib import Path

import httpx

BASE = "http://glpi/apirest.php"
DERECHOS = ((1, "R"), (2, "U"), (4, "C"), (8, "D"), (16, "P"))
TIPOS = (
    "ticket", "document", "user", "profile", "config", "itilcategory", "group", "computer", "software",
    "rule_ticket", "sla", "entity", "backup", "logs", "reservation", "knowbase", "problem", "change",
    "queuednotification", "notification",
)  # fmt: skip


def letras(valor: object) -> str:
    try:
        numero = int(str(valor))
    except ValueError:
        return str(valor)
    return "".join(letra for bit, letra in DERECHOS if numero & bit) or "-"


def main() -> None:
    app = Path("/run/secrets/glpi_app_token").read_text(encoding="utf-8").strip()
    usuario = Path("/run/secrets/glpi_user_token").read_text(encoding="utf-8").strip()
    with httpx.Client(timeout=20) as c:
        sesion = c.get(
            f"{BASE}/initSession",
            headers={"App-Token": app, "Authorization": f"user_token {usuario}"},
        )
        sesion.raise_for_status()
        h = {"App-Token": app, "Session-Token": sesion.json()["session_token"]}
        perfil = c.get(f"{BASE}/getActiveProfile", headers=h).json()["active_profile"]
        print(
            "PERFIL ACTIVO:",
            perfil["name"],
            "| interfaz:",
            perfil.get("interface"),
            "| id:",
            perfil["id"],
        )
        print({t: letras(perfil[t]) for t in TIPOS if t in perfil})
        con_derecho = sum(
            1
            for v in perfil.values()
            if isinstance(v, int | str) and str(v).isdigit() and int(v) > 0
        )
        print("TOTAL permisos distintos de cero:", con_derecho, "de", len(perfil))
        disponibles = c.get(f"{BASE}/getMyProfiles", headers=h).json()["myprofiles"]
        print("PERFILES DISPONIBLES PARA LA CUENTA:", [p["name"] for p in disponibles])
        c.get(f"{BASE}/killSession", headers=h)


main()
