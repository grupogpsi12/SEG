"""Item 2.13: matriz de perfiles y roles desde el area de administracion (RF-37, RF-05, RF-35)."""

from dataclasses import replace

import pytest

from jml.aplicacion.casos.administracion import (
    CambiarRoles,
    ConsultarMatriz,
    ConsultarUsuarios,
    GuardarPerfil,
)
from jml.dominio.errores import NoAutorizado, NoEncontrado, OperacionNoPermitida, RolesIncompatibles
from jml.dominio.tipos import Rol
from tests.fabricas import perfil
from tests.mundo import Mundo

NO_ADMIN = ["u-rrhh", "u-col", "u-tec-ad", "u-aud", "fantasma"]


def acciones(m: Mundo, prefijo: str) -> list[tuple[str, str, dict[str, object]]]:
    return [
        (r.actor, r.objeto, dict(r.datos))
        for r in m.repos.auditoria().registros()
        if r.accion.startswith(prefijo)
    ]


@pytest.mark.parametrize("usuario", NO_ADMIN)
def test_solo_el_administrador(usuario: str) -> None:
    m = Mundo.nuevo()
    with pytest.raises(NoAutorizado):
        ConsultarMatriz(m.puerto).ejecutar(usuario)
    with pytest.raises(NoAutorizado):
        GuardarPerfil(m.puerto).ejecutar(usuario, perfil("TI", "Cali"))
    with pytest.raises(NoAutorizado):
        ConsultarUsuarios(m.puerto).ejecutar(usuario)
    with pytest.raises(NoAutorizado):
        CambiarRoles(m.puerto).ejecutar(usuario, "u-col", frozenset({Rol.SOLICITANTE}))


def test_la_matriz_se_lee_completa_y_un_cambio_queda_auditado() -> None:
    """S-32: el catalogo administrable es la matriz de perfiles."""
    m = Mundo.nuevo()
    matriz = ConsultarMatriz(m.puerto).ejecutar("u-admin")
    assert len(matriz) == 18  # 6 departamentos x 3 sedes (fabricas.MATRIZ)
    original = next(p for p in matriz if (p.departamento, p.sede) == ("TI", "Cali"))
    cambiado = replace(original, licencias=(*original.licencias, "Visio"))
    GuardarPerfil(m.puerto).ejecutar("u-admin", cambiado)
    GuardarPerfil(m.puerto).ejecutar("u-admin", cambiado)  # sin cambios: no se audita otra vez
    with m.puerto.unidad_de_trabajo() as u:
        assert u.perfiles.obtener("TI", "Cali") == cambiado
    assert acciones(m, "perfil.") == [("u-admin", "TI/Cali", {"nuevo": False})]


def test_un_perfil_nuevo_se_marca_como_tal() -> None:
    m = Mundo.nuevo()
    nuevo = replace(perfil("TI", "Cali"), departamento="Legal")  # departamento fuera de la semilla
    GuardarPerfil(m.puerto).ejecutar("u-admin", nuevo)
    assert acciones(m, "perfil.") == [("u-admin", "Legal/Cali", {"nuevo": True})]


def test_la_lista_de_usuarios_trae_nombre_roles_y_estado() -> None:
    m = Mundo.nuevo()
    filas = {f.usuario_id: f for f in ConsultarUsuarios(m.puerto).ejecutar("u-admin")}
    assert filas["u-col"].colaborador_nombre == "María José Gómez Ramírez"
    assert filas["u-col"].roles == (Rol.SOLICITANTE,)
    assert filas["u-admin"].colaborador_nombre is None
    assert all(f.activo for f in filas.values())


def test_cambiar_roles_valida_incompatibilidades_y_audita() -> None:
    m = Mundo.nuevo()
    caso = CambiarRoles(m.puerto)
    with pytest.raises(RolesIncompatibles):
        caso.ejecutar("u-admin", "u-col", frozenset({Rol.RRHH, Rol.TECNICO_AD}))
    caso.ejecutar("u-admin", "u-col", frozenset({Rol.SOLICITANTE, Rol.RRHH}))
    with m.puerto.unidad_de_trabajo() as u:
        actor = u.usuarios.actor_de("u-col")
    assert actor is not None
    assert actor.roles == {Rol.SOLICITANTE, Rol.RRHH}
    assert acciones(m, "usuario.") == [
        ("u-admin", "u-col", {"antes": "solicitante", "despues": "rrhh,solicitante"})
    ]


def test_nadie_cambia_sus_propios_roles_y_no_se_inventan_usuarios() -> None:
    m = Mundo.nuevo()
    with pytest.raises(OperacionNoPermitida):
        CambiarRoles(m.puerto).ejecutar("u-admin", "u-admin", frozenset({Rol.ADMINISTRADOR}))
    with pytest.raises(NoEncontrado):
        CambiarRoles(m.puerto).ejecutar("u-admin", "nadie", frozenset({Rol.AUDITOR}))
