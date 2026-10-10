"""Colaborador y su estado (SRS 5.1). La aplicacion es la fuente de la verdad (S-06, S-07)."""

from dataclasses import dataclass, replace
from datetime import date

from jml.dominio.catalogo import ColaboradorId, DatosIngreso
from jml.dominio.errores import DatoInvalido, OperacionNoPermitida
from jml.dominio.tipos import EstadoColaborador, TipoDeVinculacion
from jml.dominio.valores import Documento, Usuario, texto_no_vacio

_E = EstadoColaborador
TRANSICIONES_DE_COLABORADOR: dict[EstadoColaborador, frozenset[EstadoColaborador]] = {
    _E.POR_INGRESAR: frozenset({_E.ACTIVO, _E.RETIRADO}),
    _E.ACTIVO: frozenset({_E.SUSPENDIDO, _E.RETIRADO}),
    _E.SUSPENDIDO: frozenset({_E.ACTIVO, _E.RETIRADO}),
    _E.RETIRADO: frozenset(),
}


@dataclass(frozen=True, slots=True)
class Colaborador:
    id: ColaboradorId
    documento: Documento
    nombres: str
    apellidos: str
    vinculacion: TipoDeVinculacion
    departamento: str
    cargo: str
    sede: str
    jefe_id: ColaboradorId | None
    fecha_ingreso: date
    fecha_fin: date | None
    estado: EstadoColaborador
    usuario: Usuario | None = None
    id_usuario_glpi: str | None = None

    def __post_init__(self) -> None:
        texto_no_vacio("id", self.id)

    @classmethod
    def por_ingresar(
        cls, id: ColaboradorId, datos: DatosIngreso, fecha_ingreso: date, usuario: Usuario
    ) -> "Colaborador":
        """S-06: se crea al registrar el ingreso, en `por_ingresar`."""
        return cls(
            id=id,
            documento=datos.documento,
            nombres=datos.nombres,
            apellidos=datos.apellidos,
            vinculacion=datos.vinculacion,
            departamento=datos.departamento,
            cargo=datos.cargo,
            sede=datos.sede,
            jefe_id=datos.jefe_id,
            fecha_ingreso=fecha_ingreso,
            fecha_fin=datos.fecha_fin,
            estado=EstadoColaborador.POR_INGRESAR,
            usuario=usuario,
        )

    @property
    def nombre_completo(self) -> str:
        return f"{self.nombres} {self.apellidos}"

    def con_estado(self, nuevo: EstadoColaborador) -> "Colaborador":
        if nuevo == self.estado:
            return self
        if nuevo not in TRANSICIONES_DE_COLABORADOR[self.estado]:
            raise OperacionNoPermitida(
                f"El colaborador no pasa de '{self.estado.value}' a '{nuevo.value}'"
            )
        return replace(self, estado=nuevo)

    def con_cambio_de_departamento(
        self, departamento: str, cargo: str, jefe_id: ColaboradorId | None
    ) -> "Colaborador":
        """S-20: lo aplica el cierre de un CDP."""
        return replace(
            self,
            departamento=texto_no_vacio("departamento", departamento),
            cargo=texto_no_vacio("cargo", cargo),
            jefe_id=jefe_id,
        )

    def con_cambio_de_sede(self, sede: str) -> "Colaborador":
        """S-20: lo aplica el cierre de un CSU."""
        return replace(self, sede=texto_no_vacio("sede", sede))

    def con_usuario_glpi(self, id_usuario_glpi: str) -> "Colaborador":
        if not id_usuario_glpi.strip():
            raise DatoInvalido("id_usuario_glpi", "no puede estar vacio")
        return replace(self, id_usuario_glpi=id_usuario_glpi)
