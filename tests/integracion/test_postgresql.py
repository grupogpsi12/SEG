"""Lo que solo PostgreSQL garantiza (2.3): CA-01 concurrente, RF-14, RD-02 y RD-10.

No corre en `make verificar` (no hay base real); se ejecuta a proposito como indica
`ajustes.py`, y sin PostgreSQL falla: es intencional, no hay nada que omitir en silencio.
"""

import threading
from dataclasses import replace
from datetime import timedelta

import pytest
from django.db import DatabaseError, connection, connections, transaction

from jml.adaptadores.salida.persistencia import models as m
from jml.adaptadores.salida.persistencia.repositorios import RepositoriosDjango
from jml.aplicacion.puertos import DuplicadoAbierto
from jml.dominio.auditoria import EventoDeAuditoria
from jml.dominio.catalogo import DatosVacaciones
from jml.dominio.solicitud import Solicitud
from jml.dominio.tipos import EstadoSolicitud, Subtipo, TipoEvento
from jml.dominio.valores import SolicitudId
from tests.dobles.reloj import RelojSimulado
from tests.fabricas import AHORA, HOY, caso, colaborador


def _vac(numero: int, estado: EstadoSolicitud = EstadoSolicitud.PENDIENTE_APROBACION) -> Solicitud:
    return Solicitud(
        id=SolicitudId.de(2026, numero), colaborador_id="col-1", tipo=TipoEvento.VAC, subtipo=None,
        fecha_efectiva=HOY + timedelta(days=7), datos=DatosVacaciones(HOY + timedelta(days=14)),
        restringido=None, solicitante_id="u-1", estado=estado, creada_en=AHORA,
    )  # fmt: skip


def test_CA_01_dos_inserciones_concurrentes_solo_una_queda_abierta(base_con_commit: None) -> None:
    repos = RepositoriosDjango(RelojSimulado())
    with repos.unidad_de_trabajo() as u:
        u.colaboradores.guardar(colaborador())
    barrera = threading.Barrier(2)
    resultados: list[str] = []

    def registrar(numero: int) -> None:
        try:
            with repos.unidad_de_trabajo() as u:
                barrera.wait()
                u.solicitudes.guardar(_vac(numero))
            resultados.append("ok")
        except DuplicadoAbierto:
            resultados.append("duplicado")
        finally:
            connections.close_all()

    hilos = [threading.Thread(target=registrar, args=(n,)) for n in (1, 2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert sorted(resultados) == ["duplicado", "ok"]
    assert m.Solicitud.objects.filter(estado__in=["pendiente_aprobacion"]).count() == 1


@pytest.mark.django_db
def test_RF_14_el_disparador_impide_cambiar_una_aprobada_aunque_se_salte_el_repositorio() -> None:
    repos = RepositoriosDjango(RelojSimulado())
    with repos.unidad_de_trabajo() as u:
        u.colaboradores.guardar(colaborador())
        u.solicitudes.guardar(_vac(1, EstadoSolicitud.APROBADA))
    with pytest.raises(DatabaseError, match="RF-14"), transaction.atomic():
        m.Solicitud.objects.filter(pk="SOL-2026-000001").update(
            fecha_efectiva=HOY + timedelta(days=30)
        )
    m.Solicitud.objects.filter(pk="SOL-2026-000001").update(estado="en_ejecucion")  # el estado si


@pytest.mark.django_db
def test_RF_14_el_campo_restringido_de_una_aprobada_tampoco_cambia() -> None:
    c = caso(TipoEvento.RET, Subtipo.RENUNCIA)
    repos = RepositoriosDjango(RelojSimulado())
    with repos.unidad_de_trabajo() as u:
        u.colaboradores.guardar(c.colaborador)
        u.solicitudes.guardar(c.solicitud)
    with pytest.raises(DatabaseError, match="RF-14"), transaction.atomic():
        m.SolicitudRestringida.objects.filter(solicitud_id=c.solicitud.id.valor).update(
            contenido="x"
        )
    with pytest.raises(DatabaseError, match="RF-14"), transaction.atomic():
        m.SolicitudRestringida.objects.filter(solicitud_id=c.solicitud.id.valor).delete()
    assert replace(c.solicitud) == c.solicitud


@pytest.mark.django_db
@pytest.mark.parametrize("tabla", ["auditoria", "decision", "cuenta_historial"])
def test_RD_02_app_backend_no_puede_modificar_las_tablas_de_solo_insercion(tabla: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_user")
        assert cursor.fetchone() == ("app_backend",), (
            "las pruebas deben conectarse como app_backend"
        )
    repos = RepositoriosDjango(RelojSimulado())
    with repos.unidad_de_trabajo() as u:
        u.auditoria.registrar("u", EventoDeAuditoria("a", "o", {}))
    for sql in (f"UPDATE {tabla} SET id = id", f"DELETE FROM {tabla}", f"TRUNCATE {tabla}"):
        with (
            pytest.raises(DatabaseError, match="permission denied"),
            transaction.atomic(),
            connection.cursor() as cursor,
        ):
            cursor.execute(sql.replace("SET id = id", "SET fecha = fecha"))


@pytest.mark.django_db
def test_RD_10_todas_las_tablas_tienen_RLS_activo() -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = current_schema() AND c.relkind = 'r' AND NOT c.relrowsecurity "
            "AND relname NOT LIKE 'django_%%' AND relname NOT LIKE 'auth_%%'"
        )
        sin_rls = [fila[0] for fila in cursor.fetchall()]
    assert sin_rls == []
