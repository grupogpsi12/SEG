"""Item 2.5: el nucleo decide quien entra tras el TOTP (RF-01, RF-02, RF-05, CA-14)."""

import pytest

from jml.aplicacion.casos.ingreso import (
    CompletarIngreso,
    DependenciasDeIngreso,
    IniciarIngreso,
    InscribirTotp,
)
from jml.aplicacion.puertos import CredencialesInvalidas, IdentidadVerificada
from jml.dominio.errores import NoAutorizado
from jml.dominio.permisos import UsuarioDelSistema
from jml.dominio.tipos import Rol
from tests.dobles.identidad import CODIGO_VALIDO, ProveedorDeIdentidadEnMemoria
from tests.mundo import Mundo


def preparar(usuario: str = "u-col") -> tuple[Mundo, ProveedorDeIdentidadEnMemoria]:
    m = Mundo.nuevo()
    proveedor = ProveedorDeIdentidadEnMemoria()
    proveedor.registrar("persona@andina.example", "una-clave-larga-123", usuario)
    return m, proveedor


def entrar(m: Mundo, proveedor: ProveedorDeIdentidadEnMemoria, codigo: str = CODIGO_VALIDO) -> str:
    primer = IniciarIngreso(DependenciasDeIngreso(proveedor, m.puerto)).ejecutar(
        "persona@andina.example", "una-clave-larga-123"
    )
    assert primer.requiere_inscripcion is True
    assert InscribirTotp(proveedor).ejecutar(primer.desafio_id).startswith("otpauth://")
    return CompletarIngreso(DependenciasDeIngreso(proveedor, m.puerto)).ejecutar(
        primer.desafio_id, codigo, primer.usuario_id
    )


def acciones(m: Mundo) -> list[tuple[str, str, dict[str, object]]]:
    return [
        (r.accion, r.objeto, dict(r.datos))
        for r in m.repos.auditoria().registros()
        if r.accion.startswith("sesion.")
    ]


def test_contrasena_y_totp_validos_dan_paso_y_se_audita() -> None:
    m, proveedor = preparar()
    assert entrar(m, proveedor) == "u-col"
    assert acciones(m) == [("sesion.iniciada", "u-col", {})]


def test_un_codigo_incorrecto_no_da_paso_y_queda_auditado_CA_14_RF_35() -> None:
    m, proveedor = preparar()
    with pytest.raises(CredencialesInvalidas):
        entrar(m, proveedor, codigo="987654")
    assert acciones(m) == [("sesion.fallida", "u-col", {"paso": "totp"})]
    assert "987654" not in repr(m.repos.auditoria().registros())


def test_RF_35_una_contrasena_rechazada_queda_auditada_sin_la_contrasena() -> None:
    m, proveedor = preparar()
    for correo in (" Persona@Andina.Example ", "nadie@andina.example"):
        with pytest.raises(CredencialesInvalidas):
            IniciarIngreso(DependenciasDeIngreso(proveedor, m.puerto)).ejecutar(
                correo, "clave-mala-123"
            )
    assert acciones(m) == [
        ("sesion.fallida", "persona@andina.example", {"paso": "contrasena"}),
        ("sesion.fallida", "nadie@andina.example", {"paso": "contrasena"}),
    ]
    assert "clave-mala-123" not in repr(m.repos.auditoria().registros())
    with pytest.raises(CredencialesInvalidas):
        IniciarIngreso(DependenciasDeIngreso(proveedor, m.puerto)).ejecutar("x" * 300, "y")
    assert len(acciones(m)[-1][1]) == 80  # cabe en la columna de la base


def test_quien_existe_en_supabase_pero_no_tiene_alta_activa_no_entra() -> None:
    m, proveedor = preparar(usuario="sin-alta")
    with pytest.raises(NoAutorizado):
        entrar(m, proveedor)
    assert acciones(m) == [
        ("sesion.denegada", "sin-alta", {"causa": "usuario_inactivo_o_sin_alta"})
    ]


def test_un_usuario_desactivado_no_entra() -> None:
    m, proveedor = preparar()
    with m.repos.unidad_de_trabajo() as u:
        u.usuarios.guardar(
            UsuarioDelSistema("u-col", "col-1", frozenset({Rol.SOLICITANTE}), activo=False)
        )
    with pytest.raises(NoAutorizado):
        entrar(m, proveedor)


def test_un_proveedor_que_no_llega_a_aal2_no_da_paso() -> None:
    class SoloAal1:
        def autenticar(self, correo: str, contrasena: str) -> object:
            raise AssertionError

        def inscribir_totp(self, desafio_id: str) -> str:
            raise AssertionError

        def verificar_totp(self, desafio_id: str, codigo: str) -> IdentidadVerificada:
            return IdentidadVerificada("u-col", nivel=1)

    m = Mundo.nuevo()
    caso = CompletarIngreso(DependenciasDeIngreso(SoloAal1(), m.puerto))  # type: ignore[arg-type]
    with pytest.raises(CredencialesInvalidas):
        caso.ejecutar("d", "123456", "u-col")
    assert acciones(m) == []


@pytest.mark.django_db
def test_RF_05_roles_incompatibles_en_la_base_niegan_el_acceso_y_se_audita() -> None:
    """El doble no puede guardar roles incompatibles (el dominio lo impide); la base si podria,
    p. ej. si alguien edita los grupos a mano. Por eso se prueba sobre el ORM."""
    from django.contrib.auth.models import Group, User

    from jml.adaptadores.salida.persistencia.repositorios import RepositoriosDjango

    m = Mundo.nuevo(repositorios=RepositoriosDjango)
    cuenta = User.objects.get(username="u-rrhh")
    cuenta.groups.add(Group.objects.get_or_create(name=Rol.TECNICO_AD.value)[0])
    proveedor = ProveedorDeIdentidadEnMemoria()
    proveedor.registrar("rosa@andina.example", "una-clave-larga-123", "u-rrhh")
    primer = IniciarIngreso(DependenciasDeIngreso(proveedor, m.puerto)).ejecutar(
        "rosa@andina.example", "una-clave-larga-123"
    )
    InscribirTotp(proveedor).ejecutar(primer.desafio_id)
    with pytest.raises(NoAutorizado):
        CompletarIngreso(DependenciasDeIngreso(proveedor, m.puerto)).ejecutar(
            primer.desafio_id, CODIGO_VALIDO, primer.usuario_id
        )
    with m.puerto.unidad_de_trabajo() as u:
        ultimo = u.auditoria.registros()[-1]
    assert (ultimo.accion, dict(ultimo.datos)) == (
        "sesion.denegada",
        {"causa": "roles_incompatibles"},
    )
