"""Datos de prueba ficticios: la matriz de perfiles del SRS 4.9 y constructores de uso comun."""

from datetime import UTC, date, datetime

from jml.dominio.catalogo import DatosIngreso
from jml.dominio.colaborador import Colaborador
from jml.dominio.perfiles import PerfilDeAcceso, RecursoCompartido
from jml.dominio.tipos import PerfilDeRecurso, TipoDeEquipo, TipoDeVinculacion
from jml.dominio.valores import Documento, Usuario

AHORA = datetime(2026, 10, 12, 15, 0, tzinfo=UTC)  # lunes 12-oct-2026, 10:00 en Bogota
HOY = date(2026, 10, 12)

COMUN_RO = RecursoCompartido(
    r"\\fs01.ad.andina.test\comun", "Común", PerfilDeRecurso.CONSULTA, "FS-Comun-RO"
)
COMUN_RW = RecursoCompartido(
    r"\\fs01.ad.andina.test\comun", "Común", PerfilDeRecurso.EDICION, "FS-Comun-RW"
)


def _rec(ruta: str, serie: str, perfil: PerfilDeRecurso, grupo: str) -> RecursoCompartido:
    return RecursoCompartido(rf"\\fs01.ad.andina.test\{ruta}", serie, perfil, grupo)


E, C = PerfilDeRecurso.EDICION, PerfilDeRecurso.CONSULTA

# departamento -> (grupos AD, grupos red, grupos M365, licencias, equipo, recursos)  [SRS 4.9]
MATRIZ: dict[
    str,
    tuple[
        tuple[str, ...],
        tuple[str, ...],
        tuple[str, ...],
        tuple[str, ...],
        TipoDeEquipo,
        tuple[RecursoCompartido, ...],
    ],
] = {
    "Gerencia": (
        ("GG-Gerencia", "FS-Gerencia-RW", "FS-Comun-RO"),
        ("NET-VPN", "NET-WIFI-CORP"),
        ("M365-Gerencia",),
        ("Suite ofimática", "Lector PDF"),
        TipoDeEquipo.PORTATIL,
        (COMUN_RO, _rec(r"departamentos\Gerencia", "Gerencia", E, "FS-Gerencia-RW")),
    ),
    "RRHH": (
        ("GG-RRHH", "FS-RRHH-RW", "FS-Comun-RO"),
        ("NET-WIFI-CORP",),
        ("M365-RRHH",),
        ("Suite ofimática",),
        TipoDeEquipo.PORTATIL,
        (
            COMUN_RO,
            _rec(r"departamentos\RRHH\Hojas de vida", "Historias laborales", E, "FS-RRHH-RW"),
        ),
    ),
    "Finanzas": (
        ("GG-Finanzas", "FS-Finanzas-RW", "FS-Presupuesto-RO", "FS-Comun-RO"),
        ("NET-WIFI-CORP",),
        ("M365-Finanzas",),
        ("Suite ofimática", "Software contable"),
        TipoDeEquipo.ESCRITORIO,
        (
            COMUN_RO,
            _rec(r"departamentos\Finanzas\Contabilidad", "Contabilidad", E, "FS-Finanzas-RW"),
            _rec(r"departamentos\Gerencia\Presupuesto", "Presupuesto", C, "FS-Presupuesto-RO"),
        ),
    ),
    "Comercial": (
        ("GG-Comercial", "FS-Comercial-RW", "FS-Comun-RO"),
        ("NET-VPN", "NET-WIFI-CORP"),
        ("M365-Comercial",),
        ("Suite ofimática", "CRM"),
        TipoDeEquipo.PORTATIL,
        (COMUN_RO, _rec(r"departamentos\Comercial", "Comercial", E, "FS-Comercial-RW")),
    ),
    "TI": (
        ("GG-TI", "FS-TI-RW", "FS-Comun-RW"),
        ("NET-VPN", "NET-WIFI-CORP", "NET-ADMIN"),
        ("M365-TI",),
        ("Suite ofimática", "Herramientas de soporte"),
        TipoDeEquipo.PORTATIL,
        (COMUN_RW, _rec(r"departamentos\TI", "TI", E, "FS-TI-RW")),
    ),
    "Operaciones": (
        ("GG-Operaciones", "FS-Operaciones-RW", "FS-Comun-RO"),
        ("NET-WIFI-CORP",),
        ("M365-Operaciones",),
        ("Suite ofimática",),
        TipoDeEquipo.ESCRITORIO,
        (COMUN_RO, _rec(r"departamentos\Operaciones", "Operaciones", E, "FS-Operaciones-RW")),
    ),
}

SEDES = ("Bogotá", "Medellín", "Cali")


def perfil(departamento: str, sede: str = "Bogotá") -> PerfilDeAcceso:
    ad, red, m365, licencias, equipo, recursos = MATRIZ[departamento]
    return PerfilDeAcceso.para(departamento, sede, ad, red, m365, licencias, equipo, recursos)


def datos_ingreso(
    vinculacion: TipoDeVinculacion = TipoDeVinculacion.EMPLEADO,
    departamento: str = "Finanzas",
    sede: str = "Bogotá",
    requiere_equipo: bool = True,
    documento: str = "10203040",
    fecha_fin: date | None = None,
) -> DatosIngreso:
    if vinculacion is not TipoDeVinculacion.EMPLEADO and fecha_fin is None:
        fecha_fin = date(2027, 6, 30)
    return DatosIngreso(
        nombres="María José",
        apellidos="Gómez Ramírez",
        documento=Documento(documento),
        vinculacion=vinculacion,
        departamento=departamento,
        cargo="Analista",
        sede=sede,
        jefe_id="jefe-1",
        fecha_fin=fecha_fin,
        requiere_equipo=requiere_equipo,
        tipo_equipo=perfil(departamento, sede).tipo_equipo if requiere_equipo else None,
    )


def colaborador(
    id: str = "col-1",
    departamento: str = "Finanzas",
    sede: str = "Bogotá",
    jefe_id: str | None = "jefe-1",
    usuario: str = "maria.gomez",
) -> Colaborador:
    from jml.dominio.tipos import EstadoColaborador

    return Colaborador(
        id=id,
        documento=Documento("10203040"),
        nombres="María José",
        apellidos="Gómez Ramírez",
        vinculacion=TipoDeVinculacion.EMPLEADO,
        departamento=departamento,
        cargo="Analista",
        sede=sede,
        jefe_id=jefe_id,
        fecha_ingreso=date(2025, 1, 15),
        fecha_fin=None,
        estado=EstadoColaborador.ACTIVO,
        usuario=Usuario(usuario),
    )


# --- escenarios de solicitudes aprobadas, listas para generar tickets ---------------------------

from dataclasses import dataclass, replace  # noqa: E402
from datetime import timedelta  # noqa: E402

from jml.dominio.catalogo import (  # noqa: E402
    DatosCambioDepartamento,
    DatosCambioSucursal,
    DatosEmergencia,
    DatosRetiro,
    DatosVacaciones,
)
from jml.dominio.permisos import Actor  # noqa: E402
from jml.dominio.solicitud import Solicitud  # noqa: E402
from jml.dominio.tipos import EstadoColaborador, Rol, Subtipo, TipoEvento  # noqa: E402
from jml.dominio.valores import CampoRestringido, SolicitudId  # noqa: E402

RRHH_ACTOR = Actor("u-rrhh", "col-rrhh", frozenset({Rol.RRHH}))
SENTINELA = "SENTINELA-RESTRINGIDA-9f3a"


@dataclass(frozen=True)
class Caso:
    solicitud: Solicitud
    colaborador: Colaborador
    actual: PerfilDeAcceso | None
    nuevo: PerfilDeAcceso | None


def caso(
    tipo: TipoEvento,
    subtipo: Subtipo | None = None,
    *,
    departamento: str = "Finanzas",
    sede: str = "Bogotá",
    destino: str = "TI",
    sede_destino: str = "Cali",
    vinculacion: TipoDeVinculacion = TipoDeVinculacion.EMPLEADO,
    requiere_equipo: bool = True,
    traslada_equipo: bool = False,
    dias: int = 7,
    numero: int = 1,
) -> Caso:
    """Construye por las reglas reales (emitir_directo) una solicitud aprobada del tipo pedido."""
    fe = HOY + timedelta(days=dias)
    sid = SolicitudId.de(2026, numero)
    c = colaborador(departamento=departamento, sede=sede)
    actual: PerfilDeAcceso | None = perfil(departamento, sede)
    nuevo: PerfilDeAcceso | None = None
    restringido: CampoRestringido | None = None
    if tipo is TipoEvento.ING:
        fin = None if vinculacion is TipoDeVinculacion.EMPLEADO else fe + timedelta(days=200)
        di = datos_ingreso(vinculacion, departamento, sede, requiere_equipo, fecha_fin=fin)
        c = Colaborador.por_ingresar("col-1", di, fe, Usuario("maria.gomez"))
        datos: object = di
        actual, nuevo = None, perfil(departamento, sede)
    elif tipo is TipoEvento.VAC:
        datos = DatosVacaciones(fe + timedelta(days=14))
    elif tipo is TipoEvento.CDP:
        datos = DatosCambioDepartamento(destino, "Nuevo cargo", "jefe-2")
        nuevo = perfil(destino, sede)
    elif tipo is TipoEvento.CSU:
        datos = DatosCambioSucursal(sede_destino, traslada_equipo)
        nuevo = perfil(departamento, sede_destino)
    elif tipo is TipoEvento.RET:
        datos, restringido = DatosRetiro(), CampoRestringido(SENTINELA)
    else:
        fe = HOY
        datos = DatosEmergencia("Seguridad", AHORA - timedelta(hours=2))
        restringido = CampoRestringido(SENTINELA)
    sujeto = c if tipo is TipoEvento.ING else replace(c, estado=EstadoColaborador.ACTIVO)
    r = Solicitud.emitir_directo(
        id=sid,
        actor=RRHH_ACTOR,
        sujeto=sujeto,
        tipo=tipo,
        subtipo=subtipo,
        fecha_efectiva=fe,
        datos=datos,  # type: ignore[arg-type]  # `datos` se arma segun el tipo
        restringido=restringido,
        justificacion="prueba",
        ahora=AHORA,
    )
    return Caso(r.solicitud, c, actual, nuevo)
