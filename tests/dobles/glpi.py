"""Doble en memoria del puerto SistemaDeTickets (GLPI) con fallos programados.

Reproduce lo que hace dificil a GLPI: caidas, errores antes de actuar, TIMEOUT DESPUES de crear
(el ticket existe pero la respuesta se perdio) y respuestas duplicadas. La prueba clave es que,
con cualquier calendario de fallos, al final existe EXACTAMENTE un ticket por clave.
"""

from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from jml.aplicacion.puertos import (
    GlpiNoDisponible,
    GlpiRechazo,
    TicketCreado,
    TiempoAgotado,
)
from jml.dominio.activos import ActivoAsignado, LicenciaAsignada
from jml.dominio.colaborador import Colaborador
from jml.dominio.tickets import Observacion, TicketDeCola
from jml.dominio.tipos import EstadoDeTicket, EstadoInicialDeTicket
from jml.dominio.valores import NombreDeSoporteSaneado, Sha256
from tests.dobles.reloj import RelojSimulado


class Fallo(StrEnum):
    ANTES = "antes"  # GlpiNoDisponible antes de actuar
    DESPUES = "despues"  # actua y luego TiempoAgotado: la respuesta se perdio
    RECHAZO = "rechazo"  # GlpiRechazo antes de actuar
    DUPLICADA = "duplicada"  # la operacion se aplica dos veces (debe ser inocua)


@dataclass
class _Remoto:
    ticket: TicketDeCola
    id_externo: str
    estado: EstadoDeTicket = EstadoDeTicket.NUEVO
    solucion: bool = False
    documentos: int = 0


@dataclass
class _Documento:
    id: str
    nombre: str
    contenido: bytes
    hash_guardado: str


@dataclass
class SistemaDeTicketsEnMemoria:
    reloj: RelojSimulado
    programados: deque[Fallo] = field(default_factory=deque)
    caida_total: bool = False
    _caida_restante: int = 0
    _remotos: dict[str, _Remoto] = field(default_factory=dict)
    _por_clave: dict[str, str] = field(default_factory=dict)
    _documentos: dict[str, _Documento] = field(default_factory=dict)
    _vinculos: set[tuple[str, str]] = field(default_factory=set)
    _usuarios: dict[str, str] = field(default_factory=dict)
    _activos: dict[str, list[ActivoAsignado]] = field(default_factory=dict)
    _licencias: dict[str, list[LicenciaAsignada]] = field(default_factory=dict)
    creaciones_reales: dict[str, int] = field(default_factory=dict)
    subidas_reales: int = 0
    llamadas: int = 0
    corromper_al_subir: bool = False

    # --- inyeccion de fallos --------------------------------------------------------------

    def programar(self, *fallos: Fallo) -> None:
        self.programados.extend(fallos)

    def caer(self, llamadas: int | None = None) -> None:
        """Las proximas `llamadas` fallan; sin argumento, hasta `recuperar()`."""
        if llamadas is None:
            self.caida_total = True
        else:
            self._caida_restante += llamadas

    def recuperar(self) -> None:
        self.caida_total = False
        self._caida_restante = 0
        self.programados.clear()

    def _cayendo(self) -> bool:
        if self.caida_total:
            return True
        if self._caida_restante > 0:
            self._caida_restante -= 1
            return True
        return False

    def _lectura[T](self, operacion: Callable[[], T]) -> T:
        self.llamadas += 1
        if self._cayendo():
            raise GlpiNoDisponible("glpi caido")
        return operacion()

    def _escritura[T](self, operacion: Callable[[], T]) -> T:
        self.llamadas += 1
        if self._cayendo():
            raise GlpiNoDisponible("glpi caido")
        if not self.programados:
            return operacion()
        fallo = self.programados.popleft()
        if fallo is Fallo.ANTES:
            raise GlpiNoDisponible("error antes de actuar")
        if fallo is Fallo.RECHAZO:
            raise GlpiRechazo("500")
        if fallo is Fallo.DESPUES:
            operacion()
            raise TiempoAgotado("respuesta perdida")
        operacion()  # DUPLICADA
        return operacion()

    # --- puerto ----------------------------------------------------------------------------

    def asegurar_usuario(self, colaborador: Colaborador) -> str:
        return self._escritura(
            lambda: self._usuarios.setdefault(colaborador.id, f"u-{colaborador.id}")
        )

    def crear_ticket(self, ticket: TicketDeCola) -> TicketCreado:
        def crear() -> TicketCreado:
            clave = ticket.clave_de_idempotencia
            if clave in self._por_clave:
                return TicketCreado(self._por_clave[clave], ya_existia=True)
            id_externo = f"G-{len(self._remotos) + 1:05d}"
            inicial = (
                EstadoDeTicket.EN_ESPERA
                if ticket.estado_inicial is EstadoInicialDeTicket.EN_ESPERA
                else EstadoDeTicket.NUEVO
            )
            self._remotos[id_externo] = _Remoto(ticket, id_externo, inicial)
            self._por_clave[clave] = id_externo
            self.creaciones_reales[clave] = self.creaciones_reales.get(clave, 0) + 1
            return TicketCreado(id_externo, ya_existia=False)

        return self._escritura(crear)

    def subir_documento(self, nombre: NombreDeSoporteSaneado, contenido: bytes) -> str:
        def subir() -> str:
            hash_ = Sha256.de_bytes(contenido).valor
            for doc in self._documentos.values():
                if doc.hash_guardado == hash_ and doc.contenido == contenido:
                    return doc.id
            doc_id = f"D-{len(self._documentos) + 1:04d}"
            hash_guardado = "0" * 64 if self.corromper_al_subir else hash_
            self._documentos[doc_id] = _Documento(doc_id, nombre.valor, contenido, hash_guardado)
            self.subidas_reales += 1
            return doc_id

        return self._escritura(subir)

    def hash_de_documento(self, id_documento: str) -> Sha256:
        def leer() -> Sha256:
            try:
                return Sha256(self._documentos[id_documento].hash_guardado)
            except KeyError:
                raise GlpiRechazo("documento inexistente") from None

        return self._lectura(leer)

    def vincular_documento(self, id_documento: str, id_ticket: str) -> None:
        def vincular() -> None:
            if id_documento not in self._documentos or id_ticket not in self._remotos:
                raise GlpiRechazo("documento o ticket inexistente")
            self._vinculos.add((id_documento, id_ticket))

        self._escritura(vincular)

    def leer_tickets(self, ids: Sequence[str]) -> Mapping[str, Observacion]:
        def leer() -> Mapping[str, Observacion]:
            ahora = self.reloj.ahora()
            return {
                i: Observacion(r.estado, r.solucion, r.documentos, ahora)
                for i in ids
                if (r := self._remotos.get(i)) is not None
            }

        return self._lectura(leer)

    def leer_activos(self, id_usuario: str) -> Sequence[ActivoAsignado]:
        return self._lectura(lambda: list(self._activos.get(id_usuario, [])))

    def leer_licencias(self, id_usuario: str) -> Sequence[LicenciaAsignada]:
        return self._lectura(lambda: list(self._licencias.get(id_usuario, [])))

    # --- el tecnico trabajando en GLPI (ayudas de prueba, fuera del puerto) --------------

    def id_de(self, clave: str) -> str:
        return self._por_clave[clave]

    def resolver(
        self,
        id_externo: str,
        con_solucion: bool = True,
        documentos: int = 0,
        estado: EstadoDeTicket = EstadoDeTicket.RESUELTO,
    ) -> None:
        r = self._remotos[id_externo]
        r.estado, r.solucion, r.documentos = estado, con_solucion, r.documentos + documentos

    def reabrir(self, id_externo: str) -> None:
        self._remotos[id_externo].estado = EstadoDeTicket.EN_CURSO

    def poner_estado(self, id_externo: str, estado: EstadoDeTicket) -> None:
        self._remotos[id_externo].estado = estado

    def adjuntar(self, id_externo: str, cantidad: int = 1) -> None:
        self._remotos[id_externo].documentos += cantidad

    def asignar_activo(self, id_usuario: str, activo: ActivoAsignado) -> ActivoAsignado:
        self._activos.setdefault(id_usuario, []).append(activo)
        return activo

    def asignar_licencia(self, id_usuario: str, licencia: LicenciaAsignada) -> LicenciaAsignada:
        self._licencias.setdefault(id_usuario, []).append(licencia)
        return licencia

    def corromper_documento(self, id_documento: str) -> None:
        self._documentos[id_documento].hash_guardado = "0" * 64

    # --- protocolos InyectorDeFallos y Tecnico de la suite de contrato -----------------------

    def timeout_despues_de_crear(self) -> None:
        self.programar(Fallo.DESPUES)

    def error_antes_de_crear(self) -> None:
        self.programar(Fallo.ANTES)

    def respuesta_duplicada(self) -> None:
        self.programar(Fallo.DUPLICADA)

    def caida(self, llamadas: int) -> None:
        self.caer(llamadas)

    def creaciones(self, clave: str) -> int:
        return self.creaciones_reales.get(clave, 0)

    # --- observacion para las pruebas -------------------------------------------------------

    def tickets_remotos(self) -> list[TicketDeCola]:
        return [r.ticket for r in self._remotos.values()]

    def vinculos_de(self, id_ticket: str) -> set[str]:
        return {d for d, t in self._vinculos if t == id_ticket}

    def documentos_subidos(self) -> int:
        return len(self._documentos)
