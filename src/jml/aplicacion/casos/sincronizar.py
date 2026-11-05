"""Sincronizacion con GLPI: tickets, cuentas derivadas, cierre, activos y licencias (RF-22 a RF-27).

GLPI es la fuente de la verdad sobre cada ticket (ADR-001). Aqui solo se interpreta lo que
informa. Cada solicitud se procesa en su propia unidad de trabajo, y repetir la sincronizacion
con los mismos datos no cambia nada (ni escribe auditoria).
"""

from dataclasses import dataclass
from datetime import datetime

from jml.aplicacion.casos._emision import registrar_eventos
from jml.aplicacion.dtos import ResultadoDeSincronizacion
from jml.aplicacion.puertos import (
    ErrorDeSistemaDeTickets,
    Reloj,
    Repositorios,
    SistemaDeTickets,
    UnidadDeTrabajo,
)
from jml.dominio.auditoria import EventoDeAuditoria
from jml.dominio.catalogo import DatosCambioDepartamento, DatosCambioSucursal
from jml.dominio.colaborador import Colaborador
from jml.dominio.cuentas import derivar_cuenta
from jml.dominio.errores import ErrorDeDominio, NoEncontrado, OperacionNoPermitida
from jml.dominio.resolucion import (
    cierre_incompleto,
    estado_derivado_del_colaborador,
    pendientes_de_cierre,
)
from jml.dominio.solicitud import Solicitud
from jml.dominio.tickets import Observacion, TicketSeguido
from jml.dominio.tipos import EstadoSolicitud, TipoEvento
from jml.dominio.valores import SolicitudId

ACTOR_DEL_WORKER = "sistema:worker"


@dataclass(frozen=True, slots=True)
class DependenciasDeSincronizacion:
    repos: Repositorios
    glpi: SistemaDeTickets
    reloj: Reloj


def _contenido(o: Observacion | None) -> tuple[int, bool, int] | None:
    return None if o is None else (int(o.estado), o.tiene_solucion, o.documentos)


class SincronizarTickets:
    def __init__(self, dependencias: DependenciasDeSincronizacion) -> None:
        self._dep = dependencias

    def ejecutar(self) -> ResultadoDeSincronizacion:
        dep = self._dep
        inicio = dep.reloj.ahora()
        with dep.repos.unidad_de_trabajo() as uow:
            creados = list(uow.tickets.creados())
        ids = [t.id_externo for t in creados if t.id_externo is not None]
        try:
            observaciones = dict(dep.glpi.leer_tickets(ids))
        except ErrorDeSistemaDeTickets:
            return self._registrar(
                inicio, "error", 0, 1
            )  # el dashboard ve la hora del ultimo exito
        solicitudes = sorted(
            {SolicitudId(t.ticket.solicitud_id) for t in creados}, key=lambda s: s.valor
        )
        errores = 0
        for sid in solicitudes:
            try:
                self._solicitud(sid, observaciones)
            except Exception as error:
                # Un dato corrupto o un rechazo de la base en una solicitud no detiene a las demas.
                # Su transaccion ya se deshizo; el fallo queda en la auditoria con un codigo
                # estable: el del dominio o `error_inesperado` (el mensaje podria llevar datos).
                errores += 1
                codigo = error.codigo if isinstance(error, ErrorDeDominio) else "error_inesperado"
                self._auditar_fallo(sid, codigo)
        return self._registrar(
            inicio, "ok" if errores == 0 else "error", len(observaciones), errores
        )

    def _auditar_fallo(self, sid: SolicitudId, codigo: str) -> None:
        with self._dep.repos.unidad_de_trabajo() as uow:
            uow.auditoria.registrar(
                ACTOR_DEL_WORKER,
                EventoDeAuditoria(
                    "sincronizacion.solicitud_fallida", sid.valor, {"codigo": codigo}
                ),
            )

    def _registrar(
        self, inicio: datetime, resultado: str, leidos: int, errores: int
    ) -> ResultadoDeSincronizacion:
        res = ResultadoDeSincronizacion(inicio, self._dep.reloj.ahora(), resultado, leidos, errores)
        with self._dep.repos.unidad_de_trabajo() as uow:
            uow.sincronizaciones.registrar(res)
        return res

    def _solicitud(self, sid: SolicitudId, observaciones: dict[str, Observacion]) -> None:
        ahora = self._dep.reloj.ahora()
        with self._dep.repos.unidad_de_trabajo() as uow:
            solicitud = uow.solicitudes.obtener(sid)
            if solicitud is None:
                raise NoEncontrado("solicitud", sid.valor)
            colaborador = uow.colaboradores.obtener(solicitud.colaborador_id)
            if colaborador is None:
                raise NoEncontrado("colaborador", solicitud.colaborador_id)
            creados = sorted(
                (t for t in uow.tickets.de_solicitud(sid) if t.id_externo is not None),
                key=lambda t: (
                    t.ticket.emitido_en,
                    t.ticket.vence_en,
                    t.ticket.clave_de_idempotencia,
                ),
            )
            for seguido in creados:
                self._ticket(uow, solicitud, colaborador, seguido, observaciones, ahora)
            self._cierre_y_colaborador(uow, solicitud, colaborador)

    def _ticket(
        self,
        uow: UnidadDeTrabajo,
        solicitud: Solicitud,
        colaborador: Colaborador,
        seguido: TicketSeguido,
        observaciones: dict[str, Observacion],
        ahora: datetime,
    ) -> None:
        nueva = observaciones.get(seguido.id_externo or "")
        if nueva is None:
            return
        anterior = seguido.observacion
        observado = seguido.observar(nueva)
        actual = observado.observacion
        if actual is None:  # pragma: no cover - observar() siempre deja una observacion
            return
        if _contenido(anterior) != _contenido(actual) or observado.reabierto != seguido.reabierto:
            uow.tickets.guardar(observado)  # solo si cambio algo: sin churn cada 5 minutos
            clave = seguido.ticket.clave_de_idempotencia
            uow.auditoria.registrar(
                ACTOR_DEL_WORKER,
                EventoDeAuditoria(
                    "ticket.estado_sincronizado",
                    clave,
                    {
                        "estado": actual.estado.name,
                        "tiene_solucion": actual.tiene_solucion,
                        "documentos": actual.documentos,
                    },
                ),
            )
            if observado.reabierto and not seguido.reabierto:
                uow.auditoria.registrar(  # RF-25
                    ACTOR_DEL_WORKER, EventoDeAuditoria("ticket.reabierto", clave, {})
                )
            if cierre_incompleto(observado) and not cierre_incompleto(seguido):
                uow.auditoria.registrar(  # RF-24
                    ACTOR_DEL_WORKER, EventoDeAuditoria("ticket.cierre_incompleto", clave, {})
                )
        sistema = seguido.ticket.sistema
        if sistema is None:
            return
        resultado = derivar_cuenta(
            uow.cuentas.obtener(solicitud.colaborador_id, sistema),
            seguido.ticket,
            anterior,
            actual,
            colaborador.id,
            ahora,
        )
        if resultado.cuenta is not None and resultado.cambio is not None:
            uow.cuentas.guardar(resultado.cuenta)
            uow.cuentas.agregar_historial(resultado.cambio)
        registrar_eventos(uow, ACTOR_DEL_WORKER, resultado.eventos)

    def _cierre_y_colaborador(
        self, uow: UnidadDeTrabajo, solicitud: Solicitud, colaborador: Colaborador
    ) -> None:
        seguidos = list(uow.tickets.de_solicitud(solicitud.id))
        actual = colaborador
        derivado = estado_derivado_del_colaborador(solicitud, seguidos)
        if derivado is not None and derivado is not colaborador.estado:
            try:
                actual = colaborador.con_estado(derivado)
            except OperacionNoPermitida:
                actual = colaborador  # p. ej. una reapertura no devuelve al colaborador atras
            else:
                uow.auditoria.registrar(
                    ACTOR_DEL_WORKER,
                    EventoDeAuditoria(
                        "colaborador.estado_derivado",
                        colaborador.id,
                        {"anterior": colaborador.estado.value, "nuevo": derivado.value},
                    ),
                )
        if solicitud.estado is EstadoSolicitud.EN_EJECUCION and pendientes_de_cierre(seguidos) == 0:
            r = solicitud.cerrar(0)  # RF-26
            uow.solicitudes.guardar(r.solicitud)
            registrar_eventos(uow, ACTOR_DEL_WORKER, r.eventos)
            actual = self._aplicar_cambio_de_perfil(r.solicitud, actual)  # S-20
        if actual is not colaborador:
            uow.colaboradores.guardar(actual)

    @staticmethod
    def _aplicar_cambio_de_perfil(solicitud: Solicitud, c: Colaborador) -> Colaborador:
        """S-20: CDP y CSU actualizan los datos laborales al cerrarse."""
        if solicitud.tipo is TipoEvento.CDP and isinstance(
            solicitud.datos, DatosCambioDepartamento
        ):
            d = solicitud.datos
            return c.con_cambio_de_departamento(
                d.departamento_nuevo, d.cargo_nuevo, d.jefe_nuevo_id
            )
        if solicitud.tipo is TipoEvento.CSU and isinstance(solicitud.datos, DatosCambioSucursal):
            return c.con_cambio_de_sede(solicitud.datos.sede_nueva)
        return c


class SincronizarActivos:
    """RF-23: copia los activos y licencias que GLPI tiene asignados a cada colaborador."""

    def __init__(self, dependencias: DependenciasDeSincronizacion) -> None:
        self._dep = dependencias

    def ejecutar(self) -> ResultadoDeSincronizacion:
        dep = self._dep
        inicio = dep.reloj.ahora()
        with dep.repos.unidad_de_trabajo() as uow:
            colaboradores = list(uow.colaboradores.con_usuario_glpi())
        leidos = errores = 0
        for c in colaboradores:
            if c.id_usuario_glpi is None:
                continue
            try:
                activos = dep.glpi.leer_activos(c.id_usuario_glpi)
                licencias = dep.glpi.leer_licencias(c.id_usuario_glpi)
            except ErrorDeSistemaDeTickets:
                errores += 1
                continue
            with dep.repos.unidad_de_trabajo() as uow:
                uow.activos.reemplazar(c.id, activos, licencias)
            leidos += 1
        return ResultadoDeSincronizacion(
            inicio, dep.reloj.ahora(), "ok" if errores == 0 else "error", leidos, errores
        )
