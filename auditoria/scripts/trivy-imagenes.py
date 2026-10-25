"""F7-03: Trivy de las cinco imágenes del proyecto, priorizado por explotabilidad real (CISA KEV y EPSS).

    python auditoria/scripts/trivy-imagenes.py

Imágenes: la de la aplicación y las cuatro de terceros que ejecutan servicios del proyecto. Trivy por
digest (herramientas.lock). KEV: catálogo de CISA de vulnerabilidades explotadas activamente. EPSS: probabilidad
de explotación en 30 días (api.first.org). Una vulnerabilidad CRITICAL o HIGH sin parche y sin KEV con EPSS bajo
es riesgo aceptable con fecha de revisión; una en KEV es urgente aunque su CVSS sea medio.
"""

import json
import subprocess
import sys
import urllib.request
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
TRIVY = (
    "aquasec/trivy:0.67.2@sha256:e2b22eac59c02003d8749f5b8d9bd073b62e30fefaef5b7c8371204e0a4b0c08"
)
IMAGENES = {
    "aplicacion": "jml-app:local",
    "bunkerweb": "bunkerity/bunkerweb:1.6.15",
    "planificador": "bunkerity/bunkerweb-scheduler:1.6.15",
    "glpi": "glpi/glpi:11.0.11",
    "mariadb": "mariadb:11.4",
}
KEV = RAIZ / ".contrato-tmp" / "kev.json"
SALIDA = RAIZ / ".contrato-tmp" / "trivy"
EPSS_UMBRAL = 0.10  # 10 % de probabilidad de explotación en 30 días


def escanear(nombre: str, imagen: str) -> list[dict[str, str]]:
    SALIDA.mkdir(parents=True, exist_ok=True)
    destino = SALIDA / f"{nombre}.json"
    subprocess.run(
        ["docker", "run", "--rm", "-v", "jml-trivy-cache:/root/.cache",
         "-v", "/var/run/docker.sock:/var/run/docker.sock", "-v", f"{SALIDA}:/out", TRIVY,
         "image", "--skip-version-check", "--severity", "HIGH,CRITICAL", "--scanners", "vuln",
         "-f", "json", "-o", f"/out/{nombre}.json", imagen],
        check=True, capture_output=True,
    )  # fmt: skip
    datos = json.loads(destino.read_text(encoding="utf-8"))
    hallazgos = []
    for r in datos.get("Results", []):
        for v in r.get("Vulnerabilities") or []:
            hallazgos.append(
                {
                    "cve": v["VulnerabilityID"], "paquete": v["PkgName"], "severidad": v["Severity"],
                    "estado": v.get("Status", ""), "corregida_en": v.get("FixedVersion", ""),
                }
            )  # fmt: skip
    return hallazgos


def epss(cves: list[str]) -> dict[str, float]:
    resultado: dict[str, float] = {}
    for i in range(0, len(cves), 80):
        tramo = ",".join(cves[i : i + 80])
        with urllib.request.urlopen(
            f"https://api.first.org/data/v1/epss?cve={tramo}", timeout=30
        ) as r:
            for fila in json.load(r)["data"]:
                resultado[fila["cve"]] = float(fila["epss"])
    return resultado


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    kev = {v["cveID"] for v in json.loads(KEV.read_text(encoding="utf-8"))["vulnerabilities"]}
    todos = {n: escanear(n, i) for n, i in IMAGENES.items()}
    cves = sorted({h["cve"] for hs in todos.values() for h in hs})
    puntajes = epss(cves) if cves else {}
    print(
        f"KEV: {len(kev)} CVE explotadas activamente en el catálogo de CISA · CVE distintas en las imágenes: {len(cves)}\n"
    )
    urgente = False
    for nombre, hallazgos in todos.items():
        sev = Counter(h["severidad"] for h in hallazgos)
        con_parche = [h for h in hallazgos if h["corregida_en"]]
        en_kev = [h for h in hallazgos if h["cve"] in kev]
        altas = [h for h in hallazgos if puntajes.get(h["cve"], 0) >= EPSS_UMBRAL]
        print(
            f"{nombre:13} {IMAGENES[nombre]:42} CRITICAL {sev['CRITICAL']:3} · HIGH {sev['HIGH']:3} · con parche {len(con_parche):3} · en KEV {len(en_kev)} · EPSS ≥ {EPSS_UMBRAL:.0%}: {len(altas)}"
        )
        for h in sorted(
            en_kev + [a for a in altas if a not in en_kev], key=lambda h: -puntajes.get(h["cve"], 0)
        ):
            marca = "KEV" if h["cve"] in kev else "EPSS"
            print(
                f"     [{marca}] {h['cve']} {h['paquete']} {h['severidad']} EPSS={puntajes.get(h['cve'], 0):.3f} parche={h['corregida_en'] or 'no'}"
            )
        for h in con_parche:
            if h["severidad"] == "CRITICAL":
                print(f"     [CRITICAL con parche] {h['cve']} {h['paquete']} → {h['corregida_en']}")
        urgente |= bool(en_kev)
    print(
        "\nVEREDICTO:",
        "HAY VULNERABILIDADES EN KEV: urgentes"
        if urgente
        else "ninguna vulnerabilidad en KEV; lo demás se prioriza por EPSS y parche disponible",
    )
    return 1 if urgente else 0


if __name__ == "__main__":
    sys.exit(main())
