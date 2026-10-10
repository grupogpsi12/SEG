"""Cuentas derivadas de los tickets resueltos (SRS 4.7, RF-25, RF-27, RD-11, S-09..S-11, S-24).

Invariante 6: el estado de una cuenta SOLO cambia por la sincronizacion de tickets. Por eso
`Cuenta` es un valor congelado sin metodos y `derivar_cuenta` es la unica funcion publica que
produce una cuenta nueva a partir de otra. Es idempotente: observar dos veces lo mismo no cambia
nada, y solo toca la cuenta del sistema del ticket (no depende del orden entre sistemas).
"""

from dataclasses import dataclass, replace
from datetime import datetime

from jml.dominio.auditoria import EventoDeAuditoria
from jml.dominio.catalogo import ColaboradorId
from jml.dominio.tickets import Observacion, TicketDeCola
from jml.dominio.tipos import (
    AccionDeTicket,
    EstadoDeCuenta,
    MarcaDeCuenta,
    SistemaDeCuenta,
)
from jml.dominio.valores import a_utc

_E = EstadoDeCuenta
_A = AccionDeTicket

# SRS 4.7, columna «Al resolverse con solucion».
ESTADO_AL_RESOLVERSE: dict[AccionDeTicket, EstadoDeCuenta] = {
    _A.ALTA: _E.ACTIVA,
    _A.SUSPENSION: _E.SUSPENDIDA,
    _A.REACTIVACION: _E.ACTIVA,
    _A.CAMBIO: _E.ACTIVA,
    _A.BAJA: _E.DESHABILITADA,
    _A.ELIMINACION: _E.ELIMINADA,
}

# SRS 4.7, columna «Mientras esta abierto». CAMBIO conserva el estado actual (se marca aparte).
ESTADO_MIENTRAS_ESTA_ABIERTO: dict[AccionDeTicket, EstadoDeCuenta | None] = {
    _A.ALTA: _E.PENDIENTE_ALTA,
    _A.SUSPENSION: _E.PENDIENTE_SUSPENSION,
    _A.REACTIVACION: _E.SUSPENDIDA,
    _A.CAMBIO: None,
    _A.BAJA: _E.PENDIENTE_BAJA,
    _A.ELIMINACION: _E.DESHABILITADA,
}

type OrdenDeOrigen = tuple[datetime, datetime]  # (emitido_en, vence_en) del ticket que gobierna


@dataclass(frozen=True, slots=True)
class Cuenta:
    colaborador_id: ColaboradorId
    sistema: SistemaDeCuenta
    estado: EstadoDeCuenta
    ticket_origen: str  # clave de idempotencia del ticket que la gobierna
    orden_origen: OrdenDeOrigen
    desde: datetime
    marca: MarcaDeCuenta | None = None


@dataclass(frozen=True, slots=True)
class CambioDeCuenta:
    """Fila de `cuenta_historial` (solo insercion)."""

    colaborador_id: ColaboradorId
    sistema: SistemaDeCuenta
    estado_anterior: EstadoDeCuenta | None
    estado_nuevo: EstadoDeCuenta
    marca_nueva: MarcaDeCuenta | None
    ticket: str
    fecha: datetime


@dataclass(frozen=True, slots=True)
class ResultadoDeDerivacion:
    cuenta: Cuenta | None
    cambio: CambioDeCuenta | None
    eventos: tuple[EventoDeAuditoria, ...]


def _sin_cambio(
    cuenta: Cuenta | None, eventos: tuple[EventoDeAuditoria, ...] = ()
) -> ResultadoDeDerivacion:
    return ResultadoDeDerivacion(cuenta, None, eventos)


def _contenido(o: Observacion | None) -> tuple[int, bool, int] | None:
    return None if o is None else (int(o.estado), o.tiene_solucion, o.documentos)


def derivar_cuenta(
    cuenta: Cuenta | None,
    ticket: TicketDeCola,
    anterior: Observacion | None,
    actual: Observacion,
    colaborador_id: ColaboradorId,
    ahora: datetime,
) -> ResultadoDeDerivacion:
    """Aplica una observacion de GLPI a la cuenta del sistema del ticket (SRS 4.7)."""
    sistema = ticket.sistema
    if sistema is None:  # Inventario: los equipos salen de los activos, no de los tickets
        return _sin_cambio(cuenta)
    if anterior is not None and actual.observada_en < anterior.observada_en:
        return _sin_cambio(cuenta)  # observacion mas vieja que la ya vista: se ignora

    ahora = a_utc(ahora, "ahora")
    accion = ticket.accion
    orden: OrdenDeOrigen = (ticket.emitido_en, ticket.vence_en)
    novedad = _contenido(anterior) != _contenido(actual)  # solo lo nuevo se audita (sin ruido)

    resuelta_ok = actual.resuelta and actual.tiene_solucion
    sin_solucion = actual.resuelta and not actual.tiene_solucion
    reabierta = anterior is not None and anterior.resuelta and not actual.resuelta

    def evento(accion_auditoria: str, **extra: str | int | bool | None) -> EventoDeAuditoria:
        datos: dict[str, str | int | bool | None] = {
            "sistema": sistema.value,
            "ticket": ticket.clave_de_idempotencia,
        }
        datos.update(extra)
        return EventoDeAuditoria(accion_auditoria, colaborador_id, datos)

    # S-09: sin cuenta solo el alta puede crearla; lo demas se ignora y se audita.
    if cuenta is None and accion is not _A.ALTA:
        eventos = (evento("cuenta.inexistente"),) if novedad else ()
        return _sin_cambio(None, eventos)

    # S-10 / S-11: si ya gobierna un ticket mas reciente, este no cambia el estado.
    if (
        cuenta is not None
        and cuenta.ticket_origen != ticket.clave_de_idempotencia
        and cuenta.orden_origen > orden
    ):
        if reabierta and cuenta.marca is not MarcaDeCuenta.REABIERTO:
            marcada = replace(cuenta, marca=MarcaDeCuenta.REABIERTO)
            cambio = CambioDeCuenta(
                colaborador_id,
                sistema,
                cuenta.estado,
                cuenta.estado,
                MarcaDeCuenta.REABIERTO,
                ticket.clave_de_idempotencia,
                ahora,
            )
            return ResultadoDeDerivacion(
                marcada, cambio, (evento("cuenta.reapertura_de_ticket_antiguo"),)
            )
        return _sin_cambio(cuenta)

    abierto = ESTADO_MIENTRAS_ESTA_ABIERTO[accion]
    if abierto is None:  # CAMBIO conserva el estado actual
        abierto = cuenta.estado if cuenta is not None else _E.ACTIVA

    if resuelta_ok:
        estado, marca = ESTADO_AL_RESOLVERSE[accion], None
    elif sin_solucion:
        # «Cierre sin solucion»: la cuenta no cambia de estado (RF-24, T5).
        estado = cuenta.estado if cuenta is not None else abierto
        marca = MarcaDeCuenta.CIERRE_SIN_SOLUCION
    else:
        if ticket.activo_desde > ahora:  # programado que aun no llega su fecha: no cuenta
            return _sin_cambio(cuenta)
        estado = abierto
        sigue_reabierto = (
            cuenta is not None
            and cuenta.marca is MarcaDeCuenta.REABIERTO
            and cuenta.ticket_origen == ticket.clave_de_idempotencia
        )
        if reabierta or sigue_reabierto:
            marca = MarcaDeCuenta.REABIERTO  # S-24: vuelve al estado «mientras esta abierto»
        elif accion is _A.CAMBIO:
            marca = MarcaDeCuenta.CAMBIO_PENDIENTE
        else:
            marca = None

    cambia_origen = cuenta is None or cuenta.ticket_origen != ticket.clave_de_idempotencia
    cambia_estado = cuenta is None or cuenta.estado != estado
    nueva = Cuenta(
        colaborador_id=colaborador_id,
        sistema=sistema,
        estado=estado,
        ticket_origen=ticket.clave_de_idempotencia,
        orden_origen=orden,
        desde=cuenta.desde if cuenta and not (cambia_estado or cambia_origen) else ahora,
        marca=marca,
    )
    if nueva == cuenta:
        return _sin_cambio(cuenta)
    cambio = CambioDeCuenta(
        colaborador_id=colaborador_id,
        sistema=sistema,
        estado_anterior=None if cuenta is None else cuenta.estado,
        estado_nuevo=estado,
        marca_nueva=marca,
        ticket=ticket.clave_de_idempotencia,
        fecha=ahora,
    )
    auditoria = evento(
        "cuenta.reabierta" if marca is MarcaDeCuenta.REABIERTO else "cuenta.estado_derivado",
        anterior=None if cuenta is None else cuenta.estado.value,
        nuevo=estado.value,
        marca=None if marca is None else marca.value,
    )
    return ResultadoDeDerivacion(nueva, cambio, (auditoria,))
