"""Utilidades compartidas para los cuatro informes de la entrega 3 (ReportLab).

No contiene datos de los informes: solo estilos, portada, encabezados, tablas, cajas de hallazgo y
un ayudante de imagen. Cada informe (informe_1..4.py) aporta su propio contenido.
"""

from __future__ import annotations

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.flowables import HRFlowable
from reportlab.platypus.frames import Frame
from reportlab.platypus.doctemplate import PageTemplate
from PIL import Image as PILImage

# Paleta sobria y consistente entre los cuatro informes.
AZUL = colors.HexColor("#0C447C")
AZUL_CLARO = colors.HexColor("#E6F1FB")
GRIS = colors.HexColor("#444441")
GRIS_CLARO = colors.HexColor("#F1EFE8")
LINEA = colors.HexColor("#D3D1C7")
VERDE = colors.HexColor("#0F6E56")
VERDE_CLARO = colors.HexColor("#E1F5EE")
AMBAR = colors.HexColor("#854F0B")
AMBAR_CLARO = colors.HexColor("#FAEEDA")
ROJO = colors.HexColor("#A32D2D")
ROJO_CLARO = colors.HexColor("#FCEBEB")

SEV_COLOR = {
    "Crítica": (ROJO, ROJO_CLARO),
    "Alta": (ROJO, ROJO_CLARO),
    "Media": (AMBAR, AMBAR_CLARO),
    "Baja": (VERDE, VERDE_CLARO),
    "Informativa": (AZUL, AZUL_CLARO),
}

PROYECTO = "Sistema integrado de eventos laborales (JML)"
EMPRESA = "Andina Servicios S.A.S. (empresa ficticia · datos ficticios)"
CURSO = "Politécnico Grancolombiano · Gerencia de Proyectos en Seguridad de la Información · Grupo D01"
FECHA = "24 de octubre de 2026"


def estilos() -> dict[str, ParagraphStyle]:
    s = getSampleStyleSheet()
    base = s["BodyText"]
    base.fontName = "Helvetica"
    base.fontSize = 9.5
    base.leading = 14
    base.spaceAfter = 6
    base.textColor = colors.HexColor("#2C2C2A")
    d = {"cuerpo": base}
    d["h1"] = ParagraphStyle("h1", parent=base, fontName="Helvetica-Bold", fontSize=15,
                             leading=19, textColor=AZUL, spaceBefore=10, spaceAfter=8)
    d["h2"] = ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=11.5,
                             leading=15, textColor=GRIS, spaceBefore=10, spaceAfter=5)
    d["h3"] = ParagraphStyle("h3", parent=base, fontName="Helvetica-Bold", fontSize=10,
                             leading=13, textColor=AZUL, spaceBefore=6, spaceAfter=3)
    d["cita"] = ParagraphStyle("cita", parent=base, fontName="Courier", fontSize=8,
                               leading=10.5, textColor=GRIS, leftIndent=6, spaceAfter=4)
    d["pie_tabla"] = ParagraphStyle("pt", parent=base, fontSize=8, leading=10.5,
                                    textColor=GRIS, spaceAfter=8)
    d["celda"] = ParagraphStyle("celda", parent=base, fontSize=8.5, leading=11.5, spaceAfter=0)
    d["celda_mono"] = ParagraphStyle("cm", parent=base, fontName="Courier", fontSize=7.8,
                                     leading=10, spaceAfter=0)
    d["celda_b"] = ParagraphStyle("cb", parent=base, fontName="Helvetica-Bold", fontSize=8.5,
                                  leading=11.5, spaceAfter=0, textColor=colors.white)
    d["titulo_portada"] = ParagraphStyle("tp", parent=base, fontName="Helvetica-Bold",
                                         fontSize=22, leading=27, textColor=AZUL, alignment=TA_CENTER)
    d["sub_portada"] = ParagraphStyle("sp", parent=base, fontSize=13, leading=18,
                                      textColor=GRIS, alignment=TA_CENTER)
    d["meta_portada"] = ParagraphStyle("mp", parent=base, fontSize=10, leading=15,
                                       textColor=GRIS, alignment=TA_CENTER)
    return d


class _Doc(SimpleDocTemplate):
    def __init__(self, ruta: str, titulo_corto: str) -> None:
        super().__init__(ruta, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
                         topMargin=2 * cm, bottomMargin=1.8 * cm, title=titulo_corto,
                         author="Grupo D01 — Arch-Sentinel")
        self.titulo_corto = titulo_corto
        marco = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="normal")
        self.addPageTemplates([PageTemplate(id="con_pie", frames=[marco], onPage=self._pie)])

    def _pie(self, canvas, doc) -> None:
        canvas.saveState()
        canvas.setStrokeColor(LINEA)
        canvas.setLineWidth(0.5)
        canvas.line(self.leftMargin, 1.4 * cm, A4[0] - self.rightMargin, 1.4 * cm)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(GRIS)
        canvas.drawString(self.leftMargin, 1.05 * cm, f"{PROYECTO} · {self.titulo_corto}")
        canvas.drawRightString(A4[0] - self.rightMargin, 1.05 * cm, f"Página {doc.page}")
        canvas.restoreState()


def portada(est: dict, numero: str, titulo: str, descripcion: str) -> list:
    return [
        Spacer(1, 3.2 * cm),
        Paragraph(f"Entrega 3 · Documento {numero}", est["meta_portada"]),
        Spacer(1, 0.5 * cm),
        Paragraph(titulo, est["titulo_portada"]),
        Spacer(1, 0.6 * cm),
        HRFlowable(width="55%", thickness=1, color=AZUL, hAlign="CENTER"),
        Spacer(1, 0.6 * cm),
        Paragraph(descripcion, est["sub_portada"]),
        Spacer(1, 2.4 * cm),
        Paragraph(PROYECTO, est["meta_portada"]),
        Paragraph(EMPRESA, est["meta_portada"]),
        Spacer(1, 0.3 * cm),
        Paragraph(CURSO, est["meta_portada"]),
        Paragraph(FECHA, est["meta_portada"]),
        Spacer(1, 1.6 * cm),
        Paragraph(
            "Todas las pruebas se ejecutaron contra el despliegue local del sistema "
            "(BunkerWeb + aplicación + PostgreSQL + GLPI 11 + MariaDB en Docker Compose). "
            "No se ejecutaron pruebas activas contra servicios de terceros (Supabase). "
            "Los secretos y tokens de las evidencias están enmascarados.",
            est["meta_portada"],
        ),
        PageBreak(),
    ]


def tabla(datos: list[list], anchos: list[float], est: dict, cabecera: bool = True,
          zebra: bool = True, sev_col: int | None = None) -> Table:
    filas = []
    for i, fila in enumerate(datos):
        nueva = []
        for celda in fila:
            if isinstance(celda, Paragraph):
                nueva.append(celda)
            else:
                estilo = est["celda_b"] if (cabecera and i == 0) else est["celda"]
                nueva.append(Paragraph(str(celda), estilo))
        filas.append(nueva)
    t = Table(filas, colWidths=anchos, repeatRows=1 if cabecera else 0)
    cmds = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINEA),
        ("LINEBEFORE", (0, 0), (-1, -1), 0.4, LINEA),
        ("LINEAFTER", (0, 0), (-1, -1), 0.4, LINEA),
        ("LINEABOVE", (0, 0), (-1, 0), 0.4, LINEA),
    ]
    if cabecera:
        cmds.append(("BACKGROUND", (0, 0), (-1, 0), AZUL))
    inicio = 1 if cabecera else 0
    for i in range(inicio, len(datos)):
        if zebra and (i - inicio) % 2 == 1:
            cmds.append(("BACKGROUND", (0, i), (-1, i), GRIS_CLARO))
        if sev_col is not None:
            texto = datos[i][sev_col]
            if isinstance(texto, Paragraph):
                texto = texto.getPlainText()
            col = SEV_COLOR.get(str(texto).strip())
            if col:
                cmds.append(("BACKGROUND", (sev_col, i), (sev_col, i), col[1]))
                cmds.append(("TEXTCOLOR", (sev_col, i), (sev_col, i), col[0]))
                cmds.append(("FONTNAME", (sev_col, i), (sev_col, i), "Helvetica-Bold"))
    t.setStyle(TableStyle(cmds))
    return t


def caja_hallazgo(est: dict, ident: str, titulo: str, severidad: str, filas: list[tuple[str, str]]) -> Table:
    col, fondo = SEV_COLOR.get(severidad, (GRIS, GRIS_CLARO))
    enc = Table([[Paragraph(f"<b>{ident} · {titulo}</b>", ParagraphStyle(
        "hh", fontName="Helvetica-Bold", fontSize=10, textColor=colors.white, leading=13)),
        Paragraph(f"<b>{severidad}</b>", ParagraphStyle(
            "hs", fontName="Helvetica-Bold", fontSize=9, textColor=col, leading=12, alignment=2))]],
        colWidths=[12.6 * cm, 4.4 * cm])
    enc.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), col), ("BACKGROUND", (1, 0), (1, 0), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.5, col), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 6)]))
    cuerpo = []
    for etiqueta, texto in filas:
        cuerpo.append([Paragraph(f"<b>{etiqueta}</b>", est["celda"]),
                       Paragraph(texto, est["celda"])])
    tb = Table(cuerpo, colWidths=[3.1 * cm, 13.9 * cm])
    tb.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("BACKGROUND", (0, 0), (-1, -1), fondo),
        ("BOX", (0, 0), (-1, -1), 0.5, col), ("LINEBELOW", (0, 0), (-1, -2), 0.3, LINEA),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    cont = Table([[enc], [tb]], colWidths=[17 * cm])
    cont.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                              ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
                              ("TOPPADDING", (0, 1), (-1, 1), 0)]))
    return KeepTogether(cont)


def figura(ruta: str, est: dict, pie: str, ancho_cm: float = 15.5, borde: bool = True) -> list:
    w, h = PILImage.open(ruta).size
    ancho = ancho_cm * cm
    alto = ancho * h / w
    maximo = 19 * cm
    if alto > maximo:
        alto = maximo
        ancho = alto * w / h
    img = Image(ruta, width=ancho, height=alto)
    img.hAlign = "CENTER"
    salida = [img]
    if borde:
        contenedor = Table([[img]], colWidths=[ancho])
        contenedor.hAlign = "CENTER"
        contenedor.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, LINEA),
                                        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
        salida = [contenedor]
    salida.append(Paragraph(f"<b>Figura.</b> {pie}", est["pie_tabla"]))
    return salida


def bloque_mono(est: dict, titulo: str, texto: str) -> Table:
    cuerpo = [[Paragraph(f"<b>{titulo}</b>", ParagraphStyle(
        "bmh", fontName="Helvetica-Bold", fontSize=8, textColor=colors.white, leading=11))]]
    for linea in texto.strip("\n").split("\n"):
        linea = linea.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        cuerpo.append([Paragraph(linea or "&nbsp;", ParagraphStyle(
            "bm", fontName="Courier", fontSize=7.4, leading=9.6, textColor=colors.HexColor("#1b1b1a")))])
    t = Table(cuerpo, colWidths=[17 * cm])
    estilos_t = [
        ("BACKGROUND", (0, 0), (0, 0), GRIS), ("BACKGROUND", (0, 1), (0, -1), colors.HexColor("#F7F6F1")),
        ("BOX", (0, 0), (-1, -1), 0.5, LINEA), ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5), ("TOPPADDING", (0, 0), (0, 0), 4),
        ("BOTTOMPADDING", (0, 0), (0, 0), 4)]
    t.setStyle(TableStyle(estilos_t))
    return t


def construir(ruta: str, titulo_corto: str, historia: list) -> None:
    _Doc(ruta, titulo_corto).build(historia)
    print("escrito:", ruta)
