"""Area de administracion (RF-37, ADR-027): matriz de perfiles y roles, solo el Administrador.

Cada cambio pasa por el dominio (validacion de la matriz, incompatibilidad de roles: RF-05) y
queda en la auditoria (RF-35). Nadie se cambia sus propios roles: el Administrador no puede
quitarse el rol por accidente ni darse otro.
"""

from jml.aplicacion.dtos import FilaDeUsuario
from jml.aplicacion.puertos import (
    AdministradorDeCuentas,
    CuentaCreada,
    CuentaRechazada,
    IdentidadNoDisponible,
    Repositorios,
    UnidadDeTrabajo,
)
from jml.dominio.auditoria import EventoDeAuditoria
from jml.dominio.errores import DatoInvalido, NoAutorizado, NoEncontrado, OperacionNoPermitida
from jml.dominio.perfiles import PerfilDeAcceso
from jml.dominio.permisos import Actor, UsuarioDelSistema, validar_roles
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
    def __init__(self, repos: Repositorios, cuentas: AdministradorDeCuentas | None = None) -> None:
        self._repos = repos
        self._cuentas = cuentas

    def _correos(self) -> dict[str, str]:
        try:
            return {} if self._cuentas is None else dict(self._cuentas.correos())
        except (IdentidadNoDisponible, CuentaRechazada):
            return {}  # la lista sigue siendo util sin los correos

    def ejecutar(self, usuario_id: str) -> tuple[FilaDeUsuario, ...]:
        with self._repos.unidad_de_trabajo() as uow:
            _administrador(uow, usuario_id)
        correos = self._correos()
        with self._repos.unidad_de_trabajo() as uow:
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
                        u.colaborador_id,
                        correos.get(u.id),
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


# --- CRUD de usuarios (ADR-035) ---------------------------------------------------------------


def _validar_alta(uow: UnidadDeTrabajo, roles: frozenset[Rol], colaborador_id: str | None) -> None:
    if not roles:
        raise DatoInvalido("roles", "elija al menos uno")
    validar_roles(roles)  # RF-05: antes de tocar Supabase
    _validar_colaborador(uow, colaborador_id, None)


def _validar_colaborador(
    uow: UnidadDeTrabajo, colaborador_id: str | None, objetivo_id: str | None
) -> None:
    if colaborador_id is None:
        return
    if uow.colaboradores.obtener(colaborador_id) is None:
        raise DatoInvalido("colaborador", "no existe")
    if any(
        u.colaborador_id == colaborador_id and u.activo and u.id != objetivo_id
        for u in uow.usuarios.todos()
    ):
        raise OperacionNoPermitida("ese colaborador ya tiene una cuenta activa")


def _otro_usuario(uow: UnidadDeTrabajo, actor: Actor, objetivo_id: str) -> UsuarioDelSistema:
    if objetivo_id == actor.usuario_id:
        raise OperacionNoPermitida("nadie modifica su propia cuenta")
    actual = next((u for u in uow.usuarios.todos() if u.id == objetivo_id), None)
    if actual is None:
        raise NoEncontrado("usuario", objetivo_id)
    return actual


class CrearUsuario:
    def __init__(self, repos: Repositorios, cuentas: AdministradorDeCuentas) -> None:
        self._repos = repos
        self._cuentas = cuentas

    def ejecutar(
        self, usuario_id: str, correo: str, roles: frozenset[Rol], colaborador_id: str | None
    ) -> CuentaCreada:
        with self._repos.unidad_de_trabajo() as uow:
            actor = _administrador(uow, usuario_id)
            _validar_alta(uow, roles, colaborador_id)
        creada = self._cuentas.crear(correo)
        try:
            with self._repos.unidad_de_trabajo() as uow:
                uow.usuarios.guardar(UsuarioDelSistema(creada.id, colaborador_id, roles))
                uow.auditoria.registrar(
                    actor.usuario_id,
                    EventoDeAuditoria(
                        "usuario.creado", creada.id, {"roles": _texto_de_roles(roles)}
                    ),
                )
        except Exception:
            self._cuentas.eliminar(creada.id)  # sin cuenta huerfana en Supabase
            raise
        return creada


class VincularUsuario:
    """Registra en esta base una cuenta que ya existe en Supabase. No usa el servicio de cuentas: un
    id inventado no da acceso, porque Supabase autentica ese id con contrasena y TOTP (RF-06)."""

    def __init__(self, repos: Repositorios) -> None:
        self._repos = repos

    def ejecutar(
        self, usuario_id: str, objetivo_id: str, roles: frozenset[Rol], colaborador_id: str | None
    ) -> None:
        with self._repos.unidad_de_trabajo() as uow:
            actor = _administrador(uow, usuario_id)
            _validar_alta(uow, roles, colaborador_id)
            if any(u.id == objetivo_id for u in uow.usuarios.todos()):
                raise OperacionNoPermitida("esa cuenta ya existe en esta base")
            uow.usuarios.guardar(UsuarioDelSistema(objetivo_id, colaborador_id, roles))
            uow.auditoria.registrar(
                actor.usuario_id,
                EventoDeAuditoria(
                    "usuario.vinculado", objetivo_id, {"roles": _texto_de_roles(roles)}
                ),
            )


class CambiarColaborador:
    def __init__(self, repos: Repositorios) -> None:
        self._repos = repos

    def ejecutar(self, usuario_id: str, objetivo_id: str, colaborador_id: str | None) -> None:
        with self._repos.unidad_de_trabajo() as uow:
            actor = _administrador(uow, usuario_id)
            actual = _otro_usuario(uow, actor, objetivo_id)
            _validar_colaborador(uow, colaborador_id, objetivo_id)
            if actual.colaborador_id == colaborador_id:
                return
            uow.usuarios.guardar(
                UsuarioDelSistema(actual.id, colaborador_id, actual.roles, actual.activo)
            )
            uow.auditoria.registrar(
                actor.usuario_id,
                EventoDeAuditoria(
                    "usuario.colaborador_cambiado",
                    objetivo_id,
                    {"antes": actual.colaborador_id or "-", "despues": colaborador_id or "-"},
                ),
            )


class _CambioDeAcceso:
    def __init__(self, repos: Repositorios, cuentas: AdministradorDeCuentas) -> None:
        self._repos = repos
        self._cuentas = cuentas

    def _cambiar(self, usuario_id: str, objetivo_id: str, activo: bool, evento: str) -> None:
        with self._repos.unidad_de_trabajo() as uow:
            actor = _administrador(uow, usuario_id)
            actual = _otro_usuario(uow, actor, objetivo_id)
        if actual.activo == activo:
            return
        # Primero Supabase: si falla, el acceso local queda como estaba y se puede repetir.
        try:
            (self._cuentas.reactivar if activo else self._cuentas.desactivar)(objetivo_id)
        except CuentaRechazada as e:
            # Sin cuenta en Supabase igual se retira el acceso local; reactivarla no tiene sentido.
            if activo or e.codigo != "user_not_found":
                raise
        with self._repos.unidad_de_trabajo() as uow:
            uow.usuarios.guardar(
                UsuarioDelSistema(actual.id, actual.colaborador_id, actual.roles, activo)
            )
            uow.auditoria.registrar(actor.usuario_id, EventoDeAuditoria(evento, objetivo_id, {}))


class DesactivarUsuario(_CambioDeAcceso):
    def ejecutar(self, usuario_id: str, objetivo_id: str) -> None:
        self._cambiar(usuario_id, objetivo_id, False, "usuario.desactivado")


class ReactivarUsuario(_CambioDeAcceso):
    def ejecutar(self, usuario_id: str, objetivo_id: str) -> None:
        self._cambiar(usuario_id, objetivo_id, True, "usuario.reactivado")


class EliminarUsuario:
    """Borra la cuenta en Supabase. La fila local queda inactiva: la auditoria y las decisiones
    siguen apuntando a ese id (invariantes 3 y 4)."""

    def __init__(self, repos: Repositorios, cuentas: AdministradorDeCuentas) -> None:
        self._repos = repos
        self._cuentas = cuentas

    def ejecutar(self, usuario_id: str, objetivo_id: str) -> None:
        with self._repos.unidad_de_trabajo() as uow:
            actor = _administrador(uow, usuario_id)
            actual = _otro_usuario(uow, actor, objetivo_id)
        if actual.activo:
            raise OperacionNoPermitida("desactive la cuenta antes de eliminarla")
        try:
            self._cuentas.eliminar(objetivo_id)
        except CuentaRechazada as e:
            if e.codigo != "user_not_found":  # repetir la operacion no es un error
                raise
            return
        with self._repos.unidad_de_trabajo() as uow:
            uow.auditoria.registrar(
                actor.usuario_id, EventoDeAuditoria("usuario.eliminado", objetivo_id, {})
            )
