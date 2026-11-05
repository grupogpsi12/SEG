"""Genera auditoria/herramientas.lock: versión o digest de CADA herramienta de la auditoría (§9.2.5).

    python auditoria/scripts/congelar-herramientas.py

Dos mediciones con versiones distintas no se comparan. Todo se LEE (paquetes instalados, la salida de
`--version` de cada comando y los digests ya fijados en el repositorio); no se escribe a mano.
Una herramienta sin versión se anota `NO-DISPONIBLE`: es mejor que callar.
"""

import importlib.metadata as md
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
SALIDA = RAIZ / "auditoria" / "herramientas.lock"
PAQUETES = [
    "pytest", "pytest-cov", "pytest-django", "pytest-timeout", "pytest-bdd", "hypothesis", "coverage",
    "mutmut", "ruff", "mypy", "django-stubs", "import-linter", "playwright", "httpx", "django",
    "reportlab", "pillow", "pyyaml",
]  # fmt: skip
COMANDOS = {
    "python": ["python", "--version"],
    "uv": ["uv", "--version"],
    "git": ["git", "--version"],
    "docker": ["docker", "--version"],
    "docker-compose": ["docker", "compose", "version", "--short"],
    "gitleaks (local)": ["gitleaks", "version"],
    "sops": ["sops", "--version"],
    "age": ["age", "--version"],
}
# Archivos del repositorio donde ya estan fijadas las imagenes y herramientas por digest o hash
FUENTES = [
    ".github/workflows/verificar.yml",
    ".github/workflows/imagen.yml",
    "infra/scripts/seguridad-dinamica.sh",
    "infra/scripts/e2e-interfaz.sh",
    "infra/scripts/carga.sh",
    "infra/scripts/restaurar-prueba.sh",
]
FIJADO = re.compile(
    r"([\w./-]+(?::[\w.-]+)?@sha256:[0-9a-f]{64})|(\b(?:bandit|pip-audit|sqlmap)==[\d.]+(?:\s+--hash=sha256:[0-9a-f]{64})?)"
)


def _salida(cmd: list[str]) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False, cwd=RAIZ)
        return (r.stdout or r.stderr).strip().splitlines()[0]
    except (OSError, subprocess.TimeoutExpired, IndexError):
        return "NO-DISPONIBLE"


def construir() -> list[str]:
    lineas = [
        f"# generado por auditoria/scripts/congelar-herramientas.py el {datetime.now(UTC):%Y-%m-%dT%H:%M:%SZ}"
    ]
    lineas.append(f"# commit {_salida(['git', 'rev-parse', 'HEAD'])}")
    lineas.append("\n[comandos]")
    lineas += [f"{n} = {_salida(c)}" for n, c in COMANDOS.items()]
    lineas.append("\n[paquetes python (entorno de desarrollo)]")
    for p in PAQUETES:
        try:
            lineas.append(f"{p} = {md.version(p)}")
        except md.PackageNotFoundError:
            lineas.append(f"{p} = NO-INSTALADO")
    lineas.append("\n[imagenes y herramientas fijadas por digest o hash en el repositorio]")
    vistas: set[str] = set()
    for fuente in FUENTES:
        ruta = RAIZ / fuente
        if not ruta.exists():
            continue
        for m in FIJADO.finditer(ruta.read_text(encoding="utf-8")):
            valor = m.group(0).strip()
            if valor not in vistas:
                vistas.add(valor)
                lineas.append(f"{valor}    # {fuente}")
    for compose in [*sorted((RAIZ / "infra").glob("compose*.yaml")), RAIZ / "Dockerfile"]:
        for m in re.finditer(
            r"([\w./-]+(?::[\w.-]+)?@sha256:[0-9a-f]{64})", compose.read_text(encoding="utf-8")
        ):
            if m.group(1) not in vistas:
                vistas.add(m.group(1))
                lineas.append(f"{m.group(1)}    # {compose.relative_to(RAIZ).as_posix()}")
    lineas.append("\n[pendientes de fijar al usarse (plan §12.4)]")
    lineas += [
        "nmap = PENDIENTE: imagen por digest en F7",
        "tshark/tcpdump = PENDIENTE: imagen por digest en F7",
        "testssl.sh = PENDIENTE: imagen por digest en F7",
        "trivy = ver aquasec/trivy arriba (fijada en imagen.yml)",
    ]
    return lineas


if __name__ == "__main__":
    texto = "\n".join(construir()) + "\n"
    SALIDA.write_text(texto, encoding="utf-8", newline="\n")
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    print(texto)
