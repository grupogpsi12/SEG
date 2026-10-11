"""Item 2.9 (adaptador): lo propio del disco que la suite de contrato no ve (RD-12, RS-17, T17)."""

import os
import stat
import sys
from pathlib import Path

import pytest

from jml.adaptadores.salida.soportes import AlmacenDeSoportesEnDisco
from jml.aplicacion.puertos import SoporteNoDisponible


def test_el_archivo_se_guarda_dentro_del_volumen_con_nombre_aleatorio(tmp_path: Path) -> None:
    almacen = AlmacenDeSoportesEnDisco(tmp_path)
    nombre = almacen.guardar(b"%PDF-1.7 x")
    assert [p.name for p in tmp_path.iterdir()] == [nombre]
    assert len(nombre) == 32
    assert (tmp_path / nombre).read_bytes() == b"%PDF-1.7 x"


def test_solo_el_duenio_puede_leerlo(tmp_path: Path) -> None:
    nombre = AlmacenDeSoportesEnDisco(tmp_path).guardar(b"%PDF-")
    modo = stat.S_IMODE(os.stat(tmp_path / nombre).st_mode)
    if sys.platform != "win32":  # Windows no tiene permisos POSIX; en el contenedor Linux si
        assert modo == 0o600


@pytest.mark.parametrize(
    "malicioso", ["../../etc/passwd", "..\\secreto", "a" * 32 + "/x", "ABCDEF" * 6, ""]
)
def test_un_nombre_que_no_es_aleatorio_no_toca_el_disco(tmp_path: Path, malicioso: str) -> None:
    """El nombre llega de la base: si alguien lo altera no puede salirse del volumen."""
    almacen = AlmacenDeSoportesEnDisco(tmp_path)
    with pytest.raises(SoporteNoDisponible):
        almacen.leer(malicioso)
    almacen.borrar(malicioso)  # idempotente y sin tocar el disco
    assert almacen.existe(malicioso) is False
    assert list(tmp_path.iterdir()) == []
