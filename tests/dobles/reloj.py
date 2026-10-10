"""Reloj simulado: fijo y avanzable (puerto Reloj)."""

from datetime import UTC, datetime, timedelta

from jml.dominio.valores import a_utc


class RelojSimulado:
    def __init__(self, inicio: datetime | None = None) -> None:
        self._ahora = a_utc(inicio or datetime(2026, 10, 12, 15, 0, tzinfo=UTC))

    def ahora(self) -> datetime:
        return self._ahora

    def avanzar(self, delta: timedelta) -> None:
        self._ahora += delta

    def fijar(self, instante: datetime) -> None:
        self._ahora = a_utc(instante)
