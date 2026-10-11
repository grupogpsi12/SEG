"""Inicio de sesion en dos pasos: contrasena y TOTP (RF-01, RF-02, RF-05; ADR-017).

El nucleo no crea la sesion web; decide si la identidad verificada (AAL2) puede entrar. Un
usuario sin cuenta activa o con roles incompatibles no entra, y el rechazo queda auditado.
"""

from dataclasses import dataclass

from jml.aplicacion.puertos import (
    CredencialesInvalidas,
    PrimerFactor,
    ProveedorDeIdentidad,
    Repositorios,
)
from jml.dominio.auditoria import EventoDeAuditoria
from jml.dominio.catalogo import UsuarioId
from jml.dominio.errores import NoAutorizado, RolesIncompatibles

ACTOR_DEL_SISTEMA = "sistema:ingreso"


@dataclass(frozen=True, slots=True)
class DependenciasDeIngreso:
    proveedor: ProveedorDeIdentidad
    repos: Repositorios


def _auditar_fallo(repos: Repositorios, objeto: str, paso: str) -> None:
    """RF-35: el intento fallido queda en la cadena. Nunca con la contrasena ni el codigo."""
    with repos.unidad_de_trabajo() as uow:
        uow.auditoria.registrar(
            ACTOR_DEL_SISTEMA, EventoDeAuditoria("sesion.fallida", objeto, {"paso": paso})
        )


class IniciarIngreso:
    def __init__(self, dependencias: DependenciasDeIngreso) -> None:
        self._dep = dependencias

    def ejecutar(self, correo: str, contrasena: str) -> PrimerFactor:
        try:
            return self._dep.proveedor.autenticar(correo, contrasena)
        except CredencialesInvalidas:
            _auditar_fallo(self._dep.repos, correo.strip().lower()[:254] or "-", "contrasena")
            raise


class InscribirTotp:
    def __init__(self, proveedor: ProveedorDeIdentidad) -> None:
        self._proveedor = proveedor

    def ejecutar(self, desafio_id: str) -> str:
        return self._proveedor.inscribir_totp(desafio_id)


class CompletarIngreso:
    """Verifica el TOTP y decide si la persona entra. Devuelve el id del usuario."""

    def __init__(self, dependencias: DependenciasDeIngreso) -> None:
        self._dep = dependencias

    def ejecutar(self, desafio_id: str, codigo: str, usuario_id: UsuarioId) -> UsuarioId:
        """`usuario_id` es el que devolvio el primer factor: solo sirve para auditar un fallo."""
        try:
            identidad = self._dep.proveedor.verificar_totp(desafio_id, codigo)
        except CredencialesInvalidas:
            _auditar_fallo(self._dep.repos, usuario_id, "totp")
            raise
        if identidad.nivel < 2:
            raise CredencialesInvalidas  # RF-01: solo AAL2 abre una sesion
        uid = identidad.usuario_id
        causa: str | None = None
        with self._dep.repos.unidad_de_trabajo() as uow:
            try:
                actor = uow.usuarios.actor_de(uid)
            except RolesIncompatibles:
                causa = "roles_incompatibles"  # RF-05
            else:
                if actor is None:
                    causa = "usuario_inactivo_o_sin_alta"
            accion = "sesion.iniciada" if causa is None else "sesion.denegada"
            datos = {} if causa is None else {"causa": causa}
            uow.auditoria.registrar(uid, EventoDeAuditoria(accion, uid, datos))
        # Se lanza FUERA de la unidad de trabajo: el rechazo tiene que quedar auditado.
        if causa is not None:
            raise NoAutorizado("ingresar", causa)
        return uid
