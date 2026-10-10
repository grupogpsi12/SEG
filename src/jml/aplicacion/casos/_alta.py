"""Alta de una solicitud: lo comun a registrar, emitir y emitir por excepcion (RF-07, RF-09, RF-39).

Traduce los errores de los puertos a errores de dominio: el caso de uso NO comprueba y luego
inserta; deja que la restriccion de la base de datos decida y solo traduce el fallo (RD-01).
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from jml.aplicacion.casos._emision import (
    emitir_tickets,
    guardar_decision,
    marcar_otras_para_revision,
    registrar_eventos,
)
from jml.aplicacion.dtos import NuevaSolicitud, SolicitudRegistrada
from jml.aplicacion.puertos import (
    AlmacenDeSoportes,
    DocumentoYaRegistrado,
    DuplicadoAbierto,
    NuevoId,
    Reloj,
    Repositorios,
    UnidadDeTrabajo,
)
from jml.dominio.catalogo import DatosIngreso
from jml.dominio.colaborador import Colaborador
from jml.dominio.errores import (
    DatoInvalido,
    DocumentoDuplicado,
    NoAutorizado,
    NoEncontrado,
    SolicitudDuplicada,
    SoporteInvalido,
)
from jml.dominio.permisos import Actor
from jml.dominio.solicitud import ResultadoSolicitud
from jml.dominio.soporte import Soporte, SoporteValidado, validar_soporte
from jml.dominio.tipos import EstadoColaborador, EstadoSolicitud, TipoEvento
from jml.dominio.usuarios import usuario_sugerido
from jml.dominio.valores import CalendarioHabil, CampoRestringido, SolicitudId, hoy_en_bogota

# Construye la solicitud con la regla de dominio que corresponda a la via (pendiente o emitida).
type Fabrica = Callable[
    [UnidadDeTrabajo, SolicitudId, Actor, Colaborador, CampoRestringido | None], ResultadoSolicitud
]


@dataclass(frozen=True, slots=True)
class DependenciasDeAlta:
    repos: Repositorios
    soportes: AlmacenDeSoportes
    reloj: Reloj
    calendario: CalendarioHabil
    nuevo_id: NuevoId


def _actor(uow: UnidadDeTrabajo, usuario_id: str) -> Actor:
    actor = uow.usuarios.actor_de(usuario_id)
    if actor is None:
        raise NoAutorizado("registrar", "el usuario no existe o esta inactivo")
    return actor


def _sujeto_de_ingreso(
    uow: UnidadDeTrabajo, e: NuevaSolicitud, datos: DatosIngreso, nuevo_id: NuevoId
) -> Colaborador:
    """S-06: el colaborador se crea al registrar el ingreso, en `por_ingresar`.

    S-26: si el documento ya pertenece a un `por_ingresar` SIN ingreso abierto (se rechazo o
    se cancelo), se reutiliza su registro; es la unica forma de que RD-12 («RRHH vuelve a
    registrar el ingreso») no choque con RD-09 (documento unico).
    """
    existente = uow.colaboradores.por_documento(datos.documento)
    if existente is not None:
        reutilizable = (
            existente.estado is EstadoColaborador.POR_INGRESAR
            and uow.solicitudes.abierta_de_tipo(existente.id, TipoEvento.ING) is None
        )
        if not reutilizable:
            raise DocumentoDuplicado(existente.id)
        if existente.usuario is None:
            raise DatoInvalido("usuario", "el colaborador por ingresar no tiene usuario")
        return Colaborador.por_ingresar(existente.id, datos, e.fecha_efectiva, existente.usuario)
    usuario = usuario_sugerido(datos.nombres, datos.apellidos, uow.colaboradores.usuarios_en_uso())
    return Colaborador.por_ingresar(nuevo_id(), datos, e.fecha_efectiva, usuario)


def dar_de_alta(
    dep: DependenciasDeAlta, e: NuevaSolicitud, fabrica: Fabrica
) -> SolicitudRegistrada:
    ahora = dep.reloj.ahora()
    validado: SoporteValidado | None = None
    if e.tipo is TipoEvento.ING:
        if e.soporte is None:
            raise SoporteInvalido("el ingreso exige el soporte de vinculacion")  # RF-39
        validado = validar_soporte(e.soporte.contenido, e.soporte.nombre)
    elif e.soporte is not None:
        raise DatoInvalido("soporte", "solo aplica a un ingreso")

    nombre_almacenado: str | None = None
    if validado is not None and e.soporte is not None:
        nombre_almacenado = dep.soportes.guardar(e.soporte.contenido)
    try:
        return _en_transaccion(dep, e, fabrica, ahora, validado, nombre_almacenado)
    except BaseException:
        # Compensacion: si la transaccion no se confirmo, no queda una copia huerfana (RD-12).
        if nombre_almacenado is not None:
            dep.soportes.borrar(nombre_almacenado)
        raise


def _en_transaccion(
    dep: DependenciasDeAlta,
    e: NuevaSolicitud,
    fabrica: Fabrica,
    ahora: datetime,
    validado: SoporteValidado | None,
    nombre_almacenado: str | None,
) -> SolicitudRegistrada:
    with dep.repos.unidad_de_trabajo() as uow:
        actor = _actor(uow, e.usuario_id)
        if e.tipo is TipoEvento.ING:
            if not isinstance(e.datos, DatosIngreso):
                raise DatoInvalido("datos", "un ingreso exige los datos de ingreso")
            sujeto = _sujeto_de_ingreso(uow, e, e.datos, dep.nuevo_id)
        else:
            if e.colaborador_id is None:
                raise DatoInvalido("colaborador_id", "obligatorio")
            encontrado = uow.colaboradores.obtener(e.colaborador_id)
            if encontrado is None:
                raise NoEncontrado("colaborador", e.colaborador_id)
            sujeto = encontrado
        restringido = CampoRestringido(e.restringido) if e.restringido is not None else None
        sid = uow.solicitudes.siguiente_id(hoy_en_bogota(ahora).year)

        r = fabrica(uow, sid, actor, sujeto, restringido)
        try:
            if e.tipo is TipoEvento.ING:
                uow.colaboradores.guardar(sujeto)
            uow.solicitudes.guardar(r.solicitud)
        except DuplicadoAbierto as duplicado:
            raise SolicitudDuplicada(duplicado.existente_id.valor) from duplicado
        except DocumentoYaRegistrado as repetido:
            raise DocumentoDuplicado(repetido.existente_id) from repetido

        guardar_decision(uow, r.decision)
        registrar_eventos(uow, actor.usuario_id, r.eventos)
        if validado is not None and nombre_almacenado is not None:
            uow.soportes.guardar(Soporte.pendiente(r.solicitud.id, validado, nombre_almacenado))

        solicitud, encolados = r.solicitud, 0
        marcadas: tuple[SolicitudId, ...] = ()
        if solicitud.estado is EstadoSolicitud.APROBADA:  # emitida: genera los tickets ya
            solicitud, encolados = emitir_tickets(
                uow, solicitud, sujeto, actor.usuario_id, ahora, dep.calendario
            )
            if solicitud.tipo is TipoEvento.EMG:
                marcadas = tuple(
                    m.id for m in marcar_otras_para_revision(uow, solicitud, actor.usuario_id)
                )
        return SolicitudRegistrada(solicitud.id, solicitud.estado, sujeto.id, encolados, marcadas)
