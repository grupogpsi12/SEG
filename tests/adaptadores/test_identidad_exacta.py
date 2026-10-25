"""F8-02 (B-09): lo que el adaptador de Supabase Auth ENVIA y como reacciona, comparado exacto.

La mutacion de los modulos de seguridad mostro que las pruebas del adaptador comprobaban el resultado
(entra o no entra) pero no la peticion: un cuerpo, una cabecera o un codigo de estado distintos pasaban
sin que nada fallara. En un adaptador de autenticacion eso es justo lo que importa (RF-01, RF-02, RS-08).
"""

import base64
import json

import httpx
import pytest

from jml.adaptadores.salida.identidad.supabase import (
    MAX_INTENTOS,
    VIGENCIA_S,
    ProveedorSupabase,
    _claims,
)
from jml.aplicacion.puertos import CredencialesInvalidas, IdentidadNoDisponible
from tests.dobles.gotrue import CLAVE_PUBLICA, GoTrueSimulado
from tests.dobles.identidad import CODIGO_VALIDO

URL = "https://proyecto.supabase.co"
CORREO, CLAVE = "ana@andina.example", "una-clave-larga-123"


class Reloj:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


class Grabadora:
    """Envuelve al GoTrue simulado y guarda cada peticion tal como salio (nombres de cabecera con su caja)."""

    def __init__(self, g: GoTrueSimulado) -> None:
        self.g = g
        self.peticiones: list[httpx.Request] = []
        self.sustitutos: dict[str, httpx.Response] = {}  # "METODO /ruta" -> respuesta forzada

    def __call__(self, peticion: httpx.Request) -> httpx.Response:
        self.peticiones.append(peticion)
        forzada = self.sustitutos.get(f"{peticion.method} {peticion.url.path}")
        if forzada is not None:
            return forzada
        return self.g.manejar(peticion)

    def cliente(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self))

    def de(self, metodo: str, ruta: str) -> httpx.Request:
        return next(p for p in self.peticiones if p.method == metodo and p.url.path == ruta)

    @staticmethod
    def cabeceras(p: httpx.Request) -> list[str]:
        return [k.decode() for k, _ in p.headers.raw]


@pytest.fixture
def gotrue() -> GoTrueSimulado:
    g = GoTrueSimulado()
    g.registrar(CORREO, CLAVE, "u-ana")
    return g


def montar(
    g: GoTrueSimulado, reloj: Reloj | None = None, url: str = URL
) -> tuple[ProveedorSupabase, Grabadora]:
    grabadora = Grabadora(g)
    return ProveedorSupabase(url, CLAVE_PUBLICA, grabadora.cliente(), reloj or Reloj()), grabadora


def test_el_inicio_de_sesion_envia_correo_y_clave_por_el_endpoint_de_token(
    gotrue: GoTrueSimulado,
) -> None:
    p, rec = montar(gotrue)
    p.autenticar(CORREO, CLAVE)
    pedido = rec.peticiones[0]
    assert (pedido.method, pedido.url.path, pedido.url.params["grant_type"]) == (
        "POST",
        "/auth/v1/token",
        "password",
    )
    assert json.loads(pedido.content) == {"email": CORREO, "password": CLAVE}
    assert "apikey" in rec.cabeceras(pedido)  # la caja exacta que espera Supabase
    assert pedido.headers["apikey"] == CLAVE_PUBLICA


def test_la_inscripcion_del_totp_pide_un_factor_totp_con_el_emisor_de_la_aplicacion(
    gotrue: GoTrueSimulado,
) -> None:
    p, rec = montar(gotrue)
    primer = p.autenticar(CORREO, CLAVE)
    p.inscribir_totp(primer.desafio_id)
    pedido = rec.de("POST", "/auth/v1/factors")
    assert json.loads(pedido.content) == {"factor_type": "totp", "issuer": "Andina Servicios"}
    assert "Authorization" in rec.cabeceras(pedido)
    assert pedido.headers["Authorization"].startswith("Bearer ")


def test_verificar_el_codigo_desafia_el_factor_y_manda_el_id_del_reto_y_el_codigo(
    gotrue: GoTrueSimulado,
) -> None:
    p, rec = montar(gotrue)
    primer = p.autenticar(CORREO, CLAVE)
    p.inscribir_totp(primer.desafio_id)
    p.verificar_totp(primer.desafio_id, f"  {CODIGO_VALIDO}  ")  # el espacio sobrante se recorta
    rutas = [f"{r.method} {r.url.path}" for r in rec.peticiones]
    reto = next(r for r in rec.peticiones if r.url.path.endswith("/challenge"))
    verificacion = next(r for r in rec.peticiones if r.url.path.endswith("/verify"))
    cuerpo = json.loads(verificacion.content)
    assert set(cuerpo) == {"challenge_id", "code"}
    assert cuerpo["code"] == CODIGO_VALIDO
    assert cuerpo["challenge_id"]  # el id que devolvio el reto, no vacio
    assert rutas.index(f"POST {reto.url.path}") < rutas.index(f"POST {verificacion.url.path}")
    # al llegar a AAL2 la sesion de Supabase se cierra solo en este dispositivo
    cierre = rec.de("POST", "/auth/v1/logout")
    assert cierre.url.params["scope"] == "local"


def test_un_servidor_que_responde_500_o_429_es_indisponible_y_dice_el_codigo(
    gotrue: GoTrueSimulado,
) -> None:
    for codigo in (500, 429):
        p, rec = montar(gotrue)
        rec.sustitutos["POST /auth/v1/token"] = httpx.Response(codigo)
        with pytest.raises(IdentidadNoDisponible, match=f"HTTP {codigo}"):
            p.autenticar(CORREO, CLAVE)


def test_un_400_no_es_indisponibilidad_sino_credenciales_invalidas(gotrue: GoTrueSimulado) -> None:
    p, _ = montar(gotrue)
    with pytest.raises(CredencialesInvalidas):
        p.autenticar(CORREO, "otra-clave")


def test_un_error_de_red_se_informa_por_su_tipo_y_sin_el_detalle(gotrue: GoTrueSimulado) -> None:
    def caido(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("detalle interno con una URL secreta")

    p = ProveedorSupabase(
        URL, CLAVE_PUBLICA, httpx.Client(transport=httpx.MockTransport(caido)), Reloj()
    )
    with pytest.raises(IdentidadNoDisponible) as e:
        p.autenticar(CORREO, CLAVE)
    assert str(e.value) == "ConnectError"


def test_las_respuestas_malformadas_dicen_que_estaba_mal(gotrue: GoTrueSimulado) -> None:
    p, rec = montar(gotrue)
    rec.sustitutos["POST /auth/v1/token"] = httpx.Response(200, content=b"<html>no es json</html>")
    with pytest.raises(IdentidadNoDisponible, match=r"^respuesta no JSON$"):
        p.autenticar(CORREO, CLAVE)
    rec.sustitutos["POST /auth/v1/token"] = httpx.Response(200, json=["una", "lista"])
    with pytest.raises(IdentidadNoDisponible, match=r"^respuesta inesperada$"):
        p.autenticar(CORREO, CLAVE)
    rec.sustitutos["POST /auth/v1/token"] = httpx.Response(200, json={"user": {"id": "x"}})
    with pytest.raises(IdentidadNoDisponible, match=r"^respuesta de token incompleta$"):
        p.autenticar(CORREO, CLAVE)


def test_una_inscripcion_sin_uri_y_una_verificacion_sin_token_son_indisponibilidad(
    gotrue: GoTrueSimulado,
) -> None:
    p, rec = montar(gotrue)
    primer = p.autenticar(CORREO, CLAVE)
    rec.sustitutos["POST /auth/v1/factors"] = httpx.Response(
        200, json={"id": "f1", "type": "totp", "totp": {}}
    )
    with pytest.raises(IdentidadNoDisponible, match=r"^inscripcion sin URI$"):
        p.inscribir_totp(primer.desafio_id)
    del rec.sustitutos["POST /auth/v1/factors"]
    p.inscribir_totp(primer.desafio_id)
    rec.sustitutos[f"POST /auth/v1/factors/{_factor(gotrue)}/verify"] = httpx.Response(200, json={})
    with pytest.raises(IdentidadNoDisponible, match=r"^verificacion sin token$"):
        p.verificar_totp(primer.desafio_id, CODIGO_VALIDO)


def _factor(g: GoTrueSimulado) -> str:
    return next(iter(g.usuarios[CORREO].factores))


def test_un_cierre_de_sesion_que_falla_no_impide_el_ingreso(gotrue: GoTrueSimulado) -> None:
    p, rec = montar(gotrue)
    rec.sustitutos["POST /auth/v1/logout"] = httpx.Response(500)
    primer = p.autenticar(CORREO, CLAVE)
    p.inscribir_totp(primer.desafio_id)
    verificada = p.verificar_totp(primer.desafio_id, CODIGO_VALIDO)
    assert (verificada.usuario_id, verificada.nivel) == ("u-ana", 2)


def test_un_segundo_ingreso_usa_el_factor_ya_verificado(gotrue: GoTrueSimulado) -> None:
    p, rec = montar(gotrue)
    primer = p.autenticar(CORREO, CLAVE)
    p.inscribir_totp(primer.desafio_id)
    p.verificar_totp(primer.desafio_id, CODIGO_VALIDO)
    rec.peticiones.clear()
    segundo = p.autenticar(CORREO, CLAVE)
    assert segundo.requiere_inscripcion is False
    p.verificar_totp(segundo.desafio_id, CODIGO_VALIDO)
    factor = _factor(gotrue)
    assert any(r.url.path == f"/auth/v1/factors/{factor}/challenge" for r in rec.peticiones)


def test_cada_codigo_fallido_cuenta_un_intento_y_el_ultimo_intento_aun_sirve(
    gotrue: GoTrueSimulado,
) -> None:
    p, _ = montar(gotrue)
    primer = p.autenticar(CORREO, CLAVE)
    p.inscribir_totp(primer.desafio_id)
    for _ in range(MAX_INTENTOS - 1):
        with pytest.raises(CredencialesInvalidas):
            p.verificar_totp(primer.desafio_id, "000000")
    verificada = p.verificar_totp(primer.desafio_id, CODIGO_VALIDO)  # quedaba un intento
    assert (verificada.usuario_id, verificada.nivel) == ("u-ana", 2)


def test_el_identificador_del_desafio_tiene_256_bits_de_entropia(gotrue: GoTrueSimulado) -> None:
    p, _ = montar(gotrue)
    ids = {p.autenticar(CORREO, CLAVE).desafio_id for _ in range(5)}
    assert len(ids) == 5
    assert {len(i) for i in ids} == {43}  # 32 bytes en base64 sin relleno


def test_un_desafio_vence_exactamente_a_los_cinco_minutos(gotrue: GoTrueSimulado) -> None:
    reloj = Reloj()
    p, _ = montar(gotrue, reloj)
    p.autenticar(CORREO, CLAVE)
    reloj.t += VIGENCIA_S - 0.001
    p.autenticar(CORREO, CLAVE)
    assert p.desafios_pendientes() == 2  # el primero aun vive un instante antes
    reloj.t += 0.001  # el primero llega justo a su vencimiento
    p.autenticar(CORREO, CLAVE)
    assert p.desafios_pendientes() == 2  # el primero ya se limpio


def test_descartar_un_desafio_que_no_existe_no_falla(gotrue: GoTrueSimulado) -> None:
    p, _ = montar(gotrue)
    p._descartar("no-existe")  # idempotente: un doble clic o un reintento no revienta


def test_la_url_con_barra_final_no_duplica_la_barra(gotrue: GoTrueSimulado) -> None:
    p, rec = montar(gotrue, url=URL + "/")
    p.autenticar(CORREO, CLAVE)
    assert rec.peticiones[0].url.path == "/auth/v1/token"


def test_el_cliente_por_defecto_tiene_un_plazo_de_diez_segundos() -> None:
    p = ProveedorSupabase(URL, CLAVE_PUBLICA)
    assert p._http.timeout == httpx.Timeout(10.0)


@pytest.mark.parametrize("largo_del_sub", [1, 2, 3, 4, 5, 6, 7, 8, 9])
def test_los_claims_se_leen_con_cualquier_relleno_de_base64(largo_del_sub: int) -> None:
    def b64(d: dict[str, str]) -> str:
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")

    sub = "x" * largo_del_sub
    assert _claims(f"{b64({'alg': 'HS256'})}.{b64({'sub': sub, 'aal': 'aal2'})}.firma") == {
        "sub": sub,
        "aal": "aal2",
    }


def test_un_token_ilegible_dice_que_es_ilegible() -> None:
    for malo in ("no-es-un-jwt", "a.%%%.c", "a.bm8gZXMganNvbg.c"):
        with pytest.raises(IdentidadNoDisponible, match=r"^token ilegible$"):
            _claims(malo)
