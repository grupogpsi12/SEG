"""Spike 0.4 / item 2.5 contra el Supabase Auth REAL del proyecto de desarrollo.

    JML_SUPABASE_URL=https://<ref>.supabase.co JML_SUPABASE_CLAVE_PUBLICA=sb_publishable_... \
        pytest --ds tests.adaptadores.ajustes tests/integracion/test_supabase_auth.py

El flujo completo (crear cuenta, inscribir TOTP, verificar, borrar) necesita ademas el secreto
`secrets/supabase_service_role`; sin el se omite con el motivo S-28. El codigo TOTP se calcula
aqui con RFC 6238 (biblioteca estandar), igual que lo haria la app autenticadora.
"""

import base64
import hashlib
import hmac
import os
import secrets
import struct
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from jml.adaptadores.salida.identidad.administracion import AdministradorSupabase
from jml.adaptadores.salida.identidad.supabase import ProveedorSupabase
from jml.aplicacion.puertos import CredencialesInvalidas

URL = os.environ.get("JML_SUPABASE_URL", "")
CLAVE = os.environ.get("JML_SUPABASE_CLAVE_PUBLICA", "")
# No usa JML_SECRETOS_DIR: tests/adaptadores/ajustes.py lo redefine a una carpeta temporal (leccion 39).
SERVICIO = Path(
    os.environ.get("JML_SERVICE_ROLE_ARCHIVO")
    or Path(__file__).resolve().parents[2] / "secrets" / "supabase_service_role"
)

pytestmark = pytest.mark.skipif(not (URL and CLAVE), reason="S-28: sin proyecto de Supabase")


def totp(secreto: str, instante: float | None = None) -> str:
    clave = base64.b32decode(secreto.upper() + "=" * (-len(secreto) % 8))
    contador = struct.pack(">Q", int((instante or time.time()) // 30))
    h = hmac.new(clave, contador, hashlib.sha1).digest()
    desplazamiento = h[-1] & 0x0F
    numero = struct.unpack(">I", h[desplazamiento : desplazamiento + 4])[0] & 0x7FFFFFFF
    return f"{numero % 1_000_000:06d}"


def test_totp_coincide_con_el_vector_de_la_rfc_6238() -> None:
    # RFC 6238, apendice B, SHA-1, T = 59 s -> 94287082 (8 digitos); con 6 digitos: 287082
    assert totp(base64.b32encode(b"12345678901234567890").decode(), 59) == "287082"


def test_RS_16_el_registro_abierto_esta_deshabilitado() -> None:
    r = httpx.get(f"{URL}/auth/v1/settings", headers={"apikey": CLAVE}, timeout=15)
    assert r.json()["disable_signup"] is True, "Supabase: Authentication > Sign In > Allow signups"


@pytest.mark.parametrize(
    "tabla", ["solicitud", "solicitud_restringida", "auditoria", "colaborador"]
)
def test_RD_10_la_data_api_no_expone_las_tablas_de_la_aplicacion(tabla: str) -> None:
    """Spike 0.2: ni por `public` ni pidiendo el esquema `app` se llega a una tabla."""
    cabeceras = {"apikey": CLAVE}
    publico = httpx.get(f"{URL}/rest/v1/{tabla}?limit=1", headers=cabeceras, timeout=15)
    assert publico.status_code == 404
    app = httpx.get(
        f"{URL}/rest/v1/{tabla}?limit=1", headers={**cabeceras, "Accept-Profile": "app"}, timeout=15
    )
    assert app.status_code >= 400
    assert app.json()["code"] == "PGRST106"  # Invalid schema: app


def test_RS_08_un_correo_inexistente_da_el_error_generico() -> None:
    with pytest.raises(CredencialesInvalidas):
        ProveedorSupabase(URL, CLAVE).autenticar(
            f"nadie-{secrets.token_hex(4)}@andina.example", "x" * 12
        )


@pytest.mark.skipif(not SERVICIO.exists(), reason="S-28: falta secrets/supabase_service_role")
def test_flujo_completo_contrasena_inscripcion_y_aal2() -> None:
    admin = AdministradorSupabase(URL, SERVICIO.read_text(encoding="utf-8").strip())
    correo, clave = f"spike-{secrets.token_hex(4)}@andina.example", secrets.token_urlsafe(18)
    uid = admin.crear(correo, clave)
    try:
        p = ProveedorSupabase(URL, CLAVE)
        primer = p.autenticar(correo, clave)
        assert (primer.usuario_id, primer.requiere_inscripcion) == (uid, True)
        secreto = parse_qs(urlparse(p.inscribir_totp(primer.desafio_id)).query)["secret"][0]
        with pytest.raises(CredencialesInvalidas):
            p.verificar_totp(primer.desafio_id, "000000" if totp(secreto) != "000000" else "111111")
        assert p.verificar_totp(primer.desafio_id, totp(secreto)).nivel == 2
        # segundo ingreso: ya no se inscribe, y con solo la contrasena no se agrega otro factor
        segundo = p.autenticar(correo, clave)
        assert segundo.requiere_inscripcion is False
        with pytest.raises(CredencialesInvalidas):
            p.inscribir_totp(segundo.desafio_id)
        time.sleep(31)  # Supabase rechaza reutilizar el mismo codigo en la misma ventana
        assert p.verificar_totp(segundo.desafio_id, totp(secreto)).nivel == 2
    finally:
        admin.eliminar(uid)
