"""Item 5.5: `infra/reporteria/clasificar.lua` ejecutado por el Fluent Bit real (revisión 24/10/2026).

ModSecurity escribe en su log el valor que disparó la regla (`found within ARGS:motivo: …`). Con la
reportería, esa línea quedaría 30 días en Loki: el filtro tapa los campos restringidos y las
credenciales antes de enviarla (invariante 5, RS-09). Necesita Docker; sin él se omite (S-28).
"""

import json
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import pytest
import yaml

RAIZ = Path(__file__).resolve().parents[2]
IMAGEN = yaml.safe_load((RAIZ / "infra" / "compose.reporteria.yaml").read_text(encoding="utf-8"))[
    "services"
]["fluent-bit"]["image"]


def _docker_disponible() -> bool:
    if shutil.which("docker") is None:
        return False
    return subprocess.run(["docker", "info"], capture_output=True, check=False).returncode == 0


SIN_DOCKER = not _docker_disponible()


def clasificar(linea: str) -> dict[str, str]:
    """Pasa una línea por el filtro Lua dentro del contenedor de Fluent Bit y devuelve el registro.

    Fluent Bit no termina solo: se arranca en segundo plano, se espera el primer vaciado y se borra.
    """
    registro = json.dumps({"log": linea, "container_name": "/jml-bunkerweb-1"})
    nombre = f"jml-prueba-lua-{uuid.uuid4().hex[:8]}"
    subprocess.run(
        [
            "docker", "run", "-d", "--name", nombre,
            "-v", f"{RAIZ / 'infra' / 'reporteria' / 'clasificar.lua'}:/f/clasificar.lua:ro",
            IMAGEN,
            "/fluent-bit/bin/fluent-bit", "-q",
            "-i", "dummy", "-p", f"dummy={registro}", "-p", "samples=1", "-t", "docker.prueba",
            "-F", "lua", "-p", "script=/f/clasificar.lua", "-p", "call=clasificar", "-m", "*",
            "-o", "stdout", "-p", "format=json_lines", "-m", "*",
        ],
        capture_output=True, check=True, timeout=120,
    )  # fmt: skip
    try:
        for _ in range(40):
            salida = subprocess.run(
                ["docker", "logs", nombre], capture_output=True, text=True, check=False
            )
            lineas = [x for x in salida.stdout.splitlines() if x.startswith("{")]
            if lineas:
                datos: dict[str, str] = json.loads(lineas[0])
                return datos
            time.sleep(0.5)
        raise AssertionError(salida.stdout + salida.stderr)
    finally:
        subprocess.run(["docker", "rm", "-f", nombre], capture_output=True, check=False)


MODSEC = (
    "2026/10/24 19:20:01 [error] 3#3: *9 [client 10.20.40.1] ModSecurity: Access denied with code 403"
    " (phase 2). Matched \"Operator `DetectSQLi' with parameter `' against variable `{var}'"
    ' (Value: `{valor}\' ) [file "/crs/rules/REQUEST-942-APPLICATION-ATTACK-SQLI.conf"]'
    ' [line "46"] [id "942100"] [msg "SQL Injection Attack Detected via libinjection"]'
    ' [data "Matched Data: s&sos found within {var}: {valor}"] [severity "2"]'
    ' [hostname "app.localhost"] [uri "/ingreso"] [unique_id "17928"]'
)


@pytest.mark.skipif(SIN_DOCKER, reason="S-28: sin Docker no se puede correr Fluent Bit")
@pytest.mark.parametrize(
    "campo", ["contrasena", "motivo", "descripcion", "codigo", "csrfmiddlewaretoken"]
)
def test_un_campo_sensible_que_dispara_el_crs_no_llega_a_loki(campo: str) -> None:
    centinela = "CENTINELA9f3a' OR '1'='1"
    r = clasificar(MODSEC.format(var=f"ARGS:{campo}", valor=centinela))
    assert r["tipo"] == "waf"
    assert "CENTINELA9f3a" not in r["log"]
    assert f"ARGS:{campo}" in r["log"]
    assert "942100" in r["log"]


@pytest.mark.skipif(SIN_DOCKER, reason="S-28: sin Docker no se puede correr Fluent Bit")
def test_un_campo_comun_conserva_el_ataque_para_investigarlo() -> None:
    r = clasificar(MODSEC.format(var="ARGS:q", valor="1 UNION SELECT password"))
    assert r["tipo"] == "waf"
    assert "UNION SELECT" in r["log"]


@pytest.mark.skipif(SIN_DOCKER, reason="S-28: sin Docker no se puede correr Fluent Bit")
def test_clasifica_acceso_proteccion_y_sistema() -> None:
    acceso = 'app.localhost 10.20.40.1 - 4f2a - [24/Oct/2026:19:20:01 +0000] "GET /salud HTTP/1.1" 200 15'
    assert clasificar(acceso)["tipo"] == "acceso"
    assert clasificar("[BADBEHAVIOR] IP 10.20.40.1 is banned for 3600s")["tipo"] == "proteccion"
    assert clasificar("[SCHEDULER] Reloading nginx")["tipo"] == "sistema"


REAL_VALUE = (
    "2026/10/24 19:18:01 [warn] 404#404: *465 ModSecurity: Warning. Matched \"Operator `Rx' with"
    " parameter `(?i)union.*?select.*?from' against variable `ARGS:{campo}' (Value: `{valor}' )"
    ' [file "/usr/share/bunkerweb/core/modsecurity/files/coreruleset-v4/rules/'
    'REQUEST-942-APPLICATION-ATTACK-SQLI.conf"] [line "334"] [id "942270"] [rev ""]'
    ' [msg "Looking for basic sql injection."] [data "Matched Data: UNION SELECT password FROM'
    ' found within ARGS:{campo}: {valor}"] [severity "2"] [hostname "app.localhost"]'
    ' [uri "/solicitudes/nueva/RET"] [unique_id "1792869"], client: 10.20.30.1'
)


@pytest.mark.skipif(SIN_DOCKER, reason="S-28: sin Docker no se puede correr Fluent Bit")
def test_la_forma_value_de_modsecurity_tambien_se_tapa() -> None:
    """Formato real de BunkerWeb 1.6.15 con CRS 4: el valor sale dos veces en la misma línea."""
    r = clasificar(
        REAL_VALUE.format(campo="motivo", valor="MOTIVO7c2e UNION SELECT password FROM users")
    )
    assert "MOTIVO7c2e" not in r["log"]
    assert "ARGS:motivo" in r["log"]
    assert "942270" in r["log"]
    comun = clasificar(REAL_VALUE.format(campo="q", valor="x UNION SELECT a FROM b"))
    assert comun["log"].count("x UNION SELECT a FROM b") == 2
