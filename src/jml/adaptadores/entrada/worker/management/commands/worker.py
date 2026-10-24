"""`python manage.py worker` (ciclo) y `worker --salud` (chequeo del contenedor, RNF-01)."""

import os
import signal
import time
from pathlib import Path
from typing import Any

import httpx
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from jml.adaptadores.entrada.worker.ciclo import Worker, esta_sano
from jml.adaptadores.entrada.worker.exportacion import exportar_ayer
from jml.adaptadores.salida.glpi.cliente import SistemaDeTicketsGlpi
from jml.adaptadores.salida.persistencia.repositorios import RepositoriosDjango
from jml.adaptadores.salida.reloj import RelojDelSistema
from jml.adaptadores.salida.soportes import AlmacenDeSoportesEnDisco
from jml.aplicacion.casos.auditoria import ExportarAuditoria
from jml.aplicacion.casos.bandeja import DependenciasDeBandeja, ProcesarBandeja
from jml.aplicacion.casos.sincronizar import (
    DependenciasDeSincronizacion,
    SincronizarActivos,
    SincronizarTickets,
)
from jml.aplicacion.puertos import SistemaDeTickets


def _secreto(nombre: str) -> str:
    """Los tokens de GLPI solo los monta el contenedor worker (CLAUDE.md: unico cliente de GLPI)."""
    ruta = Path(os.environ.get("JML_SECRETOS_DIR", "/run/secrets")) / nombre
    try:
        valor = ruta.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        valor = ""
    if not valor:
        raise CommandError(f"falta el secreto {nombre} (token de la API de GLPI, item 3.1)")
    return valor


def glpi_responde(url_api: str, cliente: httpx.Client | None = None) -> bool:
    """RNF-01: GLPI caido se detecta en menos de 2 minutos.

    El latido solo envejece tras 3 ciclos de sincronizacion (15 minutos), asi que el chequeo
    tambien pregunta a la raiz de la API. No necesita tokens: cualquier respuesta por debajo de
    500 prueba que GLPI esta arriba; un error de red o un 5xx, que no.
    """
    http = cliente or httpx.Client(timeout=5.0)
    try:
        return http.get(url_api.rstrip("/") + "/").status_code < 500
    except httpx.HTTPError:
        return False


def sistema_de_tickets() -> SistemaDeTickets:
    """Adaptador de la API v1 de GLPI (3.2, confirmado contra GLPI real en el spike 0.3)."""
    return SistemaDeTicketsGlpi(
        settings.JML_GLPI_API_URL,
        _secreto("glpi_app_token"),
        _secreto("glpi_user_token"),
        RelojDelSistema().ahora,
    )


def construir() -> Worker:
    reloj = RelojDelSistema()
    repos = RepositoriosDjango(reloj)
    glpi = sistema_de_tickets()
    soportes = AlmacenDeSoportesEnDisco(Path(settings.JML_SOPORTES_DIR))
    sync = DependenciasDeSincronizacion(repos, glpi, reloj)
    return Worker(
        bandeja=ProcesarBandeja(DependenciasDeBandeja(repos, glpi, soportes, reloj)).ejecutar,
        sincronizaciones=(
            SincronizarTickets(sync).ejecutar,
            SincronizarActivos(sync).ejecutar,
            lambda: exportar_ayer(
                ExportarAuditoria(repos), Path(settings.JML_EXPORTES_DIR), reloj.ahora()
            ),
        ),
        latido=Path(settings.JML_LATIDO_WORKER),
    )


class Command(BaseCommand):
    help = "Procesa la bandeja de salida a GLPI y sincroniza cada 5 minutos (ADR-011)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--salud", action="store_true", help="Chequeo de salud (RNF-01)")

    def handle(self, *args: Any, **opciones: Any) -> None:
        if opciones["salud"]:
            if not esta_sano(Path(settings.JML_LATIDO_WORKER), time.time()):
                raise CommandError("sin sincronizacion exitosa reciente")
            if not glpi_responde(settings.JML_GLPI_API_URL):
                raise CommandError("GLPI no responde")
            self.stdout.write("ok")
            return
        worker = construir()
        detenido = False

        def detener(*_: object) -> None:
            nonlocal detenido
            detenido = True  # termina la vuelta en curso y sale (docker stop)

        signal.signal(signal.SIGTERM, detener)
        worker.correr(lambda: not detenido)
