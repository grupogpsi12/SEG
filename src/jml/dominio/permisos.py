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
    """RF-13 y RF-15: RRHH emite cualquier tipo, salvo sobre su propia persona."""
    return actor.tiene(Rol.RRHH) and relacion is not Relacion.SI_MISMO


def puede_emitir_por_excepcion(actor: Actor, sujeto_es_rrhh: bool) -> bool:
    """SRS 4.1: solo el Administrador, y solo cuando el sujeto es una persona de RRHH (S-08)."""
    return actor.tiene(Rol.ADMINISTRADOR) and sujeto_es_rrhh


def puede_decidir(actor: Actor) -> bool:
    return actor.tiene(Rol.RRHH)


def puede_ver_restringidos(roles: frozenset[Rol]) -> bool:
    """RD-05: solo RRHH ve motivo y descripcion."""
    return Rol.RRHH in roles


def puede_ver_dashboard(roles: frozenset[Rol]) -> bool:
    """RF-29: solo roles tecnicos."""
    return bool(roles & ROLES_TECNICOS)


def puede_consultar_auditoria(roles: frozenset[Rol]) -> bool:
    return Rol.AUDITOR in roles


def puede_reintentar_emision(roles: frozenset[Rol]) -> bool:
    return Rol.ADMINISTRADOR in roles
