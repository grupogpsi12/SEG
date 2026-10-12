"""Graficos SVG generados en el servidor a partir de numeros (4.2, ADR-018, invariante 11).

Sin JavaScript ni bibliotecas. Es el UNICO lugar donde se usa `mark_safe` (CLAUDE.md lo permite
solo para este SVG): las etiquetas pasan por `escape` y los valores son enteros, de modo que
ningun dato de la base llega al SVG sin escapar.
"""

from collections.abc import Sequence

from django.utils.html import escape
from django.utils.safestring import SafeString, mark_safe

ALTO_BARRA = 22
ANCHO_ETIQUETA = 190
ANCHO_BARRAS = 300


def barras(
    titulo: str, datos: Sequence[tuple[str, int]], resaltar: str | None = None
) -> SafeString:
    """Barras horizontales. `resaltar`: la etiqueta que se pinta con el color de acento (RF-31)."""
    maximo = max((v for _, v in datos), default=0) or 1
    alto = ALTO_BARRA * max(len(datos), 1) + 8
    filas: list[str] = []
    for i, (etiqueta, valor) in enumerate(datos):
        y = 4 + i * ALTO_BARRA
        largo = round(ANCHO_BARRAS * int(valor) / maximo)
        clase = "barra resaltada" if etiqueta == resaltar else "barra"
        x, alto_barra = ANCHO_ETIQUETA, ALTO_BARRA - 6
        filas.append(
            f'<text x="{x - 6}" y="{y + 15}" text-anchor="end">{escape(etiqueta)}</text>'
            f'<rect class="{clase}" x="{x}" y="{y + 3}" width="{largo}" height="{alto_barra}"/>'
            f'<text x="{x + largo + 6}" y="{y + 15}">{int(valor)}</text>'
        )
    if not datos:
        filas.append('<text x="8" y="18">Sin datos</text>')
    ancho = ANCHO_ETIQUETA + ANCHO_BARRAS + 60
    # mark_safe: SVG construido aqui con enteros y etiquetas escapadas (ver docstring del modulo).
    return mark_safe(  # nosec B308 B703
        f'<svg class="grafico" role="img" aria-label="{escape(titulo)}"'
        f' viewBox="0 0 {ancho} {alto}" width="100%" preserveAspectRatio="xMinYMin meet" xmlns="http://www.w3.org/2000/svg">'
        f"<title>{escape(titulo)}</title>{''.join(filas)}</svg>"
    )
