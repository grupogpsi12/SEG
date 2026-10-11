"""GoTrue (Supabase Auth) simulado sobre `httpx.MockTransport`.

Reproduce solo lo que usa el adaptador: token por contrasena, factores TOTP (inscribir, desafiar,
verificar, borrar), /user, /logout y la API de administracion. Imita dos reglas de Supabase que
importan para la seguridad: con AAL1 no se inscribe un factor si ya hay uno verificado, y
`verify` devuelve un token con `aal: aal2`. Lleva la cuenta de las llamadas para las pruebas.
"""

import base64
import json
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx

from tests.dobles.identidad import CODIGO_VALIDO

CLAVE_PUBLICA = "sb_publishable_prueba"
CLAVE_SERVICIO = "sb_secret_prueba"


def jwt(sub: str, aal: str) -> str:
    def b64(d: dict[str, str]) -> str:
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")

    return f"{b64({'alg': 'HS256'})}.{b64({'sub': sub, 'aal': aal})}.firma"


@dataclass
class _Usuario:
    id: str
    correo: str
    contrasena: str
    factores: dict[str, str] = field(default_factory=dict)  # id -> "verified" | "unverified"
    baneado: bool = False


@dataclass
class GoTrueSimulado:
    usuarios: dict[str, _Usuario] = field(default_factory=dict)  # correo -> usuario
    tokens: dict[str, tuple[str, str]] = field(default_factory=dict)  # token -> (sub, aal)
    llamadas: list[str] = field(default_factory=list)
    caido: bool = False
    respuesta_aal2: str = "aal2"  # se puede alterar para probar que el adaptador lo verifica

    def registrar(self, correo: str, contrasena: str, usuario_id: str) -> None:
        self.usuarios[correo] = _Usuario(usuario_id, correo, contrasena)

    def cliente(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.manejar))

    def _por_id(self, uid: str) -> _Usuario | None:
        return next((u for u in self.usuarios.values() if u.id == uid), None)

    def _token(self, sub: str, aal: str) -> str:
        t = jwt(sub, aal) + uuid.uuid4().hex  # unico aunque se repitan sub y aal
        self.tokens[t] = (sub, aal)
        return t

    def _usuario_json(self, u: _Usuario) -> dict[str, Any]:
        factores = [
            {"id": fid, "factor_type": "totp", "status": estado}
            for fid, estado in u.factores.items()
        ]
        return {"id": u.id, "email": u.correo, **({"factors": factores} if factores else {})}

    def manejar(self, peticion: httpx.Request) -> httpx.Response:
        ruta = peticion.url.path
        self.llamadas.append(f"{peticion.method} {ruta}")
        if self.caido:
            return httpx.Response(503)
        if ruta.startswith("/auth/v1/admin/"):
            return self._admin(peticion, ruta)
        if peticion.headers.get("apikey") != CLAVE_PUBLICA:
            return httpx.Response(401, json={"msg": "no apikey"})
        cuerpo = json.loads(peticion.content) if peticion.content else {}
        if ruta == "/auth/v1/token":
            u = self.usuarios.get(cuerpo.get("email", ""))
            if u is None or u.contrasena != cuerpo.get("password") or u.baneado:
                return httpx.Response(400, json={"error_code": "invalid_credentials"})
            return httpx.Response(
                200, json={"access_token": self._token(u.id, "aal1"), "user": self._usuario_json(u)}
            )
        portador = peticion.headers.get("authorization", "").removeprefix("Bearer ")
        if portador not in self.tokens:
            return httpx.Response(401, json={"msg": "token invalido"})
        sub, aal = self.tokens[portador]
        u = self._por_id(sub)
        assert u is not None
        partes = ruta.removeprefix("/auth/v1/").split("/")
        if partes == ["user"]:
            return httpx.Response(200, json=self._usuario_json(u))
        if partes == ["logout"]:
            for t in [t for t, (s, _) in self.tokens.items() if s == sub]:
                del self.tokens[t]
            return httpx.Response(204)
        if partes == ["factors"] and peticion.method == "POST":
            if aal == "aal1" and "verified" in u.factores.values():
                return httpx.Response(422, json={"error_code": "insufficient_aal"})
            fid = uuid.uuid4().hex
            u.factores[fid] = "unverified"
            uri = f"otpauth://totp/Andina%20Servicios:{u.correo}?secret=JBSWY3DPEHPK3PXP"
            return httpx.Response(200, json={"id": fid, "type": "totp", "totp": {"uri": uri}})
        if len(partes) == 2 and partes[0] == "factors" and peticion.method == "DELETE":
            u.factores.pop(partes[1], None)
            return httpx.Response(200, json={"id": partes[1]})
        if len(partes) == 3 and partes[2] == "challenge":
            if partes[1] not in u.factores:
                return httpx.Response(404)
            return httpx.Response(200, json={"id": uuid.uuid4().hex})
        if len(partes) == 3 and partes[2] == "verify":
            if partes[1] not in u.factores or cuerpo.get("code") != CODIGO_VALIDO:
                return httpx.Response(422, json={"error_code": "mfa_verification_failed"})
            u.factores[partes[1]] = "verified"
            return httpx.Response(200, json={"access_token": self._token(sub, self.respuesta_aal2)})
        return httpx.Response(404)

    def _admin(self, peticion: httpx.Request, ruta: str) -> httpx.Response:
        if peticion.headers.get("authorization") != f"Bearer {CLAVE_SERVICIO}":
            return httpx.Response(401, json={"msg": "no autorizado"})
        cuerpo = json.loads(peticion.content) if peticion.content else {}
        resto = ruta.removeprefix("/auth/v1/admin/users").strip("/")
        if peticion.method == "POST" and not resto:
            if cuerpo["email"] in self.usuarios:
                return httpx.Response(422, json={"error_code": "email_exists"})
            if len(cuerpo["password"]) < 12:
                return httpx.Response(422, json={"error_code": "weak_password"})
            uid = str(uuid.uuid4())
            self.registrar(cuerpo["email"], cuerpo["password"], uid)
            return httpx.Response(200, json={"id": uid, "email": cuerpo["email"]})
        u = self._por_id(resto)
        if u is None:
            return httpx.Response(404, json={"error_code": "user_not_found"})
        if peticion.method == "PUT":
            u.baneado = cuerpo.get("ban_duration") not in (None, "none")
            return httpx.Response(200, json={"id": u.id})
        if peticion.method == "DELETE":
            del self.usuarios[u.correo]
            return httpx.Response(200, json={})
        return httpx.Response(405)
