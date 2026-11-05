"""F3-COV (T1, RS-08): el adaptador de Supabase falla CERRADO ante respuestas raras.

Toda respuesta que no tenga la forma esperada (no JSON, JSON que no es objeto, token ilegible,
falta de campos) acaba en `IdentidadNoDisponible` o `CredencialesInvalidas`: nunca en una
identidad verificada ni en una excepción sin traducir.
"""

import base64
import json
from collections.abc import Callable

import httpx
import pytest

from jml.adaptadores.salida.identidad.supabase import ProveedorSupabase
from jml.aplicacion.puertos import CredencialesInvalidas, IdentidadNoDisponible
from tests.dobles.gotrue import CLAVE_PUBLICA, jwt

pytestmark = pytest.mark.seguridad

Ruta = Callable[[httpx.Request], httpx.Response]


def ok(cuerpo: object, estado: int = 200) -> Ruta:
    return lambda _: httpx.Response(estado, json=cuerpo)


def proveedor(rutas: dict[str, Ruta]) -> ProveedorSupabase:
    """Responde por «MÉTODO sufijo-de-ruta»; lo no declarado es un 404 que haría fallar la prueba."""

    def manejar(p: httpx.Request) -> httpx.Response:
        clave = f"{p.method} {p.url.path.removeprefix('/auth/v1')}"
        for patron, ruta in rutas.items():
            if clave == patron or (patron.endswith("*") and clave.startswith(patron[:-1])):
                return ruta(p)
        return httpx.Response(404, json={"msg": f"ruta no simulada: {clave}"})

    return ProveedorSupabase(
        "https://x.supabase.co", CLAVE_PUBLICA, httpx.Client(transport=httpx.MockTransport(manejar))
    )


USUARIO = {"id": "u-1", "factors": []}
TOKEN = jwt("u-1", "aal1")


def con_factor(rutas: dict[str, Ruta]) -> tuple[ProveedorSupabase, str]:
    """Un proveedor que ya pasó la contraseña y tiene un factor inscrito, con `rutas` añadidas."""
    base: dict[str, Ruta] = {
        "POST /token": ok({"access_token": TOKEN, "user": USUARIO}),
        "GET /user": ok({"factors": []}),
        "POST /factors": ok({"id": "f-1", "totp": {"uri": "otpauth://totp/x?secret=ABC"}}),
        "POST /factors/f-1/challenge": ok({"id": "r-1"}),
    }
    p = proveedor({**base, **rutas})
    desafio = p.autenticar("a@b.co", "clave").desafio_id
    p.inscribir_totp(desafio)
    return p, desafio


def test_autenticar_con_respuesta_incompleta_no_da_identidad() -> None:
    with pytest.raises(IdentidadNoDisponible, match="incompleta"):
        proveedor({"POST /token": ok({"access_token": TOKEN})}).autenticar("a@b.co", "c")


@pytest.mark.parametrize("cuerpo", [b"<html>502</html>", b"[1, 2]", b'"texto"'])
def test_una_respuesta_que_no_es_un_objeto_json_es_servicio_no_disponible(cuerpo: bytes) -> None:
    p = proveedor({"POST /token": lambda _: httpx.Response(200, content=cuerpo)})
    with pytest.raises(IdentidadNoDisponible):
        p.autenticar("a@b.co", "c")


def test_inscribir_con_rechazo_o_sin_uri_no_inscribe() -> None:
    base: dict[str, Ruta] = {
        "POST /token": ok({"access_token": TOKEN, "user": USUARIO}),
        "GET /user": lambda _: httpx.Response(401, json={}),  # no se pudo listar: se sigue
    }
    p = proveedor({**base, "POST /factors": ok({}, 403)})
    with pytest.raises(IdentidadNoDisponible, match="inscripcion rechazada"):
        p.inscribir_totp(p.autenticar("a@b.co", "c").desafio_id)
    q = proveedor({**base, "POST /factors": ok({"id": "f", "totp": {}})})
    with pytest.raises(IdentidadNoDisponible, match="sin URI"):
        q.inscribir_totp(q.autenticar("a@b.co", "c").desafio_id)


def test_los_factores_verificados_no_se_borran_al_limpiar_inscripciones_abandonadas() -> None:
    borrados: list[str] = []

    def borrar(r: httpx.Request) -> httpx.Response:
        borrados.append(r.url.path)
        return httpx.Response(200)

    p, _ = con_factor(
        {
            "GET /user": ok({"factors": [{"id": "v", "status": "verified"}]}),
            "DELETE /factors/*": borrar,
        }
    )
    assert borrados == []
    assert p.desafios_pendientes() == 1


def test_un_desafio_rechazado_por_supabase_no_da_identidad() -> None:
    p, d = con_factor({"POST /factors/f-1/challenge": ok({}, 403)})
    with pytest.raises(IdentidadNoDisponible, match="desafio rechazado"):
        p.verificar_totp(d, "123456")


def test_una_verificacion_sin_token_no_da_identidad() -> None:
    p, d = con_factor({"POST /factors/f-1/verify": ok({"expires_in": 3600})})
    with pytest.raises(IdentidadNoDisponible, match="sin token"):
        p.verificar_totp(d, "123456")


def b64(datos: object) -> str:
    return base64.urlsafe_b64encode(json.dumps(datos).encode()).decode().rstrip("=")


@pytest.mark.parametrize(
    "token", ["sin-puntos", "a.%%%.c", f"a.{b64([1, 2])}.c", f"a.{b64('texto')}.c"], ids=str
)
def test_un_token_ilegible_no_da_identidad(token: str) -> None:
    p, d = con_factor({"POST /factors/f-1/verify": ok({"access_token": token})})
    with pytest.raises(IdentidadNoDisponible, match="ilegible"):
        p.verificar_totp(d, "123456")


def test_un_token_de_otro_usuario_no_da_identidad() -> None:
    """`sub` distinto del que pasó la contraseña: el desafío no puede cambiar de dueño (T1)."""
    p, d = con_factor({"POST /factors/f-1/verify": ok({"access_token": jwt("u-2", "aal2")})})
    with pytest.raises(CredencialesInvalidas):
        p.verificar_totp(d, "123456")
