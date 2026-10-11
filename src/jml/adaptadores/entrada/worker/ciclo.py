"""El ciclo del worker: bandeja de salida a GLPI y sincronizacion cada 5 minutos (ADR-011).

Es el UNICO cliente de GLPI (CLAUDE.md). Cada tarea corre aislada: si GLPI o la base fallan,
se registra en el log y el ciclo sigue (RNF-02). El latido es un archivo con la hora (epoch) de
la ultima sincronizacion exitosa; el chequeo de salud del contenedor lo lee (RNF-01). La
sincronizacion tambien mantiene activo el proyecto gratuito de Supabase (RNF-05).
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

registro = logging.getLogger(__name__)

INTERVALO_BANDEJA_S = 30.0
INTERVALO_SINCRONIZACION_S = 300.0  # ADR-011: cada 5 minutos
LATIDO_MAXIMO_S = 3 * INTERVALO_SINCRONIZACION_S  # RNF-01: tres ciclos sin sincronizar = enfermo

type Tarea = Callable[[], object]


@dataclass
class Worker:
    bandeja: Tarea
    sincronizaciones: tuple[Tarea, ...]
    latido: Path
    reloj: Callable[[], float] = time.time
    _proxima_sincronizacion: float = field(default=0.0, init=False)

    def _correr(self, nombre: str, tarea: Tarea) -> bool:
        try:
            resultado = tarea()
        except Exception:  # el ciclo no se cae por una tarea (RNF-02)
            registro.exception("tarea del worker fallida: %s", nombre)
            return False
        registro.info("tarea del worker: %s", nombre, extra={"resultado": repr(resultado)})
        return getattr(resultado, "resultado", "ok") != "error"

    def una_vuelta(self) -> None:
        self._correr("bandeja", self.bandeja)
        ahora = self.reloj()
        if ahora < self._proxima_sincronizacion:
            return
        self._proxima_sincronizacion = ahora + INTERVALO_SINCRONIZACION_S
        exitos = [
            self._correr(f"sincronizacion-{i}", t) for i, t in enumerate(self.sincronizaciones)
        ]
        if all(exitos):
            self.latido.write_text(str(ahora), encoding="ascii")

    def correr(
        self, seguir: Callable[[], bool], dormir: Callable[[float], None] = time.sleep
    ) -> None:
        while seguir():
            self.una_vuelta()
            dormir(INTERVALO_BANDEJA_S)


def esta_sano(latido: Path, ahora: float) -> bool:
    try:
        ultima = float(latido.read_text(encoding="ascii"))
    except (FileNotFoundError, ValueError):
        return False
    return 0 <= ahora - ultima <= LATIDO_MAXIMO_S
