"""La imagen instala el proyecto con `pip install .`: el paquete debe traer plantillas y estaticos.

Antes de arreglarlo, el contenedor arrancaba sin ellas y `/ingreso` daba 500 (leccion 42); las
pruebas no lo veian porque corren desde el codigo fuente.
"""

import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
WEB = RAIZ / "src" / "jml" / "adaptadores" / "entrada" / "web"


SIN_UV = shutil.which("uv") is None


@pytest.mark.skipif(SIN_UV, reason="S-28: sin uv no se puede construir el paquete")
def test_el_paquete_trae_las_plantillas_y_los_estaticos(tmp_path: Path) -> None:
    # Copia limpia: `src/jml.egg-info/SOURCES.txt` (instalacion editable local) hace que setuptools
    # incluya archivos que en la imagen y en la CI no estarian, y la prueba pasaria sin merecerlo.
    limpia = tmp_path / "fuente"
    shutil.copytree(
        RAIZ / "src", limpia / "src", ignore=shutil.ignore_patterns("*.egg-info", "__pycache__")
    )
    shutil.copy(RAIZ / "pyproject.toml", limpia / "pyproject.toml")
    salida = tmp_path / "salida"
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(salida), str(limpia)],
        check=True,
        capture_output=True,
        timeout=300,
    )
    (rueda,) = salida.glob("*.whl")
    contenido = set(zipfile.ZipFile(rueda).namelist())
    esperados = {
        "jml/adaptadores/entrada/web/" + p.relative_to(WEB).as_posix()
        for carpeta in ("templates", "static")
        for p in (WEB / carpeta).rglob("*")
        if p.is_file()
    }
    assert esperados, "no hay plantillas que verificar"
    assert not esperados - contenido, sorted(esperados - contenido)
