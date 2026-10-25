"""Gherkin de la cadena de suministro: lectura de archivos del repositorio y, con red, pip-audit."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from auditoria.herramientas import marcadores
from pytest_bdd import scenarios, then, when

scenarios("features/cadena-de-suministro.feature")

RAIZ = Path(__file__).resolve().parents[2]


@when("se lee el archivo de dependencias de la imagen", target_fixture="bloques")
def _() -> list[str]:
    texto = (RAIZ / "requirements.lock").read_text(encoding="utf-8")
    # cada dependencia empieza en una línea sin sangría que no sea comentario
    return re.split(r"\n(?=[A-Za-z0-9_.\[\]-]+==)", texto)


@then("toda dependencia tiene versión exacta y al menos un hash")
def _(bloques: list[str]) -> None:
    paquetes = [b for b in bloques if re.match(r"[A-Za-z0-9_.\[\]-]+==", b)]
    assert len(paquetes) > 10
    for b in paquetes:
        assert re.match(r"[A-Za-z0-9_.\[\]-]+==\d", b), b.splitlines()[0]
        assert "--hash=sha256:" in b, b.splitlines()[0]


@when("se leen los compose, el Dockerfile y los flujos de CI", target_fixture="fuentes")
def _() -> dict[str, list[str]]:
    imagenes = []
    for compose in sorted((RAIZ / "infra").glob("compose*.yaml")):
        servicios = yaml.safe_load(compose.read_text(encoding="utf-8")).get("services", {})
        imagenes += [
            s["image"]
            for s in servicios.values()
            if "image" in s and "JML_IMAGEN" not in s["image"]
        ]
    imagenes += re.findall(
        r"^FROM\s+(\S+)", (RAIZ / "Dockerfile").read_text(encoding="utf-8"), re.MULTILINE
    )
    acciones = [
        linea.split("uses:", 1)[1].split("#")[0].strip()
        for flujo in (RAIZ / ".github" / "workflows").glob("*.yml")
        for linea in flujo.read_text(encoding="utf-8").splitlines()
        if "uses:" in linea and "./" not in linea
    ]
    return {"imagenes": imagenes, "acciones": acciones}


@then("cada imagen de terceros lleva un resumen sha256")
def _(fuentes: dict[str, list[str]]) -> None:
    assert fuentes["imagenes"]
    sin_resumen = [i for i in fuentes["imagenes"] if "@sha256:" not in i]
    assert sin_resumen == []


@then("cada acción de GitHub se fija a un commit completo")
def _(fuentes: dict[str, list[str]]) -> None:
    assert fuentes["acciones"]
    sin_fijar = [a for a in fuentes["acciones"] if not re.search(r"@[0-9a-f]{40}$", a)]
    assert sin_fijar == []


def _pip_audit(requerimientos: Path) -> subprocess.CompletedProcess[str]:
    if shutil.which("uvx") is None:
        pytest.skip("S-37: uvx no está instalado")
    return subprocess.run(
        ["uvx", "pip-audit==2.10.1", "-r", str(requerimientos), "--no-deps", "--disable-pip"],
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )


@when("se audita el archivo de dependencias de la imagen", target_fixture="auditoria_real")
def _() -> subprocess.CompletedProcess[str]:
    return _pip_audit(RAIZ / "requirements.lock")


@then("no hay vulnerabilidades conocidas")
def _(auditoria_real: subprocess.CompletedProcess[str]) -> None:
    assert auditoria_real.returncode == 0, auditoria_real.stdout + auditoria_real.stderr


@then("una dependencia vieja sembrada sí se reporta")
def _(tmp_path: Path) -> None:
    vieja = tmp_path / "requirements.txt"
    vieja.write_text("requests==2.19.0\n", encoding="utf-8")
    assert _pip_audit(vieja).returncode == 1  # el control positivo: la herramienta ve lo malo


@when("se buscan marcadores sin reemplazar en la documentación", target_fixture="marcas")
def _() -> dict[Path, list[tuple[int, str]]]:
    return {
        ruta: m
        for carpeta in (RAIZ / "docs", RAIZ / "tasks")
        for ruta, m in marcadores.recorrer(carpeta).items()
    }


@then("no hay ninguno")
def _(marcas: dict[Path, list[tuple[int, str]]]) -> None:
    assert marcas == {}
