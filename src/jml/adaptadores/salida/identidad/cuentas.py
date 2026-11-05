"""Cliente del servicio interno de cuentas (ADR-035): implementa `AdministradorDeCuentas`.

`web` nunca ve `service_role` (invariante 8, RS-15). Solo tiene un token con el que le pide al
contenedor `admin-usuarios` las operaciones sobre cuentas, por la red interna `admin_net`.
"""

from collections.abc import Mapping
from typing import Any

import httpx

from jml.aplicacion.puertos import CuentaCreada, CuentaRechazada, IdentidadNoDisponible


class ClienteDeCuentas:
    def __init__(self, url: str, token: str, cliente: httpx.Client | None = None) -> None:
        self._url = url.rstrip("/")
        self._token = token
        self._http = cliente or httpx.Client(timeout=15.0, trust_env=False)

    def _pedir(
        self, metodo: str, ruta: str, cuerpo: object = None, timeout: float = 15.0
    ) -> dict[str, Any]:
        if not self._token:
            raise IdentidadNoDisponible("sin token del servicio de cuentas")
        try:
            r = self._http.request(
                metodo,
                self._url + ruta,
                headers={"Authorization": f"Bearer {self._token}"},
                json=cuerpo,
                timeout=timeout,
            )
        except httpx.HTTPError as e:
            raise IdentidadNoDisponible(type(e).__name__) from None
        if r.status_code >= 500 or r.status_code == 401:
            raise IdentidadNoDisponible(f"HTTP {r.status_code}")
        try:
            datos = r.json() if r.content else {}
        except ValueError:
            raise IdentidadNoDisponible("respuesta ilegible") from None
        if r.status_code >= 400:
            raise CuentaRechazada(str(datos.get("codigo", r.status_code)))
        return datos if isinstance(datos, dict) else {}

    def crear(self, correo: str) -> CuentaCreada:
        d = self._pedir("POST", "/cuentas", {"correo": correo})
        return CuentaCreada(str(d["id"]), str(d["contrasena"]))

    def desactivar(self, usuario_id: str) -> None:
        self._pedir("POST", f"/cuentas/{usuario_id}/desactivar")

    def reactivar(self, usuario_id: str) -> None:
        self._pedir("POST", f"/cuentas/{usuario_id}/reactivar")

    def eliminar(self, usuario_id: str) -> None:
        self._pedir("POST", f"/cuentas/{usuario_id}/eliminar")

    def correos(self) -> Mapping[str, str]:
        # Solo adorna la lista de usuarios: un Supabase lento no debe frenar la pagina (RNF-06).
        d = self._pedir("GET", "/cuentas", timeout=3.0).get("correos", {})
        return {str(k): str(v) for k, v in d.items()} if isinstance(d, dict) else {}
