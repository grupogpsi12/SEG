"""Entradas y salidas de los casos de uso. Solo datos: ninguna regla de negocio vive aqui.

Ningun DTO de lectura (dashboard, busqueda, ficha) tiene un campo para el motivo de un retiro
ni para la descripcion de una emergencia (RD-05, CA-10): no pueden filtrarse porque no existen.
"""

from dataclasses import dataclass
from datetime import date, datetime

from jml.dominio.activos import ActivoAsignado, LicenciaAsignada
from jml.dominio.catalogo import ColaboradorId, DatosDelEvento, UsuarioId
from jml.dominio.errores import DatoInvalido
from jml.dominio.tipos import (
    AccionDeTicket,
    ClaseTicket,
    Cola,
    EstadoColaborador,
    EstadoDeCuenta,
    EstadoDeTicket,
    EstadoSolicitud,
    MarcaDeCuenta,
    Prioridad,
    Rol,
    SistemaDeCuenta,
    Subtipo,
    TipoDeVinculacion,
    TipoEvento,
)
from jml.dominio.valores import SolicitudId

# --- escritura --------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ArchivoRecibido:
    """Bytes tal como llegaron del formulario; el nucleo los valida (RF-39), no confia en MIME."""

    nombre: str
    contenido: bytes


@dataclass(frozen=True, slots=True)
class NuevaSolicitud:
    usuario_id: UsuarioId
    tipo: TipoEvento
    fecha_efectiva: date
    datos: DatosDelEvento
    colaborador_id: ColaboradorId | None = None  # None solo en ING: el colaborador aun no existe
    subtipo: Subtipo | None = None
    restringido: str | None = None  # motivo (RET) o descripcion (EMG): texto crudo, solo para RRHH
    soporte: ArchivoRecibido | None = None
    justificacion: str | None = None
    solicitud_origen_id: SolicitudId | None = None


@dataclass(frozen=True, slots=True)
class SolicitudRegistrada:
    solicitud_id: SolicitudId
    estado: EstadoSolicitud
    colaborador_id: ColaboradorId
    tickets_encolados: int
    marcadas_para_revision: tuple[SolicitudId, ...] = ()


@dataclass(frozen=True, slots=True)
class ResultadoDeDecision:
    solicitud_id: SolicitudId
    estado: EstadoSolicitud
    tickets_encolados: int = 0


@dataclass(frozen=True, slots=True)
class ResultadoDeBandeja:
    procesadas: int
    creadas: int
    reintentos_programados: int
    solicitudes_en_error: tuple[SolicitudId, ...]
    solicitudes_en_ejecucion: tuple[SolicitudId, ...]


@dataclass(frozen=True, slots=True)
class ResultadoDeSincronizacion:
    inicio: datetime
    fin: datetime
    resultado: str  # "ok" o "error"
    tickets_leidos: int
    errores: int


@dataclass(frozen=True, slots=True)
class ContratoPorVencer:
    colaborador_id: ColaboradorId
    nombre_completo: str
    fecha_fin: date
    dias_restantes: int


@dataclass(frozen=True, slots=True)
class FilaDeSolicitud:
    """Una fila de las listas de las vistas (ADR-025). Sin campos restringidos (RD-05)."""

    id: SolicitudId
    tipo: TipoEvento
    estado: EstadoSolicitud
    fecha_efectiva: date
    creada_en: datetime
    colaborador_id: ColaboradorId
    colaborador_nombre: str
    para_revision: bool
    cancelable: bool  # el solicitante puede cancelarla: sigue pendiente (RF-11)


@dataclass(frozen=True, slots=True)
class OpcionDeColaborador:
    colaborador_id: ColaboradorId
    nombre: str


@dataclass(frozen=True, slots=True)
class PerfilDeUsuario:
    """Lo que las vistas necesitan para ofrecer el menu y los formularios correctos."""

    usuario_id: UsuarioId
    roles: frozenset[Rol]
    colaborador: OpcionDeColaborador | None


# --- lectura: dashboard (RF-29, RF-30) --------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FilaPendientes:  # (a)
    cola: Cola
    prioridad: Prioridad
    cantidad: int


@dataclass(frozen=True, slots=True)
class FilaVencidos:  # (b)
    cola: Cola
    cantidad: int


@dataclass(frozen=True, slots=True)
class FilaExposicion:  # (c)
    solicitud_id: SolicitudId
    tipo: TipoEvento
    colaborador_id: ColaboradorId
    tickets_de_baja_abiertos: int
    horas_de_exposicion: int
    desde: datetime


@dataclass(frozen=True, slots=True)
class FilaSolicitudesDelMes:  # (d)
    estado: EstadoSolicitud
    tipo: TipoEvento
    cantidad: int


@dataclass(frozen=True, slots=True)
class FilaCuentas:  # (e)
    sistema: SistemaDeCuenta
    estado: EstadoDeCuenta
    cantidad: int


@dataclass(frozen=True, slots=True)
class IndicadorDeEquipos:  # (f)
    asignados: int
    pendientes_de_devolucion: int


@dataclass(frozen=True, slots=True)
class FilaProgramado:  # (g)
    clave: str
    cola: Cola
    solicitud_id: SolicitudId
    pendiente_desde: datetime


@dataclass(frozen=True, slots=True)
class FilaIncompleto:  # (h)
    clave: str
    cola: Cola
    solicitud_id: SolicitudId
    motivo: str  # "cierre_incompleto" o "reabierto"


@dataclass(frozen=True, slots=True)
class Indicadores:
    generados_en: datetime
    ultima_sincronizacion: ResultadoDeSincronizacion | None
    cola_resaltada: Cola | None
    pendientes: tuple[FilaPendientes, ...]
    vencidos: tuple[FilaVencidos, ...]
    exposicion: tuple[FilaExposicion, ...]
    solicitudes_del_mes: tuple[FilaSolicitudesDelMes, ...]
    cuentas: tuple[FilaCuentas, ...]
    equipos: IndicadorDeEquipos
    programados: tuple[FilaProgramado, ...]
    incompletos: tuple[FilaIncompleto, ...]


# --- lectura: busqueda y ficha (RF-32, RF-33) -------------------------------------------------

TAMANO_MAXIMO_DE_PAGINA = 100


@dataclass(frozen=True, slots=True)
class FiltroDeCuentas:
    nombre: str | None = None
    documento: str | None = None
    usuario: str | None = None
    departamento: str | None = None
    sede: str | None = None
    sistema: SistemaDeCuenta | None = None
    estado_de_cuenta: EstadoDeCuenta | None = None
    pagina: int = 1
    tamano: int = 20

    def __post_init__(self) -> None:
        if self.pagina < 1:
            raise DatoInvalido("pagina", "empieza en 1")
        if not 1 <= self.tamano <= TAMANO_MAXIMO_DE_PAGINA:
            raise DatoInvalido("tamano", f"entre 1 y {TAMANO_MAXIMO_DE_PAGINA}")


@dataclass(frozen=True, slots=True)
class ResumenDeCuenta:
    sistema: SistemaDeCuenta
    estado: EstadoDeCuenta
    marca: MarcaDeCuenta | None
    desde: datetime
    ticket_origen: str


@dataclass(frozen=True, slots=True)
class FilaDeColaborador:
    colaborador_id: ColaboradorId
    nombre_completo: str
    documento: str
    usuario: str | None
    departamento: str
    sede: str
    estado: EstadoColaborador
    cuentas: tuple[ResumenDeCuenta, ...]


@dataclass(frozen=True, slots=True)
class PaginaDeCuentas:
    filas: tuple[FilaDeColaborador, ...]
    total: int
    pagina: int
    tamano: int


@dataclass(frozen=True, slots=True)
class ResumenDeSolicitud:
    id: SolicitudId
    tipo: TipoEvento
    estado: EstadoSolicitud
    fecha_efectiva: date
    creada_en: datetime


@dataclass(frozen=True, slots=True)
class ResumenDeTicket:
    clave: str
    solicitud_id: SolicitudId
    cola: Cola
    clase: ClaseTicket
    accion: AccionDeTicket
    id_externo: str | None
    estado_glpi: EstadoDeTicket | None
    tiene_solucion: bool
    reabierto: bool
    cierre_incompleto: bool


@dataclass(frozen=True, slots=True)
class FichaDeColaborador:
    colaborador_id: ColaboradorId
    nombre_completo: str
    documento: str
    vinculacion: TipoDeVinculacion
    departamento: str
    cargo: str
    sede: str
    jefe_id: ColaboradorId | None
    estado: EstadoColaborador
    usuario: str | None
    fecha_ingreso: date
    fecha_fin: date | None
    cuentas: tuple[ResumenDeCuenta, ...]
    equipos: tuple[ActivoAsignado, ...]
    licencias: tuple[LicenciaAsignada, ...]
    solicitudes: tuple[ResumenDeSolicitud, ...]
    tickets: tuple[ResumenDeTicket, ...]
