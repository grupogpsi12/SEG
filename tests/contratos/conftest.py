"""Fabricas de implementaciones. Hoy solo la del doble en memoria.

Cuando exista el adaptador real (PostgreSQL, GLPI en contenedor, disco, Supabase Auth) se agrega
una fabrica aqui y TODAS las pruebas de contrato corren contra ella SIN modificarse (CLAUDE.md).
Si un adaptador necesita cambiar una prueba de contrato, el puerto esta mal.
"""

from collections.abc import Callable
from dataclasses import dataclass

import pytest

from jml.aplicacion.puertos import (
    AlmacenDeSoportes,
    ProveedorDeIdentidad,
    Repositorios,
    SistemaDeTickets,
)
from tests.contratos.protocolos import InyectorDeFallos, Tecnico
from tests.dobles.glpi import SistemaDeTicketsEnMemoria
from tests.dobles.identidad import CODIGO_VALIDO, ProveedorDeIdentidadEnMemoria
from tests.dobles.memoria import RepositoriosEnMemoria
from tests.dobles.reloj import RelojSimulado
from tests.dobles.soportes import AlmacenDeSoportesEnMemoria


@dataclass
class EntornoDeContrato:
    reloj: RelojSimulado
    repos: Repositorios
    glpi: SistemaDeTickets
    tecnico: Tecnico
    inyector: InyectorDeFallos
    soportes: AlmacenDeSoportes
    identidad: ProveedorDeIdentidad
    registrar_credenciales: Callable[[str, str, str], None]
    codigo_totp_valido: str


def fabrica_memoria() -> EntornoDeContrato:
    reloj = RelojSimulado()
    glpi = SistemaDeTicketsEnMemoria(reloj)
    identidad = ProveedorDeIdentidadEnMemoria()
    return EntornoDeContrato(
        reloj=reloj,
        repos=RepositoriosEnMemoria(reloj),
        glpi=glpi,
        tecnico=glpi,
        inyector=glpi,
        soportes=AlmacenDeSoportesEnMemoria(),
        identidad=identidad,
        registrar_credenciales=identidad.registrar,
        codigo_totp_valido=CODIGO_VALIDO,
    )


def fabrica_orm() -> EntornoDeContrato:
    """Repositorios reales (ORM de Django); los demas puertos siguen siendo dobles.

    Sin Docker corre sobre SQLite en memoria (tests/adaptadores/ajustes.py). Las reglas
    exclusivas de PostgreSQL (disparador, REVOKE, concurrencia) estan en tests/integracion.
    """
    from jml.adaptadores.salida.persistencia.repositorios import RepositoriosDjango

    base = fabrica_memoria()
    base.repos = RepositoriosDjango(base.reloj)
    return base


FABRICAS = {"memoria": fabrica_memoria, "orm": fabrica_orm}


@pytest.fixture(params=sorted(FABRICAS))
def entorno(request: pytest.FixtureRequest) -> EntornoDeContrato:
    return FABRICAS[request.param]()
