"""Capitulos II y III: dibuja el diagrama de Gantt con pillow y genera los PDF de `docs/entregables/capitulos/`.

    uv run python auditoria/scripts/generar-capitulos.py

Las fechas del Gantt salen de los commits del repositorio (primero: 10/10/2026) y de los ADR fechados (05, 07, 10 y 11/10/2026).
Los textos son los `.md` de la misma carpeta; este guion no los modifica.
"""

import importlib.util
import sys
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

RAIZ = Path(__file__).resolve().parents[2]
CARPETA = RAIZ / "docs" / "entregables" / "capitulos"

# (nombre, desde, hasta, grupo) con el dia de octubre de 2026
TAREAS = [
    ("Especificación (SRS) y ADR 001–022", 5, 7, "doc"),
    ("Pruebas técnicas previas (spikes): GLPI, BunkerWeb, Supabase", 7, 11, "doc"),
    ("Fase 1 · Núcleo: dominio y aplicación (Hito N)", 10, 10, "dev"),
    ("Fase 2 · Adaptadores, web, identidad y WAF", 10, 12, "dev"),
    ("Fase 3 · Integración con GLPI 11", 11, 12, "dev"),
    ("Fase 4 · Dashboard y búsqueda", 11, 12, "dev"),
    ("Auditoría interna de funcionalidad y seguridad", 12, 12, "aud"),
    ("Reportería del WAF (RNF-16)", 21, 21, "dev"),
    ("Evidencias de entrega y Entrega 3", 24, 24, "dev"),
    ("Auditoría F0–F2: línea base y análisis estático", 24, 24, "aud"),
    ("Auditoría F3–F6: pruebas de seguridad, Gherkin, caja negra", 24, 25, "aud"),
    ("Auditoría F7–F8: red, tráfico, mutación, DREAD", 25, 25, "aud"),
    ("Anexo A (Excel), Entrega 3 repetida y empaquetado F9", 25, 25, "aud"),
    ("Capítulos II y III", 25, 25, "doc"),
]
COLORES = {"doc": "#5b8c5a", "dev": "#4f7cac", "aud": "#d89b2b"}
DIAS = list(range(5, 27))


def gantt(destino: Path) -> None:
    izq, ancho_dia, alto_fila, arriba = 520, 44, 34, 78
    ancho = izq + ancho_dia * len(DIAS) + 20
    alto = arriba + alto_fila * len(TAREAS) + 70
    img = Image.new("RGB", (ancho, alto), "white")
    d = ImageDraw.Draw(img)
    try:
        f, fg = ImageFont.truetype("arial.ttf", 15), ImageFont.truetype("arial.ttf", 20)
    except OSError:
        f = fg = ImageFont.load_default()
    d.text((16, 14), "Cronograma del proyecto · octubre de 2026", fill="#1d2733", font=fg)
    for i, dia in enumerate(DIAS):
        x = izq + i * ancho_dia
        fin_de_semana = date(2026, 10, dia).weekday() >= 5
        if fin_de_semana:
            d.rectangle(
                [x, arriba - 20, x + ancho_dia, arriba + alto_fila * len(TAREAS)], fill="#eef1f5"
            )
        d.text(
            (x + 12, arriba - 42), "LMXJVSD"[date(2026, 10, dia).weekday()], fill="#52606d", font=f
        )
        d.text((x + 10, arriba - 22), f"{dia:02d}", fill="#1d2733", font=f)
        d.line([x, arriba - 20, x, arriba + alto_fila * len(TAREAS)], fill="#d5dbe3")
    for k, (nombre, a, b, grupo) in enumerate(TAREAS):
        y = arriba + k * alto_fila
        d.line([16, y + alto_fila, ancho - 20, y + alto_fila], fill="#e4e8ee")
        d.text((16, y + 8), nombre, fill="#1d2733", font=f)
        x0 = izq + DIAS.index(a) * ancho_dia + 3
        x1 = izq + (DIAS.index(b) + 1) * ancho_dia - 3
        d.rounded_rectangle([x0, y + 5, x1, y + alto_fila - 5], radius=4, fill=COLORES[grupo])
    y = arriba + alto_fila * len(TAREAS) + 20
    for i, (texto, clave) in enumerate(
        (("Documentación y decisiones", "doc"), ("Desarrollo", "dev"), ("Auditoría", "aud"))
    ):
        x = 16 + i * 250
        d.rectangle([x, y, x + 20, y + 16], fill=COLORES[clave])
        d.text((x + 28, y), texto, fill="#1d2733", font=f)
    d.text(
        (16, y + 28),
        "Fechas tomadas de los commits y de los ADR fechados; las barras de un día son trabajo concentrado en esa jornada.",
        fill="#52606d",
        font=f,
    )
    img.save(destino)


def main() -> int:
    CARPETA.mkdir(parents=True, exist_ok=True)
    gantt(CARPETA / "gantt.png")
    spec = importlib.util.spec_from_file_location(
        "generar_entrega", RAIZ / "auditoria" / "scripts" / "generar-entrega.py"
    )
    assert spec is not None
    assert spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    for nombre in ("Capitulo-II-Ejecucion", "Capitulo-III-Resultados"):
        md = (CARPETA / f"{nombre}.md").read_text(encoding="utf-8")
        modulo.md_a_pdf(md, CARPETA / f"{nombre}.pdf", nombre.replace("-", " "), None, CARPETA)
        print(f"{nombre}.pdf: {(CARPETA / f'{nombre}.pdf').stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
