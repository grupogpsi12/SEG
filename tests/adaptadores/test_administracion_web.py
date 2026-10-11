"""Item 2.13 por la web: matriz de perfiles y roles (RF-37), sobre el ORM."""

from typing import Any

import pytest
from django.test import Client

from jml.adaptadores.entrada.web import composicion
from jml.adaptadores.salida.persistencia.repositorios import RepositoriosDjango
from jml.dominio.tipos import Rol
from tests.fabricas import AHORA
from tests.mundo import Mundo

pytestmark = pytest.mark.django_db
RUTAS = ["/administracion/perfiles", "/administracion/perfil", "/administracion/usuarios"]


@pytest.fixture
def mundo(monkeypatch: pytest.MonkeyPatch) -> Mundo:
    m = Mundo.nuevo(repositorios=RepositoriosDjango)
    monkeypatch.setattr(composicion, "reloj", lambda: m.reloj)
    return m


def como(usuario: str) -> Client:
    c = Client()
    s = c.session
    s["usuario_id"], s["inicio"] = usuario, AHORA.timestamp()
    s.save()
    return c


def texto(r: Any) -> str:
    return bytes(r.content).decode()


def formulario_ti_cali(**cambios: str) -> dict[str, str]:
    base = {
        "departamento": "TI",
        "sede": "Cali",
        "grupos_ad": "GG-TI\nGG-Sede-Cali",
        "grupos_red": "NET-VPN\nNET-VLAN-Cali",
        "grupos_m365": "M365-TI",
        "licencias": "Suite ofimática\nVisio",
        "tipo_equipo": "Portátil",
        "recursos": r"\\fs01.ad.andina.test\departamentos\TI | TI | Edición | FS-TI-RW",
    }
    return base | cambios


@pytest.mark.parametrize("usuario", ["u-rrhh", "u-tec-ad", "u-aud", "u-col"])
def test_solo_el_administrador_entra(mundo: Mundo, usuario: str) -> None:
    for ruta in RUTAS:
        assert como(usuario).get(ruta).status_code == 403, ruta
    r = como(usuario).post("/administracion/usuarios/u-col/roles", {"roles": ["rrhh"]}, follow=True)
    assert "No tiene permiso" in texto(r)


def test_editar_un_perfil_desde_la_matriz(mundo: Mundo) -> None:
    admin = como("u-admin")
    assert "Finanzas" in texto(admin.get("/administracion/perfiles"))
    precargado = texto(admin.get("/administracion/perfil", {"departamento": "TI", "sede": "Cali"}))
    assert "GG-TI" in precargado
    r = admin.post("/administracion/perfil", formulario_ti_cali())
    assert (r.status_code, r["Location"]) == (302, "/administracion/perfiles")
    with RepositoriosDjango(mundo.reloj).unidad_de_trabajo() as u:
        perfil = u.perfiles.obtener("TI", "Cali")
        assert perfil is not None
        assert "Visio" in perfil.licencias
        assert u.auditoria.registros()[-1].accion == "perfil.actualizado"


@pytest.mark.parametrize(
    ("recursos", "mensaje"),
    [
        ("solo | tres | partes", "4 partes"),
        (r"\\fs\x | X | Retiro de accesos | G", "ADR-022"),
        (r"\\fs\x | X | Lectura | G", "Consulta"),
        ("\\\\fs\\x | X | Edición | G\n\\\\fs\\x | Y | Consulta | H", "dos veces"),
    ],
)
def test_un_perfil_invalido_vuelve_con_el_motivo(mundo: Mundo, recursos: str, mensaje: str) -> None:
    r = como("u-admin").post("/administracion/perfil", formulario_ti_cali(recursos=recursos))
    assert r.status_code == 200
    assert mensaje in texto(r)


def test_cambiar_roles_y_rechazar_incompatibles(mundo: Mundo) -> None:
    admin = como("u-admin")
    pagina = texto(admin.get("/administracion/usuarios"))
    assert "María José Gómez Ramírez" in pagina
    assert "(usted)" in pagina  # sus propios roles no tienen formulario
    r = admin.post(
        "/administracion/usuarios/u-col/roles", {"roles": ["solicitante", "rrhh"]}, follow=True
    )
    assert "Roles actualizados" in texto(r)
    r = admin.post(
        "/administracion/usuarios/u-col/roles", {"roles": ["rrhh", "tecnico_ad"]}, follow=True
    )
    assert "no pueden combinarse" in texto(r)
    with RepositoriosDjango(mundo.reloj).unidad_de_trabajo() as u:
        actor = u.usuarios.actor_de("u-col")
    assert actor is not None
    assert actor.roles == {Rol.SOLICITANTE, Rol.RRHH}


def test_el_administrador_no_se_cambia_sus_roles(mundo: Mundo) -> None:
    r = como("u-admin").post(
        "/administracion/usuarios/u-admin/roles", {"roles": ["auditor"]}, follow=True
    )
    assert "nadie cambia sus propios roles" in texto(r)
