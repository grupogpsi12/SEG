"""F3-BD (T5, T13, invariantes 2, 3 y 8): lo que cada rol puede y no puede hacer en la base.

Corre como `app_backend` (el rol de la aplicación) contra PostgreSQL real. Cada aserción falla si
se quita el control correspondiente: el dueño separado (ADR-028), los REVOKE de la migración 0002,
los disparadores y la ausencia de permisos de `anon`, `authenticated`, `service_role` y PUBLIC.
"""

import os

import pytest
from django.db import DatabaseError, connection, transaction

pytestmark = [pytest.mark.seguridad, pytest.mark.django_db]

ESQUEMA = os.environ.get("JML_PG_ESQUEMA", "app_test")
ROLES_AJENOS = ["anon", "authenticated", "service_role"]
SOLO_INSERCION = ["auditoria", "decision", "cuenta_historial"]
PRIVILEGIOS = ["SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"]


def _tablas() -> list[str]:
    with connection.cursor() as c:
        c.execute("SELECT tablename FROM pg_tables WHERE schemaname = %s ORDER BY 1", [ESQUEMA])
        tablas = [t for (t,) in c.fetchall()]
    assert "solicitud" in tablas, "las migraciones no se aplicaron: la prueba no vigilaría nada"
    return tablas


def _debe_fallar(sql: str, motivo: str) -> None:
    with pytest.raises(DatabaseError, match=motivo), transaction.atomic(), connection.cursor() as c:
        c.execute(sql)


def test_BD_app_backend_no_es_superusuario_ni_crea_roles_ni_bases() -> None:
    with connection.cursor() as c:
        c.execute(
            "SELECT rolsuper, rolcreaterole, rolcreatedb, rolreplication FROM pg_roles "
            "WHERE rolname = current_user"
        )
        assert c.fetchone() == (False, False, False, False)


def test_BD_app_backend_no_es_dueno_de_ninguna_tabla_y_no_apaga_disparadores() -> None:
    with connection.cursor() as c:
        c.execute(
            "SELECT count(*) FROM pg_tables WHERE schemaname = %s AND tableowner = current_user",
            [ESQUEMA],
        )
        assert c.fetchone() == (0,)
    _debe_fallar(f'ALTER TABLE "{ESQUEMA}".solicitud DISABLE TRIGGER USER', "must be owner")
    _debe_fallar(f'ALTER TABLE "{ESQUEMA}".solicitud DISABLE TRIGGER ALL', "must be owner")


def test_BD_app_backend_no_crea_ni_borra_objetos_del_esquema() -> None:
    _debe_fallar(f'CREATE TABLE "{ESQUEMA}".intruso (id int)', "permission denied for schema")
    _debe_fallar(f'DROP TABLE "{ESQUEMA}".solicitud', "must be owner")
    _debe_fallar(f'ALTER TABLE "{ESQUEMA}".solicitud DISABLE ROW LEVEL SECURITY', "must be owner")


@pytest.mark.parametrize("rol", ["app_owner", *ROLES_AJENOS, "postgres"])
def test_BD_app_backend_no_puede_asumir_otro_rol(rol: str) -> None:
    _debe_fallar(f"SET ROLE {rol}", "permission denied|does not exist")


@pytest.mark.parametrize("tabla", SOLO_INSERCION)
def test_BD_las_tablas_de_solo_insercion_no_dan_update_delete_ni_truncate(tabla: str) -> None:
    with connection.cursor() as c:
        for privilegio in ("UPDATE", "DELETE", "TRUNCATE"):
            c.execute(
                "SELECT has_table_privilege(current_user, %s, %s)",
                [f'"{ESQUEMA}"."{tabla}"', privilegio],
            )
            assert c.fetchone() == (False,), (tabla, privilegio)
        c.execute(
            "SELECT has_table_privilege(current_user, %s, 'INSERT')", [f'"{ESQUEMA}"."{tabla}"']
        )
        assert c.fetchone() == (True,), f"{tabla} debe seguir aceptando inserciones"


def test_BD_anon_authenticated_y_service_role_no_tienen_nada_en_el_esquema() -> None:
    with connection.cursor() as c:
        for rol in ROLES_AJENOS:
            c.execute("SELECT has_schema_privilege(%s, %s, 'USAGE')", [rol, ESQUEMA])
            assert c.fetchone() == (False,), rol
            for tabla in _tablas():
                for privilegio in PRIVILEGIOS:
                    c.execute(
                        "SELECT has_table_privilege(%s, %s, %s)",
                        [rol, f'"{ESQUEMA}"."{tabla}"', privilegio],
                    )
                    assert c.fetchone() == (False,), (rol, tabla, privilegio)


def test_BD_PUBLIC_no_tiene_privilegios_sobre_el_esquema_ni_sus_tablas() -> None:
    with connection.cursor() as c:
        c.execute(
            "SELECT count(*) FROM pg_namespace n, aclexplode(n.nspacl) a "
            "WHERE n.nspname = %s AND a.grantee = 0",
            [ESQUEMA],
        )
        assert c.fetchone() == (0,)
        c.execute(
            "SELECT count(*) FROM pg_class k JOIN pg_namespace n ON n.oid = k.relnamespace, "
            "aclexplode(k.relacl) a WHERE n.nspname = %s AND a.grantee = 0",
            [ESQUEMA],
        )
        assert c.fetchone() == (0,)


def test_BD_todas_las_tablas_tienen_rls_y_ninguna_politica() -> None:
    with connection.cursor() as c:
        c.execute(
            "SELECT relname FROM pg_class k JOIN pg_namespace n ON n.oid = k.relnamespace "
            "WHERE n.nspname = %s AND k.relkind = 'r' AND NOT k.relrowsecurity",
            [ESQUEMA],
        )
        assert c.fetchall() == [], "tablas sin RLS"
        c.execute("SELECT count(*) FROM pg_policies WHERE schemaname = %s", [ESQUEMA])
        assert c.fetchone() == (0,), "las políticas abrirían lo que RLS cierra"


def test_BD_los_disparadores_de_inmutabilidad_existen_y_estan_activos() -> None:
    with connection.cursor() as c:
        c.execute(
            "SELECT k.relname, t.tgname, t.tgenabled FROM pg_trigger t "
            "JOIN pg_class k ON k.oid = t.tgrelid JOIN pg_namespace n ON n.oid = k.relnamespace "
            "WHERE n.nspname = %s AND NOT t.tgisinternal",
            [ESQUEMA],
        )
        disparadores = c.fetchall()
    assert {r for r, _, _ in disparadores} >= {"solicitud", "solicitud_restringida"}
    assert all(estado == "O" for _, _, estado in disparadores), disparadores
