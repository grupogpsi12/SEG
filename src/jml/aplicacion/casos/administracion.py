"""Area de administracion (RF-37, ADR-027): matriz de perfiles y roles, solo el Administrador.

Cada cambio pasa por el dominio (validacion de la matriz, incompatibilidad de roles: RF-05) y
queda en la auditoria (RF-35). Nadie se cambia sus propios roles: el Administrador no puede
quitarse el rol por accidente ni darse otro.
"""

from jml.aplicacion.dtos import FilaDeUsuario
from jml.aplicacion.puertos import Repositorios, UnidadDeTrabajo
from jml.dominio.auditoria import EventoDeAuditoria
from jml.dominio.errores import NoAutorizado, NoEncontrado, OperacionNoPermitida
from jml.dominio.perfiles import PerfilDeAcceso
from jml.dominio.permisos import Actor, UsuarioDelSistema
from jml.dominio.tipos import Rol


def _administrador(uow: UnidadDeTrabajo, usuario_id: str) -> Actor:
    actor = uow.usuarios.actor_de(usuario_id)
    if actor is None or Rol.ADMINISTRADOR not in actor.roles:
        raise NoAutorizado("administracion", "solo el Administrador del sistema")
    return actor


def _texto_de_roles(roles: frozenset[Rol]) -> str:
    return ",".join(sorted(r.value for r in roles)) or "-"


class ConsultarMatriz:
    def __init__(self, repos: Repositorios) -> None:
        self._repos = repos

    def ejecutar(self, usuario_id: str) -> tuple[PerfilDeAcceso, ...]:
        with self._repos.unidad_de_trabajo() as uow:
            _administrador(uow, usuario_id)
            return tuple(uow.perfiles.todos())


class GuardarPerfil:
    """Crea o reemplaza el perfil de un (departamento, sede). Solo afecta eventos futuros."""

    def __init__(self, repos: Repositorios) -> None:
        self._repos = repos

    def ejecutar(self, usuario_id: str, perfil: PerfilDeAcceso) -> None:
        with self._repos.unidad_de_trabajo() as uow:
            actor = _administrador(uow, usuario_id)
            anterior = uow.perfiles.obtener(perfil.departamento, perfil.sede)
            if anterior == perfil:
                return
            uow.perfiles.guardar(perfil)
            uow.auditoria.registrar(
                actor.usuario_id,
                EventoDeAuditoria(
                    "perfil.actualizado",
                    f"{perfil.departamento}/{perfil.sede}"[:80],
                    {"nuevo": anterior is None},
                ),
            )


class ConsultarUsuarios:
    def __init__(self, repos: Repositorios) -> None:
        self._repos = repos

    def ejecutar(self, usuario_id: str) -> tuple[FilaDeUsuario, ...]:
        with self._repos.unidad_de_trabajo() as uow:
            _administrador(uow, usuario_id)
            filas = []
            for u in uow.usuarios.todos():
                c = (
                    None
                    if u.colaborador_id is None
                    else uow.colaboradores.obtener(u.colaborador_id)
                )
                filas.append(
                    FilaDeUsuario(
                        u.id,
                        None if c is None else c.nombre_completo,
                        tuple(sorted(u.roles, key=lambda r: r.value)),
                        u.activo,
                    )
                )
            return tuple(filas)


class CambiarRoles:
    def __init__(self, repos: Repositorios) -> None:
        self._repos = repos

    def ejecutar(self, usuario_id: str, objetivo_id: str, roles: frozenset[Rol]) -> None:
        with self._repos.unidad_de_trabajo() as uow:
            actor = _administrador(uow, usuario_id)
            if objetivo_id == actor.usuario_id:
                raise OperacionNoPermitida("nadie cambia sus propios roles")
            actual = next((u for u in uow.usuarios.todos() if u.id == objetivo_id), None)
            if actual is None:
                raise NoEncontrado("usuario", objetivo_id)
            # RF-05: el dominio rechaza combinaciones incompatibles al construir el usuario.
            nuevo = UsuarioDelSistema(actual.id, actual.colaborador_id, roles, actual.activo)
            if nuevo.roles == actual.roles:
                return
            uow.usuarios.guardar(nuevo)
            uow.auditoria.registrar(
                actor.usuario_id,
                EventoDeAuditoria(
                    "usuario.roles_cambiados",
                    objetivo_id,
                    {"antes": _texto_de_roles(actual.roles), "despues": _texto_de_roles(roles)},
                ),
            )
