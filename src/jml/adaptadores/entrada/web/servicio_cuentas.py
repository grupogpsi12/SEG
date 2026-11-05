"""Servicio interno de cuentas (ADR-035): lo unico que corre con `service_role` (invariante 8).

Vive en el contenedor `admin-usuarios` y solo atiende a `web`, por la red interna `admin_net`:
escucha en la IP de esa red, no en las demas, y exige un token propio. Solo habla con Supabase
Auth; los roles, la auditoria y los permisos los decide el caso de uso, en `web`. Biblioteca
estandar a proposito: son cuatro rutas y una dependencia junto a esta clave seria mas superficie.
"""

import json
import logging
import re
import secrets
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Protocol

from jml.adaptadores.salida.identidad.administracion import ErrorDeAdministracion
from jml.aplicacion.puertos import IdentidadNoDisponible

PUERTO = 8090
MAXIMO_CUERPO = 4096
_ID = re.compile(
    r"^/cuentas/([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})/(desactivar|reactivar|eliminar)$"
)
_CORREO = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}$")
registro = logging.getLogger(__name__)


class Administrador(Protocol):
    def crear(self, correo: str, contrasena: str) -> str: ...
    def desactivar(self, usuario_id: str) -> None: ...
    def reactivar(self, usuario_id: str) -> None: ...
    def eliminar(self, usuario_id: str) -> None: ...
    def correos(self) -> dict[str, str]: ...


class _Servidor(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, direccion: tuple[str, int], admin: Administrador | None, token: str) -> None:
        super().__init__(direccion, _Manejador)
        self.admin = admin
        self.token = token


class _Manejador(BaseHTTPRequestHandler):
    server: _Servidor
    timeout = 20
    server_version = "cuentas"
    sys_version = ""

    def log_message(self, format: str, *args: object) -> None:
        # Sin cuerpos ni cabeceras: por aqui pasan correos, contrasenas iniciales y el token.
        if self.path == "/salud":
            return  # cada 30 s: taparia lo que importa
        registro.info("servicio de cuentas: %s", self.requestline.split(" HTTP")[0])

    def _responder(self, codigo: int, cuerpo: dict[str, object] | None = None) -> None:
        datos = b"" if cuerpo is None else json.dumps(cuerpo).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(datos)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(datos)

    def _autorizado(self) -> bool:
        recibido = self.headers.get("Authorization", "")
        esperado = f"Bearer {self.server.token}"
        return bool(self.server.token) and secrets.compare_digest(
            recibido.encode("utf-8"), esperado.encode("utf-8")
        )

    def _cuerpo(self) -> dict[str, object] | None:
        try:
            largo = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None
        if not 0 < largo <= MAXIMO_CUERPO:
            return None
        try:
            datos = json.loads(self.rfile.read(largo))
        except ValueError:
            return None
        return datos if isinstance(datos, dict) else None

    def _ejecutar(self, admin: Administrador) -> None:
        if self.command == "GET" and self.path == "/cuentas":
            self._responder(200, {"correos": admin.correos()})
            return
        if self.command == "POST" and self.path == "/cuentas":
            cuerpo = self._cuerpo()
            correo = None if cuerpo is None else cuerpo.get("correo")
            if not isinstance(correo, str) or not _CORREO.fullmatch(correo):
                self._responder(400, {"codigo": "correo_invalido"})
                return
            contrasena = secrets.token_urlsafe(18)  # 24 caracteres (RS-16 pide al menos 12)
            self._responder(201, {"id": admin.crear(correo, contrasena), "contrasena": contrasena})
            return
        coincide = _ID.fullmatch(self.path) if self.command == "POST" else None
        if coincide is None:
            self._responder(404, {"codigo": "ruta"})
            return
        getattr(admin, coincide.group(2))(coincide.group(1))
        self._responder(204)

    def _atender(self) -> None:
        if self.command == "GET" and self.path == "/salud":
            self._responder(200, {"estado": "ok"})
            return
        if not self._autorizado():
            self._responder(401, {"codigo": "token"})
            return
        admin = self.server.admin
        if admin is None:  # quien no tiene la clave (ADR-029) usa el resto de la aplicacion
            self._responder(503, {"codigo": "sin_clave"})
            return
        try:
            self._ejecutar(admin)
        except ErrorDeAdministracion as e:
            self._responder(409, {"codigo": str(e)})
        except IdentidadNoDisponible:
            self._responder(503, {"codigo": "supabase"})

    def do_GET(self) -> None:  # nombre que exige http.server
        self._atender()

    def do_POST(self) -> None:  # nombre que exige http.server
        self._atender()


def crear_servidor(host: str, puerto: int, admin: Administrador | None, token: str) -> _Servidor:
    return _Servidor((host, puerto), admin, token)


def ip_en_la_red(puerta_de_enlace: str) -> str:
    """La IP de este contenedor en `admin_net`. Un socket UDP no envia nada al conectarse: solo
    resuelve la ruta. Asi el servicio no escucha en `app`, donde estan el WAF, GLPI y el worker."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect((puerta_de_enlace, 9))
        return str(s.getsockname()[0])
