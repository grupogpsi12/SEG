"""GLPI simulado sobre la API REST v1 (`apirest.php`) para probar el adaptador real (3.2).

Imita lo que el adaptador usa y lo que hace dificil a GLPI:
- sesion con `App-Token` + `user_token`, y `Session-Token` en cada peticion (401 si vence);
- `searchText[campo]` hace una busqueda por SUBCADENA (como GLPI): el adaptador debe filtrar
  exacto;
- `externalid` NO es unico: un POST repetido crea dos tickets;
- documentos con `sha1sum` (GLPI no guarda SHA-256) y descarga con `Accept: application/octet-stream`.

Fallos en el transporte para la suite de contrato (`InyectorDeFallos`): caida (503 en cualquier
peticion), error antes de escribir (503), timeout despues de escribir (la escritura se aplica y la
respuesta no llega) y peticion duplicada (la escritura se aplica dos veces).

Es una interpretacion de la documentacion de GLPI: el spike 0.3 la confirma contra GLPI 11 real
(docs/spikes/glpi-puerto.md). Implementa tambien el protocolo `Tecnico`.
"""

import hashlib
import json
import uuid
from collections import deque
from dataclasses import dataclass, field
from email.parser import BytesParser
from email.policy import HTTP
from typing import Any
from urllib.parse import parse_qs

import httpx

from jml.dominio.activos import ActivoAsignado, LicenciaAsignada
from jml.dominio.tipos import EstadoDeTicket

APP_TOKEN = "app-token-prueba"
USER_TOKEN = "user-token-prueba"
BASE = "http://glpi.interno/apirest.php"

# EstadoDeTicket del nucleo -> estado numerico de GLPI (1 Nuevo ... 6 Cerrado)
A_GLPI = {
    EstadoDeTicket.NUEVO: 1,
    EstadoDeTicket.EN_CURSO: 2,
    EstadoDeTicket.EN_ESPERA: 4,
    EstadoDeTicket.RESUELTO: 5,
    EstadoDeTicket.CERRADO: 6,
}
_DESPLEGABLES = {
    "computermodels_id": "ComputerModel",
    "computertypes_id": "ComputerType",
    "softwares_id": "Software",
    "itilcategories_id": "ITILCategory",
}


def _json(datos: object, estado: int = 200) -> httpx.Response:
    return httpx.Response(estado, json=datos)


@dataclass
class GlpiSimulado:
    items: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)
    archivos: dict[str, bytes] = field(default_factory=dict)
    sesiones: set[str] = field(default_factory=set)
    programados: deque[str] = field(default_factory=deque)
    caidas: int = 0
    llamadas: list[str] = field(default_factory=list)
    _secuencia: int = 0

    def cliente(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.manejar))

    # --- infraestructura ----------------------------------------------------------------------

    def _nuevo_id(self) -> str:
        self._secuencia += 1
        return str(self._secuencia)

    def _tabla(self, tipo: str) -> dict[str, dict[str, Any]]:
        return self.items.setdefault(tipo, {})

    def _agregar(self, tipo: str, campos: dict[str, Any], id_: str | None = None) -> str:
        id_ = id_ or self._nuevo_id()
        self._tabla(tipo)[id_] = {**campos, "id": int(id_) if id_.isdigit() else id_}
        return id_

    def manejar(self, peticion: httpx.Request) -> httpx.Response:
        ruta = peticion.url.path.removeprefix("/apirest.php/").strip("/")
        self.llamadas.append(f"{peticion.method} {ruta}")
        if self.caidas > 0:
            self.caidas -= 1
            return httpx.Response(503, text="GLPI no disponible")
        if peticion.headers.get("app-token") != APP_TOKEN:
            return _json(["ERROR_WRONG_APP_TOKEN_PARAMETER", "app token"], 400)
        if ruta == "initSession":
            if peticion.headers.get("authorization") != f"user_token {USER_TOKEN}":
                return _json(["ERROR_LOGIN_PARAMETERS_MISSING", "credenciales"], 401)
            token = uuid.uuid4().hex
            self.sesiones.add(token)
            return _json({"session_token": token})
        if peticion.headers.get("session-token") not in self.sesiones:
            return _json(["ERROR_SESSION_TOKEN_INVALID", "sesion"], 401)
        if ruta == "killSession":
            self.sesiones.discard(peticion.headers["session-token"])
            return _json({})
        if peticion.method in ("POST", "PUT", "DELETE") and self.programados:
            fallo = self.programados.popleft()
            if fallo == "antes":
                return httpx.Response(503, text="error antes de escribir")
            if fallo == "despues":
                self._atender(peticion, ruta)
                raise httpx.ReadTimeout("respuesta perdida", request=peticion)
            self._atender(peticion, ruta)  # duplicada: la escritura llega dos veces
        return self._atender(peticion, ruta)

    # --- API ----------------------------------------------------------------------------------

    def _expandir(self, item: dict[str, Any]) -> dict[str, Any]:
        copia = dict(item)
        for campo, tipo in _DESPLEGABLES.items():
            if campo in copia:
                ref = self._tabla(tipo).get(str(copia[campo]))
                copia[campo] = (
                    ref["completename" if tipo == "ITILCategory" else "name"] if ref else ""
                )
        return copia

    def _atender(self, p: httpx.Request, ruta: str) -> httpx.Response:
        partes = ruta.split("/")
        consulta = parse_qs(p.url.query.decode())
        expandir = consulta.get("expand_dropdowns", ["false"])[0] == "true"
        if p.method == "GET" and len(partes) == 1:
            filtros = {
                k[len("searchText[") : -1]: v[0]
                for k, v in consulta.items()
                if k.startswith("searchText[")
            }
            filas = [
                i
                for i in self._tabla(partes[0]).values()
                if all(f.lower() in str(i.get(c, "")).lower() for c, f in filtros.items())
            ]
            return _json([self._expandir(i) if expandir else i for i in filas])
        if p.method == "GET" and len(partes) == 2:
            item = self._tabla(partes[0]).get(partes[1])
            if item is None:
                return _json(["ERROR_ITEM_NOT_FOUND", "no existe"], 404)
            if partes[0] == "Document" and p.headers.get("accept") == "application/octet-stream":
                return httpx.Response(200, content=self.archivos[partes[1]])
            return _json(self._expandir(item) if expandir else item)
        if p.method == "GET" and len(partes) == 3:
            padre, id_, hijo = partes
            if id_ not in self._tabla(padre):
                return _json(["ERROR_ITEM_NOT_FOUND", "no existe"], 404)
            if padre == "Document":
                filas = [i for i in self._tabla(hijo).values() if str(i["documents_id"]) == id_]
            else:
                filas = [
                    i
                    for i in self._tabla(hijo).values()
                    if i.get("itemtype") == padre and str(i.get("items_id")) == id_
                ]
            return _json(filas)
        if p.method == "POST" and len(partes) == 1:
            if partes[0] == "Document":
                return self._subir(p)
            entrada = json.loads(p.content)["input"]
            if partes[0] == "Document_Item":
                tipo, destino = entrada["itemtype"], str(entrada["items_id"])
                documento = str(entrada["documents_id"])
                if documento not in self._tabla("Document") or destino not in self._tabla(tipo):
                    return _json(["ERROR_GLPI_ADD", "item inexistente"], 400)
            if partes[0] == "ITILCategory":  # GLPI calcula el nombre completo (raiz: = nombre)
                entrada.setdefault("completename", entrada["name"])
            if (
                partes[0] == "Ticket"
            ):  # spike 0.3: GLPI recalcula la prioridad y ignora el vencimiento
                entrada.pop("priority", None)
                entrada.pop("time_to_resolve", None)
                entrada["urgency"] = entrada.get("urgency", 3)
                entrada["impact"] = entrada.get("impact", 3)
                entrada["priority"] = max(entrada["urgency"], entrada["impact"])
                entrada.setdefault("slas_id_ttr", 0)
            return _json({"id": int(self._agregar(partes[0], entrada)), "message": ""}, 201)
        if p.method == "PUT" and len(partes) == 2:
            item = self._tabla(partes[0]).get(partes[1])
            if item is None:
                return _json(["ERROR_ITEM_NOT_FOUND", "no existe"], 404)
            item.update(json.loads(p.content)["input"])
            return _json([{partes[1]: True, "message": ""}])
        if p.method == "DELETE" and len(partes) == 2:
            self._tabla(partes[0]).pop(partes[1], None)
            return _json([{partes[1]: True, "message": ""}])
        return _json(["ERROR_RESOURCE_NOT_FOUND_NOR_COMMONDBTM", ruta], 400)

    def _subir(self, p: httpx.Request) -> httpx.Response:
        cabecera = f"Content-Type: {p.headers['content-type']}\r\n\r\n".encode()
        mensaje = BytesParser(policy=HTTP).parsebytes(cabecera + p.content)
        manifiesto: dict[str, Any] = {}
        contenido = b""
        for parte in mensaje.iter_parts():
            nombre = parte.get_param("name", header="content-disposition")
            datos = parte.get_payload(decode=True)
            assert isinstance(datos, bytes)
            if nombre == "uploadManifest":
                manifiesto = json.loads(datos)
            else:
                contenido = datos
        entrada = manifiesto["input"]
        id_ = self._agregar(
            "Document",
            {
                "name": entrada["name"],
                "filename": entrada["_filename"][0],
                "sha1sum": hashlib.sha1(contenido).hexdigest(),
            },
        )
        self.archivos[id_] = contenido
        return _json({"id": int(id_), "message": "", "upload_result": {}}, 201)

    # --- InyectorDeFallos ---------------------------------------------------------------------

    def timeout_despues_de_crear(self) -> None:
        self.programados.append("despues")

    def error_antes_de_crear(self) -> None:
        self.programados.append("antes")

    def respuesta_duplicada(self) -> None:
        self.programados.append("duplicada")

    def caida(self, llamadas: int) -> None:
        self.caidas += llamadas

    def expirar_sesiones(self) -> None:
        self.sesiones.clear()

    # --- Tecnico ------------------------------------------------------------------------------

    def resolver(
        self,
        id_externo: str,
        con_solucion: bool = True,
        documentos: int = 0,
        estado: EstadoDeTicket = EstadoDeTicket.RESUELTO,
    ) -> None:
        self._tabla("Ticket")[id_externo]["status"] = A_GLPI[estado]
        if con_solucion:
            self._agregar(
                "ITILSolution",
                {"itemtype": "Ticket", "items_id": int(id_externo), "content": "Plantilla"},
            )
        for _ in range(documentos):
            doc = self._agregar(
                "Document", {"name": "acta", "filename": "acta.pdf", "sha1sum": "-"}
            )
            self._agregar(
                "Document_Item",
                {"documents_id": int(doc), "itemtype": "Ticket", "items_id": int(id_externo)},
            )

    def reabrir(self, id_externo: str) -> None:
        self._tabla("Ticket")[id_externo]["status"] = 2

    def _desplegable(self, tipo: str, nombre: str) -> int:
        for id_, item in self._tabla(tipo).items():
            if item.get("name") == nombre:
                return int(id_)
        return int(self._agregar(tipo, {"name": nombre, "completename": nombre}))

    def asignar_activo(self, id_usuario: str, activo: ActivoAsignado) -> ActivoAsignado:
        self._agregar(
            "Computer",
            {
                "name": activo.serie,
                "serial": activo.serie,
                "users_id": id_usuario,
                "computermodels_id": self._desplegable("ComputerModel", activo.modelo),
                "computertypes_id": self._desplegable("ComputerType", activo.tipo),
            },
            activo.id_glpi,
        )
        self._agregar(
            "Infocom",
            {
                "itemtype": "Computer",
                "items_id": activo.id_glpi,
                "delivery_date": activo.asignado_desde.isoformat(),
            },
        )
        if activo.tiene_acta:
            doc = self._agregar(
                "Document", {"name": "acta", "filename": "acta.pdf", "sha1sum": "-"}
            )
            self._agregar(
                "Document_Item",
                {"documents_id": int(doc), "itemtype": "Computer", "items_id": activo.id_glpi},
            )
        return activo

    def asignar_licencia(self, id_usuario: str, licencia: LicenciaAsignada) -> LicenciaAsignada:
        self._agregar(
            "SoftwareLicense",
            {
                "name": licencia.licencia,
                "serial": licencia.licencia,
                "users_id": id_usuario,
                "softwares_id": self._desplegable("Software", licencia.software),
            },
            licencia.id_glpi,
        )
        return licencia

    def creaciones(self, clave: str) -> int:
        return sum(1 for t in self._tabla("Ticket").values() if t.get("externalid") == clave)

    def ticket(self, id_externo: str) -> dict[str, Any]:
        return self._tabla("Ticket")[id_externo]

    def agregar_categoria(self, completename: str) -> int:
        return int(
            self._agregar(
                "ITILCategory",
                {"name": completename.split(">")[-1].strip(), "completename": completename},
            )
        )
