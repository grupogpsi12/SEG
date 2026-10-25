"""F9-04: el verificador de la entrega falla ante cada defecto sembrado y pasa sobre una entrega sana."""

import hashlib
import json
from pathlib import Path

import pytest
from auditoria.herramientas import verificar_entrega as v

pytestmark = pytest.mark.seguridad


def _entrega(raiz: Path) -> Path:
    (raiz / "informes").mkdir(parents=True)
    (raiz / "evidencias" / "funcionales" / "F1").mkdir(parents=True)
    (raiz / "hallazgos").mkdir()
    evidencia = raiz / "evidencias" / "funcionales" / "F1" / "salida.txt"
    evidencia.write_text("1618 passed\n", encoding="utf-8")
    (raiz / "evidencias" / "funcionales" / "F1" / "codigo.txt").write_text("0\n", encoding="utf-8")
    (raiz / "informes" / "0-maestro.md").write_text(
        "| CA-01 | Deduplicación | cumple | evidencias/funcionales/F1/salida.txt |\n",
        encoding="utf-8",
    )
    (raiz / "informes" / "0-maestro.pdf").write_bytes(b"%PDF-1.4\n" + b"0" * 2000)
    (raiz / "hallazgos" / "B-01.md").write_text(
        "# B-01 · Media — x\n**Estado:** abierto\n", encoding="utf-8"
    )
    (raiz / "trazabilidad.csv").write_text("id,estado\nCA-01,ok\n", encoding="utf-8")
    (raiz / "metricas.json").write_text(
        json.dumps({"hallazgos": {"total": 1}, "trazabilidad": {"filas": 1}}), encoding="utf-8"
    )
    lineas = [
        f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(raiz).as_posix()}"
        for p in sorted((raiz / "evidencias").rglob("*"))
        if p.is_file()
    ]
    (raiz / "manifiesto.sha256").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return raiz


def test_una_entrega_sana_pasa(tmp_path: Path) -> None:
    assert v.main(str(_entrega(tmp_path / "e"))) == 0


def test_un_marcador_sin_reemplazar_la_rechaza(tmp_path: Path) -> None:
    raiz = _entrega(tmp_path / "e")
    (raiz / "informes" / "1-extra.md").write_text(
        "Resultados de sqlmap:\n\nSQLMAP_RESULTADOS\n", encoding="utf-8"
    )
    (raiz / "informes" / "1-extra.pdf").write_bytes(b"%PDF-1.4\n" + b"0" * 2000)
    assert v.main(str(raiz)) == 1


def test_un_criterio_cumplido_sin_evidencia_la_rechaza(tmp_path: Path) -> None:
    raiz = _entrega(tmp_path / "e")
    (raiz / "informes" / "0-maestro.md").write_text(
        "| CA-12 | sqlmap | cumple | sin archivo |\n", encoding="utf-8"
    )
    assert v.main(str(raiz)) == 1


def test_un_hash_que_no_cuadra_la_rechaza(tmp_path: Path) -> None:
    raiz = _entrega(tmp_path / "e")
    (raiz / "evidencias" / "funcionales" / "F1" / "salida.txt").write_text(
        "alterado\n", encoding="utf-8"
    )
    assert v.main(str(raiz)) == 1


def test_un_archivo_de_evidencia_fuera_del_manifiesto_la_rechaza(tmp_path: Path) -> None:
    raiz = _entrega(tmp_path / "e")
    (raiz / "evidencias" / "funcionales" / "F1" / "nuevo.txt").write_text("x\n", encoding="utf-8")
    assert v.main(str(raiz)) == 1


def test_una_corrida_con_fallos_citada_como_verde_la_rechaza(tmp_path: Path) -> None:
    raiz = _entrega(tmp_path / "e")
    (raiz / "evidencias" / "funcionales" / "F1" / "codigo.txt").write_text("1\n", encoding="utf-8")
    ruta = raiz / "manifiesto.sha256"
    ruta.write_text(
        "\n".join(
            f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(raiz).as_posix()}"
            for p in sorted((raiz / "evidencias").rglob("*"))
            if p.is_file()
        )
        + "\n",
        encoding="utf-8",
    )
    (raiz / "informes" / "0-maestro.md").write_text(
        "La suite quedó verde: evidencias/funcionales/F1/\n", encoding="utf-8"
    )
    assert v.main(str(raiz)) == 1


def test_un_pdf_faltante_la_rechaza(tmp_path: Path) -> None:
    raiz = _entrega(tmp_path / "e")
    (raiz / "informes" / "0-maestro.pdf").unlink()
    assert v.main(str(raiz)) == 1
