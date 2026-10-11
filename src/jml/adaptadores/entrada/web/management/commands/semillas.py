"""`python manage.py semillas`: carga los datos ficticios de RD-07. Se puede repetir sin efecto."""

from typing import Any

from django.core.management.base import BaseCommand

from jml.adaptadores.entrada.web.semillas import aplicar
from jml.adaptadores.salida.persistencia.repositorios import RepositoriosDjango
from jml.adaptadores.salida.reloj import RelojDelSistema


class Command(BaseCommand):
    help = "Carga la matriz de perfiles y los colaboradores ficticios (idempotente)."

    def handle(self, *args: Any, **opciones: Any) -> None:
        r = aplicar(RepositoriosDjango(RelojDelSistema()))
        self.stdout.write(f"perfiles actualizados: {r.perfiles}; colaboradores: {r.colaboradores}")
