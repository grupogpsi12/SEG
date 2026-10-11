"""Rutas de la aplicacion."""

from django.urls import path, re_path

from jml.adaptadores.entrada.web import administracion, ingreso, tecnicos, vistas

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
    path("dashboard", tecnicos.dashboard, name="dashboard"),
    path("auditoria", vistas.auditoria, name="auditoria"),
    path("errores", vistas.en_error, name="en_error"),
    path("administracion/perfiles", administracion.perfiles, name="admin_perfiles"),
    path("administracion/perfil", administracion.editar_perfil, name="admin_perfil"),
    path("administracion/usuarios", administracion.usuarios, name="admin_usuarios"),
    path(
        "administracion/usuarios/<str:usuario>/roles",
        administracion.cambiar_roles,
        name="admin_roles",
    ),
    re_path(
        r"^solicitudes/(?P<solicitud>SOL-\d{4}-\d{6})/reintentar$",
        vistas.reintentar,
        name="reintentar",
    ),
    path("cuentas", tecnicos.cuentas, name="cuentas"),
    path("cuentas.csv", tecnicos.cuentas_csv, name="cuentas_csv"),
    path("colaboradores/<str:colaborador>", tecnicos.ficha, name="ficha"),
    re_path(r"^solicitudes/(?P<solicitud>SOL-\d{4}-\d{6})$", vistas.detalle, name="detalle"),
    re_path(
        r"^solicitudes/(?P<solicitud>SOL-\d{4}-\d{6})/(?P<accion>aprobar|rechazar|cancelar)$",
        vistas.decidir,
        name="decidir",
    ),
]
