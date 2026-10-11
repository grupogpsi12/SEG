"""Listas para las vistas (ADR-025): mis solicitudes, bandeja de RRHH y subordinados del jefe.

Devuelven DTOs sin campos restringidos. Los permisos se verifican aqui y no solo en la vista:
una vista que olvide el chequeo no abre la informacion (RF-03).
"""

from collections.abc import Sequence

from jml.aplicacion.dtos import FilaDeSolicitud, OpcionDeColaborador, PerfilDeUsuario
from jml.aplicacion.puertos import Repositorios, UnidadDeTrabajo
from jml.dominio.errores import DatoInvalido, NoAutorizado
from jml.dominio.permisos import Actor
from jml.dominio.solicitud import Solicitud
from jml.dominio.tipos import EstadoSolicitud, Rol
from jml.dominio.valores import Documento


def _actor(uow: UnidadDeTrabajo, usuario_id: str) -> Actor:
    actor = uow.usuarios.actor_de(usuario_id)
    if actor is None:
        raise NoAutorizado("consultar", "el usuario no existe o esta inactivo")
    return actor


def _fila(uow: UnidadDeTrabajo, s: Solicitud, usuario_id: str) -> FilaDeSolicitud:
    c = uow.colaboradores.obtener(s.colaborador_id)
    pendiente = s.estado is EstadoSolicitud.PENDIENTE_APROBACION
    return FilaDeSolicitud(
        id=s.id,
        tipo=s.tipo,
        estado=s.estado,
        fecha_efectiva=s.fecha_efectiva,
        creada_en=s.creada_en,
        colaborador_id=s.colaborador_id,
        colaborador_nombre=c.nombre_completo if c is not None else s.colaborador_id,
        para_revision=s.para_revision,
        cancelable=pendiente and s.solicitante_id == usuario_id,
    )


class MisSolicitudes:
    """RF-11: el solicitante consulta las que registro."""

    def __init__(self, repos: Repositorios) -> None:
        self._repos = repos

    def ejecutar(self, usuario_id: str) -> tuple[FilaDeSolicitud, ...]:
        with self._repos.unidad_de_trabajo() as uow:
            return tuple(
                _fila(uow, s, usuario_id) for s in uow.solicitudes.del_solicitante(usuario_id)
            )


class PendientesDeAprobacion:
    """RF-12: la bandeja de RRHH."""

    def __init__(self, repos: Repositorios) -> None:
        self._repos = repos

    def ejecutar(self, usuario_id: str) -> tuple[FilaDeSolicitud, ...]:
        with self._repos.unidad_de_trabajo() as uow:
            if Rol.RRHH not in _actor(uow, usuario_id).roles:
                raise NoAutorizado("bandeja", "solo RRHH ve las pendientes de aprobacion")
            return tuple(
                _fila(uow, s, usuario_id) for s in uow.solicitudes.pendientes_de_aprobacion()
            )


class SubordinadosDe:
    """El jefe elige entre sus subordinados directos al pedir un CDP o un CSU."""

    def __init__(self, repos: Repositorios) -> None:
        self._repos = repos

    def ejecutar(self, usuario_id: str) -> Sequence[OpcionDeColaborador]:
        with self._repos.unidad_de_trabajo() as uow:
            actor = _actor(uow, usuario_id)
            if actor.colaborador_id is None:
                return ()
            return tuple(
                OpcionDeColaborador(c.id, c.nombre_completo)
                for c in uow.colaboradores.subordinados_de(actor.colaborador_id)
            )


class MiPerfil:
    """Roles y colaborador del usuario: la vista decide con ellos el menu y los formularios."""

    def __init__(self, repos: Repositorios) -> None:
        self._repos = repos

    def ejecutar(self, usuario_id: str) -> PerfilDeUsuario:
        with self._repos.unidad_de_trabajo() as uow:
            actor = _actor(uow, usuario_id)
            c = (
                None
                if actor.colaborador_id is None
                else uow.colaboradores.obtener(actor.colaborador_id)
            )
            mio = None if c is None else OpcionDeColaborador(c.id, c.nombre_completo)
            return PerfilDeUsuario(actor.usuario_id, actor.roles, mio)


class ColaboradorPorDocumento:
    """Quien emite (RRHH, o el Administrador por excepcion) busca a la persona por documento."""

    def __init__(self, repos: Repositorios) -> None:
        self._repos = repos

    def ejecutar(self, usuario_id: str, documento: str) -> OpcionDeColaborador | None:
        with self._repos.unidad_de_trabajo() as uow:
            if not _actor(uow, usuario_id).roles & {Rol.RRHH, Rol.ADMINISTRADOR}:
                raise NoAutorizado("buscar_colaborador", "solo quien emite busca por documento")
            try:
                clave = Documento(documento)
            except DatoInvalido:
                return None  # un documento invalido no es un error: no hay nadie con ese numero
            c = uow.colaboradores.por_documento(clave)
            return None if c is None else OpcionDeColaborador(c.id, c.nombre_completo)
