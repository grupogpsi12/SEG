"""Item 2.6: semillas ficticias e idempotentes (RD-07)."""

from io import StringIO

import pytest
from django.core.management import call_command

from jml.adaptadores.entrada.web import semillas
from jml.adaptadores.salida.persistencia import models as m
from jml.adaptadores.salida.persistencia.repositorios import RepositoriosDjango
from jml.dominio.tipos import TipoDeVinculacion
from tests.dobles.reloj import RelojSimulado
from tests.fabricas import MATRIZ, SEDES, perfil


def test_la_matriz_de_las_semillas_coincide_con_la_transcripcion_del_SRS_en_las_pruebas() -> None:
    """Dos transcripciones independientes del SRS 4.9 deben coincidir celda por celda."""
    assert set(semillas.MATRIZ) == set(MATRIZ)
    assert semillas.SEDES == SEDES
    assert sorted(semillas.perfiles(), key=lambda p: (p.departamento, p.sede)) == sorted(
        (perfil(d, s) for d in MATRIZ for s in SEDES), key=lambda p: (p.departamento, p.sede)
    )


def test_30_colaboradores_ficticios_coherentes() -> None:
    cs = semillas.colaboradores()
    assert len(cs) == 30
    assert len({c.id for c in cs}) == 30
    assert len({c.documento for c in cs}) == 30
    assert len({c.usuario for c in cs}) == 30
    ids = {c.id for c in cs}
    assert all(c.jefe_id is None or c.jefe_id in ids for c in cs)
    assert {c.departamento for c in cs} == set(MATRIZ)
    assert {c.sede for c in cs} == set(SEDES)
    contratistas = [c for c in cs if c.vinculacion is TipoDeVinculacion.CONTRATISTA]
    assert contratistas
    assert all(c.fecha_fin is not None for c in contratistas)  # RF-28 tiene datos


@pytest.mark.django_db
def test_RD_07_las_semillas_son_idempotentes_y_se_auditan() -> None:
    repos = RepositoriosDjango(RelojSimulado())
    primera = semillas.aplicar(repos)
    assert (primera.perfiles, primera.colaboradores) == (18, 30)
    auditoria = m.RegistroDeAuditoria.objects.count()
    assert auditoria == 48
    segunda = semillas.aplicar(repos)
    assert (segunda.perfiles, segunda.colaboradores) == (0, 0)
    assert m.RegistroDeAuditoria.objects.count() == auditoria  # sin ruido
    assert m.Colaborador.objects.count() == 30
    assert m.PerfilDeAcceso.objects.count() == 18
    assert m.Cuenta.objects.count() == 0  # invariante 6: las cuentas solo nacen de tickets
    with repos.unidad_de_trabajo() as u:
        assert u.auditoria.verificar().valida


@pytest.mark.django_db
def test_el_comando_de_django_funciona() -> None:
    salida = StringIO()
    call_command("semillas", stdout=salida)
    assert "perfiles actualizados: 18; colaboradores: 30" in salida.getvalue()
