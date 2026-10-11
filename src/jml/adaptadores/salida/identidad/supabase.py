"""ProveedorDeIdentidad sobre la API REST de Supabase Auth (GoTrue), mediado por el servidor.

ADR-017.

Invariante 9: los tokens de Supabase NO se guardan. Entre la contrasena y el codigo TOTP el token
de nivel AAL1 vive solo en la memoria de este proceso, bajo un `desafio_id` aleatorio, durante
`VIGENCIA` como maximo; nunca va a la base, a la sesion, a un log ni al navegador. Por eso la
web corre con un solo proceso de gunicorn (con hilos): un desafio creado en un proceso no
existe en otro. Al llegar a AAL2 se cierra la sesion de Supabase y se descarta todo token.
"""

import base64
import contextlib
import json
import re
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from jml.aplicacion.puertos import (
    CredencialesInvalidas,
    IdentidadNoDisponible,
    IdentidadVerificada,
    PrimerFactor,
)

VIGENCIA_S = 300.0  # 5 minutos para completar el segundo factor
MAX_INTENTOS = 5  # codigos fallidos por desafio; ademas BunkerWeb limita por IP (RS-08)
_CODIGO = re.compile(r"^\d{6}$")
_EMISOR = "Andina Servicios"


@dataclass
class _Pendiente:
    usuario_id: str
    token_aal1: str
    factor_id: str | None
    verificado: bool  # el factor ya estaba verificado al autenticar (no se inscribe otro)
    vence: float
    intentos: int = 0


def _claims(jwt: str) -> dict[str, Any]:
    """Lee el cuerpo del JWT sin verificar la firma: llega de Supabase por TLS en respuesta a
    una peticion de este servidor, no del navegador. Solo se usa para confirmar `aal` y `sub`."""
    try:
        cuerpo = jwt.split(".")[1]
        datos = json.loads(base64.urlsafe_b64decode(cuerpo + "=" * (-len(cuerpo) % 4)))
    except (IndexError, ValueError) as e:
        raise IdentidadNoDisponible("token ilegible") from e
    if not isinstance(datos, dict):
        raise IdentidadNoDisponible("token ilegible")
    return datos


class ProveedorSupabase:
    def __init__(
        self,
        url: str,
        clave_publica: str,
        cliente: httpx.Client | None = None,
        reloj: Callable[[], float] = time.monotonic,
    ) -> None:
        self._base = url.rstrip("/") + "/auth/v1"
        self._clave = clave_publica
        self._http = cliente or httpx.Client(timeout=10.0)
        self._reloj = reloj
        self._pendientes: dict[str, _Pendiente] = {}
        self._candado = threading.Lock()

    # --- HTTP -------------------------------------------------------------------------------

    def _pedir(
        self, metodo: str, ruta: str, token: str | None = None, cuerpo: object = None
    ) -> httpx.Response:
        cabeceras = {"apikey": self._clave}
        if token is not None:
            cabeceras["Authorization"] = f"Bearer {token}"
        try:
            r = self._http.request(metodo, self._base + ruta, headers=cabeceras, json=cuerpo)
        except httpx.HTTPError as e:
            raise IdentidadNoDisponible(type(e).__name__) from None
        if r.status_code >= 500 or r.status_code == 429:
            raise IdentidadNoDisponible(f"HTTP {r.status_code}")
        return r

    @staticmethod
    def _json(r: httpx.Response) -> dict[str, Any]:
        try:
            datos = r.json()
        except ValueError:
            raise IdentidadNoDisponible("respuesta no JSON") from None
        if not isinstance(datos, dict):
            raise IdentidadNoDisponible("respuesta inesperada")
        return datos

    # --- desafios en memoria ----------------------------------------------------------------

    def _guardar(self, p: _Pendiente) -> str:
        desafio = secrets.token_urlsafe(32)
        with self._candado:
            ahora = self._reloj()
            for clave in [k for k, v in self._pendientes.items() if v.vence <= ahora]:
                del self._pendientes[clave]  # limpieza perezosa de los vencidos
            self._pendientes[desafio] = p
        return desafio

    def _pendiente(self, desafio_id: str) -> _Pendiente:
        with self._candado:
            p = self._pendientes.get(desafio_id)
            if p is None or p.vence <= self._reloj():
                self._pendientes.pop(desafio_id, None)
                raise CredencialesInvalidas
            return p

    def _descartar(self, desafio_id: str) -> None:
        with self._candado:
            self._pendientes.pop(desafio_id, None)

    def desafios_pendientes(self) -> int:
        """Para pruebas y monitoreo: cuantos segundos factores hay a medio camino."""
        with self._candado:
            return len(self._pendientes)

    # --- puerto -----------------------------------------------------------------------------

    def autenticar(self, correo: str, contrasena: str) -> PrimerFactor:
        r = self._pedir(
            "POST",
            "/token?grant_type=password",
            cuerpo={"email": correo.strip().lower(), "password": contrasena},
        )
        if r.status_code != 200:
            raise CredencialesInvalidas  # 400/401/422: identico para correo y clave (RS-08)
        datos = self._json(r)
        usuario = datos.get("user")
        token = datos.get("access_token")
        if not isinstance(usuario, dict) or not isinstance(token, str):
            raise IdentidadNoDisponible("respuesta de token incompleta")
        verificados = [
            f["id"]
            for f in usuario.get("factors") or []
            if f.get("factor_type") == "totp" and f.get("status") == "verified"
        ]
        usuario_id = str(usuario["id"])
        desafio = self._guardar(
            _Pendiente(
                usuario_id=usuario_id,
                token_aal1=token,
                factor_id=verificados[0] if verificados else None,
                verificado=bool(verificados),
                vence=self._reloj() + VIGENCIA_S,
            )
        )
        return PrimerFactor(usuario_id, desafio, requiere_inscripcion=not verificados)

    def inscribir_totp(self, desafio_id: str) -> str:
        p = self._pendiente(desafio_id)
        if p.verificado:
            # Con solo la contrasena nadie agrega un segundo factor a una cuenta que ya tiene uno.
            raise CredencialesInvalidas
        self._borrar_no_verificados(p.token_aal1)
        r = self._pedir(
            "POST", "/factors", p.token_aal1, {"factor_type": "totp", "issuer": _EMISOR}
        )
        if r.status_code != 200:
            raise IdentidadNoDisponible(f"inscripcion rechazada: HTTP {r.status_code}")
        datos = self._json(r)
        totp = datos.get("totp")
        if not isinstance(totp, dict) or not isinstance(totp.get("uri"), str):
            raise IdentidadNoDisponible("inscripcion sin URI")
        with self._candado:
            p.factor_id = str(datos["id"])
        return str(totp["uri"])

    def _borrar_no_verificados(self, token: str) -> None:
        """Una inscripcion abandonada deja un factor sin verificar; Supabase limita cuantos hay."""
        r = self._pedir("GET", "/user", token)
        if r.status_code != 200:
            return
        for f in self._json(r).get("factors") or []:
            if f.get("status") == "unverified":
                self._pedir("DELETE", f"/factors/{f['id']}", token)

    def verificar_totp(self, desafio_id: str, codigo: str) -> IdentidadVerificada:
        p = self._pendiente(desafio_id)
        if p.factor_id is None or not _CODIGO.fullmatch(codigo.strip()):
            raise CredencialesInvalidas  # RF-02: sin factor inscrito no hay AAL2
        reto = self._pedir("POST", f"/factors/{p.factor_id}/challenge", p.token_aal1)
        if reto.status_code != 200:
            raise IdentidadNoDisponible(f"desafio rechazado: HTTP {reto.status_code}")
        r = self._pedir(
            "POST",
            f"/factors/{p.factor_id}/verify",
            p.token_aal1,
            {"challenge_id": self._json(reto).get("id"), "code": codigo.strip()},
        )
        if r.status_code != 200:
            with self._candado:
                p.intentos += 1
                agotado = p.intentos >= MAX_INTENTOS
            if agotado:
                self._descartar(desafio_id)
            raise CredencialesInvalidas
        token_aal2 = self._json(r).get("access_token")
        if not isinstance(token_aal2, str):
            raise IdentidadNoDisponible("verificacion sin token")
        claims = _claims(token_aal2)
        self._descartar(desafio_id)  # un desafio se usa una sola vez
        if claims.get("aal") != "aal2" or claims.get("sub") != p.usuario_id:
            raise CredencialesInvalidas
        # La sesion de Supabase no se usa: se cierra para que su refresh token no sirva a nadie.
        # Es un mejor esfuerzo: si falla, el token igual se descarta y vence solo.
        with contextlib.suppress(IdentidadNoDisponible):
            self._pedir("POST", "/logout?scope=local", token_aal2)
        return IdentidadVerificada(p.usuario_id, nivel=2)
