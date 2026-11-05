"""Gherkin del borde: corre contra el stack LOCAL de Docker y se omite si no está levantado.

Es la vista trazable de `infra/waf/pruebas.sh` y de `auditoria/scripts/cabeceras-hostiles.sh`.
La parte que necesita escaneo de puertos completo (nmap) y captura de tráfico es F7.
"""

import shutil
import subprocess
import time

import pytest
from pytest_bdd import given, scenarios, then, when

scenarios("features/borde.feature")

HOST = "app.localhost"
BANEADA = "10.20.40.128"  # la IP que ve el WAF para quien entra desde el anfitrión (B-01)


def _docker(*args: str, entrada: str | None = None) -> str:
    if shutil.which("docker") is None:
        pytest.skip("S-37: sin docker en el PATH")
    r = subprocess.run(
        ["docker", *args],
        input=entrada,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=120,
    )
    return r.stdout + r.stderr


def _necesita_stack() -> None:
    if "jml-bunkerweb-1" not in _docker("ps", "--format", "{{.Names}}"):
        pytest.skip("S-37: el stack local no está levantado (docker compose up)")


def _curl(*cabeceras: str) -> int:
    orden = ["curl", "-sk", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "20"]
    orden += ["--resolve", f"{HOST}:443:127.0.0.1"]
    for c in cabeceras:
        orden += ["-H", c]
    orden.append(f"https://{HOST}/")
    r = subprocess.run(
        orden,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=40,
    )
    return int(r.stdout or 0)


def _levantar_baneo() -> None:
    for ip in (BANEADA, "127.0.0.1"):
        _docker(
            "compose",
            "-f",
            "infra/compose.yaml",
            "exec",
            "-T",
            "bw-scheduler",
            "bwcli",
            "unban",
            ip,
        )


@given("que no hay ninguna IP baneada")
def _() -> None:
    _necesita_stack()
    _levantar_baneo()


@when("se listan los puertos publicados por los contenedores del stack", target_fixture="puertos")
def _() -> dict[str, str]:
    _necesita_stack()
    salida = _docker("ps", "--format", "{{.Names}}\t{{.Ports}}")
    return dict(linea.split("\t", 1) for linea in salida.splitlines() if "\t" in linea)


@then("bunkerweb publica solo el 80 y el 443")
def _(puertos: dict[str, str]) -> None:
    tramos = puertos["jml-bunkerweb-1"].split(", ")
    assert {t.split("->")[0].rsplit(":", 1)[-1] for t in tramos} == {"80", "443"}


@then("ningún otro contenedor publica puertos fuera de 127.0.0.1")
def _(puertos: dict[str, str]) -> None:
    """Grafana y fluent-bit (reportería, opcional) publican en el bucle local: B-27."""
    for nombre, tramos in puertos.items():
        if nombre == "jml-bunkerweb-1" or "->" not in tramos:
            continue
        for tramo in tramos.split(", "):
            if "->" in tramo:
                assert tramo.startswith("127.0.0.1:"), (nombre, tramo)


@when(
    'la aplicación pide "http://bunkerweb:5000/instances" sin token y con un token incorrecto',
    target_fixture="codigos",
)
def _() -> list[int]:
    _necesita_stack()
    guion = (
        "import urllib.request as u, urllib.error as e\n"
        "for t in (None, 'incorrecto'):\n"
        "    r = u.Request('http://bunkerweb:5000/instances')\n"
        "    t and r.add_header('Authorization', 'Bearer ' + t)\n"
        "    try:\n"
        "        print(u.urlopen(r, timeout=10).status)\n"
        "    except e.HTTPError as x:\n"
        "        print(x.code)\n"
        "    except Exception:\n"
        "        print(0)\n"
    )
    salida = _docker("exec", "-i", "jml-web-1", "python", "-", entrada=guion)
    return [int(x) for x in salida.split()]


@then("ninguna respuesta es 200")
def _(codigos: list[int]) -> None:
    assert len(codigos) == 2
    assert 200 not in codigos


@when("se envía un ataque de inyección SQL por el User-Agent", target_fixture="ataque")
def _() -> int:
    time.sleep(1.5)
    return _curl("User-Agent: ' OR 1=1--")


@then("el WAF responde 403")
def _(ataque: int) -> None:
    assert ataque == 403


@when("se levanta el baneo y se envía una petición normal", target_fixture="normal")
def _() -> int:
    _levantar_baneo()
    time.sleep(1.5)
    return _curl("User-Agent: Mozilla/5.0 (control)")


@then("la aplicación responde con una redirección al ingreso")
def _(normal: int) -> None:
    assert normal == 302


@when(
    "se piden seis páginas legítimas a un ritmo de una por segundo y medio",
    target_fixture="codigos",
)
def _() -> list[int]:
    salida = []
    for _ in range(6):
        salida.append(_curl("User-Agent: Mozilla/5.0 (control)"))
        time.sleep(1.5)
    return salida


@then("ninguna respuesta es 429")
def _(codigos: list[int]) -> None:
    assert 429 not in codigos
    assert all(c < 400 for c in codigos), codigos


@when("se captura el tráfico entre el worker y glpi durante una sincronización")
def _() -> None:
    pytest.skip("S-38 [PENDIENTE: F7] captura de tráfico con tshark (N-1)")


@then("ninguna trama contiene las cabeceras App-Token ni Session-Token en claro")
def _() -> None:
    pytest.skip("S-38 [PENDIENTE: F7]")
