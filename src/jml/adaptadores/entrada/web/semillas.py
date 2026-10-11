"""Datos de semilla ficticios (RD-07): la matriz de perfiles del SRS 4.9 y 30 colaboradores.

Idempotente: solo escribe (y audita) lo que cambio. No crea cuentas: el estado de una cuenta
solo lo deriva la sincronizacion de tickets (invariante 6, RD-11). Tampoco crea usuarios, que
nacen en Supabase Auth con el comando `admin-usuarios` (RF-06).
"""

from dataclasses import dataclass
from datetime import date, timedelta

from jml.aplicacion.puertos import Repositorios
from jml.dominio.auditoria import EventoDeAuditoria
from jml.dominio.colaborador import Colaborador
from jml.dominio.perfiles import PerfilDeAcceso, RecursoCompartido
from jml.dominio.tipos import EstadoColaborador, PerfilDeRecurso, TipoDeEquipo, TipoDeVinculacion
from jml.dominio.usuarios import usuario_sugerido
from jml.dominio.valores import Documento

ACTOR = "sistema:semillas"
SEDES = ("Bogotá", "Medellín", "Cali")
_FS = "\\\\fs01.ad.andina.test\\"
_E, _C = PerfilDeRecurso.EDICION, PerfilDeRecurso.CONSULTA


def _r(ruta: str, serie: str, perfil: PerfilDeRecurso, grupo: str) -> RecursoCompartido:
    return RecursoCompartido(_FS + ruta, serie, perfil, grupo)


_COMUN_RO = _r("comun", "Común", _C, "FS-Comun-RO")

# departamento: (AD, red, M365, licencias, equipo, recursos)  -- SRS 4.9, datos ficticios
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
        (_COMUN_RO, _r("departamentos\\Gerencia", "Gerencia", _E, "FS-Gerencia-RW")),
    ),
    "RRHH": (
        ("GG-RRHH", "FS-RRHH-RW", "FS-Comun-RO"),
        ("NET-WIFI-CORP",),
        ("M365-RRHH",),
        ("Suite ofimática",),
        TipoDeEquipo.PORTATIL,
        (
            _COMUN_RO,
            _r("departamentos\\RRHH\\Hojas de vida", "Historias laborales", _E, "FS-RRHH-RW"),
        ),
    ),
    "Finanzas": (
        ("GG-Finanzas", "FS-Finanzas-RW", "FS-Presupuesto-RO", "FS-Comun-RO"),
        ("NET-WIFI-CORP",),
        ("M365-Finanzas",),
        ("Suite ofimática", "Software contable"),
        TipoDeEquipo.ESCRITORIO,
        (
            _COMUN_RO,
            _r("departamentos\\Finanzas\\Contabilidad", "Contabilidad", _E, "FS-Finanzas-RW"),
            _r("departamentos\\Gerencia\\Presupuesto", "Presupuesto", _C, "FS-Presupuesto-RO"),
        ),
    ),
    "Comercial": (
        ("GG-Comercial", "FS-Comercial-RW", "FS-Comun-RO"),
        ("NET-VPN", "NET-WIFI-CORP"),
        ("M365-Comercial",),
        ("Suite ofimática", "CRM"),
        TipoDeEquipo.PORTATIL,
        (_COMUN_RO, _r("departamentos\\Comercial", "Comercial", _E, "FS-Comercial-RW")),
    ),
    "TI": (
        ("GG-TI", "FS-TI-RW", "FS-Comun-RW"),
        ("NET-VPN", "NET-WIFI-CORP", "NET-ADMIN"),
        ("M365-TI",),
        ("Suite ofimática", "Herramientas de soporte"),
        TipoDeEquipo.PORTATIL,
        (
            _r("comun", "Común", _E, "FS-Comun-RW"),
            _r("departamentos\\TI", "TI", _E, "FS-TI-RW"),
        ),
    ),
    "Operaciones": (
        ("GG-Operaciones", "FS-Operaciones-RW", "FS-Comun-RO"),
        ("NET-WIFI-CORP",),
        ("M365-Operaciones",),
        ("Suite ofimática",),
        TipoDeEquipo.ESCRITORIO,
        (_COMUN_RO, _r("departamentos\\Operaciones", "Operaciones", _E, "FS-Operaciones-RW")),
    ),
}

_NOMBRES = (
    "Ana", "Bruno", "Carla", "Diego", "Elena", "Felipe", "Gloria", "Hugo", "Inés", "Julián",
    "Karen", "Luis", "María", "Nicolás", "Olga", "Pablo", "Quintina", "Rosa", "Sergio", "Tatiana",
    "Uriel", "Valeria", "Wilson", "Ximena", "Yolanda", "Zacarías", "Andrés", "Beatriz", "Camilo",
    "Daniela",
)  # fmt: skip
_APELLIDOS = (
    "Gómez Ríos", "Pérez Lara", "Muñoz Vega", "Rodríguez Paz", "Martínez Sol", "López Cruz",
    "García Luna", "Hernández Mar", "Díaz Mora", "Torres Gil",
)  # fmt: skip


def perfiles() -> list[PerfilDeAcceso]:
    return [
        PerfilDeAcceso.para(depto, sede, ad, red, m365, lic, equipo, recursos)
        for depto, (ad, red, m365, lic, equipo, recursos) in MATRIZ.items()
        for sede in SEDES
    ]


def colaboradores() -> list[Colaborador]:
    """30 colaboradores: 5 por departamento; el primero de cada uno es el jefe de los demas.

    Los dos ultimos de cada departamento son contratistas con fecha de fin escalonada, para que
    la bandeja de contratos por vencer (RF-28) tenga datos.
    """
    resultado: list[Colaborador] = []
    usados: set[str] = set()
    for d, depto in enumerate(MATRIZ):
        jefe = f"col-{d * 5 + 1:03d}"
        for k in range(5):
            n = d * 5 + k
            nombres, apellidos = _NOMBRES[n], _APELLIDOS[n % len(_APELLIDOS)]
            usuario = usuario_sugerido(nombres, apellidos, usados)
            usados.add(usuario.valor)
            contratista = k >= 3
            resultado.append(
                Colaborador(
                    id=f"col-{n + 1:03d}",
                    documento=Documento(f"{10_000_000 + n + 1}"),
                    nombres=nombres,
                    apellidos=apellidos,
                    vinculacion=TipoDeVinculacion.CONTRATISTA
                    if contratista
                    else TipoDeVinculacion.EMPLEADO,
                    departamento=depto,
                    cargo="Jefe" if k == 0 else "Analista",
                    sede=SEDES[n % len(SEDES)],
                    jefe_id=None if k == 0 else jefe,
                    fecha_ingreso=date(2024, 1 + n % 12, 1),
                    fecha_fin=date(2026, 10, 14) + timedelta(days=n) if contratista else None,
                    estado=EstadoColaborador.ACTIVO,
                    usuario=usuario,
                )
            )
    return resultado


@dataclass(frozen=True, slots=True)
class ResumenDeSemillas:
    perfiles: int
    colaboradores: int


def aplicar(repos: Repositorios) -> ResumenDeSemillas:
    """Escribe lo que falte o haya cambiado, con su evento de auditoria (RF-35)."""
    cambios_perfil = cambios_colaborador = 0
    with repos.unidad_de_trabajo() as u:
        for p in perfiles():
            if u.perfiles.obtener(p.departamento, p.sede) != p:
                u.perfiles.guardar(p)
                u.auditoria.registrar(
                    ACTOR,
                    EventoDeAuditoria("perfil.actualizado", f"{p.departamento}/{p.sede}", {}),
                )
                cambios_perfil += 1
        for c in colaboradores():
            if u.colaboradores.obtener(c.id) != c:
                u.colaboradores.guardar(c)
                u.auditoria.registrar(ACTOR, EventoDeAuditoria("colaborador.semilla", c.id, {}))
                cambios_colaborador += 1
    return ResumenDeSemillas(cambios_perfil, cambios_colaborador)
