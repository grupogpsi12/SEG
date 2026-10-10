"""Catalogo de campos por tipo de evento (SRS 4.8) y su validacion pura (RF-07, RF-08).

Los datos de cada evento son dataclasses congeladas que se validan al construirse, de modo que
un dato invalido no puede existir. Las reglas que cruzan campos con la fecha efectiva viven en
`validar_evento`. El motivo de retiro y la descripcion de una emergencia NO estan aqui: viajan
aparte como `CampoRestringido` (RD-05).
"""

from dataclasses import dataclass
from datetime import date, datetime

from jml.dominio.errores import DatoInvalido
from jml.dominio.tipos import Subtipo, TipoDeEquipo, TipoDeVinculacion, TipoEvento
from jml.dominio.valores import (
    CampoRestringido,
    Documento,
    a_utc,
    hoy_en_bogota,
    texto_no_vacio,
)

type ColaboradorId = str
type UsuarioId = str


@dataclass(frozen=True, slots=True)
class DatosIngreso:
    nombres: str
    apellidos: str
    documento: Documento
    vinculacion: TipoDeVinculacion
    departamento: str
    cargo: str
    sede: str
    jefe_id: ColaboradorId | None
    fecha_fin: date | None
    requiere_equipo: bool
    tipo_equipo: TipoDeEquipo | None

    def __post_init__(self) -> None:
        for campo in ("nombres", "apellidos", "departamento", "cargo", "sede"):
            object.__setattr__(self, campo, texto_no_vacio(campo, getattr(self, campo), 100))
        if self.vinculacion is not TipoDeVinculacion.EMPLEADO and self.fecha_fin is None:
            raise DatoInvalido("fecha_fin", "obligatoria si la vinculacion no es de empleado")
        if self.requiere_equipo and self.tipo_equipo is None:
            raise DatoInvalido("tipo_equipo", "obligatorio cuando requiere equipo")
        if not self.requiere_equipo and self.tipo_equipo is not None:
            raise DatoInvalido("tipo_equipo", "no aplica cuando no requiere equipo")


@dataclass(frozen=True, slots=True)
class DatosVacaciones:
    fecha_regreso: date


@dataclass(frozen=True, slots=True)
class DatosCambioDepartamento:
    departamento_nuevo: str
    cargo_nuevo: str
    jefe_nuevo_id: ColaboradorId | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "departamento_nuevo",
            texto_no_vacio("departamento_nuevo", self.departamento_nuevo),
        )
        object.__setattr__(self, "cargo_nuevo", texto_no_vacio("cargo_nuevo", self.cargo_nuevo))


@dataclass(frozen=True, slots=True)
class DatosCambioSucursal:
    sede_nueva: str
    traslada_equipo: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "sede_nueva", texto_no_vacio("sede_nueva", self.sede_nueva))


@dataclass(frozen=True, slots=True)
class DatosRetiro:
    """El ultimo dia laborado es la fecha efectiva; el motivo (R) va aparte."""


@dataclass(frozen=True, slots=True)
class DatosEmergencia:
    reportado_por: str
    hora_del_hecho: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "reportado_por", texto_no_vacio("reportado_por", self.reportado_por)
        )
        object.__setattr__(self, "hora_del_hecho", a_utc(self.hora_del_hecho, "hora_del_hecho"))


type DatosDelEvento = (
    DatosIngreso
    | DatosVacaciones
    | DatosCambioDepartamento
    | DatosCambioSucursal
    | DatosRetiro
    | DatosEmergencia
)

DATOS_POR_TIPO: dict[TipoEvento, type] = {
    TipoEvento.ING: DatosIngreso,
    TipoEvento.VAC: DatosVacaciones,
    TipoEvento.CDP: DatosCambioDepartamento,
    TipoEvento.CSU: DatosCambioSucursal,
    TipoEvento.RET: DatosRetiro,
    TipoEvento.EMG: DatosEmergencia,
}

SUBTIPOS_POR_TIPO: dict[TipoEvento, frozenset[Subtipo]] = {
    TipoEvento.ING: frozenset(),
    TipoEvento.VAC: frozenset(),
    TipoEvento.CDP: frozenset(),
    TipoEvento.CSU: frozenset(),
    TipoEvento.RET: frozenset({Subtipo.RENUNCIA, Subtipo.FIN_DE_CONTRATO}),
    TipoEvento.EMG: frozenset({Subtipo.DESPIDO_CON_JUSTA_CAUSA, Subtipo.FUGA_DETECTADA}),
}

# Tipos cuyo campo restringido (R) es obligatorio: motivo de RET y descripcion de EMG.
TIPOS_CON_RESTRINGIDO = frozenset({TipoEvento.RET, TipoEvento.EMG})


def validar_evento(
    tipo: TipoEvento,
    subtipo: Subtipo | None,
    fecha_efectiva: date,
    datos: DatosDelEvento,
    restringido: CampoRestringido | None,
    ahora: datetime,
) -> None:
    """Validacion pura del evento completo. Lanza `DatoInvalido`; no devuelve nada."""
    if type(datos) is not DATOS_POR_TIPO[tipo]:
        raise DatoInvalido("datos", f"no corresponden a un evento {tipo.value}")
    permitidos = SUBTIPOS_POR_TIPO[tipo]
    if permitidos:
        if subtipo not in permitidos:
            raise DatoInvalido("subtipo", f"no valido para {tipo.value}")
    elif subtipo is not None:
        raise DatoInvalido("subtipo", f"{tipo.value} no tiene subtipos")
    if tipo in TIPOS_CON_RESTRINGIDO:
        if restringido is None:
            raise DatoInvalido("restringido", f"obligatorio en {tipo.value}")
    elif restringido is not None:
        raise DatoInvalido("restringido", f"no aplica a {tipo.value}")

    hoy = hoy_en_bogota(ahora)
    # S-15: la fecha efectiva no puede estar en el pasado (RF-08 admite futuras).
    if fecha_efectiva < hoy:
        raise DatoInvalido("fecha_efectiva", "no puede estar en el pasado")

    if isinstance(datos, DatosIngreso):
        if datos.fecha_fin is not None and datos.fecha_fin <= fecha_efectiva:
            raise DatoInvalido("fecha_fin", "debe ser posterior a la fecha de ingreso")
    elif isinstance(datos, DatosVacaciones):
        if datos.fecha_regreso <= fecha_efectiva:
            raise DatoInvalido("fecha_regreso", "debe ser posterior a la fecha de inicio")
    elif isinstance(datos, DatosEmergencia):
        # S-03/S-15: una emergencia es inmediata, su fecha efectiva es la de la emision.
        if fecha_efectiva != hoy:
            raise DatoInvalido("fecha_efectiva", "una emergencia es efectiva el dia de la emision")
        if datos.hora_del_hecho > a_utc(ahora, "ahora"):
            raise DatoInvalido("hora_del_hecho", "no puede estar en el futuro")
