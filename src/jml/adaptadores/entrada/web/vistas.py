"""Vistas de infraestructura. Las de negocio solo validan, verifican el rol y llaman a un caso."""

import logging

from django.db import DatabaseError, connections
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET

registro = logging.getLogger(__name__)


@require_GET
def salud(request: HttpRequest) -> JsonResponse:
    """RNF-01: el chequeo de salud de `web` verifica la conexion con la base de datos.

    Responde sin detalles internos (RNF-02); el error real va al log con su correlation_id.
    """
    try:
        connections["default"].ensure_connection()
    except DatabaseError:
        registro.exception("la base de datos no responde")
        return JsonResponse({"estado": "no_disponible"}, status=503)
    return JsonResponse({"estado": "ok"})
