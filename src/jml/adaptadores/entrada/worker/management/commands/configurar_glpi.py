"""`python manage.py configurar_glpi`: GLPI como codigo (item 3.1). Idempotente.

Corre en el contenedor de una sola vez `configurar-glpi`, con el token de un ADMINISTRADOR de GLPI
(`glpi_admin_user_token`), que nunca monta el worker: el worker solo tiene la cuenta de servicio.
"""

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from jml.adaptadores.entrada.worker.management.commands.worker import _secreto
from jml.adaptadores.salida.glpi.configuracion import ConfiguradorGlpi
from jml.adaptadores.salida.reloj import RelojDelSistema
from jml.aplicacion.puertos import ErrorDeSistemaDeTickets


class Command(BaseCommand):
    help = "Crea en GLPI grupos, categorias, reglas, SLA de emergencia y plantillas (3.1)."

    def handle(self, *args: Any, **opciones: Any) -> None:
        configurador = ConfiguradorGlpi(
            settings.JML_GLPI_API_URL,
            _secreto("glpi_app_token"),
            _secreto("glpi_admin_user_token"),
            RelojDelSistema().ahora,
        )
        try:
            r = configurador.configurar()
        except ErrorDeSistemaDeTickets as e:
            raise CommandError(f"GLPI rechazo la configuracion: {e}") from None
        finally:
            configurador.cerrar()
        self.stdout.write(
            f"grupos: {r.grupos}; categorias: {r.categorias}; reglas: {r.reglas}; "
            f"plantillas: {r.plantillas}; SLA de emergencia: {r.sla_de_emergencia}"
        )
