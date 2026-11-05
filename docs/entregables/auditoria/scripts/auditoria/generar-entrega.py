"""F9: genera `docs/entregables/auditoria/` completa desde `auditoria/` (plan §15). Un comando regenera todo.

    uv run python auditoria/scripts/generar-entrega.py            # carpeta, informes .md y .pdf, README, manifiesto
    uv run python auditoria/scripts/generar-entrega.py --solo-pdf  # solo regenera los PDF y el manifiesto

Los informes se escriben en `auditoria/informes/*.md` con tres marcas que este script reemplaza (@@COMMIT@@,
@@TABLA_PRIORIDAD@@, @@TABLA_HALLAZGOS@@) para que las cifras salgan de los archivos y no de la memoria.
El PDF lo dibuja `reportlab`; `pillow` genera el gráfico de hallazgos por severidad.
Los `.pcap` NO se copian: contienen tokens y valores centinela.
"""

import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
import textwrap
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus import (
    Image as RLImage,
)

RAIZ = Path(__file__).resolve().parents[2]
AUD = RAIZ / "auditoria"
DEST = RAIZ / "docs" / "entregables" / "auditoria"
INFORMES = [
    "0-Informe-maestro",
    "1-Pruebas-y-cobertura",
    "2-Vulnerabilidades",
    "3-Analisis-de-trafico",
    "4-Controles-de-seguridad",
]
# Caracteres fuera de cp1252 (la fuente base de PDF): se escriben con su equivalente legible.
TRADUCCION = {
    "→": "->", "←": "<-", "↔": "<->", "≥": ">=", "≤": "<=", "≠": "!=", "≈": "~", "‖": "||", "✔": "OK", "✖": "no",
    "◐": "parcial", "○": "pendiente", "⛔": "bloqueado", "−": "-", "‑": "-", " ": " ", "ǁ": "|",
    "▲": "^", "…": "...", "‐": "-", "ʼ": "'", "⁻": "-", "¹": "1", "²": "2", "³": "3",
}  # fmt: skip


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=RAIZ, capture_output=True, text=True, check=True, encoding="utf-8"
    ).stdout.strip()


def sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


# --- marcas de los informes ----------------------------------------------------------------------


def tabla_de_prioridad() -> str:
    texto = (AUD / "score-global.md").read_text(encoding="utf-8")
    inicio = texto.index("| ID | Severidad")
    fin = texto.index("\n\n", inicio)
    return texto[inicio:fin]


def tabla_de_hallazgos() -> str:
    filas = ["| ID | Severidad | Título | Estado |", "|---|---|---|---|"]
    for ruta in sorted(
        (AUD / "hallazgos").glob("B-*.md"),
        key=lambda p: int(re.search(r"B-(\d+)", p.name).group(1)),
    ):  # type: ignore[union-attr]
        t = ruta.read_text(encoding="utf-8")
        m = re.match(r"# (B-\d+) · (\w+) — (.*)", t)
        estado = re.search(r"\*\*Estado:\*\*\s*([^\n]+)", t)
        assert m, ruta.name
        assert estado, ruta.name
        corto = re.split(r"\s+[—(]\s*|\s*\(", estado.group(1))[0].strip()
        filas.append(f"| {m.group(1)} | {m.group(2)} | {m.group(3).replace('|', '/')} | {corto} |")
    return "\n".join(filas)


def zap_directo() -> dict[str, str]:
    """Cifras de ZAP directo leidas de la evidencia registrada; si algun rol tiene FAIL, el informe no se genera."""
    salida = (
        AUD / "evidencia" / "vulnerabilidades" / "F6-09-ZAP-DIRECTO" / "salida.txt"
    ).read_text(encoding="utf-8")
    filas = re.findall(
        r"FAIL-NEW: (\d+)\s+FAIL-INPROG: \d+\s+WARN-NEW: (\d+).*?PASS: (\d+)", salida
    )
    if len(filas) != 2:
        sys.exit(f"ZAP directo: se esperaban 2 resumenes (RRHH y tecnico) y hay {len(filas)}")
    if any(int(f[0]) for f in filas):
        sys.exit("ZAP directo tiene FAIL: los informes afirman 0 y hay que reescribirlos")
    return {
        "@@ZAP_WARN_RRHH@@": filas[0][1], "@@ZAP_PASS_RRHH@@": filas[0][2],
        "@@ZAP_WARN_TEC@@": filas[1][1], "@@ZAP_PASS_TEC@@": filas[1][2],
    }  # fmt: skip


def resolver(texto: str) -> str:
    commit = git("rev-parse", "--short", "HEAD")
    fecha = datetime.now().strftime("%d/%m/%Y")  # hora local del equipo, como el resto del proyecto
    texto = (
        texto.replace("@@COMMIT@@", f"commit `{commit}` · generado el {fecha}")
        .replace("@@TABLA_PRIORIDAD@@", tabla_de_prioridad())
        .replace("@@TABLA_HALLAZGOS@@", tabla_de_hallazgos())
    )
    if "@@ZAP_" in texto:
        for marca, valor in zap_directo().items():
            texto = texto.replace(marca, valor)
    return texto


# --- gráfico con pillow ------------------------------------------------------------------------------


def grafico_de_hallazgos(destino: Path) -> None:
    metricas = json.loads((AUD / "metricas.json").read_text(encoding="utf-8"))["hallazgos"]
    datos = [("Críticos", metricas["criticos"], "#7a1f1f"), ("Altos", metricas["altos"], "#b3472a"),
             ("Medios", metricas["medios"], "#d89b2b"), ("Bajos", metricas["bajos"], "#4f7cac"),
             ("Informativos", metricas["informativos"], "#8a96a8")]  # fmt: skip
    ancho, alto = 900, 360
    img = Image.new("RGB", (ancho, alto), "white")
    d = ImageDraw.Draw(img)
    try:
        fuente = ImageFont.truetype("arial.ttf", 18)
        fuente_g = ImageFont.truetype("arial.ttf", 22)
    except OSError:
        fuente = fuente_g = ImageFont.load_default()
    d.text(
        (20, 14),
        f"Hallazgos por severidad ({metricas['total']} en total)",
        fill="#1d2733",
        font=fuente_g,
    )
    maximo = max(v for _, v, _ in datos) or 1
    for i, (nombre, valor, color) in enumerate(datos):
        y = 70 + i * 54
        largo = int(520 * valor / maximo)
        d.text((20, y + 8), nombre, fill="#1d2733", font=fuente)
        d.rectangle([180, y, 180 + max(largo, 2), y + 36], fill=color)
        d.text((190 + largo, y + 8), str(valor), fill="#1d2733", font=fuente)
    img.save(destino)


# --- Markdown -> PDF -----------------------------------------------------------------------------------


def limpio(texto: str) -> str:
    salida = []
    for c in texto:
        c = TRADUCCION.get(c, c)
        try:
            c.encode("cp1252")
        except UnicodeEncodeError:
            c = "?"
        salida.append(c)
    return "".join(salida)


def inline(texto: str) -> str:
    codigo: list[str] = []

    def guardar(m: re.Match[str]) -> str:
        codigo.append(m.group(1))
        return "@@C" + str(len(codigo) - 1) + "@@"

    t = re.sub(
        r"`([^`]+)`", guardar, limpio(texto)
    )  # el codigo no se interpreta como negrita ni cursiva
    t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    t = re.sub(r"[*][*]([^*]+)[*][*]", lambda m: "<b>" + m.group(1) + "</b>", t)
    t = re.sub(r"(?<![\w*])[*]([^*]+)[*](?![\w*])", lambda m: "<i>" + m.group(1) + "</i>", t)

    def devolver(m: re.Match[str]) -> str:
        c = codigo[int(m.group(1))].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return '<font face="Courier" size="8">' + c + "</font>"

    return re.sub(r"@@C(\d+)@@", devolver, t)


def estilos() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    n = ParagraphStyle(
        "n",
        parent=base["BodyText"],
        fontName="Helvetica",
        fontSize=9.2,
        leading=12.4,
        alignment=TA_LEFT,
        spaceAfter=4,
    )
    return {
        "n": n,
        "leyenda": ParagraphStyle(
            "leyenda",
            parent=n,
            fontName="Helvetica-Bold",
            keepWithNext=1,
            spaceBefore=4,
            spaceAfter=3,
        ),
        "h1": ParagraphStyle(
            "h1",
            parent=n,
            fontName="Helvetica-Bold",
            fontSize=19,
            leading=23,
            spaceAfter=8,
            textColor=colors.HexColor("#1f3b66"),
        ),
        "h2": ParagraphStyle(
            "h2",
            keepWithNext=1,
            parent=n,
            fontName="Helvetica-Bold",
            fontSize=13.5,
            leading=17,
            spaceBefore=10,
            spaceAfter=5,
            textColor=colors.HexColor("#1f3b66"),
        ),
        "h3": ParagraphStyle(
            "h3",
            keepWithNext=1,
            parent=n,
            fontName="Helvetica-Bold",
            fontSize=10.8,
            leading=14,
            spaceBefore=6,
            spaceAfter=3,
        ),
        "li": ParagraphStyle("li", parent=n, leftIndent=14, bulletIndent=4, spaceAfter=2),
        "celda": ParagraphStyle("celda", parent=n, fontSize=7.6, leading=9.4, spaceAfter=0),
        "cab": ParagraphStyle(
            "cab",
            parent=n,
            fontName="Helvetica-Bold",
            fontSize=7.6,
            leading=9.4,
            spaceAfter=0,
            textColor=colors.white,
        ),
    }


def anchos_de_columna(filas: list[list[str]], columnas: int, ancho_util: float) -> list[float]:
    """Reparte el ancho: cada columna recibe al menos lo que ocupa su palabra mas larga (sin partirla) y el resto se
    reparte segun cuanto texto tiene. Si ni los minimos caben, se escalan."""
    ancho_car = 4.3  # puntos por caracter a 7,6 pt (mayusculas y negrita incluidas)
    relleno = 8.0
    minimos, deseados = [], []
    for i in range(columnas):
        celdas = [re.sub(r"[`*]", "", f[i]) for f in filas]
        mas_larga = max((len(w) for c in celdas for w in c.split()), default=1)
        total = max((len(c) for c in celdas), default=1)
        minimos.append(mas_larga * ancho_car + relleno)
        deseados.append(min(total, 70) * ancho_car + relleno)
    if sum(minimos) >= ancho_util:
        escala = ancho_util / sum(minimos)
        return [m * escala for m in minimos]
    sobra = ancho_util - sum(minimos)
    falta = [max(d - m, 0.0) for d, m in zip(deseados, minimos, strict=True)]
    reparto = sum(falta) or 1.0
    return [m + sobra * f / reparto for m, f in zip(minimos, falta, strict=True)]


def tabla(filas: list[list[str]], est: dict[str, ParagraphStyle], ancho_util: float) -> Table:
    columnas = max(len(f) for f in filas)
    filas = [f + [""] * (columnas - len(f)) for f in filas]
    anchos = anchos_de_columna(filas, columnas, ancho_util)
    datos = [
        [Paragraph(inline(c), est["cab" if i == 0 else "celda"]) for c in f]
        for i, f in enumerate(filas)
    ]
    t = Table(datos, colWidths=anchos, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3b66")),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#b8c2d0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f5f9")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))  # fmt: skip
    return t


def md_a_pdf(
    md: str,
    destino: Path,
    titulo: str,
    grafico: Path | None = None,
    base: Path | None = None,
    pie_prefijo: str = "JML · Auditoría",
) -> None:
    est = estilos()
    pagina_ancho = A4[0] - 4 * cm
    historia: list = []
    lineas = md.splitlines()
    i = 0
    parrafo: list[str] = []

    def vaciar() -> None:
        if parrafo:
            leyenda = parrafo[0].startswith(("**Tabla", "**Figura"))
            historia.append(
                Paragraph(
                    "<br/>".join(inline(p) for p in parrafo), est["leyenda" if leyenda else "n"]
                )
            )
            parrafo.clear()

    while i < len(lineas):
        linea = lineas[i]
        if linea.startswith("```"):
            vaciar()
            bloque = []
            i += 1
            while i < len(lineas) and not lineas[i].startswith("```"):
                bloque.extend(
                    textwrap.wrap(limpio(lineas[i]), 105, subsequent_indent="    ") or [""]
                )
                i += 1
            historia.append(
                Preformatted(
                    "\n".join(bloque),
                    ParagraphStyle(
                        "cod",
                        fontName="Courier",
                        fontSize=7.2,
                        leading=8.8,
                        backColor=colors.HexColor("#f2f5f9"),
                        leftIndent=4,
                    ),
                )
            )
            historia.append(Spacer(1, 4))
        elif linea.startswith("|"):
            vaciar()
            filas = []
            while i < len(lineas) and lineas[i].startswith("|"):
                celdas = [c.strip() for c in re.split(r"(?<!\\)\|", lineas[i].strip())[1:-1]]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in celdas):
                    filas.append([c.replace("\\|", "|") for c in celdas])
                i += 1
            historia.append(tabla(filas, est, pagina_ancho))
            historia.append(Spacer(1, 6))
            continue
        elif linea.startswith("# "):
            vaciar()
            historia.append(Paragraph(inline(linea[2:]), est["h1"]))
            if grafico is not None and "maestro" in titulo.lower():
                pass
        elif linea.startswith("## "):
            vaciar()
            historia.append(Paragraph(inline(linea[3:]), est["h2"]))
        elif linea.startswith("### "):
            vaciar()
            historia.append(Paragraph(inline(linea[4:]), est["h3"]))
        elif linea.startswith("![") and base is not None:
            vaciar()
            m = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", linea)
            if m and (base / m.group(2)).exists():
                with Image.open(base / m.group(2)) as im:
                    ancho_px, alto_px = im.size
                if m.group(1).startswith("Figura"):
                    # Las figuras llevan texto pequeno: en una pagina apaisada, a todo el ancho, se leen sin lupa.
                    ancho_h = landscape(A4)[0] - 3 * cm
                    historia += [NextPageTemplate("apaisada"), PageBreak()]
                    historia.append(
                        RLImage(
                            str(base / m.group(2)),
                            width=ancho_h,
                            height=ancho_h * alto_px / ancho_px,
                        )
                    )
                    historia += [NextPageTemplate("normal"), PageBreak()]
                else:
                    historia.append(
                        RLImage(
                            str(base / m.group(2)),
                            width=pagina_ancho,
                            height=pagina_ancho * alto_px / ancho_px,
                        )
                    )
                    historia.append(Spacer(1, 6))
        elif re.match(r"^(\s*)([-*]|\d+\.)\s+", linea):
            vaciar()
            m = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)", linea)
            assert m
            marca = "•" if m.group(2) in "-*" else m.group(2)
            historia.append(Paragraph(inline(m.group(3)), est["li"], bulletText=limpio(marca)))
        elif linea.strip() == "---" or not linea.strip():
            vaciar()
        elif linea.strip() == "@@GRAFICO@@":
            vaciar()
            if grafico is not None:
                historia.append(RLImage(str(grafico), width=14 * cm, height=14 * cm * 360 / 900))
        else:
            parrafo.append(linea)
        i += 1
    vaciar()

    def pie(canvas, doc) -> None:  # type: ignore[no-untyped-def]
        ancho_pagina = canvas._pagesize[0]
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#52606d"))
        canvas.drawString(2 * cm, 1.1 * cm, limpio(f"{pie_prefijo} · {titulo}"))
        canvas.drawRightString(ancho_pagina - 2 * cm, 1.1 * cm, f"Página {doc.page}")
        canvas.restoreState()

    doc = BaseDocTemplate(
        str(destino),
        pagesize=A4,
        title=limpio(titulo),
        author="Grupo D01 · Politécnico Grancolombiano",
    )
    vertical = Frame(2 * cm, 1.8 * cm, A4[0] - 4 * cm, A4[1] - 3.6 * cm, id="v")
    horizontal = Frame(
        1.5 * cm, 1.8 * cm, landscape(A4)[0] - 3 * cm, landscape(A4)[1] - 3.6 * cm, id="h"
    )
    doc.addPageTemplates(
        [
            PageTemplate(id="normal", frames=[vertical], onPage=pie, pagesize=A4),
            PageTemplate(id="apaisada", frames=[horizontal], onPage=pie, pagesize=landscape(A4)),
        ]
    )
    doc.build(historia)


# --- carpeta de entrega -----------------------------------------------------------------------------------


def copiar(origen: Path, destino: Path, excluir: tuple[str, ...] = ()) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    if origen.is_dir():
        shutil.copytree(
            origen,
            destino,
            ignore=shutil.ignore_patterns("*.pcap", "__pycache__", "*.pyc", *excluir),
            dirs_exist_ok=True,
        )
    else:
        shutil.copy2(origen, destino)


def armar() -> None:
    if DEST.exists():
        shutil.rmtree(DEST)
    for d in ("informes", "evidencias", "scripts", "hallazgos", "anexos"):
        (DEST / d).mkdir(parents=True)
    # evidencias por tipo (los .pcap no viajan)
    for tipo in sorted((AUD / "evidencia").iterdir()):
        if tipo.is_dir():
            copiar(tipo, DEST / "evidencias" / tipo.name)
        else:
            copiar(tipo, DEST / "evidencias" / "estaticos" / tipo.name)
    copiar(AUD / "matriz-authz.csv", DEST / "evidencias" / "autorizacion" / "matriz-authz.csv")
    for nombre in ("hallazgos",):
        copiar(AUD / nombre, DEST / nombre)
    # scripts: los de la auditoria, las herramientas y los de infraestructura que invocan
    copiar(AUD / "scripts", DEST / "scripts" / "auditoria")
    copiar(AUD / "herramientas", DEST / "scripts" / "herramientas")
    copiar(AUD / "laboratorio", DEST / "scripts" / "laboratorio")
    copiar(RAIZ / "infra" / "scripts", DEST / "scripts" / "infra")
    copiar(RAIZ / "infra" / "waf" / "pruebas.sh", DEST / "scripts" / "infra" / "waf-pruebas.sh")
    # raiz de la entrega
    for nombre in (
        "trazabilidad.csv",
        "metricas.json",
        "asvs-l2.csv",
        "herramientas.lock",
        "dread-anclas.md",
    ):
        copiar(AUD / nombre, DEST / nombre)
    for nombre in ("score-global.md", "propuestas-adr.md", "defectos-sembrados.md", "triage-f6.md", "exenciones-trivy.md",
                   "revision-manual-f2-08.md", "verificacion-anexo-a.md", "verificacion-anexo-a-excel.md", "anexo-a-matriz.csv",
                   "estado-auditoria.md"):  # fmt: skip
        if (AUD / nombre).exists():
            copiar(AUD / nombre, DEST / "anexos" / nombre)
    copiar(AUD / "referencias" / "AnexoA-tablas.json", DEST / "anexos" / "AnexoA-tablas.json")
    copiar(AUD / "referencias" / "AnexoA-tablas.sha256", DEST / "anexos" / "AnexoA-tablas.sha256")
    copiar(AUD / "herramientas" / "verificar_entrega.py", DEST / "verificar-entrega.py")
    copiar(AUD / "herramientas" / "marcadores.py", DEST / "marcadores.py")


def informes(solo_pdf: bool) -> None:
    grafico = DEST / "informes" / "hallazgos-por-severidad.png"
    grafico_de_hallazgos(grafico)
    for nombre in INFORMES:
        fuente = AUD / "informes" / f"{nombre}.md"
        if not fuente.exists():
            sys.exit(f"falta el informe fuente {fuente}")
        md = resolver(fuente.read_text(encoding="utf-8"))
        publico = md.replace(
            "@@GRAFICO@@", "![Hallazgos por severidad](hallazgos-por-severidad.png)"
        )
        (DEST / "informes" / f"{nombre}.md").write_text(publico, encoding="utf-8", newline="\n")
        md_a_pdf(md, DEST / "informes" / f"{nombre}.pdf", nombre.replace("-", " "), grafico)


def readme() -> None:
    commit = git("rev-parse", "--short", "HEAD")
    texto = f"""# Entrega de la auditoría · Sistema integrado de eventos laborales (JML)

Andina Servicios S.A.S. es una empresa ficticia y todos los datos lo son. Politécnico Grancolombiano · Gerencia de Proyectos en Seguridad de la Información · Grupo D01.

Generada el {datetime.now().strftime("%d/%m/%Y")} desde el commit `{commit}` de la rama `auditoria/entrega` (base auditada: `5fa3f32`). Todo lo de esta carpeta se regenera con un comando: `uv run python auditoria/scripts/generar-entrega.py`.

## Qué hay aquí

| Ruta | Contenido |
|---|---|
| `informes/0-Informe-maestro` | El informe extenso: alcance, método, resultados, hallazgos por prioridad, remediación y lo que queda pendiente (`.md` y `.pdf`) |
| `informes/1-Pruebas-y-cobertura` | Suite, cobertura de ramas, mutación, Gherkin, defectos sembrados |
| `informes/2-Vulnerabilidades` | Estático, dependencias, imágenes, escaneo dinámico, red, bases, TLS, WAF |
| `informes/3-Analisis-de-trafico` | Capturas por tramo, centinelas, tokens en claro |
| `informes/4-Controles-de-seguridad` | Controles por propiedad, criterios de aceptación CA-01 a CA-21, ASVS y el Excel del Anexo A |
| `evidencias/` | `funcionales`, `estaticos`, `vulnerabilidades`, `trafico`, `autorizacion`, `disponibilidad`, `controles-positivos`. Cada carpeta lleva `cmd.txt`, `salida.txt`, `version.txt`, `commit.txt`, `fecha-utc.txt` y `codigo.txt` |
| `hallazgos/B-nn.md` | Un archivo por hallazgo, con DREAD, evidencia, corrección, prueba de regresión, falsabilidad e indicador temprano |
| `scripts/` | Los guiones que generan la evidencia y los PDF |
| `anexos/` | Puntajes DREAD, propuestas de ADR, defectos sembrados, triage, verificación del Anexo A (PDF y Excel) |
| `trazabilidad.csv`, `metricas.json`, `asvs-l2.csv`, `herramientas.lock`, `dread-anclas.md` | Datos de la auditoría |
| `manifiesto.sha256` | El hash de cada archivo de esta carpeta |
| `verificar-entrega.py` | Falla si hay un marcador sin reemplazar, un criterio de aceptación sin evidencia o un hash que no cuadra |

## Cómo comprobarla

```bash
python docs/entregables/auditoria/verificar-entrega.py docs/entregables/auditoria
```

## Lo que NO se incluye

- Los archivos `.pcap` de las capturas de tráfico: llevan tokens de GLPI y valores centinela. Se conservan el comando, el análisis enmascarado y el hash.
- Cualquier secreto. Los valores están enmascarados y `gitleaks` se corrió sobre esta carpeta.

## Alcance y reglas de compromiso

Solo el stack local de Docker. GLPI 11 desechable. Supabase únicamente en lectura de catálogo, autorizada por el equipo el 24/10/2026. Nada de Azure, Cloudflare ni terceros. Antes de cada escáner: copia de la base, worker detenido, baneos levantados y un identificador de correlación de laboratorio; después, restauración.
"""
    (DEST / "README.md").write_text(texto, encoding="utf-8", newline="\n")


def manifiesto() -> None:
    lineas = []
    for ruta in sorted(DEST.rglob("*")):
        if ruta.is_file() and ruta.name != "manifiesto.sha256":
            lineas.append(f"{sha256(ruta)}  {ruta.relative_to(DEST).as_posix()}")
    (DEST / "manifiesto.sha256").write_text(
        "\n".join(lineas) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"manifiesto: {len(lineas)} archivos")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    solo_pdf = "--solo-pdf" in sys.argv
    if not solo_pdf:
        armar()
    else:
        (DEST / "informes").mkdir(parents=True, exist_ok=True)
    informes(solo_pdf)
    if not solo_pdf:
        readme()
    manifiesto()
    csv_filas = sum(1 for _ in csv.reader((AUD / "trazabilidad.csv").open(encoding="utf-8"))) - 1
    print(f"entrega en {DEST.relative_to(RAIZ)} · trazabilidad {csv_filas} filas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
