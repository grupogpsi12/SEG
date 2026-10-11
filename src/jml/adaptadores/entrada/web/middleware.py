"""Middleware propio: proxy confiable, correlation_id y CSP (RS-05, RS-07, RS-09)."""

import contextlib
import ipaddress
import re
import uuid
from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse

from jml.adaptadores.registro import CORRELACION

type Vista = Callable[[HttpRequest], HttpResponse]

# Las cabeceras son input no confiable (RS-05): solo se acepta un id con forma segura.
_ID_VALIDO = re.compile(r"^[A-Za-z0-9-]{8,64}$")


def proxy_confiable(siguiente: Vista) -> Vista:
    """RS-05: `X-Forwarded-For` y `X-Forwarded-Proto` solo valen si la peticion viene de BunkerWeb.

    Si la conexion llega de una IP de `JML_PROXIES_CONFIABLES` (la IP fija del contenedor
    bunkerweb), se toma la ultima IP de `X-Forwarded-For` (la que agrego BunkerWeb) como cliente
    y el esquema de `X-Forwarded-Proto`. De cualquier otro origen las cabeceras se descartan.
    No se usa `SECURE_PROXY_SSL_HEADER`, que confiaria en la cabecera venga de donde venga.
    """
    confiables = frozenset(settings.JML_PROXIES_CONFIABLES)

    def middleware(request: HttpRequest) -> HttpResponse:
        meta = request.META
        reenviado = meta.pop("HTTP_X_FORWARDED_FOR", "")
        esquema = meta.pop("HTTP_X_FORWARDED_PROTO", "")
        if meta.get("REMOTE_ADDR") in confiables:
            cliente = reenviado.split(",")[-1].strip()
            # cabecera ausente o invalida: queda la IP de BunkerWeb
            with contextlib.suppress(ValueError):
                meta["REMOTE_ADDR"] = str(ipaddress.ip_address(cliente))
            if esquema in ("http", "https"):
                meta["wsgi.url_scheme"] = esquema
        return siguiente(request)

    return middleware


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
