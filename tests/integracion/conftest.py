"""Base de pruebas para PostgreSQL real (Supabase de desarrollo, SRS 3.5), sin crear bases.

`app_backend` no puede crear bases ni esquemas (minimo privilegio). Por eso el administrador crea
UNA vez el esquema `app_test` a nombre de `app_backend` (ver docs/spikes/supabase.md) y aqui solo se
rehacen sus tablas con las migraciones y se vacian al terminar. Un duenio SI puede borrar objetos
aunque no tenga DELETE/TRUNCATE, de modo que RD-02 se prueba de verdad.
"""

import os
from collections.abc import Generator

import pytest
from django.conf import settings
from django.core.management import call_command
from django.db import connections

ESQUEMA = os.environ.get("JML_PG_ESQUEMA", "app_test")


def _alias() -> str:
    """El duenio migra y limpia (ADR-028); si no esta configurado, app_backend (base vieja)."""
    return "duenio" if "duenio" in settings.DATABASES else "default"


def _vaciar_esquema() -> None:
    """Borra tablas y funciones del esquema de pruebas (el duenio puede, aunque no tenga DELETE)."""
    with connections[_alias()].cursor() as c:
        c.execute(f'SET search_path = "{ESQUEMA}"')
        c.execute("SELECT tablename FROM pg_tables WHERE schemaname = %s", [ESQUEMA])
        for (tabla,) in c.fetchall():
            c.execute(f'DROP TABLE IF EXISTS "{ESQUEMA}"."{tabla}" CASCADE')
        c.execute(
            "SELECT p.oid::regprocedure::text FROM pg_proc p JOIN pg_namespace n "
            "ON n.oid = p.pronamespace WHERE n.nspname = %s",
            [ESQUEMA],
        )
        for (funcion,) in c.fetchall():
            c.execute(f"DROP FUNCTION IF EXISTS {funcion} CASCADE")


def _recrear_esquema() -> None:
    _vaciar_esquema()
    call_command("migrate", verbosity=0, interactive=False, database=_alias())


@pytest.fixture
def base_con_commit(django_db_setup: None, django_db_blocker: object) -> Generator[None]:
    """Para pruebas con hilos que confirman de verdad (CA-01).

    No usa `transaction=True`: Django limpiaria con TRUNCATE, que `app_backend` no puede hacer
    (RD-02). Al terminar se rehace el esquema.
    """
    with django_db_blocker.unblock():  # type: ignore[attr-defined]  # API de pytest-django
        yield
        _recrear_esquema()


@pytest.fixture(scope="session")
def django_db_setup(django_db_blocker: object) -> Generator[None]:
    with django_db_blocker.unblock():  # type: ignore[attr-defined]  # API de pytest-django
        _recrear_esquema()
    yield
    with django_db_blocker.unblock():  # type: ignore[attr-defined]
        _vaciar_esquema()
        connections.close_all()
