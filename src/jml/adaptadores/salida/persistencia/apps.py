"""Configuracion de la app de persistencia."""

from django.apps import AppConfig


class PersistenciaConfig(AppConfig):
    name = "jml.adaptadores.salida.persistencia"
    label = "persistencia"
    default_auto_field = "django.db.models.BigAutoField"
