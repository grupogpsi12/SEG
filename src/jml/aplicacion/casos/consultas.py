"""Consultas de lectura: contratos por vencer, dashboard, busqueda y ficha (RF-28 a RF-33).

El dashboard y la ficha son solo para roles tecnicos (RF-29, T10); cada consulta de ficha se
audita (RF-35). Ningun resultado puede llevar campos restringidos: los DTOs no los tienen.
"""

from dataclasses import dataclass, replace
from datetime import timedelta

from jml.aplicacion.dtos import (
    TAMANO_MAXIMO_DE_PAGINA,
    ContratoPorVencer,
    FichaDeColaborador,
    FilaDeColaborador,
    FiltroDeCuentas,
    Indicadores,
    PaginaDeCuentas,
)
from jml.aplicacion.puertos import Reloj, Repositorios
from jml.dominio.auditoria import EventoDeAuditoria
from jml.dominio.errores import NoAutorizado, NoEncontrado
from jml.dominio.permisos import Actor, puede_ver_dashboard
from jml.dominio.tipos import Cola, EstadoColaborador, Rol, TipoEvento
from jml.dominio.valores import hoy_en_bogota

DIAS_DE_AVISO = 7  # RF-28

# RF-31: cada tecnico ve por defecto su cola resaltada.
COLA_DE_ROL: dict[Rol, Cola] = {
    Rol.TECNICO_AD: Cola.AD,
    Rol.TECNICO_COMUNICACIONES: Cola.COMUNICACIONES,
    Rol.TECNICO_LICENCIAS: Cola.LICENCIAS,
    Rol.TECNICO_INVENTARIO: Cola.INVENTARIO,
}


@dataclass(frozen=True, slots=True)
class DependenciasDeConsulta:
    repos: Repositorios
    reloj: Reloj


def _actor(dep: DependenciasDeConsulta, usuario_id: str) -> Actor:
    with dep.repos.unidad_de_trabajo() as uow:
        actor = uow.usuarios.actor_de(usuario_id)
    if actor is None:
        raise NoAutorizado("consultar", "el usuario no existe o esta inactivo")
    return actor


def _exigir_tecnico(actor: Actor, accion: str) -> None:
    if not puede_ver_dashboard(actor.roles):
        raise NoAutorizado(accion, "solo los roles tecnicos consultan esta informacion")


class ContratosPorVencer:
    """RF-28: colaboradores cuyo contrato vence en 7 dias y aun no tienen un retiro abierto."""

    def __init__(self, dependencias: DependenciasDeConsulta) -> None:
        self._dep = dependencias

    def ejecutar(self, usuario_id: str) -> tuple[ContratoPorVencer, ...]:
        actor = _actor(self._dep, usuario_id)
        if Rol.RRHH not in actor.roles:
            raise NoAutorizado("contratos_por_vencer", "solo RRHH ve los contratos por vencer")
        hoy = hoy_en_bogota(self._dep.reloj.ahora())
        limite = hoy + timedelta(days=DIAS_DE_AVISO)
        filas: list[ContratoPorVencer] = []
        with self._dep.repos.unidad_de_trabajo() as uow:
            for c in uow.colaboradores.con_fin_de_contrato():
                if c.fecha_fin is None or not hoy <= c.fecha_fin <= limite:
                    continue
                if c.estado not in (EstadoColaborador.ACTIVO, EstadoColaborador.SUSPENDIDO):
                    continue
                if uow.solicitudes.abierta_de_tipo(c.id, TipoEvento.RET) is not None:
                    continue
                filas.append(
                    ContratoPorVencer(
                        c.id, c.nombre_completo, c.fecha_fin, (c.fecha_fin - hoy).days
                    )
                )
        return tuple(sorted(filas, key=lambda f: (f.fecha_fin, f.colaborador_id)))


class ConsultarDashboard:
    def __init__(self, dependencias: DependenciasDeConsulta) -> None:
        self._dep = dependencias

    def ejecutar(self, usuario_id: str) -> Indicadores:
        actor = _actor(self._dep, usuario_id)
        _exigir_tecnico(actor, "dashboard")
        indicadores = self._dep.repos.indicadores(self._dep.reloj.ahora())
        propia = next((COLA_DE_ROL[r] for r in COLA_DE_ROL if r in actor.roles), None)
        return replace(indicadores, cola_resaltada=propia)


class BuscarCuentas:
    def __init__(self, dependencias: DependenciasDeConsulta) -> None:
        self._dep = dependencias

    def ejecutar(self, usuario_id: str, filtro: FiltroDeCuentas) -> PaginaDeCuentas:
        actor = _actor(self._dep, usuario_id)
        _exigir_tecnico(actor, "buscar_cuentas")
        return self._dep.repos.buscar_cuentas(filtro)


class ConsultarFicha:
    def __init__(self, dependencias: DependenciasDeConsulta) -> None:
        self._dep = dependencias

    def ejecutar(self, usuario_id: str, colaborador_id: str) -> FichaDeColaborador:
        actor = _actor(self._dep, usuario_id)
        _exigir_tecnico(actor, "ficha")
        ficha = self._dep.repos.ficha(colaborador_id)
        if ficha is None:
            raise NoEncontrado("colaborador", colaborador_id)
        with self._dep.repos.unidad_de_trabajo() as uow:  # RF-35, T10: toda consulta queda auditada
            uow.auditoria.registrar(
                actor.usuario_id, EventoDeAuditoria("ficha.consultada", colaborador_id, {})
            )
        return ficha


MAXIMO_EXPORTADO = 5000  # tope de RF-34: 300 colaboradores esperados (RNF-06), con holgura


class ExportarCuentas:
    """RF-34: todas las filas de una busqueda, para el CSV. Es una consulta masiva (T10): se
    audita con el filtro usado y la cantidad exportada."""

    def __init__(self, dependencias: DependenciasDeConsulta) -> None:
        self._dep = dependencias

    def ejecutar(self, usuario_id: str, filtro: FiltroDeCuentas) -> tuple[FilaDeColaborador, ...]:
        actor = _actor(self._dep, usuario_id)
        _exigir_tecnico(actor, "exportar_cuentas")
        filas: list[FilaDeColaborador] = []
        pagina = 1
        while len(filas) < MAXIMO_EXPORTADO:
            p = self._dep.repos.buscar_cuentas(
                replace(filtro, pagina=pagina, tamano=TAMANO_MAXIMO_DE_PAGINA)
            )
            filas.extend(p.filas)
            if pagina * p.tamano >= p.total:
                break
            pagina += 1
        filas = filas[:MAXIMO_EXPORTADO]
        usado = {
            k: str(v)
            for k, v in (
                ("nombre", filtro.nombre),
                ("documento", filtro.documento),
                ("usuario", filtro.usuario),
                ("departamento", filtro.departamento),
                ("sede", filtro.sede),
                ("sistema", filtro.sistema),
                ("estado_de_cuenta", filtro.estado_de_cuenta),
            )
            if v is not None
        }
        with self._dep.repos.unidad_de_trabajo() as uow:
            uow.auditoria.registrar(
                actor.usuario_id,
                EventoDeAuditoria("cuentas.exportadas", "busqueda", {**usado, "filas": len(filas)}),
            )
        return tuple(filas)
