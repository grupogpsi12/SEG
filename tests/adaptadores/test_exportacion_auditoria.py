"""RD-04: exportacion diaria de la auditoria con el ancla de la cadena (2.4)."""

import json
from datetime import timedelta
from pathlib import Path

from jml.adaptadores.entrada.worker.exportacion import escribir, exportar_ayer
from jml.aplicacion.casos.auditoria import ExportarAuditoria
from jml.dominio.auditoria import calcular_hash
from tests.fabricas import HOY, SENTINELA
from tests.mundo import Mundo, retiro, vacaciones


def test_exporta_los_registros_del_dia_verificables_sin_la_base() -> None:
    m = Mundo.nuevo()
    m.registrar(vacaciones())
    m.emitir(retiro(restringido=SENTINELA))
    exp = ExportarAuditoria(m.puerto).ejecutar(HOY)
    assert exp.lineas
    assert exp.cadena_valida
    anterior = None
    for linea in exp.lineas:
        d = json.loads(linea)
        contenido = json.dumps(
            d["registro"], sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
        assert calcular_hash(d["hash_anterior"], contenido) == d["hash"]  # cada linea se verifica
        if anterior is not None:
            assert d["hash_anterior"] == anterior
        anterior = d["hash"]
    assert exp.ancla_hash == anterior  # la cabeza de la cadena
    assert SENTINELA not in "".join(exp.lineas)  # RD-05


def test_un_dia_sin_registros_exporta_vacio_pero_con_el_ancla_de_toda_la_cadena() -> None:
    m = Mundo.nuevo()
    m.registrar(vacaciones())
    hoy = ExportarAuditoria(m.puerto).ejecutar(HOY)
    hace_un_mes = ExportarAuditoria(m.puerto).ejecutar(HOY - timedelta(days=30))
    assert hace_un_mes.lineas == ()
    assert (hace_un_mes.ancla_secuencia, hace_un_mes.ancla_hash) == (
        hoy.ancla_secuencia,
        hoy.ancla_hash,
    )


def test_el_worker_exporta_ayer_una_sola_vez(tmp_path: Path) -> None:
    m = Mundo.nuevo()
    m.registrar(vacaciones())
    caso = ExportarAuditoria(m.puerto)
    manana = m.reloj.ahora() + timedelta(days=1)
    assert exportar_ayer(caso, tmp_path, manana) is True
    assert exportar_ayer(caso, tmp_path, manana) is False  # idempotente
    ancla = json.loads((tmp_path / f"ancla-{HOY.isoformat()}.json").read_text(encoding="utf-8"))
    assert ancla["registros_del_dia"] >= 1
    assert ancla["cadena_valida"] is True
    lineas = (tmp_path / f"auditoria-{HOY.isoformat()}.jsonl").read_text(encoding="utf-8")
    assert len(lineas.splitlines()) == ancla["registros_del_dia"]
    assert not list(tmp_path.glob("*.tmp"))


def test_una_cadena_rota_se_exporta_igual_y_queda_en_el_log(tmp_path: Path, caplog: object) -> None:
    import logging

    m = Mundo.nuevo()
    m.registrar(vacaciones())
    exp = ExportarAuditoria(m.puerto).ejecutar(HOY)
    rota = type(exp)(exp.dia, exp.lineas, exp.ancla_secuencia, exp.ancla_hash, False)

    class Caso:
        def ejecutar(self, dia: object) -> object:
            return rota

    with caplog.at_level(logging.ERROR):  # type: ignore[attr-defined]
        assert exportar_ayer(Caso(), tmp_path, m.reloj.ahora() + timedelta(days=1))  # type: ignore[arg-type]
    assert "NO es valida" in caplog.text  # type: ignore[attr-defined]
    assert escribir(rota, tmp_path) is False
