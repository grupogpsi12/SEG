"""Bandeja de salida (outbox, RF-18): tickets por crear en GLPI y su politica de reintento."""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum

from jml.dominio.errores import DatoInvalido
from jml.dominio.tickets import TicketDeCola
from jml.dominio.valores import a_utc

MAX_INTENTOS = 10  # RF-18

# S-13: 30 s, 1 min, 2 min, 5 min, 10 min y luego 15 min fijos. Indice = intentos ya fallidos - 1.
ESPERAS_DE_REINTENTO = (
    timedelta(seconds=30),
    timedelta(minutes=1),
    timedelta(minutes=2),
    timedelta(minutes=5),
    timedelta(minutes=10),
    timedelta(minutes=15),
)


def espera_de_reintento(intentos_fallidos: int) -> timedelta:
    """Funcion pura: la espera crece con los intentos fallidos y luego se queda en 15 min."""
    if intentos_fallidos < 1:
        raise DatoInvalido("intentos_fallidos", "se espera al menos un intento fallido")
    return ESPERAS_DE_REINTENTO[min(intentos_fallidos, len(ESPERAS_DE_REINTENTO)) - 1]


class EstadoDeEntrada(StrEnum):
    PENDIENTE = "pendiente"
    ENVIADA = "enviada"
    FALLIDA = "fallida"  # agoto los intentos; la solicitud paso a `error`
    DESCARTADA = "descartada"  # la solicitud se cancelo antes de crearse


@dataclass(frozen=True, slots=True)
class EntradaDeBandeja:
    ticket: TicketDeCola
    estado: EstadoDeEntrada
    intentos: int
    proximo_intento: datetime
    ultimo_error: str | None = None

    @property
    def clave(self) -> str:
        return self.ticket.clave_de_idempotencia

    @property
    def solicitud_id(self) -> str:
        return self.ticket.solicitud_id

    @classmethod
    def nueva(cls, ticket: TicketDeCola, ahora: datetime) -> "EntradaDeBandeja":
        return cls(ticket, EstadoDeEntrada.PENDIENTE, 0, a_utc(ahora, "ahora"))

    def enviada(self) -> "EntradaDeBandeja":
        return replace(self, estado=EstadoDeEntrada.ENVIADA, ultimo_error=None)

    def descartada(self) -> "EntradaDeBandeja":
        return replace(self, estado=EstadoDeEntrada.DESCARTADA)

    def fallo(self, codigo: str, ahora: datetime) -> "EntradaDeBandeja":
        """Registra un fallo. Al decimo intento fallido la entrada queda `fallida` (RF-18)."""
        intentos = self.intentos + 1
        if intentos >= MAX_INTENTOS:
            return replace(
                self, estado=EstadoDeEntrada.FALLIDA, intentos=intentos, ultimo_error=codigo
            )
        return replace(
            self,
            intentos=intentos,
            proximo_intento=a_utc(ahora, "ahora") + espera_de_reintento(intentos),
            ultimo_error=codigo,
        )

    def reiniciada(self, ahora: datetime) -> "EntradaDeBandeja":
        """RF-38: el Administrador reintenta; vuelve a empezar la cuenta de intentos."""
        return replace(
            self,
            estado=EstadoDeEntrada.PENDIENTE,
            intentos=0,
            proximo_intento=a_utc(ahora, "ahora"),
            ultimo_error=None,
        )
