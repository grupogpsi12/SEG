"""App de Django de la entrada worker: el comando `python manage.py worker`."""

from django.apps import AppConfig


class WorkerConfig(AppConfig):
    name = "jml.adaptadores.entrada.worker"
    label = "worker"
