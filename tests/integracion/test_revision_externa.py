"""Revision externa del 11/10/2026: H1, H2 y H3 reproducidos contra PostgreSQL real.

Ver docs/spikes/revision-externa-2026-10-11.md. Solo PostgreSQL muestra estos fallos: SQLite no
tiene duenios, disparadores ni bloqueos de fila.
"""

import threading
from collections.abc import Callable

import pytest
from django.db import DatabaseError, connection, connections, transaction

from jml.adaptadores.salida.persistencia import models as m
from jml.adaptadores.salida.persistencia import repositorios as r
from jml.adaptadores.salida.persistencia.repositorios import RepositoriosDjango
from jml.aplicacion.casos.decidir import (
    AprobarSolicitud,
    CancelarSolicitud,
    DependenciasDeDecision,
)
from jml.dominio.errores import ErrorDeDominio
from jml.dominio.permisos import UsuarioDelSistema
from jml.dominio.tipos import Rol
from jml.dominio.valores import CalendarioHabil, SolicitudId
from tests.mundo import Mundo, vacaciones

# --- H3: dos decisiones simultaneas sobre la misma solicitud ----------------------------------


def _carrera(monkeypatch: pytest.MonkeyPatch, acciones: list[Callable[[], object]]) -> list[str]:
    """Corre las acciones en hilos que leen la solicitud a la vez (barrera antes de la lectura)."""
    barrera = threading.Barrier(len(acciones), timeout=30)
    original = r.RepoSolicitudes.obtener

    def obtener_sincronizado(self: r.RepoSolicitudes, sid: SolicitudId) -> object:
        barrera.wait()
        return original(self, sid)

    monkeypatch.setattr(r.RepoSolicitudes, "obtener", obtener_sincronizado)
    resultados: list[str] = []

    def correr(accion: Callable[[], object]) -> None:
        try:
            accion()
            resultados.append("ok")
        except ErrorDeDominio as e:
            resultados.append(e.codigo)
        finally:
            connections.close_all()

    hilos = [threading.Thread(target=correr, args=(a,)) for a in acciones]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=60)
    monkeypatch.setattr(r.RepoSolicitudes, "obtener", original)
    return sorted(resultados)


def _mundo_con_pendiente() -> tuple[Mundo, SolicitudId, DependenciasDeDecision]:
    m_ = Mundo.nuevo(repositorios=RepositoriosDjango)
    with m_.puerto.unidad_de_trabajo() as u:
        u.usuarios.guardar(UsuarioDelSistema("u-rrhh-2", None, frozenset({Rol.RRHH})))
    sid = m_.registrar(vacaciones()).solicitud_id
    dep = DependenciasDeDecision(m_.puerto, m_.reloj, CalendarioHabil(), m_.soportes)
    return m_, sid, dep


def test_H3_dos_aprobaciones_simultaneas_solo_una_se_acepta(
    base_con_commit: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, sid, dep = _mundo_con_pendiente()
    resultados = _carrera(
        monkeypatch,
        [
            lambda: AprobarSolicitud(dep).ejecutar("u-rrhh", sid),
            lambda: AprobarSolicitud(dep).ejecutar("u-rrhh-2", sid),
        ],
    )
    assert resultados == ["ok", "transicion_invalida"]
    assert m.Decision.objects.filter(solicitud_id=sid.valor, tipo="aprobar").count() == 1
    assert m.RegistroDeAuditoria.objects.filter(accion="solicitud.aprobada").count() == 1


def test_H3_aprobar_contra_cancelar_solo_gana_una(
    base_con_commit: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, sid, dep = _mundo_con_pendiente()
    resultados = _carrera(
        monkeypatch,
        [
            lambda: AprobarSolicitud(dep).ejecutar("u-rrhh", sid),
            lambda: CancelarSolicitud(dep).ejecutar("u-col", sid),
        ],
    )
    # Gana una sola, la que tome primero el candado. Si gana la cancelacion, la aprobacion ve
    # una cancelada (transicion invalida); si gana la aprobacion, el colaborador ya no puede
    # cancelar una aprobada: solo RRHH lo hace (RF-11), y el dominio responde «no autorizado».
    assert resultados.count("ok") == 1, resultados
    assert set(resultados) - {"ok"} <= {"transicion_invalida", "no_autorizado"}, resultados
    assert m.Decision.objects.filter(solicitud_id=sid.valor).count() == 1


# --- H2: el disparador valida las transiciones de estado --------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("estado", ["cerrada", "aprobada", "rechazada", "en_ejecucion"])
def test_H2_no_se_puede_devolver_a_pendiente_para_editar(estado: str) -> None:
    m_ = Mundo.nuevo(repositorios=RepositoriosDjango)
    sid = m_.registrar(vacaciones()).solicitud_id
    # Se salta el repositorio y el dominio, como alguien con acceso directo a la base. Primero
    # se lleva la solicitud al estado de partida por transiciones validas.
    caminos = {
        "aprobada": ["aprobada"],
        "en_ejecucion": ["aprobada", "en_ejecucion"],
        "cerrada": ["aprobada", "en_ejecucion", "cerrada"],
        "rechazada": ["rechazada"],
    }
    for paso in caminos[estado]:
        m.Solicitud.objects.filter(pk=sid.valor).update(estado=paso)
    with pytest.raises(DatabaseError, match="RF-14"), transaction.atomic():
        m.Solicitud.objects.filter(pk=sid.valor).update(estado="pendiente_aprobacion")


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("desde", "hacia"),
    [("cerrada", "en_ejecucion"), ("cancelada", "aprobada"), ("en_ejecucion", "aprobada")],
)
def test_H2_transiciones_que_el_dominio_no_tiene_se_rechazan(desde: str, hacia: str) -> None:
    m_ = Mundo.nuevo(repositorios=RepositoriosDjango)
    sid = m_.registrar(vacaciones()).solicitud_id
    caminos = {
        "cerrada": ["aprobada", "en_ejecucion", "cerrada"],
        "cancelada": ["cancelada"],
        "en_ejecucion": ["aprobada", "en_ejecucion"],
    }
    for paso in caminos[desde]:
        m.Solicitud.objects.filter(pk=sid.valor).update(estado=paso)
    with pytest.raises(DatabaseError, match="RF-14"), transaction.atomic():
        m.Solicitud.objects.filter(pk=sid.valor).update(estado=hacia)


@pytest.mark.django_db
def test_H2_un_cambio_sin_cambio_de_estado_sigue_permitido() -> None:
    m_ = Mundo.nuevo(repositorios=RepositoriosDjango)
    sid = m_.registrar(vacaciones()).solicitud_id
    m.Solicitud.objects.filter(pk=sid.valor).update(estado="aprobada")
    m.Solicitud.objects.filter(pk=sid.valor).update(para_revision=True)  # marca, no contenido
    assert m.Solicitud.objects.get(pk=sid.valor).para_revision is True


# --- H1: app_backend no es duenio ------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "sql",
    [
        "ALTER TABLE solicitud DISABLE TRIGGER solicitud_inmutable",
        "ALTER TABLE auditoria DISABLE ROW LEVEL SECURITY",
        "CREATE TABLE intrusa (x int)",
        "DROP TABLE decision",
    ],
)
def test_H1_app_backend_no_puede_cambiar_permisos_ni_estructura(sql: str) -> None:
    with connection.cursor() as c:
        c.execute("SELECT current_user")
        assert c.fetchone() == ("app_backend",)
    with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as c:
        c.execute(sql)


@pytest.mark.django_db
def test_H1_app_backend_no_puede_darse_permiso_sobre_la_auditoria() -> None:
    """Sin ser duenio, el GRANT solo avisa «no privileges were granted»: el UPDATE sigue negado."""
    with transaction.atomic(), connection.cursor() as c:
        c.execute("GRANT UPDATE ON auditoria TO app_backend")
    with (
        pytest.raises(DatabaseError, match="permission denied"),
        transaction.atomic(),
        connection.cursor() as c,
    ):
        c.execute("UPDATE auditoria SET actor = 'manipulado'")


@pytest.mark.django_db
def test_H1_app_backend_sigue_pudiendo_operar() -> None:
    """Los permisos minimos alcanzan para la aplicacion: escribir, leer, insertar en auditoria."""
    Mundo.nuevo(repositorios=RepositoriosDjango).registrar(vacaciones())
    assert m.Solicitud.objects.count() == 1
    assert m.RegistroDeAuditoria.objects.exists()
