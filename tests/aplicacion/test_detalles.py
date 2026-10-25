"""F8-02 (B-09): detalles que la mutacion de `aplicacion` mostro sin comprobar.

Cada prueba fija un dato que un caso de uso devuelve o dice (la entidad que no se encontro, los roles
ordenados, la frontera de un rango) y que antes solo se miraba por su tipo.
"""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from enum import Enum

import pytest

from jml.aplicacion.casos.administracion import CambiarRoles, ConsultarUsuarios
from jml.aplicacion.casos.listados import (
    ColaboradorPorDocumento,
    ConsultarSolicitud,
    PendientesDeAprobacion,
    _como_texto,
)
from jml.dominio.errores import NoEncontrado, OperacionNoPermitida
from jml.dominio.tipos import Rol
from jml.dominio.valores import SolicitudId
from tests.fabricas import HOY
from tests.mundo import Mundo, cambio_de_departamento, ingreso, vacaciones


def _no_encontrado(llamada) -> tuple[str, str]:  # type: ignore[no-untyped-def]
    with pytest.raises(NoEncontrado) as e:
        llamada()
    return e.value.entidad, e.value.referencia


def test_lo_que_no_se_encuentra_dice_que_entidad_y_cual_referencia() -> None:
    m = Mundo.nuevo()
    sid = m.registrar(vacaciones()).solicitud_id
    fantasma = SolicitudId("SOL-2026-999999")
    assert _no_encontrado(lambda: m.ficha("u-tec-ad", "no-existe")) == ("colaborador", "no-existe")
    assert _no_encontrado(lambda: m.aprobar("u-rrhh", fantasma)) == ("solicitud", "SOL-2026-999999")
    assert _no_encontrado(lambda: m.reintentar("u-admin", fantasma)) == (
        "solicitud",
        "SOL-2026-999999",
    )
    assert _no_encontrado(lambda: ConsultarSolicitud(m.puerto).ejecutar("u-rrhh", fantasma)) == (
        "solicitud",
        "SOL-2026-999999",
    )
    assert _no_encontrado(lambda: m.registrar(replace(vacaciones(), colaborador_id="col-x"))) == (
        "colaborador",
        "col-x",
    )
    assert sid.valor == "SOL-2026-000001"


def test_un_ingreso_a_un_departamento_sin_perfil_dice_cual_perfil_falta() -> None:
    m = Mundo.nuevo()
    assert _no_encontrado(
        lambda: m.emitir(ingreso(departamento="Marte", sede="Bogotá", requiere_equipo=False))
    ) == (
        "perfil de acceso",
        "Marte / Bogotá",
    )


def test_cambiar_roles_dice_a_quien_no_encontro_y_no_deja_cambiar_los_propios() -> None:
    m = Mundo.nuevo()
    caso = CambiarRoles(m.puerto)
    assert _no_encontrado(
        lambda: caso.ejecutar("u-admin", "nadie", frozenset({Rol.SOLICITANTE}))
    ) == (
        "usuario",
        "nadie",
    )
    with pytest.raises(OperacionNoPermitida, match="nadie cambia sus propios roles"):
        caso.ejecutar("u-admin", "u-admin", frozenset({Rol.SOLICITANTE}))


def test_cambiar_roles_conserva_el_colaborador_y_si_esta_activo() -> None:
    m = Mundo.nuevo()
    antes = {u.id: u for u in _usuarios(m)}["u-col"]
    CambiarRoles(m.puerto).ejecutar("u-admin", "u-col", frozenset({Rol.SOLICITANTE, Rol.RRHH}))
    despues = {u.id: u for u in _usuarios(m)}["u-col"]
    assert despues.roles == {Rol.SOLICITANTE, Rol.RRHH}
    assert (despues.colaborador_id, despues.activo) == (antes.colaborador_id, antes.activo)
    assert despues.colaborador_id is not None


def _usuarios(m: Mundo):  # type: ignore[no-untyped-def]
    with m.puerto.unidad_de_trabajo() as u:
        return list(u.usuarios.todos())


def test_la_lista_de_usuarios_trae_nombre_roles_ordenados_y_estado() -> None:
    m = Mundo.nuevo()
    filas = {f.usuario_id: f for f in ConsultarUsuarios(m.puerto).ejecutar("u-admin")}
    assert filas["u-admin"].colaborador_nombre is None  # el administrador no tiene colaborador
    assert filas["u-col"].colaborador_nombre is not None
    for f in filas.values():
        assert list(f.roles) == sorted(f.roles, key=lambda r: r.value)
        assert f.activo is True


def test_la_busqueda_por_documento_devuelve_el_nombre() -> None:
    m = Mundo.nuevo()
    op = ColaboradorPorDocumento(m.puerto).ejecutar("u-rrhh", "10203040")
    assert op is not None
    assert (op.colaborador_id, op.nombre) == ("col-1", "María José Gómez Ramírez")


def test_el_texto_de_un_valor_para_la_pantalla() -> None:
    class Color(Enum):
        ROJO = "rojo"

    assert _como_texto(None) == "—"
    assert _como_texto(True) == "Sí"
    assert _como_texto(False) == "No"
    assert _como_texto(Color.ROJO) == "rojo"
    assert _como_texto(7) == "7"
    # 03:30 UTC es 22:30 del dia anterior en Bogota (UTC-5): la hora se muestra en la zona de la empresa
    assert _como_texto(datetime(2026, 10, 13, 3, 30, tzinfo=UTC)) == "2026-10-12 22:30"


def test_el_detalle_de_una_solicitud_trae_las_fechas_el_colaborador_y_la_revision() -> None:
    m = Mundo.nuevo()
    sid = m.registrar(vacaciones()).solicitud_id
    d = ConsultarSolicitud(m.puerto).ejecutar("u-rrhh", sid)
    assert d.fila.colaborador_id == "col-1"
    assert d.fila.colaborador_nombre == "María José Gómez Ramírez"
    assert d.fila.fecha_efectiva == m.solicitud(sid).fecha_efectiva
    assert d.fila.creada_en == m.solicitud(sid).creada_en
    assert d.fila.para_revision is False
    # `cancelable` depende de QUIEN consulta: la cancela el solicitante, no RRHH
    assert d.fila.cancelable is False
    assert ConsultarSolicitud(m.puerto).ejecutar("u-col", sid).fila.cancelable is True
    assert PendientesDeAprobacion(m.puerto).ejecutar("u-rrhh")[0].cancelable is False


def test_los_contratos_por_vencer_incluyen_hoy_y_no_se_cortan_en_el_primero_fuera_de_rango() -> (
    None
):
    m = Mundo.nuevo()
    with m.repos.unidad_de_trabajo() as u:
        # `con_fin_de_contrato` los recorre en orden de insercion: el primero queda fuera de rango
        u.colaboradores.guardar(replace(m.colaborador("col-1"), fecha_fin=HOY - timedelta(days=1)))
        u.colaboradores.guardar(replace(m.colaborador("col-9"), fecha_fin=HOY))
        u.colaboradores.guardar(replace(m.colaborador("jefe-1"), fecha_fin=HOY + timedelta(days=2)))
    filas = m.contratos_por_vencer("u-rrhh")
    assert [
        (f.colaborador_id, f.nombre_completo, f.fecha_fin, f.dias_restantes) for f in filas
    ] == [
        ("col-9", "Otto Nieto", HOY, 0),
        ("jefe-1", "Jorge Mejía", HOY + timedelta(days=2), 2),
    ]


def test_un_cambio_de_departamento_pendiente_no_es_para_revision() -> None:
    m = Mundo.nuevo()
    sid = m.registrar(cambio_de_departamento(destino="Comercial")).solicitud_id
    assert ConsultarSolicitud(m.puerto).ejecutar("u-rrhh", sid).fila.para_revision is False
