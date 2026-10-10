"""Enumeraciones del dominio. Los nombres siguen el glosario del SRS (secciones 3 y 4)."""

from enum import IntEnum, StrEnum


class TipoEvento(StrEnum):
    ING = "ING"
    VAC = "VAC"
    CDP = "CDP"
    CSU = "CSU"
    RET = "RET"
    EMG = "EMG"


class Subtipo(StrEnum):
    RENUNCIA = "renuncia"
    FIN_DE_CONTRATO = "fin_de_contrato"
    DESPIDO_CON_JUSTA_CAUSA = "despido_con_justa_causa"
    FUGA_DETECTADA = "fuga_detectada"


class EstadoSolicitud(StrEnum):
    PENDIENTE_APROBACION = "pendiente_aprobacion"
    APROBADA = "aprobada"
    EN_EJECUCION = "en_ejecucion"
    ERROR = "error"
    CERRADA = "cerrada"
    RECHAZADA = "rechazada"
    CANCELADA = "cancelada"


# RD-01 y lessons.md n.º 1: `error` y `en_ejecucion` son estados ABIERTOS.
ESTADOS_ABIERTOS = frozenset(
    {
        EstadoSolicitud.PENDIENTE_APROBACION,
        EstadoSolicitud.APROBADA,
        EstadoSolicitud.EN_EJECUCION,
        EstadoSolicitud.ERROR,
    }
)
ESTADOS_FINALES = frozenset(EstadoSolicitud) - ESTADOS_ABIERTOS


class Cola(StrEnum):
    AD = "AD"
    COMUNICACIONES = "COMUNICACIONES"
    LICENCIAS = "LICENCIAS"
    INVENTARIO = "INVENTARIO"
    REVISION_MANUAL = "REVISION_MANUAL"


class ClaseTicket(StrEnum):
    CIERRE_INMEDIATO = "cierre_inmediato"
    CIERRE_PROGRAMADO = "cierre_programado"
    POSTERIOR = "posterior"


class AccionDeTicket(StrEnum):
    """Que hace el ticket sobre la cuenta; alimenta la tabla de derivacion (SRS 4.7)."""

    ALTA = "alta"
    SUSPENSION = "suspension"
    REACTIVACION = "reactivacion"
    CAMBIO = "cambio"
    BAJA = "baja"
    ELIMINACION = "eliminacion"
    EQUIPO = "equipo"


class EstadoInicialDeTicket(StrEnum):
    NUEVO = "Nuevo"
    EN_ESPERA = "En espera"


class EstadoDeTicket(IntEnum):
    """Estados de GLPI en el orden que importa para RF-24 (>= RESUELTO)."""

    NUEVO = 1
    EN_ESPERA = 2
    EN_CURSO = 3
    RESUELTO = 4
    CERRADO = 5


class SistemaDeCuenta(StrEnum):
    AD = "AD"
    RED = "Red"
    M365 = "M365"


class EstadoDeCuenta(StrEnum):
    PENDIENTE_ALTA = "pendiente_alta"
    ACTIVA = "activa"
    PENDIENTE_SUSPENSION = "pendiente_suspension"
    SUSPENDIDA = "suspendida"
    PENDIENTE_BAJA = "pendiente_baja"
    DESHABILITADA = "deshabilitada"
    ELIMINADA = "eliminada"


class MarcaDeCuenta(StrEnum):
    CAMBIO_PENDIENTE = "cambio_pendiente"
    REABIERTO = "reabierto"
    CIERRE_SIN_SOLUCION = "cierre_sin_solucion"


class PerfilDeRecurso(StrEnum):
    CONSULTA = "Consulta"
    EDICION = "Edición"
    RETIRO_DE_ACCESOS = "Retiro de accesos"


class Prioridad(StrEnum):
    MEDIA = "Media"
    ALTA = "Alta"
    MUY_ALTA = "Muy alta"


class Rol(StrEnum):
    SOLICITANTE = "solicitante"
    RRHH = "rrhh"
    TECNICO_AD = "tecnico_ad"
    TECNICO_COMUNICACIONES = "tecnico_comunicaciones"
    TECNICO_LICENCIAS = "tecnico_licencias"
    TECNICO_INVENTARIO = "tecnico_inventario"
    AUDITOR = "auditor"
    ADMINISTRADOR = "administrador"


ROLES_TECNICOS = frozenset(
    {
        Rol.TECNICO_AD,
        Rol.TECNICO_COMUNICACIONES,
        Rol.TECNICO_LICENCIAS,
        Rol.TECNICO_INVENTARIO,
    }
)


class TipoDeVinculacion(StrEnum):
    EMPLEADO = "empleado"
    CONTRATISTA = "contratista"
    PRACTICANTE = "practicante"
    TEMPORAL = "temporal"


class TipoDeEquipo(StrEnum):
    PORTATIL = "Portátil"
    ESCRITORIO = "Escritorio"


class EstadoColaborador(StrEnum):
    POR_INGRESAR = "por_ingresar"
    ACTIVO = "activo"
    SUSPENDIDO = "suspendido"
    RETIRADO = "retirado"


class EstadoDeSoporte(StrEnum):
    PENDIENTE = "pendiente"
    SUBIDO = "subido"
    DESCARTADO = "descartado"
