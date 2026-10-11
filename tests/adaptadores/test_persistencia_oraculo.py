"""CA-15 (parte de 2.3): las consultas del ORM dan EXACTAMENTE lo mismo que el oraculo en memoria.

La misma semilla de `tests/aplicacion/test_consultas.py` se construye dos veces con los casos de
uso reales: sobre el doble y sobre el ORM. Despues se comparan los indicadores (a) a (h), la
busqueda con varios filtros y la ficha de cada colaborador.
"""

from datetime import UTC, datetime, timedelta

import pytest

from jml.adaptadores.salida.persistencia.repositorios import RepositoriosDjango
from jml.aplicacion.dtos import FiltroDeCuentas
from jml.dominio.tipos import EstadoDeCuenta, SistemaDeCuenta
from tests.aplicacion.test_consultas import semilla
from tests.mundo import Mundo

# Cada hora durante 4 dias y luego cada dia hasta pasar la eliminacion a 90 dias: asi cada
# vencimiento y cada ventana de 7 dias (b, c, g) cruza su borde al menos una vez.
BARRIDO = [timedelta(hours=h) for h in range(-6, 96)] + [timedelta(days=d) for d in range(4, 125)]


def instantes(m: Mundo) -> list[datetime]:
    """El barrido mas los bordes exactos de cada ticket (emision, activacion y vencimiento, +-1 s)."""
    base = m.reloj.ahora()
    bordes: set[datetime] = {base + d for d in BARRIDO}
    for t in m.repos.almacen.tickets.values():
        siete_dias_antes = t.ticket.activo_desde - timedelta(days=7)  # borde de la ventana (g)
        for instante in (
            t.ticket.emitido_en,
            t.ticket.activo_desde,
            t.ticket.vence_en,
            siete_dias_antes,
        ):
            bordes |= {instante - timedelta(seconds=1), instante, instante + timedelta(seconds=1)}
    return sorted(bordes)


FILTROS = [
    FiltroDeCuentas(),
    FiltroDeCuentas(tamano=2, pagina=2),
    FiltroDeCuentas(nombre="maria gomez"),
    FiltroDeCuentas(departamento="finanzas"),
    FiltroDeCuentas(sede="bogota"),
    FiltroDeCuentas(sistema=SistemaDeCuenta.AD),
    FiltroDeCuentas(estado_de_cuenta=EstadoDeCuenta.PENDIENTE_BAJA),
    FiltroDeCuentas(sistema=SistemaDeCuenta.M365, estado_de_cuenta=EstadoDeCuenta.PENDIENTE_ALTA),
    FiltroDeCuentas(documento="70000009"),
    FiltroDeCuentas(usuario="otto"),
]


@pytest.mark.django_db
def test_CA_15_el_orm_coincide_con_el_oraculo() -> None:
    oraculo, ids = semilla()
    real, ids_real = semilla(RepositoriosDjango)
    assert ids == ids_real
    for ahora in instantes(oraculo):
        assert real.puerto.indicadores(ahora) == oraculo.puerto.indicadores(ahora), ahora
    for filtro in FILTROS:
        assert real.puerto.buscar_cuentas(filtro) == oraculo.puerto.buscar_cuentas(filtro)
    for colaborador in ("col-1", "col-9", "jefe-1", "col-rrhh", "col-n1", "no-existe"):
        assert real.puerto.ficha(colaborador) == oraculo.puerto.ficha(colaborador)


@pytest.mark.django_db
def test_CA_15_tambien_tras_resolver_reabrir_y_cerrar() -> None:
    def avanzar(m: Mundo) -> None:
        with m.puerto.unidad_de_trabajo() as u:
            tickets = [t for t in u.tickets.creados()]
        for i, t in enumerate(tickets):
            if i % 3 == 0:
                m.glpi.resolver(t.id_externo or "", con_solucion=True, documentos=1)
            elif i % 3 == 1:
                m.glpi.resolver(t.id_externo or "", con_solucion=False)
        m.avanzar(timedelta(minutes=5))
        m.sincronizar()
        for i, t in enumerate(tickets):
            if i % 3 == 0 and i % 2 == 0:
                m.glpi.reabrir(t.id_externo or "")
        m.avanzar(timedelta(minutes=5))
        m.sincronizar()

    oraculo, _ = semilla()
    real, _ = semilla(RepositoriosDjango)
    avanzar(oraculo)
    avanzar(real)
    for ahora in instantes(oraculo)[::3]:
        assert real.puerto.indicadores(ahora) == oraculo.puerto.indicadores(ahora), ahora
    for filtro in FILTROS:
        assert real.puerto.buscar_cuentas(filtro) == oraculo.puerto.buscar_cuentas(filtro)
    for colaborador in ("col-1", "col-9", "jefe-1", "col-n1"):
        assert real.puerto.ficha(colaborador) == oraculo.puerto.ficha(colaborador)


@pytest.mark.django_db
def test_CA_15_el_mes_corta_exactamente_a_las_0000_de_bogota() -> None:
    """Una solicitud creada a las 00:00:00 del 1-nov (Bogota) ya es de noviembre, no de octubre."""
    from dataclasses import replace

    from tests.mundo import vacaciones

    borde = datetime(2026, 11, 1, 5, 0, tzinfo=UTC)
    resultados = []
    for repositorios in (None, RepositoriosDjango):
        m = Mundo.nuevo() if repositorios is None else Mundo.nuevo(repositorios=repositorios)
        sid = m.registrar(vacaciones()).solicitud_id
        with m.puerto.unidad_de_trabajo() as u:
            s = u.solicitudes.obtener(sid)
            assert s is not None
            u.solicitudes.guardar(replace(s, creada_en=borde))
        resultados.append(
            [
                m.puerto.indicadores(borde + d).solicitudes_del_mes
                for d in (timedelta(seconds=-1), timedelta(0))
            ]
        )
    oraculo, real = resultados
    assert real == oraculo
    assert oraculo[0] == ()  # 31-oct 23:59:59: la solicitud aun no es "del mes" de octubre
    assert len(oraculo[1]) == 1  # 1-nov 00:00:00: es de noviembre
