"""Item 2.5: lo propio del adaptador de Supabase Auth, mas alla de la suite de contrato.

Invariante 9 (tokens no guardados), RF-02 (inscripcion), RS-08 (errores genericos e intentos)
y la administracion de cuentas con `service_role` (RF-06).
"""

import httpx
import pytest

from jml.adaptadores.salida.identidad.administracion import (
    AdministradorSupabase,
    ErrorDeAdministracion,
)
from jml.adaptadores.salida.identidad.supabase import MAX_INTENTOS, VIGENCIA_S, ProveedorSupabase
from jml.aplicacion.puertos import CredencialesInvalidas, IdentidadNoDisponible
from tests.dobles.gotrue import CLAVE_PUBLICA, CLAVE_SERVICIO, GoTrueSimulado
from tests.dobles.identidad import CODIGO_VALIDO

URL = "https://proyecto.supabase.co"
CORREO, CLAVE = "ana@andina.example", "una-clave-larga-123"


class Reloj:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def gotrue() -> GoTrueSimulado:
    g = GoTrueSimulado()
    g.registrar(CORREO, CLAVE, "u-ana")
    return g


def proveedor(g: GoTrueSimulado, reloj: Reloj | None = None) -> ProveedorSupabase:
    return ProveedorSupabase(URL, CLAVE_PUBLICA, g.cliente(), reloj or Reloj())


def ingresar(p: ProveedorSupabase) -> str:
    primer = p.autenticar(CORREO, CLAVE)
    p.inscribir_totp(primer.desafio_id)
    p.verificar_totp(primer.desafio_id, CODIGO_VALIDO)
    return primer.usuario_id


def test_al_llegar_a_aal2_no_queda_ningun_token_ni_sesion_de_supabase(
    gotrue: GoTrueSimulado,
) -> None:
    """S-29: el token AAL1 solo vivio en memoria y la sesion de Supabase se cerro."""
    p = proveedor(gotrue)
    ingresar(p)
    assert p.desafios_pendientes() == 0
    assert gotrue.tokens == {}  # logout: el refresh de Supabase no sirve a nadie
    assert "POST /auth/v1/logout" in gotrue.llamadas


def test_el_desafio_vence_a_los_cinco_minutos(gotrue: GoTrueSimulado) -> None:
    reloj = Reloj()
    p = proveedor(gotrue, reloj)
    primer = p.autenticar(CORREO, CLAVE)
    p.inscribir_totp(primer.desafio_id)
    reloj.t += VIGENCIA_S
    with pytest.raises(CredencialesInvalidas):
        p.verificar_totp(primer.desafio_id, CODIGO_VALIDO)
    assert p.desafios_pendientes() == 0


def test_los_desafios_vencidos_se_limpian_solos(gotrue: GoTrueSimulado) -> None:
    reloj = Reloj()
    p = proveedor(gotrue, reloj)
    for _ in range(3):
        p.autenticar(CORREO, CLAVE)
    reloj.t += VIGENCIA_S + 1
    p.autenticar(CORREO, CLAVE)
    assert p.desafios_pendientes() == 1


def test_tras_varios_codigos_fallidos_el_desafio_se_anula(gotrue: GoTrueSimulado) -> None:
    p = proveedor(gotrue)
    primer = p.autenticar(CORREO, CLAVE)
    p.inscribir_totp(primer.desafio_id)
    for _ in range(MAX_INTENTOS):
        with pytest.raises(CredencialesInvalidas):
            p.verificar_totp(primer.desafio_id, "000000")
    with pytest.raises(CredencialesInvalidas):  # ni siquiera el codigo bueno sirve ya
        p.verificar_totp(primer.desafio_id, CODIGO_VALIDO)


@pytest.mark.parametrize("codigo", ["", "12345", "1234567", "abcdef", "12 456"])
def test_un_codigo_mal_formado_no_llega_a_supabase(gotrue: GoTrueSimulado, codigo: str) -> None:
    p = proveedor(gotrue)
    primer = p.autenticar(CORREO, CLAVE)
    p.inscribir_totp(primer.desafio_id)
    antes = len(gotrue.llamadas)
    with pytest.raises(CredencialesInvalidas):
        p.verificar_totp(primer.desafio_id, codigo)
    assert len(gotrue.llamadas) == antes


def test_con_solo_la_contrasena_no_se_inscribe_otro_factor(gotrue: GoTrueSimulado) -> None:
    """Quien robo la contrasena no puede agregar su propio TOTP a una cuenta ya protegida (T1)."""
    p = proveedor(gotrue)
    ingresar(p)
    segundo = p.autenticar(CORREO, CLAVE)
    with pytest.raises(CredencialesInvalidas):
        p.inscribir_totp(segundo.desafio_id)


def test_una_inscripcion_abandonada_no_acumula_factores(gotrue: GoTrueSimulado) -> None:
    p = proveedor(gotrue)
    for _ in range(3):
        p.inscribir_totp(p.autenticar(CORREO, CLAVE).desafio_id)
    assert len(gotrue.usuarios[CORREO].factores) == 1


def test_un_token_que_no_es_aal2_no_da_identidad(gotrue: GoTrueSimulado) -> None:
    gotrue.respuesta_aal2 = "aal1"
    p = proveedor(gotrue)
    primer = p.autenticar(CORREO, CLAVE)
    p.inscribir_totp(primer.desafio_id)
    with pytest.raises(CredencialesInvalidas):
        p.verificar_totp(primer.desafio_id, CODIGO_VALIDO)


def test_supabase_caido_es_un_error_distinto_de_credenciales(gotrue: GoTrueSimulado) -> None:
    gotrue.caido = True
    with pytest.raises(IdentidadNoDisponible):
        proveedor(gotrue).autenticar(CORREO, CLAVE)


def test_un_error_de_red_no_filtra_detalles(gotrue: GoTrueSimulado) -> None:
    def falla(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to db.interno:5432 password=xyz")

    p = ProveedorSupabase(URL, CLAVE_PUBLICA, httpx.Client(transport=httpx.MockTransport(falla)))
    with pytest.raises(IdentidadNoDisponible) as e:
        p.autenticar(CORREO, CLAVE)
    assert "xyz" not in str(e.value)


def test_la_clave_publica_viaja_en_cada_peticion(gotrue: GoTrueSimulado) -> None:
    p = ProveedorSupabase(URL, "otra-clave", gotrue.cliente())
    with pytest.raises(CredencialesInvalidas):  # 401 de Supabase: nunca se autentica
        p.autenticar(CORREO, CLAVE)


# --- administracion (RF-06) -------------------------------------------------------------------


def admin(g: GoTrueSimulado, clave: str = CLAVE_SERVICIO) -> AdministradorSupabase:
    return AdministradorSupabase(URL, clave, g.cliente())


def test_el_administrador_crea_una_cuenta_que_luego_ingresa(gotrue: GoTrueSimulado) -> None:
    uid = admin(gotrue).crear(" Beto@Andina.Example ", "otra-clave-larga-456")
    primer = proveedor(gotrue).autenticar("beto@andina.example", "otra-clave-larga-456")
    assert primer.usuario_id == uid
    assert primer.requiere_inscripcion is True


def test_un_usuario_desactivado_ya_no_ingresa(gotrue: GoTrueSimulado) -> None:
    uid = admin(gotrue).crear("beto@andina.example", "otra-clave-larga-456")
    admin(gotrue).desactivar(uid)
    with pytest.raises(CredencialesInvalidas):
        proveedor(gotrue).autenticar("beto@andina.example", "otra-clave-larga-456")


@pytest.mark.parametrize(
    ("correo", "clave", "codigo"),
    [
        (CORREO, "otra-clave-larga-456", "email_exists"),
        ("x@andina.example", "corta", "weak_password"),
    ],
)
def test_los_rechazos_de_supabase_se_explican(
    gotrue: GoTrueSimulado, correo: str, clave: str, codigo: str
) -> None:
    with pytest.raises(ErrorDeAdministracion, match=codigo):
        admin(gotrue).crear(correo, clave)


def test_sin_la_clave_de_servicio_no_se_administra_nada(gotrue: GoTrueSimulado) -> None:
    with pytest.raises(ErrorDeAdministracion):
        admin(gotrue, CLAVE_PUBLICA).crear("x@andina.example", "otra-clave-larga-456")


def test_eliminar_compensa_un_alta_a_medias(gotrue: GoTrueSimulado) -> None:
    uid = admin(gotrue).crear("beto@andina.example", "otra-clave-larga-456")
    admin(gotrue).eliminar(uid)
    assert "beto@andina.example" not in gotrue.usuarios
