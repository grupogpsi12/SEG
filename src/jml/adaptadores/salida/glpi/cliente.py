"""SistemaDeTickets sobre la API REST v1 de GLPI 11 (`apirest.php`), item 3.2.

PROVISIONAL hasta el spike 0.3 (docs/spikes/glpi-puerto.md): esta escrito contra la documentacion
de la API v1 y probado contra un GLPI simulado (`tests/dobles/glpi_api.py`) con la suite de
contrato. Lo que el spike debe confirmar esta marcado con «spike 0.3».

Decisiones:
- Idempotencia de tickets: la clave va en `externalid` y se busca antes de crear. GLPI no la
  hace unica, asi que despues de crear se purgan los duplicados (se conserva el de menor id): un
  POST repetido por la red no deja dos tickets (RF-18, CA-07).
- Documentos: GLPI guarda SHA-1. Se busca por `sha1sum` antes de subir (una sola subida, RF-40) y
  `hash_de_documento` descarga el archivo y calcula el SHA-256 (lessons n.24, opcion a).
- Usuarios (RF-21): se buscan por `registration_number` = id del colaborador; `name` es ese mismo
  id porque nadie inicia sesion en GLPI con ellos (sin credenciales). Nombres y apellidos reales.
- Solo el worker usa este cliente (CLAUDE.md): un hilo, una sesion que se renueva si vence.
- Nunca viaja un campo restringido: el contenido es `TicketDeCola.como_texto()` (RF-20, RD-05).
"""

import contextlib
import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime
from typing import Any

import httpx

from jml.aplicacion.puertos import (
    GlpiNoDisponible,
    GlpiRechazo,
    TicketCreado,
    TiempoAgotado,
)
from jml.dominio.activos import ActivoAsignado, LicenciaAsignada
from jml.dominio.colaborador import Colaborador
from jml.dominio.tickets import Observacion, TicketDeCola
from jml.dominio.tipos import EstadoDeTicket, EstadoInicialDeTicket, Prioridad
from jml.dominio.valores import BOGOTA, NombreDeSoporteSaneado, Sha256

# GLPI: 1 Nuevo, 2 En curso (asignado), 3 En curso (planificado), 4 En espera, 5 Resuelto,
# 6 Cerrado. El nucleo solo necesita el orden «>= Resuelto» (RF-24). Spike 0.3, punto 6.
DE_GLPI = {
    1: EstadoDeTicket.NUEVO,
    2: EstadoDeTicket.EN_CURSO,
    3: EstadoDeTicket.EN_CURSO,
    4: EstadoDeTicket.EN_ESPERA,
    5: EstadoDeTicket.RESUELTO,
    6: EstadoDeTicket.CERRADO,
}
PRIORIDAD = {Prioridad.MEDIA: 3, Prioridad.ALTA: 4, Prioridad.MUY_ALTA: 5}
_TODO = {"range": "0-999"}


class ClienteGlpiV1:
    """Sesion, errores y operaciones genericas de la API v1. Lo usan el adaptador del puerto y
    el configurador de GLPI (3.1)."""

    def __init__(
        self,
        url_api: str,
        app_token: str,
        user_token: str,
        reloj: Callable[[], datetime],
        cliente: httpx.Client | None = None,
    ) -> None:
        self._base = url_api.rstrip("/")
        self._app = app_token
        self._usuario = user_token
        self._reloj = reloj
        self._http = cliente or httpx.Client(timeout=30.0)
        self._sesion: str | None = None
        self._categorias: dict[str, int] = {}

    # --- HTTP y errores ----------------------------------------------------------------------

    def _iniciar_sesion(self) -> str:
        r = self._enviar(
            "GET", "initSession", cabeceras={"Authorization": f"user_token {self._usuario}"}
        )
        datos = self._exigir(r, "iniciar sesion")  # credenciales o App-Token invalidos: rechazo
        self._sesion = str(datos["session_token"])
        return self._sesion

    def _enviar(
        self,
        metodo: str,
        ruta: str,
        cabeceras: Mapping[str, str] | None = None,
        **opciones: Any,
    ) -> httpx.Response:
        h = {"App-Token": self._app, **(cabeceras or {})}
        try:
            r = self._http.request(metodo, f"{self._base}/{ruta}", headers=h, **opciones)
        except httpx.TimeoutException:
            if metodo in ("POST", "PUT", "DELETE"):
                raise TiempoAgotado(f"{metodo} {ruta.split('/')[0]}") from None  # pudo aplicarse
            raise GlpiNoDisponible(f"timeout en {ruta.split('/')[0]}") from None
        except httpx.HTTPError as e:
            raise GlpiNoDisponible(type(e).__name__) from None
        if r.status_code >= 500 or r.status_code == 429:
            raise GlpiNoDisponible(f"HTTP {r.status_code}")
        return r

    def _api(self, metodo: str, ruta: str, **opciones: Any) -> httpx.Response:
        """Con sesion; si vencio (401) se abre otra una vez y se repite."""
        for intento in range(2):
            sesion = self._sesion or self._iniciar_sesion()
            cabeceras = {"Session-Token": sesion, **opciones.pop("cabeceras", {})}
            r = self._enviar(metodo, ruta, cabeceras=cabeceras, **opciones)
            if r.status_code == 401 and intento == 0:
                self._sesion = None
                opciones["cabeceras"] = {k: v for k, v in cabeceras.items() if k != "Session-Token"}
                continue
            return r
        return r  # pragma: no cover - el bucle siempre retorna

    def _exigir(self, r: httpx.Response, que: str) -> Any:
        if r.status_code >= 400:
            # El cuerpo de error de GLPI es ["CODIGO", "mensaje"]: solo el codigo va al error.
            try:
                codigo = r.json()[0]
            except (ValueError, KeyError, IndexError, TypeError):
                codigo = r.status_code
            raise GlpiRechazo(f"{que}: {codigo}")
        return r.json() if r.content else None

    def _lista(self, tipo: str, **filtros: str) -> list[dict[str, Any]]:
        params = {**_TODO, **{f"searchText[{k}]": v for k, v in filtros.items()}}
        datos = self._exigir(self._api("GET", tipo, params=params), f"listar {tipo}")
        return list(datos) if isinstance(datos, list) else []

    def _existe(self, tipo: str, id_: str) -> bool:
        r = self._api("GET", f"{tipo}/{id_}")
        if r.status_code in (400, 404):
            return False
        self._exigir(r, f"leer {tipo}")
        return True

    def _crear(self, tipo: str, entrada: Mapping[str, Any]) -> str:
        datos = self._exigir(
            self._api("POST", tipo, json={"input": dict(entrada)}), f"crear {tipo}"
        )
        return str(datos["id"])

    def _asegurar(self, tipo: str, nombre: str, campos: Mapping[str, Any]) -> str:
        """Idempotente por nombre exacto: crea si falta y devuelve el id."""
        for item in self._lista(tipo, name=nombre):
            if item.get("name") == nombre:
                return str(item["id"])
        return self._crear(tipo, {"name": nombre, **campos})

    def cerrar(self) -> None:
        if self._sesion is not None:
            with contextlib.suppress(GlpiNoDisponible):
                self._api("GET", "killSession")
            self._sesion = None


class SistemaDeTicketsGlpi(ClienteGlpiV1):
    # --- puerto ------------------------------------------------------------------------------

    def asegurar_usuario(self, colaborador: Colaborador) -> str:
        campos = {
            "name": colaborador.id,
            "registration_number": colaborador.id,
            "firstname": colaborador.nombres,
            "realname": colaborador.apellidos,
            "comment": f"Usuario de directorio: {colaborador.usuario or '-'}",
            "is_active": 1,
        }
        existentes = [
            u
            for u in self._lista("User", registration_number=colaborador.id)
            if u.get("registration_number") == colaborador.id
        ]
        if existentes:
            uid = str(existentes[0]["id"])
            self._exigir(self._api("PUT", f"User/{uid}", json={"input": campos}), "actualizar User")
            return uid
        return self._crear("User", campos)

    def _por_clave(self, clave: str) -> list[str]:
        ids = [
            str(t["id"])
            for t in self._lista("Ticket", externalid=clave)
            if t.get("externalid") == clave  # searchText es por subcadena: se filtra exacto
        ]
        return sorted(ids, key=lambda i: (len(i), i))

    def _sin_duplicados(self, clave: str) -> str | None:
        ids = self._por_clave(clave)
        for sobrante in ids[1:]:  # GLPI no hace unico externalid: se conserva el primero
            self._api("DELETE", f"Ticket/{sobrante}", params={"force_purge": "true"})
        return ids[0] if ids else None

    def _categoria(self, nombre: str) -> int:
        """Spike 0.3, punto 4: una categoria desconocida queda en 0 y la regla de GLPI la manda
        a «Revision manual» (3.1)."""
        if nombre not in self._categorias:
            hallada = [
                c
                for c in self._lista("ITILCategory", completename=nombre)
                if c.get("completename") == nombre
            ]
            self._categorias[nombre] = int(hallada[0]["id"]) if hallada else 0
        return self._categorias[nombre]

    def crear_ticket(self, ticket: TicketDeCola) -> TicketCreado:
        clave = ticket.clave_de_idempotencia
        existente = self._sin_duplicados(clave)
        if existente is not None:
            return TicketCreado(existente, ya_existia=True)
        en_espera = ticket.estado_inicial is EstadoInicialDeTicket.EN_ESPERA
        self._crear(
            "Ticket",
            {
                "name": ticket.titulo,
                "content": ticket.como_texto(),  # solo datos tecnicos (RF-20)
                "externalid": clave,
                "status": 4 if en_espera else 1,
                "priority": PRIORIDAD[ticket.prioridad],
                "itilcategories_id": self._categoria(ticket.categoria),
                "time_to_resolve": ticket.vence_en.astimezone(BOGOTA).strftime("%Y-%m-%d %H:%M:%S"),
            },
        )
        conservado = self._sin_duplicados(clave)
        if conservado is None:  # pragma: no cover - acabamos de crearlo
            raise GlpiRechazo("ticket creado y no encontrado")
        return TicketCreado(conservado, ya_existia=False)

    def subir_documento(self, nombre: NombreDeSoporteSaneado, contenido: bytes) -> str:
        sha1 = hashlib.sha1(contenido).hexdigest()
        for d in self._lista("Document", sha1sum=sha1):
            if d.get("sha1sum") == sha1:
                return str(d["id"])
        manifiesto = {"input": {"name": nombre.valor, "_filename": [nombre.valor]}}
        r = self._api(
            "POST",
            "Document",
            data={"uploadManifest": json.dumps(manifiesto)},
            files={"filename[0]": (nombre.valor, contenido, "application/pdf")},
        )
        return str(self._exigir(r, "subir Document")["id"])

    def hash_de_documento(self, id_documento: str) -> Sha256:
        r = self._api(
            "GET", f"Document/{id_documento}", cabeceras={"Accept": "application/octet-stream"}
        )
        if r.status_code >= 400:
            self._exigir(r, "descargar Document")
        return Sha256.de_bytes(r.content)

    def vincular_documento(self, id_documento: str, id_ticket: str) -> None:
        if not self._existe("Ticket", id_ticket):
            raise GlpiRechazo(f"ticket inexistente: {id_ticket}")
        r = self._api("GET", f"Document/{id_documento}/Document_Item", params=_TODO)
        vinculos = self._exigir(r, "leer vinculos") or []
        if any(
            v.get("itemtype") == "Ticket" and str(v.get("items_id")) == id_ticket for v in vinculos
        ):
            return
        self._crear(
            "Document_Item",
            {"documents_id": id_documento, "itemtype": "Ticket", "items_id": id_ticket},
        )

    def _sub(self, tipo: str, id_: str, hijo: str) -> list[dict[str, Any]]:
        datos = self._exigir(self._api("GET", f"{tipo}/{id_}/{hijo}", params=_TODO), f"leer {hijo}")
        return list(datos) if isinstance(datos, list) else []

    def leer_tickets(self, ids: Sequence[str]) -> Mapping[str, Observacion]:
        ahora = self._reloj()
        resultado: dict[str, Observacion] = {}
        for id_ in ids:
            r = self._api("GET", f"Ticket/{id_}")
            if r.status_code in (400, 404):
                continue  # desconocido: se omite (contrato)
            ticket = self._exigir(r, "leer Ticket")
            resultado[id_] = Observacion(
                DE_GLPI.get(int(ticket["status"]), EstadoDeTicket.EN_CURSO),
                bool(self._sub("Ticket", id_, "ITILSolution")),
                len(self._sub("Ticket", id_, "Document_Item")),
                ahora,
            )
        return resultado

    def leer_activos(self, id_usuario: str) -> Sequence[ActivoAsignado]:
        """Spike 0.3, punto 12: equipos (Computer) del usuario; fecha de entrega del Infocom y
        acta = algun documento vinculado al equipo."""
        activos = []
        for c in self._lista("Computer", users_id=id_usuario):
            if str(c.get("users_id")) != id_usuario:
                continue
            cid = str(c["id"])
            r = self._api("GET", f"Computer/{cid}", params={"expand_dropdowns": "true"})
            detalle = self._exigir(r, "leer Computer")
            infocom = self._sub("Computer", cid, "Infocom")
            entrega = infocom[0].get("delivery_date") if infocom else None
            activos.append(
                ActivoAsignado(
                    id_glpi=cid,
                    tipo=detalle.get("computertypes_id") or "Equipo",
                    serie=detalle.get("serial") or "-",
                    modelo=detalle.get("computermodels_id") or "-",
                    asignado_desde=date.fromisoformat(entrega[:10]) if entrega else date.min,
                    tiene_acta=bool(self._sub("Computer", cid, "Document_Item")),
                )
            )
        return activos

    def leer_licencias(self, id_usuario: str) -> Sequence[LicenciaAsignada]:
        licencias = []
        for lic in self._lista("SoftwareLicense", users_id=id_usuario):
            if str(lic.get("users_id")) != id_usuario:
                continue
            lid = str(lic["id"])
            r = self._api("GET", f"SoftwareLicense/{lid}", params={"expand_dropdowns": "true"})
            detalle = self._exigir(r, "leer SoftwareLicense")
            licencias.append(
                LicenciaAsignada(
                    lid,
                    detalle.get("softwares_id") or "-",
                    detalle.get("serial") or detalle.get("name") or "-",
                )
            )
        return licencias
