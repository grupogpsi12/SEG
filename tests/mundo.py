"""Entorno de pruebas del nucleo: dobles + usuarios, colaboradores y la matriz de perfiles.

Arma todos los casos de uso sobre los dobles en memoria. Las pruebas de aplicacion y los
escenarios de extremo a extremo se escriben contra esto, sin red ni disco (CLAUDE.md).
"""

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta

from jml.aplicacion.casos._alta import DependenciasDeAlta
from jml.aplicacion.casos.bandeja import DependenciasDeBandeja, ProcesarBandeja, ReintentarEmision
from jml.aplicacion.casos.consultas import (
    BuscarCuentas,
    ConsultarDashboard,
    ConsultarFicha,
    ContratosPorVencer,
    DependenciasDeConsulta,
)
from jml.aplicacion.casos.decidir import (
    AprobarSolicitud,
    CancelarSolicitud,
    DependenciasDeDecision,
    RechazarSolicitud,
)
from jml.aplicacion.casos.emitir import EmitirPorExcepcion, EmitirSolicitud
from jml.aplicacion.casos.registrar import RegistrarSolicitud
from jml.aplicacion.casos.sincronizar import (
    DependenciasDeSincronizacion,
    SincronizarActivos,
    SincronizarTickets,
)
from jml.aplicacion.dtos import (
    ArchivoRecibido,
    ContratoPorVencer,
    FichaDeColaborador,
    FiltroDeCuentas,
    Indicadores,
    NuevaSolicitud,
    PaginaDeCuentas,
    ResultadoDeBandeja,
    ResultadoDeDecision,
    ResultadoDeSincronizacion,
    SolicitudRegistrada,
)
from jml.dominio.catalogo import (
    DatosCambioDepartamento,
    DatosCambioSucursal,
    DatosEmergencia,
    DatosIngreso,
    DatosRetiro,
    DatosVacaciones,
)
from jml.dominio.colaborador import Colaborador
from jml.dominio.permisos import UsuarioDelSistema
from jml.dominio.solicitud import Solicitud
from jml.dominio.tipos import (
    EstadoColaborador,
    Rol,
    Subtipo,
    TipoDeVinculacion,
    TipoEvento,
)
from jml.dominio.valores import CalendarioHabil, Documento, SolicitudId, Usuario
from tests.dobles.glpi import SistemaDeTicketsEnMemoria
from tests.dobles.memoria import RepositoriosEnMemoria
from tests.dobles.reloj import RelojSimulado
from tests.dobles.soportes import AlmacenDeSoportesEnMemoria
from tests.fabricas import AHORA, HOY, MATRIZ, SEDES, SENTINELA, datos_ingreso, perfil

PDF_VALIDO = b"%PDF-1.7\n" + b"contenido del acta de inicio\n" * 5
SOPORTE_VALIDO = ArchivoRecibido("acta_de_inicio.pdf", PDF_VALIDO)

# Usuarios del sistema (id de usuario -> (colaborador, roles))
USUARIOS: dict[str, tuple[str | None, frozenset[Rol]]] = {
    "u-rrhh": ("col-rrhh", frozenset({Rol.RRHH})),
    "u-admin": (None, frozenset({Rol.ADMINISTRADOR})),
    "u-col": ("col-1", frozenset({Rol.SOLICITANTE})),
    "u-jefe": ("jefe-1", frozenset({Rol.SOLICITANTE})),
    "u-otro": ("col-9", frozenset({Rol.SOLICITANTE})),
    "u-tec-ad": (None, frozenset({Rol.TECNICO_AD})),
    "u-tec-com": (None, frozenset({Rol.TECNICO_COMUNICACIONES})),
    "u-tec-lic": (None, frozenset({Rol.TECNICO_LICENCIAS})),
    "u-tec-inv": (None, frozenset({Rol.TECNICO_INVENTARIO})),
    "u-aud": (None, frozenset({Rol.AUDITOR})),
}


def _persona(id_: str, nombres: str, apellidos: str, doc: str, depto: str, usuario: str,
             jefe: str | None, sede: str = "Bogotá") -> Colaborador:  # fmt: skip
    return Colaborador(
        id=id_,
        documento=Documento(doc),
        nombres=nombres,
        apellidos=apellidos,
        vinculacion=TipoDeVinculacion.EMPLEADO,
        departamento=depto,
        cargo="Analista",
        sede=sede,
        jefe_id=jefe,
        fecha_ingreso=date(2025, 1, 15),
        fecha_fin=None,
        estado=EstadoColaborador.ACTIVO,
        usuario=Usuario(usuario),
    )


@dataclass
class Mundo:
    reloj: RelojSimulado
    repos: RepositoriosEnMemoria
    glpi: SistemaDeTicketsEnMemoria
    soportes: AlmacenDeSoportesEnMemoria
    calendario: CalendarioHabil

    # --- construccion ------------------------------------------------------------------------

    @classmethod
    def nuevo(cls, calendario: CalendarioHabil | None = None) -> "Mundo":
        reloj = RelojSimulado(AHORA)
        m = cls(
            reloj=reloj,
            repos=RepositoriosEnMemoria(reloj),
            glpi=SistemaDeTicketsEnMemoria(reloj),
            soportes=AlmacenDeSoportesEnMemoria(),
            calendario=calendario or CalendarioHabil(),
        )
        m._sembrar()
        return m

    def _sembrar(self) -> None:
        with self.repos.unidad_de_trabajo() as u:
            for depto in MATRIZ:
                for sede in SEDES:
                    u.perfiles.guardar(perfil(depto, sede))
            for c in (
                _persona("col-rrhh", "Rosa", "Herrera", "70000001", "RRHH", "rosa.herrera", None),
                _persona("jefe-1", "Jorge", "Mejía", "70000002", "Finanzas", "jorge.mejia", None),
                _persona("col-1", "María José", "Gómez Ramírez", "10203040", "Finanzas",
                         "maria.gomez", "jefe-1"),
                _persona("col-9", "Otto", "Nieto", "70000009", "Comercial", "otto.nieto", None),
            ):  # fmt: skip
                u.colaboradores.guardar(c)
            for uid, (colaborador, roles) in USUARIOS.items():
                u.usuarios.guardar(UsuarioDelSistema(uid, colaborador, roles))
        self._contador = 0

    # --- dependencias ------------------------------------------------------------------------

    def _nuevo_id(self) -> str:
        self._contador += 1
        return f"col-n{self._contador}"

    @property
    def _alta(self) -> DependenciasDeAlta:
        return DependenciasDeAlta(
            self.repos, self.soportes, self.reloj, self.calendario, self._nuevo_id
        )

    @property
    def _decision(self) -> DependenciasDeDecision:
        return DependenciasDeDecision(self.repos, self.reloj, self.calendario, self.soportes)

    @property
    def _bandeja(self) -> DependenciasDeBandeja:
        return DependenciasDeBandeja(self.repos, self.glpi, self.soportes, self.reloj)

    @property
    def _sync(self) -> DependenciasDeSincronizacion:
        return DependenciasDeSincronizacion(self.repos, self.glpi, self.reloj)

    @property
    def _consulta(self) -> DependenciasDeConsulta:
        return DependenciasDeConsulta(self.repos, self.reloj)

    # --- casos de uso ------------------------------------------------------------------------

    def registrar(self, e: NuevaSolicitud) -> SolicitudRegistrada:
        return RegistrarSolicitud(self._alta).ejecutar(e)

    def emitir(self, e: NuevaSolicitud) -> SolicitudRegistrada:
        return EmitirSolicitud(self._alta).ejecutar(e)

    def emitir_por_excepcion(self, e: NuevaSolicitud) -> SolicitudRegistrada:
        return EmitirPorExcepcion(self._alta).ejecutar(e)

    def aprobar(
        self, usuario: str, sid: SolicitudId, justificacion: str | None = None
    ) -> ResultadoDeDecision:
        return AprobarSolicitud(self._decision).ejecutar(usuario, sid, justificacion)

    def rechazar(
        self, usuario: str, sid: SolicitudId, justificacion: str | None
    ) -> ResultadoDeDecision:
        return RechazarSolicitud(self._decision).ejecutar(usuario, sid, justificacion)

    def cancelar(
        self, usuario: str, sid: SolicitudId, justificacion: str | None = None
    ) -> ResultadoDeDecision:
        return CancelarSolicitud(self._decision).ejecutar(usuario, sid, justificacion)

    def bandeja(self, limite: int = 50) -> ResultadoDeBandeja:
        return ProcesarBandeja(self._bandeja).ejecutar(limite)

    def reintentar(self, usuario: str, sid: SolicitudId) -> None:
        ReintentarEmision(self.repos, self.reloj).ejecutar(usuario, sid)

    def sincronizar(self) -> ResultadoDeSincronizacion:
        return SincronizarTickets(self._sync).ejecutar()

    def sincronizar_activos(self) -> ResultadoDeSincronizacion:
        return SincronizarActivos(self._sync).ejecutar()

    def contratos_por_vencer(self, usuario: str) -> tuple[ContratoPorVencer, ...]:
        return ContratosPorVencer(self._consulta).ejecutar(usuario)

    def dashboard(self, usuario: str) -> Indicadores:
        return ConsultarDashboard(self._consulta).ejecutar(usuario)

    def buscar(self, usuario: str, filtro: FiltroDeCuentas) -> PaginaDeCuentas:
        return BuscarCuentas(self._consulta).ejecutar(usuario, filtro)

    def ficha(self, usuario: str, colaborador_id: str) -> FichaDeColaborador:
        return ConsultarFicha(self._consulta).ejecutar(usuario, colaborador_id)

    # --- ayudas de lectura -------------------------------------------------------------------

    def solicitud(self, sid: SolicitudId) -> Solicitud:
        with self.repos.unidad_de_trabajo() as u:
            s = u.solicitudes.obtener(sid)
        assert s is not None
        return s

    def colaborador(self, colaborador_id: str) -> Colaborador:
        with self.repos.unidad_de_trabajo() as u:
            c = u.colaboradores.obtener(colaborador_id)
        assert c is not None
        return c

    def acciones_de_auditoria(self) -> list[str]:
        return [r.accion for r in self.repos.auditoria().registros()]

    def avanzar(self, delta: timedelta) -> None:
        self.reloj.avanzar(delta)

    def correr_bandeja_hasta_vaciar(
        self, maximo: int = 60, paso: timedelta = timedelta(minutes=1)
    ) -> None:
        """Procesa la bandeja y deja correr el reloj (para las esperas) hasta que no queda nada."""
        for _ in range(maximo):
            self.bandeja()
            pendientes = [
                e for e in self.repos.almacen.bandeja.values() if e.estado.value == "pendiente"
            ]
            if not pendientes:
                return
            self.avanzar(paso)

    def tecnico_resuelve_todo(self, sid: SolicitudId, *, con_acta: bool = True) -> None:
        """Todos los tickets creados de la solicitud: resueltos con solucion (y acta en Inventario)."""
        with self.repos.unidad_de_trabajo() as u:
            tickets = list(u.tickets.de_solicitud(sid))
        for t in tickets:
            if t.id_externo is not None:
                docs = 1 if (t.ticket.cola.value == "INVENTARIO" and con_acta) else 0
                self.glpi.resolver(t.id_externo, True, documentos=docs)


# --- constructores de solicitudes ---------------------------------------------------------------


def vacaciones(usuario: str = "u-col", colaborador: str = "col-1", dias: int = 7,
               regreso: int = 21, justificacion: str | None = None) -> NuevaSolicitud:  # fmt: skip
    fe = HOY + timedelta(days=dias)
    return NuevaSolicitud(
        usuario_id=usuario,
        tipo=TipoEvento.VAC,
        fecha_efectiva=fe,
        datos=DatosVacaciones(HOY + timedelta(days=regreso)),
        colaborador_id=colaborador,
        justificacion=justificacion,
    )


def ingreso(
    usuario: str = "u-rrhh",
    *,
    nombres: str = "Camila",
    apellidos: str = "Torres Vega",
    documento: str = "80000001",
    vinculacion: TipoDeVinculacion = TipoDeVinculacion.EMPLEADO,
    departamento: str = "Finanzas",
    sede: str = "Bogotá",
    requiere_equipo: bool = True,
    soporte: ArchivoRecibido | None = SOPORTE_VALIDO,
    dias: int = 14,
) -> NuevaSolicitud:
    fe = HOY + timedelta(days=dias)
    datos = replace(
        datos_ingreso(vinculacion, departamento, sede, requiere_equipo, documento,
                      fecha_fin=None if vinculacion is TipoDeVinculacion.EMPLEADO else fe + timedelta(days=200)),
        nombres=nombres,
        apellidos=apellidos,
    )  # fmt: skip
    assert isinstance(datos, DatosIngreso)
    return NuevaSolicitud(
        usuario_id=usuario,
        tipo=TipoEvento.ING,
        fecha_efectiva=fe,
        datos=datos,
        soporte=soporte,
        justificacion="Contratación aprobada",
    )


def retiro(usuario: str = "u-rrhh", colaborador: str = "col-1", subtipo: Subtipo = Subtipo.RENUNCIA,
           dias: int = 10, restringido: str = SENTINELA) -> NuevaSolicitud:  # fmt: skip
    return NuevaSolicitud(
        usuario_id=usuario,
        tipo=TipoEvento.RET,
        subtipo=subtipo,
        fecha_efectiva=HOY + timedelta(days=dias),
        datos=DatosRetiro(),
        colaborador_id=colaborador,
        restringido=restringido,
        justificacion="Retiro solicitado",
    )


def emergencia(usuario: str = "u-rrhh", colaborador: str = "col-1",
               subtipo: Subtipo = Subtipo.FUGA_DETECTADA, ahora: datetime = AHORA) -> NuevaSolicitud:  # fmt: skip
    return NuevaSolicitud(
        usuario_id=usuario,
        tipo=TipoEvento.EMG,
        subtipo=subtipo,
        fecha_efectiva=HOY,
        datos=DatosEmergencia("Seguridad", ahora - timedelta(hours=1)),
        colaborador_id=colaborador,
        restringido=SENTINELA,
        justificacion="Emergencia de seguridad",
    )


def cambio_de_departamento(usuario: str = "u-jefe", colaborador: str = "col-1",
                           destino: str = "TI", dias: int = 3) -> NuevaSolicitud:  # fmt: skip
    return NuevaSolicitud(
        usuario_id=usuario,
        tipo=TipoEvento.CDP,
        fecha_efectiva=HOY + timedelta(days=dias),
        datos=DatosCambioDepartamento(destino, "Desarrollador", "jefe-1"),
        colaborador_id=colaborador,
        justificacion="Reasignación",
    )


def cambio_de_sucursal(usuario: str = "u-jefe", colaborador: str = "col-1", sede: str = "Cali",
                       traslada: bool = True, dias: int = 3) -> NuevaSolicitud:  # fmt: skip
    return NuevaSolicitud(
        usuario_id=usuario,
        tipo=TipoEvento.CSU,
        fecha_efectiva=HOY + timedelta(days=dias),
        datos=DatosCambioSucursal(sede, traslada),
        colaborador_id=colaborador,
        justificacion="Traslado",
    )
