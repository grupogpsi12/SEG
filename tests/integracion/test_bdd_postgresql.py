"""Gherkin que solo corre contra PostgreSQL real (`infra/scripts/integracion-local.sh`).

Los pasos invocan las pruebas de base de datos que ya existen (`test_postgresql.py` y
`test_roles_bd.py`): este archivo solo las une al texto trazable, no las repite.
"""

from pathlib import Path

import pytest
from pytest_bdd import given, scenario, then, when

from tests.integracion import test_postgresql as pg
from tests.integracion import test_roles_bd as roles

FEATURE = str(
    Path(__file__).resolve().parents[1] / "bdd" / "features" / "inmutabilidad-postgresql.feature"
)


@pytest.fixture
def hecho() -> dict[str, bool]:
    """Qué comprobaciones corrieron sin lanzar: lo que un `Entonces` verifica."""
    return {}


@pytest.mark.django_db
@scenario(FEATURE, "Adversarial — modificar una solicitud aprobada saltándose el repositorio")
def test_modificar_una_aprobada() -> None: ...


@pytest.mark.django_db
@scenario(FEATURE, "Adversarial — modificar o borrar el campo restringido de una aprobada")
def test_campo_restringido_de_una_aprobada() -> None: ...


@pytest.mark.django_db
@scenario(FEATURE, "Adversarial — borrar o modificar las tablas de solo inserción")
def test_tablas_de_solo_insercion() -> None: ...


@pytest.mark.django_db
@scenario(
    FEATURE, "Adversarial — el rol de la aplicación no apaga disparadores ni asume otros roles"
)
def test_sin_privilegios_de_dueno() -> None: ...


@pytest.mark.django_db
@scenario(FEATURE, "Borde — anon, authenticated y PUBLIC no tienen nada en el esquema")
def test_sin_acceso_ajeno() -> None: ...


@scenario(FEATURE, "Adversarial — dos altas simultáneas, una gana")
def test_altas_simultaneas() -> None: ...


@given("una solicitud aprobada en la base")
def _() -> None:
    """La crea la prueba invocada en el paso siguiente."""


@when("se intenta cambiar su fecha efectiva con el rol de la aplicación")
def _(hecho: dict[str, bool]) -> None:
    pg.test_RF_14_el_disparador_impide_cambiar_una_aprobada_aunque_se_salte_el_repositorio()
    hecho["rf14"] = True


@then("el disparador la rechaza y el contenido no cambia")
def _(hecho: dict[str, bool]) -> None:
    assert hecho["rf14"]


@when("se intenta cambiar o borrar su campo restringido con el rol de la aplicación")
def _(hecho: dict[str, bool]) -> None:
    pg.test_RF_14_el_campo_restringido_de_una_aprobada_tampoco_cambia()
    hecho["restringido"] = True


@then("el disparador lo rechaza en los dos casos")
def _(hecho: dict[str, bool]) -> None:
    assert hecho["restringido"]


@when(
    "el rol de la aplicación ejecuta UPDATE, DELETE y TRUNCATE sobre auditoria, decision y cuenta_historial"
)
def _(hecho: dict[str, bool]) -> None:
    for tabla in ("auditoria", "decision", "cuenta_historial"):
        pg.test_RD_02_app_backend_no_puede_modificar_las_tablas_de_solo_insercion(tabla)
        roles.test_BD_las_tablas_de_solo_insercion_no_dan_update_delete_ni_truncate(tabla)
    hecho["solo_insercion"] = True


@then("las tres sentencias fallan por falta de privilegio")
def _(hecho: dict[str, bool]) -> None:
    assert hecho["solo_insercion"]


@when("el rol de la aplicación intenta deshabilitar el disparador de solicitud y asumir anon")
def _(hecho: dict[str, bool]) -> None:
    roles.test_BD_app_backend_no_es_dueno_de_ninguna_tabla_y_no_apaga_disparadores()
    roles.test_BD_app_backend_no_puede_asumir_otro_rol("anon")
    hecho["sin_dueno"] = True


@then("ambas cosas fallan")
def _(hecho: dict[str, bool]) -> None:
    assert hecho["sin_dueno"]


@when("se consultan los privilegios de anon, authenticated, service_role y PUBLIC")
def _(hecho: dict[str, bool]) -> None:
    roles.test_BD_anon_authenticated_y_service_role_no_tienen_nada_en_el_esquema()
    roles.test_BD_PUBLIC_no_tiene_privilegios_sobre_el_esquema_ni_sus_tablas()
    hecho["sin_acceso"] = True


@then("ninguno tiene acceso al esquema ni a sus tablas")
def _(hecho: dict[str, bool]) -> None:
    assert hecho["sin_acceso"]


@then("todas las tablas tienen RLS activo y ninguna política")
def _() -> None:
    roles.test_BD_todas_las_tablas_tienen_rls_y_ninguna_politica()
    pg.test_RD_10_todas_las_tablas_tienen_RLS_activo()


@when("dos conexiones registran la misma solicitud a la vez", target_fixture="altas")
def _(base_con_commit: None) -> bool:
    pg.test_CA_01_dos_inserciones_concurrentes_solo_una_queda_abierta(base_con_commit)
    return True


@then("una queda abierta y la otra se rechaza como duplicada")
def _(altas: bool) -> None:
    assert altas
