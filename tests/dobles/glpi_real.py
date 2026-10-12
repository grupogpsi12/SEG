"""Ayudantes de la suite de contrato contra un GLPI REAL (spike 0.3).

`TecnicoGlpiReal` trabaja los tickets como una persona de TI, con la cuenta de ADMINISTRADOR de
GLPI (no la de servicio: la de servicio no resuelve tickets). `TransporteConFallos` inyecta en el
transporte HTTP las mismas fallas que la suite exige (`InyectorDeFallos`) sin necesitar un proxy
aparte: corta o duplica la peticion entre el adaptador y GLPI.
"""

import os
from collections import deque
from typing import Any

import httpx

from jml.dominio.activos import ActivoAsignado, LicenciaAsignada
from jml.dominio.tipos import EstadoDeTicket

A_GLPI = {
    EstadoDeTicket.NUEVO: 1,
    EstadoDeTicket.EN_CURSO: 2,
    EstadoDeTicket.EN_ESPERA: 4,
    EstadoDeTicket.RESUELTO: 5,
    EstadoDeTicket.CERRADO: 6,
}


class TransporteConFallos(httpx.BaseTransport):
    """Envuelve un transporte real. Las lecturas solo fallan por caida; las escrituras tambien
    por los fallos programados (antes, despues, duplicada)."""

    def __init__(self, real: httpx.BaseTransport) -> None:
        self._real = real
        self._programados: deque[str] = deque()
        self._caidas = 0

    # --- InyectorDeFallos ---------------------------------------------------------------------

    def timeout_despues_de_crear(self) -> None:
        self._programados.append("despues")

    def error_antes_de_crear(self) -> None:
        self._programados.append("antes")

    def respuesta_duplicada(self) -> None:
        self._programados.append("duplicada")

    def caida(self, llamadas: int) -> None:
        self._caidas += llamadas

    def recuperar(self) -> None:
        """GLPI vuelve a responder: se cancelan las caidas que falten (CA-07)."""
        self._caidas = 0

    # --- transporte ---------------------------------------------------------------------------

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if self._caidas > 0:
            self._caidas -= 1
            return httpx.Response(503, text="GLPI no disponible", request=request)
        escritura = request.method in ("POST", "PUT", "DELETE") and "initSession" not in str(
            request.url
        )
        if not (escritura and self._programados):
            return self._real.handle_request(request)
        fallo = self._programados.popleft()
        if fallo == "antes":
            return httpx.Response(503, text="error antes de escribir", request=request)
        if fallo == "despues":
            self._real.handle_request(request).read()
            raise httpx.ReadTimeout("respuesta perdida", request=request)
        self._real.handle_request(request).read()  # duplicada: llega dos veces
        return self._real.handle_request(request)


class TecnicoGlpiReal:
    """Una persona de TI con perfil de administrador trabajando en GLPI por la API."""

    def __init__(
        self, url_api: str, app_token: str, token_admin: str, transporte: Any = None
    ) -> None:
        self._base = url_api.rstrip("/")
        self._http = httpx.Client(timeout=60.0, transport=transporte)
        r = self._http.get(
            f"{self._base}/initSession",
            headers={"App-Token": app_token, "Authorization": f"user_token {token_admin}"},
        )
        r.raise_for_status()
        self._cab = {"App-Token": app_token, "Session-Token": r.json()["session_token"]}

    def _pedir(self, metodo: str, ruta: str, **kw: Any) -> Any:
        r = self._http.request(metodo, f"{self._base}/{ruta}", headers=self._cab, **kw)
        if r.status_code >= 400:
            raise AssertionError(f"{metodo} {ruta}: {r.status_code} {r.text[:300]}")
        return r.json() if r.content else None

    def _crear(self, tipo: str, entrada: dict[str, Any]) -> str:
        return str(self._pedir("POST", tipo, json={"input": entrada})["id"])

    def _desplegable(self, tipo: str, nombre: str) -> str:
        for x in self._pedir("GET", tipo, params={"searchText[name]": nombre, "range": "0-99"}):
            if x["name"] == nombre:
                return str(x["id"])
        return self._crear(tipo, {"name": nombre})

    # --- Tecnico ------------------------------------------------------------------------------

    def resolver(
        self,
        id_externo: str,
        con_solucion: bool = True,
        documentos: int = 0,
        estado: EstadoDeTicket = EstadoDeTicket.RESUELTO,
    ) -> None:
        if con_solucion:
            self._crear(
                "ITILSolution",
                {"itemtype": "Ticket", "items_id": id_externo, "content": "Plantilla"},
            )
        for _ in range(documentos):
            doc = self._crear("Document", {"name": "acta", "filename": "acta.pdf"})
            self._crear(
                "Document_Item", {"documents_id": doc, "itemtype": "Ticket", "items_id": id_externo}
            )
        self._pedir("PUT", f"Ticket/{id_externo}", json={"input": {"status": A_GLPI[estado]}})

    def reabrir(self, id_externo: str) -> None:
        self._pedir("PUT", f"Ticket/{id_externo}", json={"input": {"status": 2}})

    def asignar_activo(self, id_usuario: str, activo: ActivoAsignado) -> ActivoAsignado:
        """GLPI asigna sus propios identificadores: se devuelve el activo con el id real."""
        cid = self._crear(
            "Computer",
            {
                "name": activo.serie,
                "serial": activo.serie,
                "users_id": id_usuario,
                "computermodels_id": self._desplegable("ComputerModel", activo.modelo),
                "computertypes_id": self._desplegable("ComputerType", activo.tipo),
            },
        )
        self._crear(
            "Infocom",
            {
                "itemtype": "Computer",
                "items_id": cid,
                "delivery_date": activo.asignado_desde.isoformat(),
            },
        )
        if activo.tiene_acta:
            doc = self._crear("Document", {"name": "acta", "filename": "acta.pdf"})
            self._crear(
                "Document_Item", {"documents_id": doc, "itemtype": "Computer", "items_id": cid}
            )
        return ActivoAsignado(
            cid, activo.tipo, activo.serie, activo.modelo, activo.asignado_desde, activo.tiene_acta
        )

    def asignar_licencia(self, id_usuario: str, licencia: LicenciaAsignada) -> LicenciaAsignada:
        lid = self._crear(
            "SoftwareLicense",
            {
                "name": licencia.licencia,
                "serial": licencia.licencia,
                "users_id": id_usuario,
                "softwares_id": self._desplegable("Software", licencia.software),
            },
        )
        return LicenciaAsignada(lid, licencia.software, licencia.licencia)

    # --- observacion para las pruebas de enrutamiento ------------------------------------------

    def ticket(self, id_externo: str) -> dict[str, Any]:
        return dict(self._pedir("GET", f"Ticket/{id_externo}"))

    def grupos_asignados(self, id_externo: str) -> set[str]:
        """Nombres de los grupos asignados al ticket (tipo 2 = asignado)."""
        vinculos = self._pedir("GET", f"Ticket/{id_externo}/Group_Ticket", params={"range": "0-99"})
        return {
            str(self._pedir("GET", f"Group/{v['groups_id']}")["name"])
            for v in vinculos
            if int(v["type"]) == 2
        }

    def sla_de(self, id_sla: Any) -> tuple[str, int, str]:
        sla = self._pedir("GET", f"SLA/{id_sla}")
        return str(sla["name"]), int(sla["number_time"]), str(sla["definition_time"])

    def nombres(self, tipo: str, campo: str) -> set[str]:
        return {str(x[campo]) for x in self._pedir("GET", tipo, params={"range": "0-999"})}

    def contenidos(self, tipo: str, prefijo: str) -> list[str]:
        filas = self._pedir("GET", tipo, params={"searchText[name]": prefijo, "range": "0-99"})
        return [str(f.get("content", "")) for f in filas if str(f["name"]).startswith(prefijo)]

    def limpiar(self) -> None:
        """Borra los tickets de las pruebas (clave `SOL-...`): GLPI conserva el estado entre
        pruebas y la suite espera empezar sin ninguno. SOLO para un GLPI de pruebas."""
        if os.environ.get("JML_GLPI_DE_PRUEBAS") != "si":
            raise RuntimeError(
                "limpiar() borra tickets: defina JML_GLPI_DE_PRUEBAS=si (GLPI de pruebas)"
            )
        tickets = self._pedir(
            "GET", "Ticket", params={"searchText[externalid]": "SOL-", "range": "0-999"}
        )
        for t in tickets:
            if str(t.get("externalid", "")).startswith("SOL-"):
                self._pedir("DELETE", f"Ticket/{t['id']}", params={"force_purge": "true"})
        # Las actas que crean los ayudantes de la suite (nombre y archivo fijos).
        for doc in self._pedir(
            "GET", "Document", params={"searchText[filename]": "acta.pdf", "range": "0-99"}
        ):
            if doc.get("filename") == "acta.pdf" and doc.get("name") == "acta":
                self._pedir("DELETE", f"Document/{doc['id']}", params={"force_purge": "true"})
        # Los equipos y licencias de la prueba de activos (series fijas de la suite de contrato).
        for tipo, serie in (("Computer", "SN-1"), ("SoftwareLicense", "K-001")):
            for item in self._pedir(
                "GET", tipo, params={"searchText[serial]": serie, "range": "0-99"}
            ):
                if item.get("serial") == serie:
                    self._pedir("DELETE", f"{tipo}/{item['id']}", params={"force_purge": "true"})

    def creaciones(self, clave: str) -> int:
        tickets = self._pedir(
            "GET", "Ticket", params={"searchText[externalid]": clave, "range": "0-99"}
        )
        return sum(1 for t in tickets if t.get("externalid") == clave)
