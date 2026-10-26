"""RD-04: el worker deja cada dia la auditoria del dia anterior y el ancla de la cadena en un
volumen. Un script del host (`infra/scripts/copiar-exportes.sh`) la copia a un disco externo sin
sobrescribir (ADR-031): la aplicacion no sabe adonde va la copia.

Idempotente: si el ancla del dia ya existe, no se toca nada. Se escribe primero a un temporal y
se renombra, y el ancla va al final: un ancla presente implica un archivo de registros completo.
"""

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

from jml.aplicacion.casos.auditoria import ExportacionDeAuditoria, ExportarAuditoria
from jml.dominio.valores import hoy_en_bogota

registro = logging.getLogger(__name__)


def _escribir_atomico(ruta: Path, texto: str) -> None:
    temporal = ruta.with_suffix(ruta.suffix + ".tmp")
    temporal.write_text(texto, encoding="utf-8")
    os.replace(temporal, ruta)


def escribir(exportacion: ExportacionDeAuditoria, directorio: Path) -> bool:
    dia = exportacion.dia.isoformat()
    ancla = directorio / f"ancla-{dia}.json"
    if ancla.exists():
        return False
    _escribir_atomico(
        directorio / f"auditoria-{dia}.jsonl",
        "".join(linea + "\n" for linea in exportacion.lineas),
    )
    _escribir_atomico(
        ancla,
        json.dumps(
            {
                "dia": dia,
                "registros_del_dia": len(exportacion.lineas),
                "ancla_secuencia": exportacion.ancla_secuencia,
                "ancla_hash": exportacion.ancla_hash,
                "cadena_valida": exportacion.cadena_valida,
            },
            sort_keys=True,
        ),
    )
    return True


def exportar_ayer(caso: ExportarAuditoria, directorio: Path, ahora: datetime) -> bool:
    """Se llama en cada sincronizacion; solo trabaja una vez por dia."""
    dia = hoy_en_bogota(ahora) - timedelta(days=1)
    if (directorio / f"ancla-{dia.isoformat()}.json").exists():
        return False
    exportacion = caso.ejecutar(dia)
    if not exportacion.cadena_valida:
        # Se exporta igual: es la evidencia. El Auditor ve el detalle en /auditoria (RF-36).
        registro.error("la cadena de auditoria NO es valida al exportar el %s", dia.isoformat())
    return escribir(exportacion, directorio)
