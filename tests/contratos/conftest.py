"""Fabricas de implementaciones. Hoy solo la del doble en memoria.

Cuando exista el adaptador real (PostgreSQL, GLPI en contenedor, disco, Supabase Auth) se agrega
una fabrica aqui y TODAS las pruebas de contrato corren contra ella SIN modificarse (CLAUDE.md).
Si un adaptador necesita cambiar una prueba de contrato, el puerto esta mal.
"""

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

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


def fabrica_memoria(directorio: Path) -> EntornoDeContrato:
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


def fabrica_orm(directorio: Path) -> EntornoDeContrato:
    """Adaptadores reales: repositorios sobre el ORM, soportes en disco (`tmp_path`) e identidad
    sobre la API de Supabase Auth (contra un GoTrue simulado; la prueba real esta en integracion).

    GLPI y reloj siguen siendo dobles hasta el spike 0.3.

    Sin Docker corre sobre SQLite en memoria (tests/adaptadores/ajustes.py). Las reglas
    exclusivas de PostgreSQL (disparador, REVOKE, concurrencia) estan en tests/integracion.
    """
    from jml.adaptadores.salida.identidad.supabase import ProveedorSupabase
    from jml.adaptadores.salida.persistencia.repositorios import RepositoriosDjango
    from jml.adaptadores.salida.soportes import AlmacenDeSoportesEnDisco
    from tests.dobles.gotrue import CLAVE_PUBLICA, GoTrueSimulado

    base = fabrica_memoria(directorio)
    base.repos = RepositoriosDjango(base.reloj)
    base.soportes = AlmacenDeSoportesEnDisco(directorio)
    gotrue = GoTrueSimulado()
    base.identidad = ProveedorSupabase("https://x.supabase.co", CLAVE_PUBLICA, gotrue.cliente())
    base.registrar_credenciales = gotrue.registrar
    return base


def fabrica_glpi_api(directorio: Path) -> EntornoDeContrato:
    """El adaptador REAL de GLPI (API v1) contra un GLPI simulado (3.2; contra GLPI real, la
    fabrica `glpi_real`). Lo demas es el doble en memoria: existe por SistemaDeTickets."""
    from jml.adaptadores.salida.glpi.cliente import SistemaDeTicketsGlpi
    from tests.dobles.glpi_api import APP_TOKEN, BASE, USER_TOKEN, GlpiSimulado

    base = fabrica_memoria(directorio)
    glpi = GlpiSimulado()
    base.glpi = SistemaDeTicketsGlpi(BASE, APP_TOKEN, USER_TOKEN, base.reloj.ahora, glpi.cliente())
    base.tecnico = glpi
    base.inyector = glpi
    return base


def fabrica_glpi_real(directorio: Path) -> EntornoDeContrato:
    """El adaptador REAL contra un GLPI REAL (spike 0.3). Solo se registra si estan las variables
    de entorno: se corre dentro de la red de Docker (docs/spikes/glpi-puerto.md)."""
    import httpx

    from jml.adaptadores.salida.glpi.cliente import SistemaDeTicketsGlpi
    from tests.dobles.glpi_real import TecnicoGlpiReal, TransporteConFallos

    url, app = os.environ["JML_GLPI_API_URL"], os.environ["JML_GLPI_APP_TOKEN"]
    base = fabrica_memoria(directorio)
    transporte = TransporteConFallos(httpx.HTTPTransport())
    base.glpi = SistemaDeTicketsGlpi(
        url,
        app,
        os.environ["JML_GLPI_USER_TOKEN"],
        base.reloj.ahora,
        httpx.Client(transport=transporte, timeout=60.0),
    )
    base.tecnico = TecnicoGlpiReal(url, app, os.environ["JML_GLPI_ADMIN_TOKEN"])
    base.tecnico.limpiar()
    base.inyector = transporte
    return base


FABRICAS = {"memoria": fabrica_memoria, "orm": fabrica_orm, "glpi_api": fabrica_glpi_api}
if "JML_GLPI_API_URL" in os.environ:
    FABRICAS["glpi_real"] = fabrica_glpi_real


@pytest.fixture(params=sorted(FABRICAS))
def entorno(request: pytest.FixtureRequest, tmp_path: Path) -> EntornoDeContrato:
    return FABRICAS[request.param](tmp_path)
