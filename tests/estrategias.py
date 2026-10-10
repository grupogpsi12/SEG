"""Estrategias de hypothesis con vocabulario del dominio."""

from hypothesis import strategies as st

from jml.dominio.perfiles import PerfilDeAcceso, RecursoCompartido
from jml.dominio.tipos import PerfilDeRecurso, TipoDeEquipo

GRUPOS = [f"G{i}" for i in range(8)]
RUTAS = [rf"\\fs01.ad.andina.test\r{i}" for i in range(5)]
SEDES = ["Bogotá", "Medellín", "Cali"]


@st.composite
def recursos(draw: st.DrawFn) -> tuple[RecursoCompartido, ...]:
    rutas = draw(st.lists(st.sampled_from(RUTAS), unique=True, max_size=4))
    return tuple(
        RecursoCompartido(
            ruta,
            f"serie-{ruta[-1]}",
            draw(st.sampled_from([PerfilDeRecurso.CONSULTA, PerfilDeRecurso.EDICION])),
            draw(st.sampled_from(GRUPOS)),
        )
        for ruta in rutas
    )


@st.composite
def perfiles(draw: st.DrawFn) -> PerfilDeAcceso:
    def grupos() -> st.SearchStrategy[tuple[str, ...]]:
        return st.lists(st.sampled_from(GRUPOS), max_size=5).map(tuple)

    return PerfilDeAcceso(
        departamento=draw(st.sampled_from(["TI", "RRHH", "Finanzas"])),
        sede=draw(st.sampled_from(SEDES)),
        grupos_ad=draw(grupos()),
        grupos_red=draw(grupos()),
        grupos_m365=draw(grupos()),
        licencias=draw(grupos()),
        tipo_equipo=draw(st.sampled_from(list(TipoDeEquipo))),
        recursos=draw(recursos()),
    )
