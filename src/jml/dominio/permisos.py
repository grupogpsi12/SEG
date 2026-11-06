"""Quien puede hacer que (SRS 3.3 y 4.1; RF-03, RF-05, RF-15). Reglas puras, sin E/S."""

from dataclasses import dataclass
from enum import StrEnum

from jml.dominio.catalogo import ColaboradorId, UsuarioId
from jml.dominio.errores import RolesIncompatibles
from jml.dominio.tipos import ROLES_TECNICOS, Rol, Subtipo, TipoEvento


class Relacion(StrEnum):
    SI_MISMO = "si_mismo"
    SUBORDINADO_DIRECTO = "subordinado_directo"
    TERCERO = "tercero"


def _construir_incompatibles() -> frozenset[frozenset[Rol]]:
    pares: set[frozenset[Rol]] = set()
    for tecnico in ROLES_TECNICOS:
        pares.add(frozenset({Rol.RRHH, tecnico}))
        pares.add(frozenset({Rol.ADMINISTRADOR, tecnico}))
    pares.add(frozenset({Rol.RRHH, Rol.ADMINISTRADOR}))
    # El Auditor es incompatible con todos los demas roles (SRS 3.3).
    for otro in Rol:
        if otro is not Rol.AUDITOR:
            pares.add(frozenset({Rol.AUDITOR, otro}))
    return frozenset(pares)


ROLES_INCOMPATIBLES = _construir_incompatibles()


def validar_roles(roles: frozenset[Rol]) -> None:
    """RF-05: una persona con roles incompatibles es rechazada."""
    ordenados = sorted(roles, key=lambda r: r.value)
    for i, uno in enumerate(ordenados):
        for otro in ordenados[i + 1 :]:
            if frozenset({uno, otro}) in ROLES_INCOMPATIBLES:
                raise RolesIncompatibles(uno.value, otro.value)


@dataclass(frozen=True, slots=True)
class Actor:
    usuario_id: UsuarioId
    colaborador_id: ColaboradorId | None
    roles: frozenset[Rol]

    def __post_init__(self) -> None:
        validar_roles(self.roles)

    def tiene(self, rol: Rol) -> bool:
        return rol in self.roles


@dataclass(frozen=True, slots=True)
class UsuarioDelSistema:
    """Usuario de Django vinculado a Supabase Auth, sin contrasena local (SRS 5.1)."""

    id: UsuarioId
    colaborador_id: ColaboradorId | None
    roles: frozenset[Rol]
    activo: bool = True

    def __post_init__(self) -> None:
        validar_roles(self.roles)

    def como_actor(self) -> Actor:
        return Actor(self.id, self.colaborador_id, self.roles)


def relacion_con(
    actor: Actor, sujeto_id: ColaboradorId, jefe_del_sujeto: ColaboradorId | None
) -> Relacion:
    if actor.colaborador_id is not None and actor.colaborador_id == sujeto_id:
        return Relacion.SI_MISMO
    if actor.colaborador_id is not None and actor.colaborador_id == jefe_del_sujeto:
        return Relacion.SUBORDINADO_DIRECTO
    return Relacion.TERCERO


def puede_registrar_como_solicitante(
    actor: Actor, tipo: TipoEvento, subtipo: Subtipo | None, relacion: Relacion
) -> bool:
    """Registro que queda pendiente de aprobacion (SRS 3.3 y 4.1).

    El colaborador solo registra sus vacaciones y su renuncia; el jefe directo, los cambios de
    departamento y de sucursal de sus subordinados. Todo lo demas lo emite RRHH.
    """
    if not actor.tiene(Rol.SOLICITANTE):
        return False
    if relacion is Relacion.SI_MISMO:
        return tipo is TipoEvento.VAC or (tipo is TipoEvento.RET and subtipo is Subtipo.RENUNCIA)
    if relacion is Relacion.SUBORDINADO_DIRECTO:
        return tipo in (TipoEvento.CDP, TipoEvento.CSU)
    return False


def puede_emitir_directo(actor: Actor, relacion: Relacion) -> bool:
    """RF-13 y la demostración académica: RRHH y Administrador emiten cualquier tipo."""
    return bool(actor.roles & {Rol.RRHH, Rol.ADMINISTRADOR}) and relacion is not Relacion.SI_MISMO


def puede_emitir_por_excepcion(actor: Actor, sujeto_es_rrhh: bool) -> bool:
    """SRS 4.1: solo el Administrador, y solo cuando el sujeto es una persona de RRHH (S-08)."""
    return actor.tiene(Rol.ADMINISTRADOR) and sujeto_es_rrhh


def puede_decidir(actor: Actor) -> bool:
    return actor.tiene(Rol.RRHH)


def puede_ver_restringidos(roles: frozenset[Rol]) -> bool:
    """RD-05: RRHH y Administrador los ven en la demostración académica."""
    return bool(roles & {Rol.RRHH, Rol.ADMINISTRADOR})


def puede_ver_solicitud(actor: Actor, solicitante_id: str) -> bool:
    """El detalle lo abren RRHH y quien la registro."""
    return puede_ver_restringidos(actor.roles) or actor.usuario_id == solicitante_id


def puede_consultar_tickets(roles: frozenset[Rol]) -> bool:
    """RF-41: los tecnicos y el Administrador, que reintenta las emisiones en error."""
    return Rol.ADMINISTRADOR in roles or puede_ver_dashboard(roles)


def puede_ver_dashboard(roles: frozenset[Rol]) -> bool:
    """RF-29: roles técnicos; el Administrador ve todo en la demostración académica."""
    return Rol.ADMINISTRADOR in roles or bool(roles & ROLES_TECNICOS)


def puede_consultar_auditoria(roles: frozenset[Rol]) -> bool:
    return bool(roles & {Rol.AUDITOR, Rol.ADMINISTRADOR})


def puede_reintentar_emision(roles: frozenset[Rol]) -> bool:
    return Rol.ADMINISTRADOR in roles
