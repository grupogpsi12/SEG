"""ADR-025: casos de uso de lectura para las vistas de 2.7 (RF-11, RF-12, RF-28)."""

import dataclasses

import pytest

from jml.aplicacion.casos.listados import (
    ColaboradorPorDocumento,
    MiPerfil,
    MisSolicitudes,
    PendientesDeAprobacion,
    SubordinadosDe,
)
from jml.dominio.errores import NoAutorizado
from jml.dominio.tipos import EstadoSolicitud, Rol
from tests.fabricas import SENTINELA
from tests.mundo import Mundo, cambio_de_departamento, retiro, vacaciones


def test_mis_solicitudes_son_las_que_registre_con_el_nombre_del_sujeto() -> None:
    m = Mundo.nuevo()
    vac = m.registrar(vacaciones())
    m.registrar(cambio_de_departamento())  # la registro el jefe, no u-col
    filas = MisSolicitudes(m.puerto).ejecutar("u-col")
    assert [(f.id, f.colaborador_nombre) for f in filas] == [
        (vac.solicitud_id, "María José Gómez Ramírez")
    ]
    assert filas[0].estado is EstadoSolicitud.PENDIENTE_APROBACION
    assert filas[0].cancelable is True


def test_una_solicitud_aprobada_o_final_no_es_cancelable_por_el_solicitante() -> None:
    m = Mundo.nuevo()
    a = m.registrar(vacaciones())
    m.aprobar("u-rrhh", a.solicitud_id)
    assert [f.cancelable for f in MisSolicitudes(m.puerto).ejecutar("u-col")] == [False]


def test_mis_solicitudes_de_quien_no_registro_nada_esta_vacia() -> None:
    assert MisSolicitudes(Mundo.nuevo().puerto).ejecutar("u-otro") == ()


def test_pendientes_de_aprobacion_solo_para_rrhh() -> None:
    m = Mundo.nuevo()
    a = m.registrar(vacaciones())
    b = m.registrar(cambio_de_departamento())
    m.aprobar("u-rrhh", b.solicitud_id)
    filas = PendientesDeAprobacion(m.puerto).ejecutar("u-rrhh")
    assert [f.id for f in filas] == [a.solicitud_id]
    for usuario in ("u-col", "u-jefe", "u-admin", "u-tec-ad", "u-aud", "fantasma"):
        with pytest.raises(NoAutorizado):
            PendientesDeAprobacion(m.puerto).ejecutar(usuario)


def test_las_filas_nunca_llevan_el_campo_restringido() -> None:
    m = Mundo.nuevo()
    m.emitir(retiro(restringido=SENTINELA))
    m.registrar(vacaciones())
    todo = repr(MisSolicitudes(m.puerto).ejecutar("u-col")) + repr(
        PendientesDeAprobacion(m.puerto).ejecutar("u-rrhh")
    )
    todo += repr([dataclasses.fields(type(f)) for f in MisSolicitudes(m.puerto).ejecutar("u-rrhh")])
    assert SENTINELA not in todo
    assert "motivo" not in todo.lower()


def test_el_jefe_ve_a_sus_subordinados_directos() -> None:
    m = Mundo.nuevo()
    opciones = SubordinadosDe(m.puerto).ejecutar("u-jefe")
    assert [(o.colaborador_id, o.nombre) for o in opciones] == [
        ("col-1", "María José Gómez Ramírez")
    ]


def test_quien_no_es_colaborador_o_no_tiene_equipo_ve_una_lista_vacia() -> None:
    m = Mundo.nuevo()
    assert SubordinadosDe(m.puerto).ejecutar("u-admin") == ()  # sin colaborador asociado
    assert SubordinadosDe(m.puerto).ejecutar("u-col") == ()  # empleado sin equipo
    with pytest.raises(NoAutorizado):
        SubordinadosDe(m.puerto).ejecutar("fantasma")


def test_mi_perfil_trae_roles_y_colaborador() -> None:
    m = Mundo.nuevo()
    perfil = MiPerfil(m.puerto).ejecutar("u-col")
    assert perfil.roles == {Rol.SOLICITANTE}
    assert perfil.colaborador is not None
    assert (perfil.colaborador.colaborador_id, perfil.colaborador.nombre) == (
        "col-1",
        "María José Gómez Ramírez",
    )
    admin = MiPerfil(m.puerto).ejecutar("u-admin")
    assert admin.roles == {Rol.ADMINISTRADOR}
    assert admin.colaborador is None
    with pytest.raises(NoAutorizado):
        MiPerfil(m.puerto).ejecutar("fantasma")


def test_rrhh_encuentra_a_una_persona_por_su_documento() -> None:
    m = Mundo.nuevo()
    buscar = ColaboradorPorDocumento(m.puerto)
    encontrada = buscar.ejecutar("u-rrhh", " 10203040 ")
    assert encontrada is not None
    assert encontrada.colaborador_id == "col-1"
    assert buscar.ejecutar("u-rrhh", "99999999") is None
    assert buscar.ejecutar("u-rrhh", "x") is None  # documento invalido: no hay nadie, no es error
    assert buscar.ejecutar("u-admin", "10203040") is not None  # emite por excepcion
    for usuario in ("u-col", "u-jefe", "u-tec-ad"):
        with pytest.raises(NoAutorizado):
            buscar.ejecutar(usuario, "10203040")
