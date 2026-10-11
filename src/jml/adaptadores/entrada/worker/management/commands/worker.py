"""`python manage.py worker` (ciclo) y `worker --salud` (chequeo del contenedor, RNF-01)."""

import signal
import time
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from jml.adaptadores.entrada.worker.ciclo import Worker, esta_sano
from jml.adaptadores.salida.persistencia.repositorios import RepositoriosDjango
from jml.adaptadores.salida.reloj import RelojDelSistema
from jml.adaptadores.salida.soportes import AlmacenDeSoportesEnDisco
from jml.aplicacion.casos.bandeja import DependenciasDeBandeja, ProcesarBandeja
from jml.aplicacion.casos.sincronizar import (
    DependenciasDeSincronizacion,
    SincronizarActivos,
    SincronizarTickets,
)
from jml.aplicacion.puertos import SistemaDeTickets


def sistema_de_tickets() -> SistemaDeTickets:
    """El adaptador de GLPI llega con el item 3.2 (despues del spike 0.3)."""
    raise CommandError("el adaptador de GLPI todavia no existe (item 3.2 de tasks/todo.md)")


def construir() -> Worker:
    reloj = RelojDelSistema()
    repos = RepositoriosDjango(reloj)
    glpi = sistema_de_tickets()
    soportes = AlmacenDeSoportesEnDisco(Path(settings.JML_SOPORTES_DIR))
    sync = DependenciasDeSincronizacion(repos, glpi, reloj)
    return Worker(
        bandeja=ProcesarBandeja(DependenciasDeBandeja(repos, glpi, soportes, reloj)).ejecutar,
        sincronizaciones=(SincronizarTickets(sync).ejecutar, SincronizarActivos(sync).ejecutar),
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
            self.stdout.write("ok")
            return
        worker = construir()
        detenido = False

        def detener(*_: object) -> None:
            nonlocal detenido
            detenido = True  # termina la vuelta en curso y sale (docker stop)

        signal.signal(signal.SIGTERM, detener)
        worker.correr(lambda: not detenido)
