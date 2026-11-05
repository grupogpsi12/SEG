"""Alta y baja de cuentas en Supabase Auth con la clave `service_role` (RF-06, invariante 8).

Solo la usa el contenedor `admin-usuarios`, con su comando y su servicio interno (ADR-035): es el
unico que monta el secreto `supabase_service_role`. La web y el worker nunca lo instancian.
"""

from typing import Any

import httpx

from jml.aplicacion.puertos import IdentidadNoDisponible

BANEO_INDEFINIDO = "876000h"  # ~100 anios: Supabase no tiene "desactivar", solo banear
_MAXIMO_DE_PAGINAS = 50


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

    def reactivar(self, usuario_id: str) -> None:
        self._pedir("PUT", f"/{usuario_id}", {"ban_duration": "none"})

    def eliminar(self, usuario_id: str) -> None:
        """Tambien es la compensacion: si la base falla tras crear, no queda una cuenta huerfana."""
        self._pedir("DELETE", f"/{usuario_id}")

    def correos(self) -> dict[str, str]:
        """Id -> correo de todas las cuentas, por paginas."""
        correos: dict[str, str] = {}
        for pagina in range(1, _MAXIMO_DE_PAGINAS + 1):
            usuarios = self._pedir("GET", f"?page={pagina}&per_page=200").get("users", [])
            if not usuarios:
                break
            correos.update({str(u["id"]): str(u.get("email", "")) for u in usuarios})
        return correos
