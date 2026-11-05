"""Logs en JSON con correlation_id y sin campos prohibidos (RS-09, RD-05, CLAUDE.md).

El filtro tapa cualquier atributo extra cuyo nombre contenga una palabra prohibida, tambien
dentro de diccionarios anidados. Un `CampoRestringido` ya se imprime como `<oculto>`.
"""

import json
import logging
import unicodedata
from contextvars import ContextVar
from datetime import UTC, datetime

CORRELACION: ContextVar[str] = ContextVar("correlation_id", default="-")

PALABRAS_PROHIBIDAS = ("password", "contrasena", "token", "totp", "secret", "motivo", "descripcion")
FILTRADO = "[filtrado]"

# Atributos que trae todo LogRecord; el resto son los `extra` que agrega quien registra.
_ESTANDAR = set(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {"message", "asctime"}


def _prohibida(clave: str) -> bool:
    # Sin acentos: `contraseña` y `descripción` tambien se filtran (B-21).
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFKD", clave.lower()) if not unicodedata.combining(c)
    )
    return any(p in sin_acentos for p in PALABRAS_PROHIBIDAS)


def _limpiar(valor: object) -> object:
    if isinstance(valor, dict):
        return {k: FILTRADO if _prohibida(str(k)) else _limpiar(v) for k, v in valor.items()}
    if isinstance(valor, list | tuple | set | frozenset):
        return [_limpiar(v) for v in valor]  # revision externa M1: las listas tambien
    return valor


class FiltroDeCorrelacion(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = CORRELACION.get()
        return True


class FiltroDeCamposProhibidos(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        for clave in list(vars(record)):
            if clave in _ESTANDAR:
                continue
            valor = getattr(record, clave)
            setattr(record, clave, FILTRADO if _prohibida(clave) else _limpiar(valor))
        return True


class FormatoJSON(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        salida: dict[str, object] = {
            "fecha": datetime.fromtimestamp(record.created, UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "nivel": record.levelname,
            "logger": record.name,
            "mensaje": record.getMessage(),
            "correlation_id": getattr(record, "correlation_id", "-"),
        }
        for clave, valor in vars(record).items():
            if clave not in _ESTANDAR and clave not in salida:
                salida[clave] = valor
        if record.exc_info:
            salida["excepcion"] = self.formatException(record.exc_info)
        return json.dumps(salida, ensure_ascii=False, default=str)
