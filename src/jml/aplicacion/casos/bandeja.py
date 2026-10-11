"""Bandeja de salida: crea los tickets en GLPI con reintentos e idempotencia (RF-18, RF-38).

Es el unico lugar que habla con GLPI para escribir. Cada entrada se procesa en su propia
unidad de trabajo, y las llamadas a GLPI se hacen FUERA de ellas (no se retiene una
transaccion mientras se espera la red). Como `crear_ticket` es idempotente por clave, un
timeout tras crear solo obliga a reintentar: nunca duplica.
"""

from dataclasses import dataclass, field

from jml.aplicacion.bandeja import EntradaDeBandeja, EstadoDeEntrada
from jml.aplicacion.casos._emision import registrar_eventos
from jml.aplicacion.dtos import ResultadoDeBandeja
from jml.aplicacion.puertos import (
    AlmacenDeSoportes,
    ErrorDeSistemaDeTickets,
    GlpiRechazo,
    Reloj,
    Repositorios,
    SistemaDeTickets,
    SoporteNoDisponible,
    UnidadDeTrabajo,
)
from jml.dominio.auditoria import EventoDeAuditoria
from jml.dominio.colaborador import Colaborador
from jml.dominio.errores import NoAutorizado, NoEncontrado
from jml.dominio.soporte import Soporte
from jml.dominio.tickets import TicketSeguido
from jml.dominio.tipos import EstadoDeSoporte, EstadoSolicitud
from jml.dominio.valores import SolicitudId

ACTOR_DEL_WORKER = "sistema:worker"


@dataclass(frozen=True, slots=True)
class DependenciasDeBandeja:
    repos: Repositorios
    glpi: SistemaDeTickets
    soportes: AlmacenDeSoportes
    reloj: Reloj


@dataclass
class _Conteo:
    procesadas: int = 0
    creadas: int = 0
    reintentos: int = 0
    en_error: list[SolicitudId] = field(default_factory=list)
    en_ejecucion: list[SolicitudId] = field(default_factory=list)


class ProcesarBandeja:
    def __init__(self, dependencias: DependenciasDeBandeja) -> None:
        self._dep = dependencias

    def ejecutar(self, limite: int = 50) -> ResultadoDeBandeja:
        dep = self._dep
        with dep.repos.unidad_de_trabajo() as uow:
            claves = [e.clave for e in uow.bandeja.vencidas(dep.reloj.ahora(), limite)]
        cuenta = _Conteo()
        for clave in claves:
            self._procesar(clave, cuenta)
        return ResultadoDeBandeja(
            cuenta.procesadas,
            cuenta.creadas,
            cuenta.reintentos,
            tuple(cuenta.en_error),
            tuple(cuenta.en_ejecucion),
        )

    # --- una entrada -----------------------------------------------------------------------

    def _cargar(self, clave: str) -> tuple[EntradaDeBandeja, Colaborador, Soporte | None] | None:
        """Lee lo necesario; None si la entrada ya no debe procesarse."""
        dep = self._dep
        with dep.repos.unidad_de_trabajo() as uow:
            entrada = uow.bandeja.obtener(clave)
            if entrada is None or entrada.estado is not EstadoDeEntrada.PENDIENTE:
                return None
            sid = SolicitudId(entrada.solicitud_id)
            solicitud = uow.solicitudes.obtener(sid)
            if solicitud is None:
                raise NoEncontrado("solicitud", sid.valor)
            if solicitud.estado is EstadoSolicitud.ERROR:
                return None  # espera el reintento del Administrador (RF-38)
            if solicitud.estado is not EstadoSolicitud.APROBADA:
                uow.bandeja.guardar(entrada.descartada())  # cancelada o ya cerrada: no se crea
                return None
            colaborador = uow.colaboradores.obtener(solicitud.colaborador_id)
            if colaborador is None:
                raise NoEncontrado("colaborador", solicitud.colaborador_id)
            return entrada, colaborador, uow.soportes.obtener(sid)

    def _procesar(self, clave: str, cuenta: _Conteo) -> None:
        cargado = self._cargar(clave)
        if cargado is None:
            return
        entrada, colaborador, soporte = cargado
        cuenta.procesadas += 1
        try:
            id_usuario = colaborador.id_usuario_glpi or self._dep.glpi.asegurar_usuario(colaborador)
            id_documento, soporte_nuevo, copia = self._soporte(entrada, soporte)
            creado = self._dep.glpi.crear_ticket(entrada.ticket)
            if entrada.ticket.adjunta_soporte and id_documento is not None:
                self._dep.glpi.vincular_documento(id_documento, creado.id_externo)
        except SoporteNoDisponible:
            self._a_error(entrada, "soporte_perdido", cuenta)  # RD-12
            return
        except ErrorDeSistemaDeTickets as error:
            self._fallo(entrada, error.codigo, cuenta)
            return
        self._confirmar(entrada, colaborador, id_usuario, creado.id_externo, soporte_nuevo, cuenta)
        if copia is not None:
            self._dep.soportes.borrar(copia)  # tras verificar el hash y confirmar (RF-40)

    def _soporte(
        self, entrada: EntradaDeBandeja, soporte: Soporte | None
    ) -> tuple[str | None, Soporte | None, str | None]:
        """Sube el soporte UNA sola vez (idempotente por contenido) y verifica su hash.

        Devuelve (id del documento, soporte actualizado si cambio, copia local a borrar).
        """
        if not entrada.ticket.adjunta_soporte or soporte is None:
            return None, None, None
        if soporte.estado is EstadoDeSoporte.SUBIDO:
            return soporte.id_documento_glpi, None, None
        contenido = self._dep.soportes.leer(
            soporte.nombre_almacenado
        )  # puede lanzar SoporteNoDisponible
        documento = self._dep.glpi.subir_documento(soporte.nombre_original, contenido)
        if self._dep.glpi.hash_de_documento(documento) != soporte.sha256:
            raise GlpiRechazo("el hash del documento no coincide")
        return documento, soporte.subido(documento), soporte.nombre_almacenado

    def _confirmar(
        self,
        entrada: EntradaDeBandeja,
        colaborador: Colaborador,
        id_usuario: str,
        id_externo: str,
        soporte_nuevo: Soporte | None,
        cuenta: _Conteo,
    ) -> None:
        dep = self._dep
        sid = SolicitudId(entrada.solicitud_id)
        with dep.repos.unidad_de_trabajo() as uow:
            if colaborador.id_usuario_glpi is None:
                uow.colaboradores.guardar(colaborador.con_usuario_glpi(id_usuario))
            if soporte_nuevo is not None:
                uow.soportes.guardar(soporte_nuevo)
                uow.auditoria.registrar(
                    ACTOR_DEL_WORKER,
                    EventoDeAuditoria(
                        "soporte.subido", sid.valor, {"sha256": soporte_nuevo.sha256.valor}
                    ),
                )
            seguido = uow.tickets.por_clave(entrada.clave) or TicketSeguido(entrada.ticket)
            uow.tickets.guardar(seguido.creado(id_externo))
            uow.bandeja.guardar(entrada.enviada())
            solicitud = uow.solicitudes.obtener(sid)
            if solicitud is None:
                raise NoEncontrado("solicitud", sid.valor)
            if solicitud.estado is not EstadoSolicitud.APROBADA:
                # R1: se cancelo mientras GLPI creaba el ticket. El ticket YA existe en GLPI:
                # se registra y se audita como huerfano para que TI lo cierre; se respeta la cancelacion.
                uow.auditoria.registrar(
                    ACTOR_DEL_WORKER,
                    EventoDeAuditoria(
                        "ticket.huerfano",
                        entrada.clave,
                        {"id_externo": id_externo, "solicitud_estado": solicitud.estado.value},
                    ),
                )
                cuenta.creadas += 1
                return
            actualizada = solicitud.registrar_ticket_creado(entrada.clave)
            uow.auditoria.registrar(
                ACTOR_DEL_WORKER,
                EventoDeAuditoria(
                    "ticket.creado",
                    entrada.clave,
                    {"cola": entrada.ticket.cola.value, "id_externo": id_externo},
                ),
            )
            esperadas = frozenset(e.clave for e in uow.bandeja.de_solicitud(sid))
            if esperadas <= set(actualizada.tickets):
                r = actualizada.iniciar_ejecucion(esperadas)
                actualizada = r.solicitud
                registrar_eventos(uow, ACTOR_DEL_WORKER, r.eventos)
                cuenta.en_ejecucion.append(sid)
            uow.solicitudes.guardar(actualizada)
        cuenta.creadas += 1

    def _fallo(self, entrada: EntradaDeBandeja, codigo: str, cuenta: _Conteo) -> None:
        """Un fallo de GLPI: espera creciente; al 10.º intento la solicitud pasa a `error`."""
        dep = self._dep
        ahora = dep.reloj.ahora()
        with dep.repos.unidad_de_trabajo() as uow:
            nueva = entrada.fallo(codigo, ahora)
            uow.bandeja.guardar(nueva)
            if nueva.estado is EstadoDeEntrada.FALLIDA:
                self._marcar_error(uow, SolicitudId(entrada.solicitud_id), codigo, cuenta)
            else:
                cuenta.reintentos += 1

    def _a_error(self, entrada: EntradaDeBandeja, codigo: str, cuenta: _Conteo) -> None:
        with self._dep.repos.unidad_de_trabajo() as uow:
            self._marcar_error(uow, SolicitudId(entrada.solicitud_id), codigo, cuenta)

    @staticmethod
    def _marcar_error(uow: UnidadDeTrabajo, sid: SolicitudId, codigo: str, cuenta: _Conteo) -> None:
        solicitud = uow.solicitudes.obtener(sid)
        if solicitud is None:
            raise NoEncontrado("solicitud", sid.valor)
        if solicitud.estado is not EstadoSolicitud.APROBADA:
            return
        r = solicitud.fallar_emision(codigo)
        uow.solicitudes.guardar(r.solicitud)
        registrar_eventos(uow, ACTOR_DEL_WORKER, r.eventos)
        cuenta.en_error.append(sid)


class ReintentarEmision:
    """RF-38: el Administrador devuelve a la bandeja una solicitud en `error`."""

    def __init__(self, repos: Repositorios, reloj: Reloj) -> None:
        self._repos = repos
        self._reloj = reloj

    def ejecutar(self, usuario_id: str, solicitud_id: SolicitudId) -> None:
        ahora = self._reloj.ahora()
        with self._repos.unidad_de_trabajo() as uow:
            actor = uow.usuarios.actor_de(usuario_id)
            if actor is None:
                raise NoAutorizado("reintentar", "el usuario no existe o esta inactivo")
            solicitud = uow.solicitudes.obtener(solicitud_id)
            if solicitud is None:
                raise NoEncontrado("solicitud", solicitud_id.valor)
            r = solicitud.reintentar(actor)
            uow.solicitudes.guardar(r.solicitud)
            registrar_eventos(uow, actor.usuario_id, r.eventos)
            for entrada in uow.bandeja.de_solicitud(solicitud_id):
                if entrada.estado in (EstadoDeEntrada.PENDIENTE, EstadoDeEntrada.FALLIDA):
                    uow.bandeja.guardar(entrada.reiniciada(ahora))
