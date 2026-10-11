"""Alta y baja de cuentas en Supabase Auth con la clave `service_role` (RF-06, invariante 8).

Solo la usa el comando `admin_usuarios`, que corre en el contenedor `admin-usuarios`: es el
unico que monta el secreto `supabase_service_role`. La web y el worker nunca lo importan.
"""

from typing import Any

import httpx

from jml.aplicacion.puertos import IdentidadNoDisponible

BANEO_INDEFINIDO = "876000h"  # ~100 anios: Supabase no tiene "desactivar", solo banear


class ErrorDeAdministracion(Exception):
    """Supabase rechazo la operacion (p. ej. el correo ya existe o la contrasena es debil)."""


class AdministradorSupabase:
    def __init__(self, url: str, clave_servicio: str, cliente: httpx.Client | None = None) -> None:
        self._base = url.rstrip("/") + "/auth/v1/admin/users"
        self._cabeceras = {"apikey": clave_servicio, "Authorization": f"Bearer {clave_servicio}"}
        self._http = cliente or httpx.Client(timeout=15.0)

    def _pedir(self, metodo: str, ruta: str = "", cuerpo: object = None) -> dict[str, Any]:
        try:
            r = self._http.request(metodo, self._base + ruta, headers=self._cabeceras, json=cuerpo)
        except httpx.HTTPError as e:
            raise IdentidadNoDisponible(type(e).__name__) from None
        if r.status_code >= 500:
            raise IdentidadNoDisponible(f"HTTP {r.status_code}")
        if r.status_code >= 400:
            # El mensaje de Supabase no lleva secretos (p. ej. "email_exists"); se muestra al admin.
            try:
                detalle = r.json().get("error_code") or r.json().get("msg") or r.status_code
            except ValueError:
                detalle = r.status_code
            raise ErrorDeAdministracion(str(detalle))
        return r.json() if r.content else {}

    def crear(self, correo: str, contrasena: str) -> str:
        """Crea la cuenta confirmada (no hay correos: fuera de alcance) y devuelve su id."""
        datos = self._pedir(
            "POST",
            cuerpo={"email": correo.strip().lower(), "password": contrasena, "email_confirm": True},
        )
        return str(datos["id"])

    def desactivar(self, usuario_id: str) -> None:
        self._pedir("PUT", f"/{usuario_id}", {"ban_duration": BANEO_INDEFINIDO})

    def eliminar(self, usuario_id: str) -> None:
        """Compensacion: si la base falla tras crear la cuenta, no queda una cuenta huerfana."""
        self._pedir("DELETE", f"/{usuario_id}")
