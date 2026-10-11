"""Rutas de la aplicacion."""

from django.urls import path

from jml.adaptadores.entrada.web import vistas

urlpatterns = [
    path("salud", vistas.salud, name="salud"),
]
