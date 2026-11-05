"""Diagramas de arquitectura de seguridad (ReportLab Graphics, vectoriales) para el Documento 4."""

from __future__ import annotations

from reportlab.graphics.shapes import Drawing, Group, Line, PolyLine, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.units import cm

import comun as c

ANCHO = 17 * cm


def _texto(g, x, y, t, size=8.5, bold=False, col=colors.HexColor("#2C2C2A"), anchor="middle") -> None:
    g.add(String(x, y, t, fontName="Helvetica-Bold" if bold else "Helvetica",
                 fontSize=size, fillColor=col, textAnchor=anchor))


def _caja(g, x, y, w, hh, titulo, sub, fill, borde, tcol) -> None:
    g.add(Rect(x, y, w, hh, rx=5, ry=5, fillColor=fill, strokeColor=borde, strokeWidth=0.8))
    if sub:
        _texto(g, x + w / 2, y + hh - 13, titulo, 8.6, True, tcol)
        _texto(g, x + w / 2, y + 7, sub, 7.2, False, tcol)
    else:
        _texto(g, x + w / 2, y + hh / 2 - 3, titulo, 8.4, True, tcol)


def _flecha(g, x1, y1, x2, y2, col=c.GRIS, etiqueta="", dash=False) -> None:
    ln = Line(x1, y1, x2, y2, strokeColor=col, strokeWidth=1.1)
    if dash:
        ln.strokeDashArray = [2, 2]
    g.add(ln)
    import math
    ang = math.atan2(y2 - y1, x2 - x1)
    L = 5
    g.add(Polygon([x2, y2,
                   x2 - L * math.cos(ang - 0.5), y2 - L * math.sin(ang - 0.5),
                   x2 - L * math.cos(ang + 0.5), y2 - L * math.sin(ang + 0.5)],
                  fillColor=col, strokeColor=col))
    if etiqueta:
        _texto(g, (x1 + x2) / 2, (y1 + y2) / 2 + 3, etiqueta, 6.6, False, c.GRIS)


def arquitectura() -> Drawing:
    """Defensa en profundidad: capas desde el usuario hasta los datos, con el control de cada tramo."""
    W, H = ANCHO, 13.2 * cm
    d = Drawing(W, H)
    g = Group()
    cx = W / 2
    bw = 13.4 * cm
    bx = cx - bw / 2
    bh = 1.1 * cm
    gap = 0.95 * cm  # espacio para las flechas entre filas

    # Posiciones (borde inferior de cada caja), de arriba hacia abajo.
    y_user = H - 0.35 * cm - bh
    y_waf = y_user - 1.3 * cm - bh   # hueco mayor: aloja la frontera de confianza
    y_app = y_waf - gap - bh
    y_wrk = y_app - gap - bh
    y_dat = y_wrk - 1.3 * cm - bh

    _caja(g, bx, y_user, bw, bh, "Usuario (navegador)", "Sesión Django · cookie Secure/HttpOnly/SameSite", c.GRIS_CLARO, c.LINEA, c.GRIS)
    _caja(g, bx, y_waf, bw, bh, "Borde — BunkerWeb (WAF)", "TLS 1.3 · ModSecurity + OWASP CRS 4 · límite de peticiones · HSTS", c.AZUL_CLARO, c.AZUL, c.AZUL)
    _caja(g, bx, y_app, bw, bh, "Aplicación — Django + Gunicorn", "Autorización por rol · formularios · CSP · campos restringidos aislados", c.VERDE_CLARO, c.VERDE, c.VERDE)
    _caja(g, bx, y_wrk, bw, bh, "Worker (único cliente de GLPI)", "Outbox idempotente · soporte PDF validado · sin campos restringidos", c.VERDE_CLARO, c.VERDE, c.VERDE)

    # Flecha usuario <-> WAF (HTTPS, doble sentido) sobre el eje central
    xh = cx - 0.3 * cm
    _flecha(g, xh, y_user, xh, y_waf + bh, c.AZUL)
    _flecha(g, xh + 0.6 * cm, y_waf + bh, xh + 0.6 * cm, y_user, c.AZUL)
    _texto(g, xh - 1.0 * cm, (y_user + y_waf + bh) / 2 - 2, "HTTPS", 6.8, True, c.AZUL)
    # WAF -> App (HTTP interno)
    _flecha(g, cx, y_waf, cx, y_app + bh, c.VERDE)
    _texto(g, cx + 2.3 * cm, (y_waf + y_app + bh) / 2 - 2, "HTTP interno", 6.6, False, c.GRIS)
    # App -> Worker (cola / outbox)
    _flecha(g, cx, y_app, cx, y_wrk + bh, c.GRIS, dash=True)

    # Fila de datos: Supabase (izq) y GLPI (der)
    dw = 6.1 * cm
    _caja(g, bx, y_dat, dw, bh, "Supabase (nube)", "PostgreSQL TLS · Auth TOTP · RLS", colors.HexColor("#EEEDFE"), colors.HexColor("#534AB7"), colors.HexColor("#3C3489"))
    _caja(g, bx + bw - dw, y_dat, dw, bh, "GLPI 11 + MariaDB", "Fuente de estado de tickets", colors.HexColor("#FAEEDA"), c.AMBAR, c.AMBAR)
    # App -> Supabase (baja por el margen izquierdo, despejado del texto del Worker)
    xs_sup = bx + 0.7 * cm
    _flecha(g, xs_sup, y_app, xs_sup, y_dat + bh, colors.HexColor("#534AB7"))
    _texto(g, xs_sup + 1.0 * cm, (y_app + y_dat + bh) / 2, "TLS", 6.6, True, colors.HexColor("#3C3489"))
    # Worker -> GLPI (baja por el margen derecho)
    xg = bx + bw - 0.7 * cm
    _flecha(g, xg, y_wrk, xg, y_dat + bh, c.AMBAR)
    _texto(g, xg - 1.3 * cm, (y_wrk + y_dat + bh) / 2, "API REST", 6.6, True, c.AMBAR)

    # Marco de red interna: envuelve WAF..datos (no el usuario)
    fm_top = y_waf + bh + 0.22 * cm
    fm_bot = y_dat - 0.28 * cm
    g.add(Rect(bx - 0.4 * cm, fm_bot, bw + 0.8 * cm, fm_top - fm_bot,
               rx=7, ry=7, fillColor=None, strokeColor=c.LINEA, strokeWidth=0.7, strokeDashArray=[3, 3]))

    # Frontera de confianza: línea justo debajo del Usuario, etiqueta a la derecha encima
    yb = y_user - 0.42 * cm
    g.add(Line(bx - 0.4 * cm, yb, bx + bw + 0.4 * cm, yb, strokeColor=c.AZUL, strokeWidth=0.7, strokeDashArray=[4, 2]))
    _texto(g, bx + bw + 0.35 * cm, yb + 0.1 * cm, "Frontera de confianza", 6.8, True, c.AZUL, "end")
    # Etiqueta de la red interna: centrada bajo el marco, despejada
    _texto(g, cx, fm_bot - 0.32 * cm, "Host Azure · redes Docker internas (solo el WAF publica 80/443)", 6.8, False, c.GRIS)

    d.add(g)
    return d


def cia() -> Drawing:
    """Tres columnas C-I-A con los controles principales de cada propiedad."""
    W, H = ANCHO, 9.6 * cm
    d = Drawing(W, H)
    g = Group()
    colw = 5.3 * cm
    gap = (W - 3 * colw) / 2
    xs = [0, colw + gap, 2 * (colw + gap)]
    titulos = [
        ("Confidencialidad", c.AZUL, c.AZUL_CLARO,
         ["TLS 1.3 en el borde", "Campos restringidos\nen tabla aparte", "Nunca a GLPI, logs\nni dashboard", "RLS y esquema\nno expuesto", "Logs sin secretos\nni campos sensibles"]),
        ("Autenticidad", c.VERDE, c.VERDE_CLARO,
         ["Supabase Auth\ncontraseña + TOTP (AAL2)", "Sesión solo tras\nverificar el 2.º factor", "Autorización por rol\nen cada vista", "Doble firma:\nsolicitante y RRHH", "Tokens de GLPI\nfuera de la interfaz"]),
        ("Integridad", c.AMBAR, c.AMBAR_CLARO,
         ["Auditoría encadenada\nSHA-256 + ancla", "Solicitud aprobada\ninmutable (disparador)", "Auditoría solo\ninserción (REVOKE)", "Deduplicación en\nla base de datos", "ORM parametrizado\n+ WAF (anti-inyección)"]),
    ]
    for i, (tit, col, fill, items) in enumerate(titulos):
        x = xs[i]
        g.add(Rect(x, H - 0.95 * cm, colw, 0.8 * cm, rx=5, ry=5, fillColor=col, strokeColor=col))
        _texto(g, x + colw / 2, H - 0.62 * cm, tit, 10, True, colors.white)
        yy = H - 1.25 * cm
        for it in items:
            lineas = it.split("\n")
            alto = 0.52 * cm + 0.3 * cm * (len(lineas) - 1)
            yy -= alto + 0.18 * cm
            g.add(Rect(x, yy, colw, alto, rx=4, ry=4, fillColor=fill, strokeColor=col, strokeWidth=0.6))
            for j, ln in enumerate(lineas):
                _texto(g, x + colw / 2, yy + alto - 11 - j * 10, ln, 7.3, False, col if col != c.AMBAR else colors.HexColor("#633806"))
    d.add(g)
    return d
