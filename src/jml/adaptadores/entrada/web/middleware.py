"""Middleware propio: correlation_id por peticion y la CSP de la aplicacion (RS-07, RS-09)."""

import re
import uuid
from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse

from jml.adaptadores.registro import CORRELACION

type Vista = Callable[[HttpRequest], HttpResponse]

# Las cabeceras son input no confiable (RS-05): solo se acepta un id con forma segura.
_ID_VALIDO = re.compile(r"^[A-Za-z0-9-]{8,64}$")


def correlacion(siguiente: Vista) -> Vista:
    def middleware(request: HttpRequest) -> HttpResponse:
        recibido = request.headers.get("X-Request-ID", "")
        identificador = recibido if _ID_VALIDO.fullmatch(recibido) else uuid.uuid4().hex
        marca = CORRELACION.set(identificador)
        try:
            respuesta = siguiente(request)
        finally:
            CORRELACION.reset(marca)
        respuesta["X-Request-ID"] = identificador
        return respuesta

    return middleware


def politica_de_contenido(siguiente: Vista) -> Vista:
    """La CSP de la aplicacion la envia Django; BunkerWeb la conserva (KEEP_UPSTREAM_HEADERS)."""

    def middleware(request: HttpRequest) -> HttpResponse:
        respuesta = siguiente(request)
        respuesta["Content-Security-Policy"] = settings.POLITICA_DE_CONTENIDO
        return respuesta

    return middleware
