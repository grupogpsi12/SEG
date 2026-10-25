"""Enumera las rutas de `config.urls` con una URL de ejemplo para cada una (F3-U03, F3-U07, F5)."""

from django.urls import URLPattern, get_resolver, reverse

# Ejemplos para los parámetros; una ruta nueva con un parámetro que no esté aquí hace fallar la
# prueba con un KeyError: obliga a revisar la matriz de autorización.
EJEMPLOS = {
    "tipo": "VAC",
    "solicitud": "SOL-2026-000001",
    "accion": "aprobar",
    "usuario": "u-ana",
    "colaborador": "col-1",
}


def rutas() -> dict[str, str]:
    """nombre de la ruta -> URL de ejemplo (con `/` inicial)."""
    salida: dict[str, str] = {}
    for p in get_resolver().url_patterns:
        assert isinstance(p, URLPattern), (
            "las rutas anidadas no están contempladas: agregarlas aquí"
        )
        assert p.name is not None, "toda ruta debe tener nombre"
        parametros = set(p.pattern.regex.groupindex) | set(getattr(p.pattern, "converters", {}))
        salida[p.name] = reverse(p.name, kwargs={k: EJEMPLOS[k] for k in sorted(parametros)})
    return salida
