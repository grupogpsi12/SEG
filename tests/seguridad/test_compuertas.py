"""B-16: la CI invoca scripts por su ruta; si git los guarda sin bit de ejecución, el paso falla.

En Windows el sistema de archivos no tiene ese bit, así que la prueba lo lee del índice de git
(`git ls-files -s`), que es lo que ve el ejecutor de Linux de la CI. `glpi-real` quedó en rojo en
`5fa3f32` por `infra/scripts/preparar-entorno.sh` (modo 100644, «Permission denied»).
"""

import re
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
FLUJO = RAIZ / ".github" / "workflows" / "verificar.yml"
# Un script .sh invocado como comando: al inicio de la línea o tras variables de entorno
INVOCACION = re.compile(r"^\s*(?:run:\s*)?(?:[A-Z_]+=\S+\s+)*(infra/\S+\.sh)\b", re.MULTILINE)


def _modos() -> dict[str, str]:
    salida = subprocess.run(
        ["git", "ls-files", "-s", "infra"], cwd=RAIZ, capture_output=True, text=True, check=True
    ).stdout
    return {l.split("\t")[1]: l.split()[0] for l in salida.splitlines()}  # noqa: E741


@pytest.mark.seguridad
def test_B_16_los_scripts_que_invoca_la_ci_son_ejecutables() -> None:
    invocados = sorted(set(INVOCACION.findall(FLUJO.read_text(encoding="utf-8"))))
    assert invocados, "el patrón no reconoce ninguna invocación: la prueba no vigila nada"
    modos = _modos()
    sin_permiso = [s for s in invocados if modos.get(s) != "100755"]
    assert not sin_permiso, f"git los guarda sin bit de ejecución: {sin_permiso}"
