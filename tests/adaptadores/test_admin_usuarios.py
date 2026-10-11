"""Item 2.5 / RF-06: el comando `admin_usuarios` contra el GoTrue simulado y la base de pruebas."""

import io
import re

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError

from jml.adaptadores.entrada.web.management.commands import admin_usuarios
from jml.adaptadores.salida.identidad.administracion import AdministradorSupabase
from jml.adaptadores.salida.identidad.supabase import ProveedorSupabase
from jml.adaptadores.salida.persistencia.repositorios import RepositoriosDjango
from jml.dominio.tipos import Rol
from tests.dobles.gotrue import CLAVE_PUBLICA, CLAVE_SERVICIO, GoTrueSimulado
from tests.mundo import Mundo

pytestmark = pytest.mark.django_db
URL = "https://x.supabase.co"


@pytest.fixture
def gotrue(monkeypatch: pytest.MonkeyPatch) -> GoTrueSimulado:
    Mundo.nuevo(repositorios=RepositoriosDjango)  # colaboradores col-1, jefe-1, ...
    g = GoTrueSimulado()
    monkeypatch.setattr(
        admin_usuarios,
        "administrador",
        lambda: AdministradorSupabase(URL, CLAVE_SERVICIO, g.cliente()),
    )
    return g


def correr(*args: str) -> str:
    salida = io.StringIO()
    call_command("admin_usuarios", *args, stdout=salida)
    return salida.getvalue()


def auditoria(accion: str) -> list[str]:
    with RepositoriosDjango(None).unidad_de_trabajo() as u:  # type: ignore[arg-type]  # sin reloj
        return [r.objeto for r in u.auditoria.registros() if r.accion == accion]


def test_crear_da_de_alta_en_supabase_y_en_la_aplicacion(gotrue: GoTrueSimulado) -> None:
    """S-31: la contrasena inicial se muestra una sola vez."""
    salida = correr(
        "crear", "--correo", "Nueva@Andina.Example", "--rol", "rrhh", "--colaborador", "col-1"
    )
    uid = re.search(r"usuario creado: (\S+)", salida).group(1)  # type: ignore[union-attr]
    clave = re.search(r"una sola vez\): (\S+)", salida).group(1)  # type: ignore[union-attr]
    assert len(clave) >= 12
    cuenta = User.objects.get(username=uid)
    assert not cuenta.has_usable_password()  # la contrasena vive solo en Supabase
    assert [g.name for g in cuenta.groups.all()] == [Rol.RRHH.value]
    assert auditoria("usuario.creado") == [uid]
    # y con esa contrasena puede empezar el ingreso (el TOTP lo inscribe en el primer ingreso)
    primer = ProveedorSupabase(URL, CLAVE_PUBLICA, gotrue.cliente()).autenticar(
        "nueva@andina.example", clave
    )
    assert (primer.usuario_id, primer.requiere_inscripcion) == (uid, True)


def test_roles_incompatibles_no_llegan_a_supabase(gotrue: GoTrueSimulado) -> None:
    with pytest.raises(CommandError, match="incompatibles"):
        correr("crear", "--correo", "x@andina.example", "--rol", "rrhh", "--rol", "tecnico_ad")
    assert gotrue.llamadas == []


def test_un_colaborador_inexistente_se_rechaza_antes_de_crear(gotrue: GoTrueSimulado) -> None:
    with pytest.raises(CommandError, match="no existe el colaborador"):
        correr(
            "crear", "--correo", "x@andina.example", "--rol", "solicitante", "--colaborador", "zz"
        )
    assert gotrue.usuarios == {}


def test_un_correo_repetido_se_explica(gotrue: GoTrueSimulado) -> None:
    correr("crear", "--correo", "x@andina.example", "--rol", "auditor")
    with pytest.raises(CommandError, match="email_exists"):
        correr("crear", "--correo", "x@andina.example", "--rol", "auditor")


def test_si_la_base_falla_la_cuenta_de_supabase_se_elimina(
    gotrue: GoTrueSimulado, monkeypatch: pytest.MonkeyPatch
) -> None:
    def rota() -> object:
        raise RuntimeError("base caida")

    monkeypatch.setattr(RepositoriosDjango, "unidad_de_trabajo", lambda self: rota())
    monkeypatch.setattr(admin_usuarios, "repositorios", lambda: RepositoriosDjango(None))  # type: ignore[arg-type]
    with pytest.raises(RuntimeError):
        correr("crear", "--correo", "x@andina.example", "--rol", "auditor")
    assert gotrue.usuarios == {}


def test_desactivar_banea_y_desactiva(gotrue: GoTrueSimulado) -> None:
    uid = re.search(  # type: ignore[union-attr]
        r"usuario creado: (\S+)",
        correr("crear", "--correo", "x@andina.example", "--rol", "auditor"),
    ).group(1)
    correr("desactivar", "--usuario", uid)
    assert User.objects.get(username=uid).is_active is False
    assert gotrue.usuarios["x@andina.example"].baneado is True
    assert auditoria("usuario.desactivado") == [uid]
    with pytest.raises(CommandError, match="ya esta inactivo"):
        correr("desactivar", "--usuario", uid)


def test_sin_el_secreto_de_servicio_el_comando_no_corre(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JML_SECRETOS_DIR", str(tmp_path))
    with pytest.raises(CommandError, match="supabase_service_role"):
        admin_usuarios.administrador()
