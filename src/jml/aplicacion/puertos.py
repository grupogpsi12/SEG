"""Puertos de salida (SRS 10.1), cada uno con una implementacion real futura y un doble.

Solo existen estos seis: Repositorios (con su unidad de trabajo), Auditoria, SistemaDeTickets,
ProveedorDeIdentidad, Reloj y AlmacenDeSoportes. Un puerto nuevo exige una segunda
implementacion y un ADR (CLAUDE.md).
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Protocol, Self

from jml.aplicacion.bandeja import EntradaDeBandeja
from jml.aplicacion.dtos import (
    FichaDeColaborador,
    FiltroDeCuentas,
    Indicadores,
    PaginaDeCuentas,
    ResultadoDeSincronizacion,
)
from jml.dominio.activos import ActivoAsignado, LicenciaAsignada
from jml.dominio.auditoria import EventoDeAuditoria, RegistroDeAuditoria, ResultadoDeVerificacion
from jml.dominio.catalogo import ColaboradorId, UsuarioId
from jml.dominio.colaborador import Colaborador
from jml.dominio.cuentas import CambioDeCuenta, Cuenta
from jml.dominio.perfiles import PerfilDeAcceso
from jml.dominio.permisos import Actor, UsuarioDelSistema
from jml.dominio.solicitud import Decision, Solicitud
from jml.dominio.soporte import Soporte
from jml.dominio.tickets import Observacion, TicketDeCola, TicketSeguido
from jml.dominio.tipos import Rol, SistemaDeCuenta, TipoEvento
from jml.dominio.valores import Documento, NombreDeSoporteSaneado, Sha256, SolicitudId

type NuevoId = Callable[[], str]  # generador de identificadores inyectado (no es un puerto)

# --- errores de los puertos -------------------------------------------------------------------


class ErrorDePuerto(Exception):
    """Fallo de un colaborador externo del nucleo (base de datos, GLPI, identidad, disco)."""


class DuplicadoAbierto(ErrorDePuerto):
    """RD-01: ya existe una solicitud abierta del mismo (colaborador, tipo)."""

    def __init__(self, existente_id: SolicitudId) -> None:
        super().__init__(f"duplicado abierto: {existente_id.valor}")
        self.existente_id = existente_id


class DocumentoYaRegistrado(ErrorDePuerto):
    """RD-09: el documento ya pertenece a un colaborador que no esta retirado."""

    def __init__(self, existente_id: ColaboradorId) -> None:
        super().__init__(f"documento ya registrado: {existente_id}")
        self.existente_id = existente_id


class ContenidoDeSolicitudModificado(ErrorDePuerto):
    """RF-14: se intento cambiar el contenido de una solicitud ya aprobada (disparador)."""

    def __init__(self, solicitud_id: SolicitudId) -> None:
        super().__init__(f"contenido inmutable: {solicitud_id.valor}")
        self.solicitud_id = solicitud_id


class ErrorDeSistemaDeTickets(ErrorDePuerto):
    codigo = "glpi_error"


class GlpiNoDisponible(ErrorDeSistemaDeTickets):
    codigo = "glpi_no_disponible"


class TiempoAgotado(ErrorDeSistemaDeTickets):
    """La respuesta se perdio: el ticket PUDO crearse (por eso crear_ticket es idempotente)."""

    codigo = "glpi_timeout"


class GlpiRechazo(ErrorDeSistemaDeTickets):
    codigo = "glpi_rechazo"


class SoporteNoDisponible(ErrorDePuerto):
    """RD-12: la copia temporal del soporte ya no esta en el volumen."""


class CredencialesInvalidas(ErrorDePuerto):
    """Mensaje generico a proposito: no revela si el correo existe (RS-08)."""

    def __init__(self) -> None:
        super().__init__("credenciales invalidas")


# --- Reloj ------------------------------------------------------------------------------------


class Reloj(Protocol):
    def ahora(self) -> datetime:
        """Instante actual con zona horaria."""
        ...


# --- Auditoria --------------------------------------------------------------------------------


class Auditoria(Protocol):
    """Unica via de escritura de la cadena de hashes (invariante 4)."""

    def registrar(self, actor: str, evento: EventoDeAuditoria) -> RegistroDeAuditoria: ...

    def registros(self) -> Sequence[RegistroDeAuditoria]:
        """Todos los registros, en orden de secuencia."""
        ...

    def verificar(self) -> ResultadoDeVerificacion: ...


# --- AlmacenDeSoportes ------------------------------------------------------------------------


class AlmacenDeSoportes(Protocol):
    """Volumen temporal `noexec` (RD-12). La aplicacion web nunca abre ni sirve el archivo."""

    def guardar(self, contenido: bytes) -> str:
        """Guarda con un nombre aleatorio y lo devuelve."""
        ...

    def leer(self, nombre: str) -> bytes:
        """Solo del worker, al subirlo a GLPI. `SoporteNoDisponible` si ya no esta."""
        ...

    def borrar(self, nombre: str) -> None:
        """Idempotente: borrar algo que no existe no es un error."""
        ...

    def existe(self, nombre: str) -> bool: ...


# --- ProveedorDeIdentidad ---------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PrimerFactor:
    """Contrasena verificada; falta el TOTP. Todavia NO es una sesion (RF-01)."""

    usuario_id: UsuarioId
    desafio_id: str
    requiere_inscripcion: bool  # RF-02: primer ingreso, hay que inscribir el TOTP


@dataclass(frozen=True, slots=True)
class IdentidadVerificada:
    usuario_id: UsuarioId
    nivel: int  # 2 = AAL2: contrasena + TOTP


class ProveedorDeIdentidad(Protocol):
    def autenticar(self, correo: str, contrasena: str) -> PrimerFactor:
        """`CredencialesInvalidas` identico para correo desconocido y contrasena incorrecta."""
        ...

    def inscribir_totp(self, desafio_id: str) -> str:
        """Devuelve el secreto/URI para el codigo QR; el factor queda pendiente de verificar."""
        ...

    def verificar_totp(self, desafio_id: str, codigo: str) -> IdentidadVerificada:
        """Solo con un codigo valido se alcanza AAL2; si no, `CredencialesInvalidas`."""
        ...


# --- SistemaDeTickets (GLPI) ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TicketCreado:
    id_externo: str
    ya_existia: bool  # True si la clave de idempotencia ya tenia un ticket


class SistemaDeTickets(Protocol):
    """GLPI es la fuente de la verdad sobre el estado de cada ticket (ADR-001, ADR-016).

    PROVISIONAL hasta el spike 0.3: debe confirmarse que GLPI permite buscar un ticket por
    referencia externa y un documento por hash. Todas las escrituras son idempotentes.
    """

    def asegurar_usuario(self, colaborador: Colaborador) -> str:
        """RF-21: crea o actualiza el usuario sin credenciales; devuelve su id en GLPI."""
        ...

    def crear_ticket(self, ticket: TicketDeCola) -> TicketCreado:
        """Idempotente por `clave_de_idempotencia`, tambien tras un timeout (RF-18)."""
        ...

    def subir_documento(self, nombre: NombreDeSoporteSaneado, contenido: bytes) -> str:
        """Idempotente por contenido: subir dos veces los mismos bytes devuelve el mismo id."""
        ...

    def hash_de_documento(self, id_documento: str) -> Sha256:
        """Hash SHA-256 que GLPI tiene del documento, para verificar antes de borrar la copia."""
        ...

    def vincular_documento(self, id_documento: str, id_ticket: str) -> None:
        """Idempotente."""
        ...

    def leer_tickets(self, ids: Sequence[str]) -> Mapping[str, Observacion]:
        """Estado, solucion y adjuntos de cada ticket (RF-22). Los ids desconocidos se omiten."""
        ...

    def leer_activos(self, id_usuario: str) -> Sequence[ActivoAsignado]: ...

    def leer_licencias(self, id_usuario: str) -> Sequence[LicenciaAsignada]: ...


# --- Repositorios y unidad de trabajo ---------------------------------------------------------


class RepoSolicitudes(Protocol):
    def siguiente_id(self, anio: int) -> SolicitudId:
        """Consecutivo SOL-AAAA-NNNNNN por anio."""
        ...

    def guardar(self, solicitud: Solicitud) -> None:
        """Inserta o actualiza.

        `DuplicadoAbierto` si deja dos abiertas del mismo (colaborador, tipo) (RD-01);
        `ContenidoDeSolicitudModificado` si cambia el contenido de una ya aprobada (RF-14).
        """
        ...

    def obtener(self, solicitud_id: SolicitudId) -> Solicitud | None: ...

    def abiertas_de(self, colaborador_id: ColaboradorId) -> Sequence[Solicitud]: ...

    def de_colaborador(self, colaborador_id: ColaboradorId) -> Sequence[Solicitud]: ...

    def abierta_de_tipo(
        self, colaborador_id: ColaboradorId, tipo: TipoEvento
    ) -> Solicitud | None: ...

    # ADR-025: lecturas para las vistas.
    def del_solicitante(self, usuario_id: UsuarioId) -> Sequence[Solicitud]:
        """Las que registro ese usuario (abiertas y finales), por orden de identificador."""
        ...

    def pendientes_de_aprobacion(self) -> Sequence[Solicitud]: ...


class RepoColaboradores(Protocol):
    def guardar(self, colaborador: Colaborador) -> None:
        """`DocumentoYaRegistrado` si otro colaborador no retirado tiene el mismo documento."""
        ...

    def obtener(self, colaborador_id: ColaboradorId) -> Colaborador | None: ...

    def por_documento(self, documento: Documento) -> Colaborador | None:
        """El colaborador no retirado con ese documento, si existe."""
        ...

    def usuarios_en_uso(self) -> frozenset[str]: ...

    def con_usuario_glpi(self) -> Sequence[Colaborador]: ...

    def con_fin_de_contrato(self) -> Sequence[Colaborador]: ...

    def subordinados_de(self, jefe_id: ColaboradorId) -> Sequence[Colaborador]:
        """ADR-025: subordinados directos que no estan retirados, por identificador."""
        ...


class RepoUsuarios(Protocol):
    def guardar(self, usuario: UsuarioDelSistema) -> None: ...

    def actor_de(self, usuario_id: UsuarioId) -> Actor | None:
        """None si no existe o esta inactivo."""
        ...

    def roles_de_colaborador(self, colaborador_id: ColaboradorId) -> frozenset[Rol]: ...


class RepoPerfiles(Protocol):
    def guardar(self, perfil: PerfilDeAcceso) -> None: ...

    def obtener(self, departamento: str, sede: str) -> PerfilDeAcceso | None: ...


class RepoTickets(Protocol):
    def guardar(self, seguido: TicketSeguido) -> None: ...

    def por_clave(self, clave: str) -> TicketSeguido | None: ...

    def de_solicitud(self, solicitud_id: SolicitudId) -> Sequence[TicketSeguido]: ...

    def creados(self) -> Sequence[TicketSeguido]:
        """Los que ya tienen id en GLPI: son los que la sincronizacion consulta."""
        ...


class RepoCuentas(Protocol):
    def obtener(self, colaborador_id: ColaboradorId, sistema: SistemaDeCuenta) -> Cuenta | None: ...

    def guardar(self, cuenta: Cuenta) -> None: ...

    def agregar_historial(self, cambio: CambioDeCuenta) -> None:
        """Solo insercion (RD-02)."""
        ...

    def historial(self, colaborador_id: ColaboradorId) -> Sequence[CambioDeCuenta]: ...


class RepoDecisiones(Protocol):
    def agregar(self, decision: Decision) -> None:
        """Solo insercion (RD-02)."""
        ...

    def de_solicitud(self, solicitud_id: SolicitudId) -> Sequence[Decision]: ...


class RepoSoportes(Protocol):
    def guardar(self, soporte: Soporte) -> None: ...

    def obtener(self, solicitud_id: SolicitudId) -> Soporte | None: ...


class RepoBandeja(Protocol):
    def encolar(self, entradas: Sequence[EntradaDeBandeja]) -> None: ...

    def guardar(self, entrada: EntradaDeBandeja) -> None: ...

    def vencidas(self, ahora: datetime, limite: int) -> Sequence[EntradaDeBandeja]:
        """Pendientes con `proximo_intento <= ahora`, por orden de proximo intento."""
        ...

    def obtener(self, clave: str) -> EntradaDeBandeja | None: ...

    def de_solicitud(self, solicitud_id: SolicitudId) -> Sequence[EntradaDeBandeja]: ...


class RepoActivos(Protocol):
    def reemplazar(
        self,
        colaborador_id: ColaboradorId,
        activos: Sequence[ActivoAsignado],
        licencias: Sequence[LicenciaAsignada],
    ) -> None:
        """Copia de GLPI, reemplazada en cada sincronizacion."""
        ...

    def activos_de(self, colaborador_id: ColaboradorId) -> Sequence[ActivoAsignado]: ...

    def licencias_de(self, colaborador_id: ColaboradorId) -> Sequence[LicenciaAsignada]: ...


class RepoSincronizaciones(Protocol):
    def registrar(self, resultado: ResultadoDeSincronizacion) -> None: ...

    def ultima(self) -> ResultadoDeSincronizacion | None: ...


class UnidadDeTrabajo(Protocol):
    """Transaccion atomica: todo o nada (CA-02). Si el bloque lanza, no queda rastro."""

    # Propiedades de solo lectura: asi un doble o un adaptador pueden exponer subtipos concretos.
    @property
    def solicitudes(self) -> RepoSolicitudes: ...
    @property
    def colaboradores(self) -> RepoColaboradores: ...
    @property
    def usuarios(self) -> RepoUsuarios: ...
    @property
    def perfiles(self) -> RepoPerfiles: ...
    @property
    def tickets(self) -> RepoTickets: ...
    @property
    def cuentas(self) -> RepoCuentas: ...
    @property
    def decisiones(self) -> RepoDecisiones: ...
    @property
    def soportes(self) -> RepoSoportes: ...
    @property
    def bandeja(self) -> RepoBandeja: ...
    @property
    def activos(self) -> RepoActivos: ...
    @property
    def sincronizaciones(self) -> RepoSincronizaciones: ...
    @property
    def auditoria(self) -> Auditoria: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        tipo: type[BaseException] | None,
        error: BaseException | None,
        traza: TracebackType | None,
    ) -> None: ...


class Repositorios(Protocol):
    def unidad_de_trabajo(self) -> UnidadDeTrabajo: ...

    # Consultas de lectura (RF-29 a RF-33). El doble en memoria las calcula en Python simple y
    # su resultado es el ORACULO contra el que se compara la consulta SQL (CA-15).
    def indicadores(self, ahora: datetime) -> Indicadores: ...

    def buscar_cuentas(self, filtro: FiltroDeCuentas) -> PaginaDeCuentas: ...

    def ficha(self, colaborador_id: ColaboradorId) -> FichaDeColaborador | None: ...
