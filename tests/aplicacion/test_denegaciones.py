"""F8-02 (B-09): cada denegacion dice QUE accion se nego y POR QUE.

La mutacion de `aplicacion` mostro que las pruebas solo miraban el tipo de la excepcion. Pero la accion
alimenta el evento `acceso.denegado` (B-25) y el motivo se muestra al usuario: si cambian en silencio,
el registro de denegaciones y los mensajes dejan de coincidir con lo que paso.
"""

from collections.abc import Callable
from dataclasses import replace

import pytest

from jml.aplicacion.bandeja import espera_de_reintento
from jml.aplicacion.casos.administracion import (
    CambiarRoles,
    ConsultarMatriz,
    ConsultarUsuarios,
    GuardarPerfil,
)
from jml.aplicacion.casos.auditoria import ConsultarAuditoria, VerificarAuditoria
from jml.aplicacion.casos.consultas import ExportarCuentas
from jml.aplicacion.casos.listados import (
    ColaboradorPorDocumento,
    MiPerfil,
    MisSolicitudes,
    PendientesDeAprobacion,
    SolicitudesEnError,
    SubordinadosDe,
)
from jml.aplicacion.dtos import FiltroDeCuentas
from jml.dominio.errores import DatoInvalido, NoAutorizado
from jml.dominio.tipos import Rol
from tests.fabricas import perfil
from tests.mundo import Mundo, vacaciones

SIN_USUARIO = "el usuario no existe o esta inactivo"
SOLO_TECNICOS = "solo los roles tecnicos consultan esta informacion"


def _denegacion(llamada: Callable[[], object]) -> tuple[str, str]:
    with pytest.raises(NoAutorizado) as e:
        llamada()
    return e.value.accion, e.value.motivo


def test_las_denegaciones_de_administracion_dicen_accion_y_motivo() -> None:
    m = Mundo.nuevo()
    esperado = ("administracion", "solo el Administrador del sistema")
    llamadas: tuple[Callable[[], object], ...] = (
        lambda: ConsultarMatriz(m.puerto).ejecutar("u-col"),
        lambda: GuardarPerfil(m.puerto).ejecutar("u-col", perfil("TI", "Cali")),
        lambda: ConsultarUsuarios(m.puerto).ejecutar("u-col"),
        lambda: CambiarRoles(m.puerto).ejecutar("u-col", "u-col", frozenset({Rol.SOLICITANTE})),
    )
    assert [_denegacion(c) for c in llamadas] == [esperado] * 4


def test_las_denegaciones_de_la_auditoria_dicen_accion_y_motivo() -> None:
    m = Mundo.nuevo()
    esperado = ("auditoria", "solo el Auditor consulta la auditoria")
    for usuario in ("u-admin", "fantasma"):
        assert _denegacion(lambda u=usuario: ConsultarAuditoria(m.puerto).ejecutar(u)) == esperado  # type: ignore[misc]
        assert _denegacion(lambda u=usuario: VerificarAuditoria(m.puerto).ejecutar(u)) == esperado  # type: ignore[misc]


def test_la_pagina_de_la_auditoria_empieza_en_uno() -> None:
    m = Mundo.nuevo()
    with pytest.raises(DatoInvalido) as e:
        ConsultarAuditoria(m.puerto).ejecutar("u-aud", 0)
    assert (e.value.campo, e.value.motivo) == ("pagina", "empieza en 1")
    # la pagina 1 SI es valida (frontera): el cambio `< 1` por `<= 1` la rechazaria
    assert ConsultarAuditoria(m.puerto).ejecutar("u-aud", 1).pagina == 1


def test_la_consulta_de_un_usuario_inexistente_dice_consultar() -> None:
    m = Mundo.nuevo()
    esperado = ("consultar", SIN_USUARIO)
    assert _denegacion(lambda: m.dashboard("fantasma")) == esperado
    assert _denegacion(lambda: MiPerfil(m.puerto).ejecutar("fantasma")) == esperado
    assert _denegacion(lambda: SubordinadosDe(m.puerto).ejecutar("fantasma")) == esperado


def test_las_consultas_tecnicas_dicen_su_accion() -> None:
    m = Mundo.nuevo()
    dep = m._consulta
    assert _denegacion(lambda: m.dashboard("u-rrhh")) == ("dashboard", SOLO_TECNICOS)
    assert _denegacion(lambda: m.buscar("u-rrhh", FiltroDeCuentas())) == (
        "buscar_cuentas",
        SOLO_TECNICOS,
    )
    assert _denegacion(lambda: m.ficha("u-rrhh", "col-1")) == ("ficha", SOLO_TECNICOS)
    assert _denegacion(lambda: ExportarCuentas(dep).ejecutar("u-rrhh", FiltroDeCuentas())) == (
        "exportar_cuentas",
        SOLO_TECNICOS,
    )


def test_los_contratos_por_vencer_son_solo_de_rrhh() -> None:
    m = Mundo.nuevo()
    assert _denegacion(lambda: m.contratos_por_vencer("u-admin")) == (
        "contratos_por_vencer",
        "solo RRHH ve los contratos por vencer",
    )


def test_las_denegaciones_de_los_listados_dicen_accion_y_motivo() -> None:
    m = Mundo.nuevo()
    assert _denegacion(lambda: PendientesDeAprobacion(m.puerto).ejecutar("u-col")) == (
        "bandeja",
        "solo RRHH ve las pendientes de aprobacion",
    )
    assert _denegacion(lambda: ColaboradorPorDocumento(m.puerto).ejecutar("u-col", "10203040")) == (
        "buscar_colaborador",
        "solo quien emite busca por documento",
    )
    assert _denegacion(lambda: SolicitudesEnError(m.puerto).ejecutar("u-col")) == (
        "solicitudes_en_error",
        "solo el Administrador reintenta",
    )


def test_la_pagina_de_mis_solicitudes_empieza_en_uno() -> None:
    m = Mundo.nuevo()
    with pytest.raises(DatoInvalido) as e:
        MisSolicitudes(m.puerto).ejecutar("u-col", pagina=0)
    assert (e.value.campo, e.value.motivo) == ("pagina", "empieza en 1")
    assert MisSolicitudes(m.puerto).ejecutar("u-col", pagina=1).filas == ()  # frontera valida


def test_el_filtro_de_cuentas_dice_que_campo_es_invalido() -> None:
    with pytest.raises(DatoInvalido) as e:
        FiltroDeCuentas(pagina=0)
    assert (e.value.campo, e.value.motivo) == ("pagina", "empieza en 1")
    for tamano in (0, 101):
        with pytest.raises(DatoInvalido) as e:
            FiltroDeCuentas(tamano=tamano)
        assert (e.value.campo, e.value.motivo) == ("tamano", "entre 1 y 100")


def test_registrar_decidir_y_reintentar_con_usuario_inexistente_dicen_su_accion() -> None:
    m = Mundo.nuevo()
    sid = m.registrar(vacaciones()).solicitud_id
    assert _denegacion(lambda: m.registrar(vacaciones(usuario="fantasma"))) == (
        "registrar",
        SIN_USUARIO,
    )
    assert _denegacion(lambda: m.aprobar("fantasma", sid)) == ("decidir", SIN_USUARIO)
    assert _denegacion(lambda: m.rechazar("fantasma", sid, "x")) == ("decidir", SIN_USUARIO)
    assert _denegacion(lambda: m.cancelar("fantasma", sid)) == ("decidir", SIN_USUARIO)
    assert _denegacion(lambda: m.reintentar("fantasma", sid)) == ("reintentar", SIN_USUARIO)


def test_la_espera_de_reintento_exige_un_intento_fallido() -> None:
    with pytest.raises(DatoInvalido) as e:
        espera_de_reintento(0)
    assert (e.value.campo, e.value.motivo) == (
        "intentos_fallidos",
        "se espera al menos un intento fallido",
    )


def test_los_datos_invalidos_de_un_registro_dicen_su_campo() -> None:
    m = Mundo.nuevo()
    with pytest.raises(DatoInvalido) as e:
        m.registrar(replace(vacaciones(), colaborador_id=None))
    assert (e.value.campo, e.value.motivo) == ("colaborador_id", "obligatorio")
