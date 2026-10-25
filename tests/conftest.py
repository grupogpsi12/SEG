"""Perfiles de hypothesis: `mutacion` es determinista y mas corto, para que mutmut sea estable."""

import os
import re
from pathlib import Path

import pytest
from hypothesis import HealthCheck, settings

settings.register_profile(
    "mutacion",
    derandomize=True,
    max_examples=25,
    deadline=None,
    suppress_health_check=list(HealthCheck),
    database=None,
)
settings.register_profile("ci", deadline=None, suppress_health_check=[HealthCheck.too_slow])
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "ci"))


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """La fabrica `orm` de la suite de contrato usa la base de pruebas de pytest-django.

    Se marca en la coleccion (y aqui, en el conftest raiz, para que aplique a toda corrida)
    porque pytest-django no prepara la base si la pide un fixture parametrizado.
    """
    for item in items:
        llamada = getattr(item, "callspec", None)
        if llamada is not None and llamada.params.get("entorno") == "orm":
            item.add_marker(pytest.mark.django_db)


if os.environ.get("JML_PG_HOST"):
    # Contra PostgreSQL real no se crean bases (app_backend no puede): se usa el esquema app_test.
    from tests.integracion.conftest import base_con_commit, django_db_setup  # noqa: F401


def pytest_configure(config: pytest.Config) -> None:
    """Las etiquetas de los `.feature` (@T1, @RF-01…) son marcadores de pytest; con
    `--strict-markers` hay que declararlas. Se leen de los propios archivos: una etiqueta mal
    escrita falla en el trazado (tests/bdd/test_trazabilidad.py), no aqui."""
    for feature in (Path(__file__).parent / "bdd" / "features").glob("*.feature"):
        for etiqueta in set(re.findall(r"(?<!\S)@([\w.-]+)", feature.read_text(encoding="utf-8"))):
            config.addinivalue_line("markers", f"{etiqueta}: etiqueta de Gherkin")
