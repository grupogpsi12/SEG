"""`python manage.py admin_usuarios crear|desactivar`: el UNICO alta y baja de usuarios (RF-06).

Corre en el contenedor `admin-usuarios`, el unico que monta el secreto `supabase_service_role`
(invariante 8). No hay registro abierto: la cuenta nace aqui en Supabase Auth y, con el mismo
id, en Django con sus roles (grupos). El TOTP lo inscribe la persona en su primer ingreso (RF-02).

La contrasena inicial es aleatoria y se muestra UNA vez en la terminal del administrador, que la
entrega por un canal fuera de la aplicacion (no hay correos: fuera de alcance).
"""

import os
import secrets
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from jml.adaptadores.salida.identidad.administracion import (
    AdministradorSupabase,
    ErrorDeAdministracion,
)
from jml.adaptadores.salida.persistencia.repositorios import RepositoriosDjango
from jml.adaptadores.salida.reloj import RelojDelSistema
from jml.aplicacion.puertos import IdentidadNoDisponible, Repositorios
from jml.dominio.auditoria import EventoDeAuditoria
from jml.dominio.errores import RolesIncompatibles
from jml.dominio.permisos import UsuarioDelSistema, validar_roles
from jml.dominio.tipos import Rol

ACTOR = "sistema:admin-usuarios"


def administrador() -> AdministradorSupabase:
    ruta = Path(os.environ.get("JML_SECRETOS_DIR", "/run/secrets")) / "supabase_service_role"
    try:
        clave = ruta.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        raise CommandError(
            "falta el secreto supabase_service_role (solo en admin-usuarios)"
        ) from None
    if not settings.JML_SUPABASE_URL or not clave:
        raise CommandError("faltan JML_SUPABASE_URL o la clave de servicio")
    return AdministradorSupabase(settings.JML_SUPABASE_URL, clave)


def repositorios() -> Repositorios:
    return RepositoriosDjango(RelojDelSistema())


class Command(BaseCommand):
    help = "Crea o desactiva usuarios en Supabase Auth y en la aplicacion (RF-06)."

    def add_arguments(self, parser: CommandParser) -> None:
        sub = parser.add_subparsers(dest="accion", required=True)
        crear = sub.add_parser("crear", help="Crea la cuenta con sus roles")
        crear.add_argument("--correo", required=True)
        crear.add_argument(
            "--rol", action="append", required=True, choices=[r.value for r in Rol], dest="roles"
        )
        crear.add_argument("--colaborador", help="Id del colaborador al que corresponde")
        desactivar = sub.add_parser("desactivar", help="Banea la cuenta y la desactiva")
        desactivar.add_argument("--usuario", required=True, help="Id de Supabase del usuario")

    def handle(self, *args: Any, **o: Any) -> None:
        try:
            if o["accion"] == "crear":
                self._crear(o["correo"], frozenset(Rol(r) for r in o["roles"]), o["colaborador"])
            else:
                self._desactivar(o["usuario"])
        except (ErrorDeAdministracion, IdentidadNoDisponible) as e:
            raise CommandError(f"Supabase rechazo la operacion: {e}") from None

    def _crear(self, correo: str, roles: frozenset[Rol], colaborador: str | None) -> None:
        try:
            validar_roles(roles)  # RF-05: antes de tocar Supabase
        except RolesIncompatibles as e:
            raise CommandError(str(e)) from None
        repos = repositorios()
        if colaborador is not None:
            with repos.unidad_de_trabajo() as u:
                if u.colaboradores.obtener(colaborador) is None:
                    raise CommandError(f"no existe el colaborador {colaborador}")
        admin = administrador()
        contrasena = secrets.token_urlsafe(18)  # 24 caracteres (RS-16 pide al menos 12)
        uid = admin.crear(correo, contrasena)
        try:
            with repos.unidad_de_trabajo() as u:
                u.usuarios.guardar(UsuarioDelSistema(uid, colaborador, roles))
                u.auditoria.registrar(
                    ACTOR,
                    EventoDeAuditoria(
                        "usuario.creado", uid, {"roles": ",".join(sorted(r.value for r in roles))}
                    ),
                )
        except Exception:
            admin.eliminar(uid)  # sin cuenta huerfana en Supabase
            raise
        self.stdout.write(f"usuario creado: {uid}")
        self.stdout.write(f"contrasena inicial (se muestra una sola vez): {contrasena}")

    def _desactivar(self, uid: str) -> None:
        repos = repositorios()
        with repos.unidad_de_trabajo() as u:
            actor = u.usuarios.actor_de(uid)
        if actor is None:
            raise CommandError(f"el usuario {uid} no existe o ya esta inactivo")
        administrador().desactivar(uid)
        with repos.unidad_de_trabajo() as u:
            u.usuarios.guardar(
                UsuarioDelSistema(uid, actor.colaborador_id, actor.roles, activo=False)
            )
            u.auditoria.registrar(ACTOR, EventoDeAuditoria("usuario.desactivado", uid, {}))
        self.stdout.write(f"usuario desactivado: {uid}")
