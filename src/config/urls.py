"""Rutas de la aplicacion."""

from django.urls import path, re_path

from jml.adaptadores.entrada.web import vistas

urlpatterns = [
    path("salud", vistas.salud, name="salud"),
    path("", vistas.inicio, name="inicio"),
    path("solicitudes", vistas.solicitudes, name="solicitudes"),
    path("solicitudes/nueva", vistas.nueva_indice, name="nueva_indice"),
    path("solicitudes/nueva/<str:tipo>", vistas.nueva, name="nueva"),
    path("bandeja", vistas.bandeja, name="bandeja"),
    re_path(
        r"^solicitudes/(?P<solicitud>SOL-\d{4}-\d{6})/(?P<accion>aprobar|rechazar|cancelar)$",
        vistas.decidir,
        name="decidir",
    ),
]
