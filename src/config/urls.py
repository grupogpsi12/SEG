"""Rutas de la aplicacion."""

from django.urls import path, re_path

from jml.adaptadores.entrada.web import ingreso, vistas

urlpatterns = [
    path("salud", vistas.salud, name="salud"),
    path("", vistas.inicio, name="inicio"),
    path("ingreso", ingreso.ingreso, name="ingreso"),
    path("ingreso/segundo-factor", ingreso.segundo_factor, name="segundo_factor"),
    path("salir", ingreso.salir, name="salir"),
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
