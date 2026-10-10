"""Agregado `Solicitud`: maquina de estados, decisiones e inmutabilidad (RF-07 a RF-15, RF-39).

La tabla de transiciones es dato explicito. Fuente: SRS 4.2 y `docs/img/estados.dot`, con dos
adiciones registradas como supuestos: `error -> cancelada` (S-19, necesaria para RD-12) y la
ausencia de `en_ejecucion -> error` (S-14, el diagrama no la trae).
"""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date, datetime
from enum import StrEnum
from types import MappingProxyType

from jml.dominio.auditoria import EventoDeAuditoria
from jml.dominio.catalogo import (
    ColaboradorId,
    DatosDelEvento,
    UsuarioId,
    validar_evento,
)
from jml.dominio.colaborador import Colaborador
from jml.dominio.errores import (
    AutoAprobacionProhibida,
    CancelacionNoPermitida,
    CierreNoPermitido,
    ColaboradorNoElegible,
    JustificacionRequerida,
    NoAutorizado,
    OperacionNoPermitida,
    TransicionInvalida,
)
from jml.dominio.permisos import (
    Actor,
    Relacion,
    puede_decidir,
    puede_emitir_directo,
    puede_emitir_por_excepcion,
    puede_registrar_como_solicitante,
    puede_reintentar_emision,
    relacion_con,
)
from jml.dominio.tipos import (
    ESTADOS_ABIERTOS,
    ESTADOS_FINALES,
    EstadoColaborador,
    EstadoSolicitud,
    Rol,
    Subtipo,
    TipoEvento,
)
from jml.dominio.valores import CampoRestringido, SolicitudId, a_utc


class Accion(StrEnum):
    APROBAR = "aprobar"
    RECHAZAR = "rechazar"
    CANCELAR_SOLICITANTE = "cancelar_solicitante"
    CANCELAR_RRHH = "cancelar_rrhh"
    INICIAR_EJECUCION = "iniciar_ejecucion"
    FALLAR_EMISION = "fallar_emision"
    REINTENTAR = "reintentar"
    CERRAR = "cerrar"


_S = EstadoSolicitud
_A = Accion

# (estado, accion) -> estado. Todo lo que no esta aqui es `TransicionInvalida`.
TRANSICIONES: Mapping[tuple[EstadoSolicitud, Accion], EstadoSolicitud] = MappingProxyType(
    {
        (_S.PENDIENTE_APROBACION, _A.APROBAR): _S.APROBADA,
        (_S.PENDIENTE_APROBACION, _A.RECHAZAR): _S.RECHAZADA,
        (_S.PENDIENTE_APROBACION, _A.CANCELAR_SOLICITANTE): _S.CANCELADA,
        (_S.APROBADA, _A.INICIAR_EJECUCION): _S.EN_EJECUCION,
        (_S.APROBADA, _A.FALLAR_EMISION): _S.ERROR,
        (_S.APROBADA, _A.CANCELAR_RRHH): _S.CANCELADA,
        (_S.ERROR, _A.REINTENTAR): _S.APROBADA,
        (_S.ERROR, _A.CANCELAR_RRHH): _S.CANCELADA,  # S-19
        (_S.EN_EJECUCION, _A.CERRAR): _S.CERRADA,
    }
)


class TipoDeDecision(StrEnum):
    APROBAR = "aprobar"
    RECHAZAR = "rechazar"
    EMITIR = "emitir"
    EMITIR_POR_EXCEPCION = "emitir_por_excepcion"
    CANCELAR = "cancelar"


@dataclass(frozen=True, slots=True)
class Decision:
    """Registro de solo insercion de quien decidio que y por que (tabla `decision`)."""

    solicitud_id: SolicitudId
    tipo: TipoDeDecision
    justificacion: str | None
    usuario_id: UsuarioId
    fecha: datetime


@dataclass(frozen=True, slots=True)
class ResultadoSolicitud:
    solicitud: "Solicitud"
    decision: Decision | None
    eventos: tuple[EventoDeAuditoria, ...]


# S-25: a que estados de colaborador aplica cada evento.
_E = EstadoColaborador
ESTADOS_ELEGIBLES: Mapping[TipoEvento, frozenset[EstadoColaborador]] = MappingProxyType(
    {
        TipoEvento.ING: frozenset({_E.POR_INGRESAR}),
        TipoEvento.VAC: frozenset({_E.ACTIVO}),
        TipoEvento.CDP: frozenset({_E.ACTIVO}),
        TipoEvento.CSU: frozenset({_E.ACTIVO}),
        TipoEvento.RET: frozenset({_E.ACTIVO, _E.SUSPENDIDO}),
        TipoEvento.EMG: frozenset({_E.ACTIVO, _E.SUSPENDIDO, _E.POR_INGRESAR}),
    }
)


def _justificacion(valor: str | None, accion: str, obligatoria: bool) -> str | None:
    limpia = valor.strip() if valor is not None else ""
    if not limpia:
        if obligatoria:
            raise JustificacionRequerida(accion)
        return None
    return limpia


@dataclass(frozen=True, slots=True)
class Solicitud:
    id: SolicitudId
    colaborador_id: ColaboradorId
    tipo: TipoEvento
    subtipo: Subtipo | None
    fecha_efectiva: date
    datos: DatosDelEvento
    restringido: CampoRestringido | None
    solicitante_id: UsuarioId
    estado: EstadoSolicitud
    creada_en: datetime
    solicitud_origen_id: SolicitudId | None = None
    tickets: tuple[str, ...] = ()  # claves de idempotencia de los tickets ya creados en GLPI
    para_revision: bool = False  # RF-10; es una marca, no contenido

    # --- consultas ----------------------------------------------------------------------------

    @property
    def abierta(self) -> bool:
        return self.estado in ESTADOS_ABIERTOS

    @property
    def final(self) -> bool:
        return self.estado in ESTADOS_FINALES

    def contenido(self) -> tuple[object, ...]:
        """Todo lo que RF-14 declara inmutable tras la aprobacion (no incluye estado ni tickets)."""
        return (
            self.id,
            self.colaborador_id,
            self.tipo,
            self.subtipo,
            self.fecha_efectiva,
            self.datos,
            self.restringido,
            self.solicitante_id,
            self.creada_en,
            self.solicitud_origen_id,
        )

    # --- creacion -----------------------------------------------------------------------------

    @classmethod
    def _crear(
        cls,
        *,
        id: SolicitudId,
        sujeto: Colaborador,
        tipo: TipoEvento,
        subtipo: Subtipo | None,
        fecha_efectiva: date,
        datos: DatosDelEvento,
        restringido: CampoRestringido | None,
        solicitante_id: UsuarioId,
        estado: EstadoSolicitud,
        ahora: datetime,
        origen: SolicitudId | None,
    ) -> "Solicitud":
        if sujeto.estado not in ESTADOS_ELEGIBLES[tipo]:
            raise ColaboradorNoElegible(tipo.value, sujeto.estado.value)
        validar_evento(tipo, subtipo, fecha_efectiva, datos, restringido, ahora)
        return cls(
            id=id,
            colaborador_id=sujeto.id,
            tipo=tipo,
            subtipo=subtipo,
            fecha_efectiva=fecha_efectiva,
            datos=datos,
            restringido=restringido,
            solicitante_id=solicitante_id,
            estado=estado,
            creada_en=a_utc(ahora, "ahora"),
            solicitud_origen_id=origen,
        )

    @staticmethod
    def _evento(accion: str, s: "Solicitud", **extra: str | int | bool | None) -> EventoDeAuditoria:
        # Sin justificacion ni campos restringidos: viven en `decision` y `solicitud_restringida`.
        datos: dict[str, str | int | bool | None] = {
            "tipo": s.tipo.value,
            "estado": s.estado.value,
            "colaborador_id": s.colaborador_id,
        }
        datos.update(extra)
        return EventoDeAuditoria(accion, s.id.valor, datos)

    @classmethod
    def registrar_pendiente(
        cls,
        *,
        id: SolicitudId,
        actor: Actor,
        sujeto: Colaborador,
        tipo: TipoEvento,
        subtipo: Subtipo | None,
        fecha_efectiva: date,
        datos: DatosDelEvento,
        restringido: CampoRestringido | None,
        ahora: datetime,
        solicitud_origen_id: SolicitudId | None = None,
    ) -> ResultadoSolicitud:
        """Registro de un colaborador o de un jefe: queda `pendiente_aprobacion` (3.3, 4.1)."""
        relacion = relacion_con(actor, sujeto.id, sujeto.jefe_id)
        if not puede_registrar_como_solicitante(actor, tipo, subtipo, relacion):
            raise NoAutorizado(
                "registrar", f"un {tipo.value} no lo registra este rol sobre este sujeto"
            )
        s = cls._crear(
            id=id,
            sujeto=sujeto,
            tipo=tipo,
            subtipo=subtipo,
            fecha_efectiva=fecha_efectiva,
            datos=datos,
            restringido=restringido,
            solicitante_id=actor.usuario_id,
            estado=_S.PENDIENTE_APROBACION,
            ahora=ahora,
            origen=solicitud_origen_id,
        )
        return ResultadoSolicitud(
            s, None, (cls._evento("solicitud.registrada", s, via="solicitante"),)
        )

    @classmethod
    def emitir_directo(
        cls,
        *,
        id: SolicitudId,
        actor: Actor,
        sujeto: Colaborador,
        tipo: TipoEvento,
        subtipo: Subtipo | None,
        fecha_efectiva: date,
        datos: DatosDelEvento,
        restringido: CampoRestringido | None,
        justificacion: str | None,
        ahora: datetime,
        solicitud_origen_id: SolicitudId | None = None,
    ) -> ResultadoSolicitud:
        """RF-13: RRHH registra y emite en un solo paso, con justificacion obligatoria."""
        relacion = relacion_con(actor, sujeto.id, sujeto.jefe_id)
        if not puede_emitir_directo(actor, relacion):
            if actor.tiene(Rol.RRHH) and relacion is Relacion.SI_MISMO:
                raise AutoAprobacionProhibida("emitir")  # RF-15
            raise NoAutorizado("emitir", "solo RRHH emite directamente")
        texto = _justificacion(justificacion, "emitir", obligatoria=True)
        s = cls._crear(
            id=id,
            sujeto=sujeto,
            tipo=tipo,
            subtipo=subtipo,
            fecha_efectiva=fecha_efectiva,
            datos=datos,
            restringido=restringido,
            solicitante_id=actor.usuario_id,
            estado=_S.APROBADA,
            ahora=ahora,
            origen=solicitud_origen_id,
        )
        decision = Decision(s.id, TipoDeDecision.EMITIR, texto, actor.usuario_id, a_utc(ahora))
        return ResultadoSolicitud(
            s,
            decision,
            (
                cls._evento("solicitud.registrada", s, via="rrhh"),
                cls._evento("solicitud.emitida", s, justificada=True),
            ),
        )

    @classmethod
    def emitir_por_excepcion(
        cls,
        *,
        id: SolicitudId,
        actor: Actor,
        sujeto: Colaborador,
        sujeto_es_rrhh: bool,
        tipo: TipoEvento,
        subtipo: Subtipo | None,
        fecha_efectiva: date,
        datos: DatosDelEvento,
        restringido: CampoRestringido | None,
        justificacion: str | None,
        ahora: datetime,
        solicitud_origen_id: SolicitudId | None = None,
    ) -> ResultadoSolicitud:
        """SRS 4.1, S-08: el Administrador emite SOLO cuando el sujeto es una persona de RRHH.

        No es una aprobacion (el Administrador no aprueba): es una emision excepcional,
        siempre justificada y con su propio evento de auditoria.
        """
        if not puede_emitir_por_excepcion(actor, sujeto_es_rrhh):
            raise NoAutorizado(
                "emitir_por_excepcion", "solo el Administrador, y solo sobre una persona de RRHH"
            )
        texto = _justificacion(justificacion, "emitir_por_excepcion", obligatoria=True)
        s = cls._crear(
            id=id,
            sujeto=sujeto,
            tipo=tipo,
            subtipo=subtipo,
            fecha_efectiva=fecha_efectiva,
            datos=datos,
            restringido=restringido,
            solicitante_id=actor.usuario_id,
            estado=_S.APROBADA,
            ahora=ahora,
            origen=solicitud_origen_id,
        )
        decision = Decision(
            s.id, TipoDeDecision.EMITIR_POR_EXCEPCION, texto, actor.usuario_id, a_utc(ahora)
        )
        return ResultadoSolicitud(
            s,
            decision,
            (
                cls._evento("solicitud.registrada", s, via="administrador"),
                cls._evento("solicitud.emitida_por_excepcion", s, justificada=True),
            ),
        )

    # --- transiciones -------------------------------------------------------------------------

    def _transicion(self, accion: Accion) -> "Solicitud":
        try:
            nuevo = TRANSICIONES[(self.estado, accion)]
        except KeyError:
            raise TransicionInvalida(self.estado.value, accion.value) from None
        return replace(self, estado=nuevo)

    def _exigir_que_decide_rrhh(self, actor: Actor, accion: str) -> None:
        if not puede_decidir(actor):
            raise NoAutorizado(accion, "solo RRHH decide")
        if actor.colaborador_id is not None and actor.colaborador_id == self.colaborador_id:
            raise AutoAprobacionProhibida(accion)  # RF-15, T15

    def aprobar(
        self, actor: Actor, justificacion: str | None, ahora: datetime
    ) -> ResultadoSolicitud:
        """RF-12: la justificacion es opcional al aprobar."""
        self._exigir_que_decide_rrhh(actor, "aprobar")
        texto = _justificacion(justificacion, "aprobar", obligatoria=False)
        nueva = self._transicion(Accion.APROBAR)
        decision = Decision(self.id, TipoDeDecision.APROBAR, texto, actor.usuario_id, a_utc(ahora))
        return ResultadoSolicitud(nueva, decision, (self._evento("solicitud.aprobada", nueva),))

    def rechazar(
        self, actor: Actor, justificacion: str | None, ahora: datetime
    ) -> ResultadoSolicitud:
        """RF-12: rechazar exige justificacion."""
        self._exigir_que_decide_rrhh(actor, "rechazar")
        nueva = self._transicion(Accion.RECHAZAR)
        texto = _justificacion(justificacion, "rechazar", obligatoria=True)
        decision = Decision(self.id, TipoDeDecision.RECHAZAR, texto, actor.usuario_id, a_utc(ahora))
        return ResultadoSolicitud(
            nueva, decision, (self._evento("solicitud.rechazada", nueva, justificada=True),)
        )

    def cancelar_por_solicitante(self, actor: Actor, ahora: datetime) -> ResultadoSolicitud:
        """RF-11: el solicitante cancela mientras este pendiente de aprobacion."""
        if actor.usuario_id != self.solicitante_id:
            raise NoAutorizado("cancelar", "solo quien registro la solicitud puede cancelarla")
        nueva = self._transicion(Accion.CANCELAR_SOLICITANTE)
        decision = Decision(self.id, TipoDeDecision.CANCELAR, None, actor.usuario_id, a_utc(ahora))
        return ResultadoSolicitud(nueva, decision, (self._evento("solicitud.cancelada", nueva),))

    def cancelar_por_rrhh(
        self, actor: Actor, justificacion: str | None, ahora: datetime
    ) -> ResultadoSolicitud:
        """RF-11: RRHH cancela una aprobada (o en error, S-19) mientras no haya tickets creados."""
        self._exigir_que_decide_rrhh(actor, "cancelar")
        if self.estado in (_S.APROBADA, _S.ERROR) and self.tickets:
            raise CancelacionNoPermitida("ya se creo al menos un ticket en GLPI")
        texto = _justificacion(justificacion, "cancelar", obligatoria=False)
        nueva = self._transicion(Accion.CANCELAR_RRHH)
        decision = Decision(self.id, TipoDeDecision.CANCELAR, texto, actor.usuario_id, a_utc(ahora))
        return ResultadoSolicitud(nueva, decision, (self._evento("solicitud.cancelada", nueva),))

    def registrar_ticket_creado(self, clave_de_idempotencia: str) -> "Solicitud":
        """Anota la referencia a un ticket creado; no toca el contenido. Idempotente."""
        if self.estado is not _S.APROBADA:
            raise TransicionInvalida(self.estado.value, "registrar_ticket_creado")
        if clave_de_idempotencia in self.tickets:
            return self
        return replace(self, tickets=(*self.tickets, clave_de_idempotencia))

    def iniciar_ejecucion(self, claves_esperadas: frozenset[str]) -> ResultadoSolicitud:
        """aprobada -> en_ejecucion cuando TODOS los tickets existen en GLPI."""
        nueva = self._transicion(Accion.INICIAR_EJECUCION)
        if not claves_esperadas <= set(self.tickets):
            raise OperacionNoPermitida("faltan tickets por crear en GLPI")
        return ResultadoSolicitud(nueva, None, (self._evento("solicitud.en_ejecucion", nueva),))

    def fallar_emision(self, codigo: str) -> ResultadoSolicitud:
        """RF-18 / RD-12: GLPI rechazo tras los reintentos, o se perdio la copia del soporte."""
        nueva = self._transicion(Accion.FALLAR_EMISION)
        return ResultadoSolicitud(
            nueva, None, (self._evento("solicitud.error", nueva, codigo=codigo),)
        )

    def reintentar(self, actor: Actor) -> ResultadoSolicitud:
        """RF-38: solo el Administrador."""
        if not puede_reintentar_emision(actor.roles):
            raise NoAutorizado("reintentar", "solo el Administrador reintenta")
        nueva = self._transicion(Accion.REINTENTAR)
        return ResultadoSolicitud(nueva, None, (self._evento("solicitud.reintentada", nueva),))

    def cerrar(self, pendientes_de_cierre: int) -> ResultadoSolicitud:
        """RF-26: cierra cuando no queda ningun ticket de cierre sin resolver."""
        nueva = self._transicion(Accion.CERRAR)
        if pendientes_de_cierre > 0:
            raise CierreNoPermitido(pendientes_de_cierre)
        return ResultadoSolicitud(nueva, None, (self._evento("solicitud.cerrada", nueva),))

    def marcar_para_revision(self) -> ResultadoSolicitud:
        """RF-10: una EMG marca las abiertas de otros tipos; no cambia el estado ni el contenido."""
        if not self.abierta:
            raise TransicionInvalida(self.estado.value, "marcar_para_revision")
        if self.para_revision:
            return ResultadoSolicitud(self, None, ())
        nueva = replace(self, para_revision=True)
        return ResultadoSolicitud(
            nueva, None, (self._evento("solicitud.marcada_para_revision", nueva),)
        )
