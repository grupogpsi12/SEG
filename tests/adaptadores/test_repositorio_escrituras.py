"""El repositorio no reescribe lo que no cambio (hallazgo de la integracion contra PostgreSQL).

El campo restringido de una solicitud aprobada es inmutable (RF-14): el disparador de PostgreSQL
rechaza hasta un UPDATE con el mismo valor. SQLite no tiene el disparador, asi que esta prueba
cuenta las escrituras: guardar de nuevo una solicitud no debe tocar `solicitud_restringida`.
"""

from dataclasses import replace

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from jml.adaptadores.salida.persistencia.repositorios import RepositoriosDjango
from jml.dominio.tipos import EstadoSolicitud, Subtipo, TipoEvento
from tests.dobles.reloj import RelojSimulado
from tests.fabricas import caso


def _escrituras_en_restringida(consultas: list[dict[str, str]]) -> list[str]:
    return [
        q["sql"]
        for q in consultas
        if "solicitud_restringida" in q["sql"]
        and q["sql"].lstrip().upper().startswith(("UPDATE", "DELETE"))
    ]


@pytest.mark.django_db
def test_guardar_de_nuevo_una_solicitud_aprobada_no_reescribe_el_campo_restringido() -> None:
    c = caso(TipoEvento.RET, Subtipo.RENUNCIA)
    repos = RepositoriosDjango(RelojSimulado())
    with repos.unidad_de_trabajo() as u:
        u.colaboradores.guardar(c.colaborador)
        u.solicitudes.guardar(c.solicitud)  # inserta, restringido incluido
    with CaptureQueriesContext(connection) as capturadas, repos.unidad_de_trabajo() as u:
        siguiente = replace(c.solicitud, estado=EstadoSolicitud.EN_EJECUCION, tickets=("k1",))
        u.solicitudes.guardar(siguiente)
    assert _escrituras_en_restringida(capturadas.captured_queries) == []
    with repos.unidad_de_trabajo() as u:
        leida = u.solicitudes.obtener(c.solicitud.id)
    assert leida == siguiente
    assert leida is not None
    assert leida.restringido == c.solicitud.restringido  # sigue intacto


@pytest.mark.django_db
def test_un_restringido_distinto_si_se_escribe_mientras_esta_pendiente() -> None:
    from jml.dominio.valores import CampoRestringido

    c = caso(TipoEvento.RET, Subtipo.RENUNCIA)
    pendiente = replace(c.solicitud, estado=EstadoSolicitud.PENDIENTE_APROBACION)
    repos = RepositoriosDjango(RelojSimulado())
    with repos.unidad_de_trabajo() as u:
        u.colaboradores.guardar(c.colaborador)
        u.solicitudes.guardar(pendiente)
        u.solicitudes.guardar(replace(pendiente, restringido=CampoRestringido("corregido")))
        leida = u.solicitudes.obtener(pendiente.id)
    assert leida is not None
    assert leida.restringido == CampoRestringido("corregido")
