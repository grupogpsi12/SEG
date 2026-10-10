"""Perfiles de acceso y recursos compartidos (SRS 4.9, RF-16, ADR-022).

"Retiro de accesos" no se configura en la matriz: lo genera el dominio al retirar un recurso
(`AccesoARecurso.retiro`). Por eso `RecursoCompartido` solo admite Consulta o Edicion.
"""

from dataclasses import dataclass

from jml.dominio.errores import DatoInvalido
from jml.dominio.tipos import PerfilDeRecurso, TipoDeEquipo
from jml.dominio.valores import ascii_minuscula, texto_no_vacio


@dataclass(frozen=True, slots=True)
class RecursoCompartido:
    ruta: str
    serie: str
    perfil: PerfilDeRecurso
    grupo: str

    def __post_init__(self) -> None:
        for campo in ("ruta", "serie", "grupo"):
            texto_no_vacio(campo, getattr(self, campo), 300)
        if self.perfil is PerfilDeRecurso.RETIRO_DE_ACCESOS:
            raise DatoInvalido(
                "perfil", "'Retiro de accesos' no se configura en la matriz (ADR-022)"
            )


@dataclass(frozen=True, slots=True)
class AccesoARecurso:
    """Una linea de la lista de verificacion: que perfil aplicar (o retirar) en un recurso."""

    ruta: str
    serie: str
    perfil: PerfilDeRecurso
    grupo: str

    @classmethod
    def aplicar(cls, recurso: RecursoCompartido) -> "AccesoARecurso":
        return cls(recurso.ruta, recurso.serie, recurso.perfil, recurso.grupo)

    @classmethod
    def retiro(cls, recurso: RecursoCompartido) -> "AccesoARecurso":
        return cls(recurso.ruta, recurso.serie, PerfilDeRecurso.RETIRO_DE_ACCESOS, recurso.grupo)

    def como_texto(self) -> str:
        return (
            f"{self.ruta} | serie: {self.serie} | perfil: {self.perfil.value} | grupo: {self.grupo}"
        )


def _ordenado(valores: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(set(valores)))


def nombre_de_sede(sede: str) -> str:
    """`Bogotá` -> `Bogota` para los grupos `GG-Sede-<sede>` y `NET-VLAN-<sede>`."""
    return ascii_minuscula(texto_no_vacio("sede", sede)).replace(" ", "").capitalize()


@dataclass(frozen=True, slots=True)
class PerfilDeAcceso:
    departamento: str
    sede: str
    grupos_ad: tuple[str, ...]
    grupos_red: tuple[str, ...]
    grupos_m365: tuple[str, ...]
    licencias: tuple[str, ...]
    tipo_equipo: TipoDeEquipo
    recursos: tuple[RecursoCompartido, ...]

    def __post_init__(self) -> None:
        texto_no_vacio("departamento", self.departamento)
        texto_no_vacio("sede", self.sede)
        # Normalizacion: el orden de entrada no importa, de modo que `==` compara contenido.
        for campo in ("grupos_ad", "grupos_red", "grupos_m365", "licencias"):
            object.__setattr__(self, campo, _ordenado(getattr(self, campo)))
        rutas = [r.ruta for r in self.recursos]
        if len(rutas) != len(set(rutas)):
            raise DatoInvalido("recursos", "una ruta no puede aparecer dos veces en un perfil")
        object.__setattr__(self, "recursos", tuple(sorted(self.recursos, key=lambda r: r.ruta)))

    @classmethod
    def para(
        cls,
        departamento: str,
        sede: str,
        grupos_ad: tuple[str, ...],
        grupos_red: tuple[str, ...],
        grupos_m365: tuple[str, ...],
        licencias: tuple[str, ...],
        tipo_equipo: TipoDeEquipo,
        recursos: tuple[RecursoCompartido, ...],
    ) -> "PerfilDeAcceso":
        """Compone el perfil del departamento y le suma los grupos de la sede (SRS 4.9)."""
        nombre = nombre_de_sede(sede)
        return cls(
            departamento,
            sede,
            (*grupos_ad, f"GG-Sede-{nombre}"),
            (*grupos_red, f"NET-VLAN-{nombre}"),
            grupos_m365,
            licencias,
            tipo_equipo,
            recursos,
        )

    def accesos_de_retiro(self) -> tuple[AccesoARecurso, ...]:
        """RET y EMG: 'Retiro de accesos' en TODOS los recursos compartidos."""
        return tuple(AccesoARecurso.retiro(r) for r in self.recursos)

    def accesos_a_aplicar(self) -> tuple[AccesoARecurso, ...]:
        return tuple(AccesoARecurso.aplicar(r) for r in self.recursos)


@dataclass(frozen=True, slots=True)
class DiferenciaDePerfiles:
    departamento_destino: str
    sede_destino: str
    grupos_ad_agregar: tuple[str, ...]
    grupos_ad_quitar: tuple[str, ...]
    grupos_red_agregar: tuple[str, ...]
    grupos_red_quitar: tuple[str, ...]
    grupos_m365_agregar: tuple[str, ...]
    grupos_m365_quitar: tuple[str, ...]
    licencias_agregar: tuple[str, ...]
    licencias_quitar: tuple[str, ...]
    recursos_a_aplicar: tuple[AccesoARecurso, ...]
    recursos_a_retirar: tuple[AccesoARecurso, ...]
    equipo_nuevo: TipoDeEquipo | None  # None si el tipo de equipo no cambia

    @property
    def cambia_ad(self) -> bool:
        return bool(
            self.grupos_ad_agregar
            or self.grupos_ad_quitar
            or self.recursos_a_aplicar
            or self.recursos_a_retirar
        )

    @property
    def cambia_red(self) -> bool:
        return bool(self.grupos_red_agregar or self.grupos_red_quitar)

    @property
    def cambia_m365(self) -> bool:
        return bool(
            self.grupos_m365_agregar
            or self.grupos_m365_quitar
            or self.licencias_agregar
            or self.licencias_quitar
        )

    @property
    def esta_vacia(self) -> bool:
        return not (
            self.cambia_ad or self.cambia_red or self.cambia_m365 or self.equipo_nuevo is not None
        )


def _restar(a: tuple[str, ...], b: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(x for x in a if x not in set(b))


def diferencia(actual: PerfilDeAcceso, nuevo: PerfilDeAcceso) -> DiferenciaDePerfiles:
    """Lo que hay que quitar y agregar para pasar de `actual` a `nuevo` (CDP y CSU).

    Un recurso cuya ruta sigue en el perfil nuevo pero con otro perfil o grupo se aplica de
    nuevo (no se retira y se vuelve a dar). Solo se retiran las rutas que desaparecen.
    """
    en_actual = set(actual.recursos)
    rutas_nuevas = {r.ruta for r in nuevo.recursos}
    return DiferenciaDePerfiles(
        departamento_destino=nuevo.departamento,
        sede_destino=nuevo.sede,
        grupos_ad_agregar=_restar(nuevo.grupos_ad, actual.grupos_ad),
        grupos_ad_quitar=_restar(actual.grupos_ad, nuevo.grupos_ad),
        grupos_red_agregar=_restar(nuevo.grupos_red, actual.grupos_red),
        grupos_red_quitar=_restar(actual.grupos_red, nuevo.grupos_red),
        grupos_m365_agregar=_restar(nuevo.grupos_m365, actual.grupos_m365),
        grupos_m365_quitar=_restar(actual.grupos_m365, nuevo.grupos_m365),
        licencias_agregar=_restar(nuevo.licencias, actual.licencias),
        licencias_quitar=_restar(actual.licencias, nuevo.licencias),
        recursos_a_aplicar=tuple(
            AccesoARecurso.aplicar(r) for r in nuevo.recursos if r not in en_actual
        ),
        recursos_a_retirar=tuple(
            AccesoARecurso.retiro(r) for r in actual.recursos if r.ruta not in rutas_nuevas
        ),
        equipo_nuevo=nuevo.tipo_equipo if nuevo.tipo_equipo != actual.tipo_equipo else None,
    )


def aplicar(dif: DiferenciaDePerfiles, base: PerfilDeAcceso) -> PerfilDeAcceso:
    """Inversa de `diferencia`: `aplicar(diferencia(a, b), a) == b` (P5)."""
    retiradas = {a.ruta for a in dif.recursos_a_retirar}
    reaplicadas = {a.ruta for a in dif.recursos_a_aplicar}
    conservados = tuple(
        r for r in base.recursos if r.ruta not in retiradas and r.ruta not in reaplicadas
    )
    nuevos = tuple(
        RecursoCompartido(a.ruta, a.serie, a.perfil, a.grupo) for a in dif.recursos_a_aplicar
    )

    def combinar(
        actual: tuple[str, ...], agregar: tuple[str, ...], quitar: tuple[str, ...]
    ) -> tuple[str, ...]:
        return (*_restar(actual, quitar), *agregar)

    return PerfilDeAcceso(
        departamento=dif.departamento_destino,
        sede=dif.sede_destino,
        grupos_ad=combinar(base.grupos_ad, dif.grupos_ad_agregar, dif.grupos_ad_quitar),
        grupos_red=combinar(base.grupos_red, dif.grupos_red_agregar, dif.grupos_red_quitar),
        grupos_m365=combinar(base.grupos_m365, dif.grupos_m365_agregar, dif.grupos_m365_quitar),
        licencias=combinar(base.licencias, dif.licencias_agregar, dif.licencias_quitar),
        tipo_equipo=dif.equipo_nuevo or base.tipo_equipo,
        recursos=(*conservados, *nuevos),
    )
