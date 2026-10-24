"""Doble en memoria de Repositorios, Auditoria y la unidad de trabajo.

La unidad de trabajo hace ROLLBACK REAL: al entrar toma una instantanea del almacen y, si el
bloque lanza, la restaura. Asi la prueba puede forzar un fallo en el ultimo paso y comprobar que
no queda rastro de los anteriores (CA-02). La restriccion de duplicado abierto aplica EXACTAMENTE
la regla de RD-01 (mismo conjunto de estados abiertos) y la del documento unico, RD-09.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from types import TracebackType
from typing import Self

from jml.aplicacion.bandeja import EntradaDeBandeja, EstadoDeEntrada
from jml.aplicacion.dtos import (
    FichaDeColaborador,
    FiltroDeCuentas,
    Indicadores,
    PaginaDeCuentas,
    ResultadoDeSincronizacion,
)
from jml.aplicacion.puertos import (
    ContenidoDeSolicitudModificado,
    DocumentoYaRegistrado,
    DuplicadoAbierto,
    Reloj,
)
from jml.dominio.activos import ActivoAsignado, LicenciaAsignada
from jml.dominio.auditoria import (
    EventoDeAuditoria,
    RegistroDeAuditoria,
    ResultadoDeVerificacion,
    encadenar,
    verificar_cadena,
)
from jml.dominio.catalogo import ColaboradorId, UsuarioId
from jml.dominio.colaborador import Colaborador
from jml.dominio.cuentas import CambioDeCuenta, Cuenta
from jml.dominio.perfiles import PerfilDeAcceso
from jml.dominio.permisos import Actor, UsuarioDelSistema
from jml.dominio.solicitud import Decision, Solicitud
from jml.dominio.soporte import Soporte
from jml.dominio.tickets import TicketSeguido
from jml.dominio.tipos import (
    ESTADOS_ABIERTOS,
    EstadoColaborador,
    EstadoSolicitud,
    Rol,
    SistemaDeCuenta,
    TipoEvento,
)
from jml.dominio.valores import Documento, SolicitudId
from tests.dobles import consultas


class FalloInyectado(Exception):
    """Fallo de infraestructura simulado para probar el rollback."""


@dataclass
class Almacen:
    solicitudes: dict[str, Solicitud] = field(default_factory=dict)
    consecutivos: dict[int, int] = field(default_factory=dict)
    colaboradores: dict[str, Colaborador] = field(default_factory=dict)
    usuarios: dict[str, UsuarioDelSistema] = field(default_factory=dict)
    perfiles: dict[tuple[str, str], PerfilDeAcceso] = field(default_factory=dict)
    tickets: dict[str, TicketSeguido] = field(default_factory=dict)
    cuentas: dict[tuple[str, SistemaDeCuenta], Cuenta] = field(default_factory=dict)
    historial: list[CambioDeCuenta] = field(default_factory=list)
    decisiones: list[Decision] = field(default_factory=list)
    soportes: dict[str, Soporte] = field(default_factory=dict)
    bandeja: dict[str, EntradaDeBandeja] = field(default_factory=dict)
    activos: dict[str, tuple[ActivoAsignado, ...]] = field(default_factory=dict)
    licencias: dict[str, tuple[LicenciaAsignada, ...]] = field(default_factory=dict)
    sincronizaciones: list[ResultadoDeSincronizacion] = field(default_factory=list)
    auditoria: list[RegistroDeAuditoria] = field(default_factory=list)

    def instantanea(self) -> "Almacen":
        # Todos los valores son inmutables: basta copiar los contenedores.
        return Almacen(
            dict(self.solicitudes), dict(self.consecutivos), dict(self.colaboradores),
            dict(self.usuarios), dict(self.perfiles), dict(self.tickets), dict(self.cuentas),
            list(self.historial), list(self.decisiones), dict(self.soportes), dict(self.bandeja),
            dict(self.activos), dict(self.licencias), list(self.sincronizaciones),
            list(self.auditoria),
        )  # fmt: skip

    def restaurar(self, otra: "Almacen") -> None:
        for nombre in self.__dataclass_fields__:
            setattr(self, nombre, getattr(otra, nombre))


# --- repositorios -----------------------------------------------------------------------------


class _RepoSolicitudes:
    def __init__(self, a: Almacen) -> None:
        self.a = a

    def siguiente_id(self, anio: int) -> SolicitudId:
        n = self.a.consecutivos.get(anio, 0) + 1
        self.a.consecutivos[anio] = n
        return SolicitudId.de(anio, n)

    def guardar(self, solicitud: Solicitud) -> None:
        previa = self.a.solicitudes.get(solicitud.id.valor)
        if (
            previa is not None
            and previa.estado is not EstadoSolicitud.PENDIENTE_APROBACION
            and previa.contenido() != solicitud.contenido()  # RF-14: el disparador de la BD
        ):
            raise ContenidoDeSolicitudModificado(solicitud.id)
        if solicitud.estado in ESTADOS_ABIERTOS:  # RD-01: indice unico parcial
            for otra in self.a.solicitudes.values():
                if (
                    otra.id != solicitud.id
                    and otra.colaborador_id == solicitud.colaborador_id
                    and otra.tipo is solicitud.tipo
                    and otra.estado in ESTADOS_ABIERTOS
                ):
                    raise DuplicadoAbierto(otra.id)
        self.a.solicitudes[solicitud.id.valor] = solicitud

    def obtener(self, solicitud_id: SolicitudId) -> Solicitud | None:
        return self.a.solicitudes.get(solicitud_id.valor)

    def abiertas_de(self, colaborador_id: ColaboradorId) -> Sequence[Solicitud]:
        return sorted(
            (
                s
                for s in self.a.solicitudes.values()
                if s.colaborador_id == colaborador_id and s.estado in ESTADOS_ABIERTOS
            ),
            key=lambda s: s.id.valor,
        )

    def de_colaborador(self, colaborador_id: ColaboradorId) -> Sequence[Solicitud]:
        return sorted(
            (s for s in self.a.solicitudes.values() if s.colaborador_id == colaborador_id),
            key=lambda s: s.id.valor,
        )

    def abierta_de_tipo(self, colaborador_id: ColaboradorId, tipo: TipoEvento) -> Solicitud | None:
        return next((s for s in self.abiertas_de(colaborador_id) if s.tipo is tipo), None)

    def del_solicitante(
        self, usuario_id: UsuarioId, desde: int = 0, hasta: int | None = None
    ) -> Sequence[Solicitud]:
        return sorted(
            (s for s in self.a.solicitudes.values() if s.solicitante_id == usuario_id),
            key=lambda s: s.id.valor,
        )[desde:hasta]

    def contar_del_solicitante(self, usuario_id: UsuarioId) -> int:
        return len(self.del_solicitante(usuario_id))

    def pendientes_de_aprobacion(self) -> Sequence[Solicitud]:
        pendientes = (
            s
            for s in self.a.solicitudes.values()
            if s.estado is EstadoSolicitud.PENDIENTE_APROBACION
        )
        return sorted(pendientes, key=lambda s: s.id.valor)

    def en_error(self) -> Sequence[Solicitud]:
        en_error = (s for s in self.a.solicitudes.values() if s.estado is EstadoSolicitud.ERROR)
        return sorted(en_error, key=lambda s: s.id.valor)


class _RepoColaboradores:
    def __init__(self, a: Almacen) -> None:
        self.a = a

    def guardar(self, colaborador: Colaborador) -> None:
        if colaborador.estado is not EstadoColaborador.RETIRADO:  # RD-09: unico entre no retirados
            for otro in self.a.colaboradores.values():
                if (
                    otro.id != colaborador.id
                    and otro.documento == colaborador.documento
                    and otro.estado is not EstadoColaborador.RETIRADO
                ):
                    raise DocumentoYaRegistrado(otro.id)
        self.a.colaboradores[colaborador.id] = colaborador

    def obtener(self, colaborador_id: ColaboradorId) -> Colaborador | None:
        return self.a.colaboradores.get(colaborador_id)

    def por_documento(self, documento: Documento) -> Colaborador | None:
        return next(
            (
                c
                for c in self.a.colaboradores.values()
                if c.documento == documento and c.estado is not EstadoColaborador.RETIRADO
            ),
            None,
        )

    def usuarios_en_uso(self) -> frozenset[str]:
        return frozenset(c.usuario.valor for c in self.a.colaboradores.values() if c.usuario)

    def con_usuario_glpi(self) -> Sequence[Colaborador]:
        return sorted(
            (c for c in self.a.colaboradores.values() if c.id_usuario_glpi), key=lambda c: c.id
        )

    def subordinados_de(self, jefe_id: ColaboradorId) -> Sequence[Colaborador]:
        return sorted(
            (
                c
                for c in self.a.colaboradores.values()
                if c.jefe_id == jefe_id and c.estado is not EstadoColaborador.RETIRADO
            ),
            key=lambda c: c.id,
        )

    def con_fin_de_contrato(self) -> Sequence[Colaborador]:
        return sorted(
            (c for c in self.a.colaboradores.values() if c.fecha_fin is not None),
            key=lambda c: c.id,
        )


class _RepoUsuarios:
    def __init__(self, a: Almacen) -> None:
        self.a = a

    def guardar(self, usuario: UsuarioDelSistema) -> None:
        self.a.usuarios[usuario.id] = usuario

    def todos(self) -> Sequence[UsuarioDelSistema]:
        return sorted(self.a.usuarios.values(), key=lambda u: u.id)

    def actor_de(self, usuario_id: UsuarioId) -> Actor | None:
        u = self.a.usuarios.get(usuario_id)
        return u.como_actor() if u is not None and u.activo else None

    def roles_de_colaborador(self, colaborador_id: ColaboradorId) -> frozenset[Rol]:
        roles: set[Rol] = set()
        for u in self.a.usuarios.values():
            if u.activo and u.colaborador_id == colaborador_id:
                roles |= u.roles
        return frozenset(roles)


class _RepoPerfiles:
    def __init__(self, a: Almacen) -> None:
        self.a = a

    def guardar(self, perfil: PerfilDeAcceso) -> None:
        self.a.perfiles[(perfil.departamento, perfil.sede)] = perfil

    def obtener(self, departamento: str, sede: str) -> PerfilDeAcceso | None:
        return self.a.perfiles.get((departamento, sede))

    def todos(self) -> Sequence[PerfilDeAcceso]:
        return [self.a.perfiles[k] for k in sorted(self.a.perfiles)]


class _RepoTickets:
    def __init__(self, a: Almacen) -> None:
        self.a = a

    def guardar(self, seguido: TicketSeguido) -> None:
        self.a.tickets[seguido.ticket.clave_de_idempotencia] = seguido

    def por_clave(self, clave: str) -> TicketSeguido | None:
        return self.a.tickets.get(clave)

    def de_solicitud(self, solicitud_id: SolicitudId) -> Sequence[TicketSeguido]:
        return sorted(
            (t for t in self.a.tickets.values() if t.ticket.solicitud_id == solicitud_id.valor),
            key=lambda t: t.ticket.clave_de_idempotencia,
        )

    def creados(self) -> Sequence[TicketSeguido]:
        return sorted(
            (t for t in self.a.tickets.values() if t.id_externo is not None),
            key=lambda t: t.ticket.clave_de_idempotencia,
        )


class _RepoCuentas:
    def __init__(self, a: Almacen) -> None:
        self.a = a

    def obtener(self, colaborador_id: ColaboradorId, sistema: SistemaDeCuenta) -> Cuenta | None:
        return self.a.cuentas.get((colaborador_id, sistema))

    def guardar(self, cuenta: Cuenta) -> None:
        self.a.cuentas[(cuenta.colaborador_id, cuenta.sistema)] = cuenta

    def agregar_historial(self, cambio: CambioDeCuenta) -> None:
        self.a.historial.append(cambio)

    def historial(self, colaborador_id: ColaboradorId) -> Sequence[CambioDeCuenta]:
        return [c for c in self.a.historial if c.colaborador_id == colaborador_id]


class _RepoDecisiones:
    def __init__(self, a: Almacen) -> None:
        self.a = a

    def agregar(self, decision: Decision) -> None:
        self.a.decisiones.append(decision)

    def de_solicitud(self, solicitud_id: SolicitudId) -> Sequence[Decision]:
        return [d for d in self.a.decisiones if d.solicitud_id == solicitud_id]


class _RepoSoportes:
    def __init__(self, a: Almacen) -> None:
        self.a = a

    def guardar(self, soporte: Soporte) -> None:
        self.a.soportes[soporte.solicitud_id.valor] = soporte

    def obtener(self, solicitud_id: SolicitudId) -> Soporte | None:
        return self.a.soportes.get(solicitud_id.valor)


class _RepoBandeja:
    def __init__(self, a: Almacen) -> None:
        self.a = a

    def encolar(self, entradas: Sequence[EntradaDeBandeja]) -> None:
        for e in entradas:
            self.a.bandeja.setdefault(e.clave, e)  # idempotente por clave

    def guardar(self, entrada: EntradaDeBandeja) -> None:
        self.a.bandeja[entrada.clave] = entrada

    def vencidas(self, ahora: datetime, limite: int) -> Sequence[EntradaDeBandeja]:
        listas = [
            e
            for e in self.a.bandeja.values()
            if e.estado is EstadoDeEntrada.PENDIENTE and e.proximo_intento <= ahora
        ]
        listas.sort(key=lambda e: (e.proximo_intento, e.clave))
        return listas[:limite]

    def obtener(self, clave: str) -> EntradaDeBandeja | None:
        return self.a.bandeja.get(clave)

    def de_solicitud(self, solicitud_id: SolicitudId) -> Sequence[EntradaDeBandeja]:
        return sorted(
            (e for e in self.a.bandeja.values() if e.solicitud_id == solicitud_id.valor),
            key=lambda e: e.clave,
        )


class _RepoActivos:
    def __init__(self, a: Almacen) -> None:
        self.a = a

    def reemplazar(
        self,
        colaborador_id: ColaboradorId,
        activos: Sequence[ActivoAsignado],
        licencias: Sequence[LicenciaAsignada],
    ) -> None:
        self.a.activos[colaborador_id] = tuple(activos)
        self.a.licencias[colaborador_id] = tuple(licencias)

    def activos_de(self, colaborador_id: ColaboradorId) -> Sequence[ActivoAsignado]:
        return self.a.activos.get(colaborador_id, ())

    def licencias_de(self, colaborador_id: ColaboradorId) -> Sequence[LicenciaAsignada]:
        return self.a.licencias.get(colaborador_id, ())


class _RepoSincronizaciones:
    def __init__(self, a: Almacen) -> None:
        self.a = a

    def registrar(self, resultado: ResultadoDeSincronizacion) -> None:
        self.a.sincronizaciones.append(resultado)

    def ultima(self) -> ResultadoDeSincronizacion | None:
        return self.a.sincronizaciones[-1] if self.a.sincronizaciones else None


class AuditoriaEnMemoria:
    """Cadena de hashes; con `fallar_en` simula una caida al escribir el N-esimo registro."""

    def __init__(self, a: Almacen, reloj: Reloj, estado: "ControlDeFallos") -> None:
        self.a = a
        self.reloj = reloj
        self.estado = estado

    def registrar(self, actor: str, evento: EventoDeAuditoria) -> RegistroDeAuditoria:
        self.estado.llamadas_a_auditoria += 1
        if self.estado.fallar_en_auditoria == self.estado.llamadas_a_auditoria:
            raise FalloInyectado("la auditoria no pudo escribirse")
        anterior = self.a.auditoria[-1] if self.a.auditoria else None
        registro = encadenar(anterior, self.reloj.ahora(), actor, evento)
        self.a.auditoria.append(registro)
        return registro

    def registros(self) -> Sequence[RegistroDeAuditoria]:
        return tuple(self.a.auditoria)

    def total(self) -> int:
        return len(self.a.auditoria)

    def tramo(self, desde: int, hasta: int) -> Sequence[RegistroDeAuditoria]:
        return tuple(self.a.auditoria[desde:hasta])

    def verificar(self) -> ResultadoDeVerificacion:
        return verificar_cadena(self.a.auditoria)


@dataclass
class ControlDeFallos:
    fallar_en_auditoria: int | None = None  # numero de llamada (desde que se fija) que falla
    llamadas_a_auditoria: int = 0

    def fallar_en_la_llamada(self, n: int) -> None:
        self.fallar_en_auditoria = n
        self.llamadas_a_auditoria = 0

    def sin_fallos(self) -> None:
        self.fallar_en_auditoria = None


class UnidadDeTrabajoEnMemoria:
    def __init__(self, a: Almacen, reloj: Reloj, control: ControlDeFallos) -> None:
        self._a = a
        self._instantanea: Almacen | None = None
        self.solicitudes = _RepoSolicitudes(a)
        self.colaboradores = _RepoColaboradores(a)
        self.usuarios = _RepoUsuarios(a)
        self.perfiles = _RepoPerfiles(a)
        self.tickets = _RepoTickets(a)
        self.cuentas = _RepoCuentas(a)
        self.decisiones = _RepoDecisiones(a)
        self.soportes = _RepoSoportes(a)
        self.bandeja = _RepoBandeja(a)
        self.activos = _RepoActivos(a)
        self.sincronizaciones = _RepoSincronizaciones(a)
        self.auditoria = AuditoriaEnMemoria(a, reloj, control)

    def __enter__(self) -> Self:
        self._instantanea = self._a.instantanea()
        return self

    def __exit__(
        self,
        tipo: type[BaseException] | None,
        error: BaseException | None,
        traza: TracebackType | None,
    ) -> None:
        if error is not None and self._instantanea is not None:
            self._a.restaurar(self._instantanea)
        self._instantanea = None


class RepositoriosEnMemoria:
    def __init__(self, reloj: Reloj) -> None:
        self.reloj = reloj
        self.almacen = Almacen()
        self.control = ControlDeFallos()

    def unidad_de_trabajo(self) -> UnidadDeTrabajoEnMemoria:
        return UnidadDeTrabajoEnMemoria(self.almacen, self.reloj, self.control)

    # --- consultas de lectura: el ORACULO de la consulta SQL (CA-15) ---
    def indicadores(self, ahora: datetime) -> Indicadores:
        return consultas.indicadores(self.almacen, ahora)

    def buscar_cuentas(self, filtro: FiltroDeCuentas) -> PaginaDeCuentas:
        return consultas.buscar_cuentas(self.almacen, filtro)

    def ficha(self, colaborador_id: ColaboradorId) -> FichaDeColaborador | None:
        return consultas.ficha(self.almacen, colaborador_id)

    # --- lectura directa para las pruebas ---
    def auditoria(self) -> AuditoriaEnMemoria:
        return AuditoriaEnMemoria(self.almacen, self.reloj, self.control)
