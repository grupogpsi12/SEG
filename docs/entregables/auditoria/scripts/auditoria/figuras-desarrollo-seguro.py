"""Figuras del entregable «Propuesta de controles de seguridad»: cuatro diagramas dibujados con pillow.

    uv run python auditoria/scripts/figuras-desarrollo-seguro.py

Salida: `docs/Desarrollo Seguro/figuras/*.png`. Los diagramas representan lo que el sistema implementa y lo que se verificó;
los controles se numeran (C-01 ...) y la tabla del documento usa los mismos numeros.
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

RAIZ = Path(__file__).resolve().parents[2]
DESTINO = RAIZ / "docs" / "Desarrollo Seguro" / "figuras"

TINTA, SUAVE, LINEA = "#1d2733", "#52606d", "#9aa5b4"
AZUL, VERDE, NARANJA, GRIS, ROJO = "#dbe7f5", "#dcefdc", "#fbe7c6", "#eceff3", "#f6d9d9"
BORDE = {AZUL: "#4f7cac", VERDE: "#4f8a4f", NARANJA: "#c98a1d", GRIS: "#8a96a8", ROJO: "#b34a4a"}


def fuente(tam: int, negrita: bool = False) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    for nombre in (
        "arialbd.ttf" if negrita else "arial.ttf",
        "DejaVuSans-Bold.ttf" if negrita else "DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(nombre, tam)
        except OSError:
            continue
    return ImageFont.load_default()


class Lienzo:
    def __init__(self, ancho: int, alto: int, titulo: str) -> None:
        self.img = Image.new("RGB", (ancho, alto), "white")
        self.d = ImageDraw.Draw(self.img)
        self.d.text((24, 16), titulo, fill=TINTA, font=fuente(26, True))

    def ajustar(self, texto: str, tam: int, ancho: int, negrita: bool = False) -> list[str]:
        f = fuente(tam, negrita)
        lineas: list[str] = []
        for parrafo in texto.split("\n"):
            actual = ""
            for palabra in parrafo.split():
                prueba = f"{actual} {palabra}".strip()
                if self.d.textlength(prueba, font=f) <= ancho:
                    actual = prueba
                else:
                    lineas.append(actual)
                    actual = palabra
            lineas.append(actual)
        return lineas

    def caja(
        self,
        x: int,
        y: int,
        w: int,
        h: int,
        titulo: str,
        detalle: str = "",
        color: str = AZUL,
        tam: int = 17,
    ) -> tuple[int, int, int, int]:
        self.d.rounded_rectangle(
            [x, y, x + w, y + h], radius=10, fill=color, outline=BORDE[color], width=2
        )
        cursor = y + 10
        for linea in self.ajustar(titulo, tam + 1, w - 20, True):
            self.d.text((x + 10, cursor), linea, fill=TINTA, font=fuente(tam + 1, True))
            cursor += tam + 6
        for linea in self.ajustar(detalle, tam - 2, w - 20):
            self.d.text((x + 10, cursor), linea, fill=SUAVE, font=fuente(tam - 2))
            cursor += tam + 1
        return x, y, w, h

    def zona(self, x: int, y: int, w: int, h: int, nombre: str) -> None:
        self.d.rounded_rectangle([x, y, x + w, y + h], radius=14, outline=LINEA, width=2)
        self.d.text((x + 14, y + 8), nombre, fill=SUAVE, font=fuente(16, True))

    def flecha(
        self,
        a: tuple[int, int],
        b: tuple[int, int],
        texto: str = "",
        desplazar: tuple[int, int] = (0, -22),
    ) -> None:
        self.d.line([a, b], fill=TINTA, width=3)
        dx, dy = b[0] - a[0], b[1] - a[1]
        largo = max((dx * dx + dy * dy) ** 0.5, 1)
        ux, uy = dx / largo, dy / largo
        p1 = (b[0] - 14 * ux + 7 * uy, b[1] - 14 * uy - 7 * ux)
        p2 = (b[0] - 14 * ux - 7 * uy, b[1] - 14 * uy + 7 * ux)
        self.d.polygon([b, p1, p2], fill=TINTA)
        if texto:
            mx, my = (a[0] + b[0]) // 2 + desplazar[0], (a[1] + b[1]) // 2 + desplazar[1]
            ancho = self.d.textlength(texto, font=fuente(14))
            self.d.rectangle([mx - 4, my - 2, mx + ancho + 4, my + 18], fill="white")
            self.d.text((mx, my), texto, fill=TINTA, font=fuente(14))

    def numero(self, x: int, y: int, texto: str) -> None:
        self.d.ellipse([x, y, x + 46, y + 28], fill="#1f3b66")
        ancho = self.d.textlength(texto, font=fuente(13, True))
        self.d.text((x + (46 - ancho) / 2, y + 6), texto, fill="white", font=fuente(13, True))

    def leyenda(self, x: int, y: int, items: list[tuple[str, str]]) -> None:
        for i, (texto, color) in enumerate(items):
            self.d.rectangle(
                [x + i * 300, y, x + i * 300 + 20, y + 16], fill=color, outline=BORDE[color]
            )
            self.d.text((x + i * 300 + 28, y), texto, fill=TINTA, font=fuente(15))

    def guardar(self, nombre: str) -> None:
        DESTINO.mkdir(parents=True, exist_ok=True)
        self.img.save(DESTINO / nombre)


def insignias(c: Lienzo, caja: tuple[int, int, int, int], textos: list[str]) -> None:
    """Numeros de control a lo largo del borde superior de una caja, a la derecha."""
    x, y, w, _ = caja
    for i, texto in enumerate(reversed(textos)):
        c.numero(x + w - 56 - i * 52, y - 14, texto)


def arquitectura() -> None:
    c = Lienzo(
        1700, 1060, "Figura 1. Arquitectura de seguridad: capas, zonas de confianza y controles"
    )
    ancho, hueco, x0 = 300, 40, 20
    col = [x0 + i * (ancho + hueco) for i in range(5)]
    # Capa 1: navegador en el equipo local (ADR-031: sin exposición pública)
    c.zona(
        10,
        56,
        1680,
        130,
        "Navegador en el equipo local: https://app.localhost y https://glpi.localhost (entrada no confiable)",
    )
    c.caja(
        col[1],
        86,
        ancho,
        90,
        "Personas usuarias",
        "RRHH, solicitantes, técnicos, auditoría y administración",
        GRIS,
    )
    c.caja(
        col[2],
        86,
        ancho,
        90,
        "Entradas maliciosas",
        "escáneres y ataques hacia los puertos 80 y 443",
        ROJO,
    )
    # Capa 2: borde
    c.zona(10, 210, 1680, 190, "Borde: único servicio con puertos (80 y 443)")
    waf = c.caja(
        col[0],
        245,
        1280,
        140,
        "BunkerWeb 1.6.15: WAF y proxy inverso",
        "TLS 1.2 y 1.3 con certificado autofirmado y HSTS · ModSecurity con OWASP CRS 4 en modo de bloqueo · límite de 2 peticiones por segundo · bloqueo de una hora por mal comportamiento · cabeceras de seguridad · protege app.localhost y glpi.localhost",
        VERDE,
        18,
    )
    rep = c.caja(
        col[4] - 20,
        245,
        ancho + 20,
        140,
        "Reportería del WAF",
        "Fluent Bit clasifica, Loki almacena en un volumen local y Grafana muestra (solo en 127.0.0.1)",
        AZUL,
        17,
    )
    insignias(c, waf, ["C-01", "C-02", "C-03"])
    insignias(c, rep, ["C-15"])
    # Capa 3: red app
    c.zona(10, 430, 1680, 250, "Red «app» (confianza media)")
    auth = c.caja(
        col[0],
        465,
        ancho,
        195,
        "Supabase Auth (único servicio externo)",
        "Contraseña y TOTP (nivel AAL2) · se consulta por HTTPS desde el servidor · la clave service_role solo existe en el contenedor de administración",
        NARANJA,
    )
    web = c.caja(
        col[1],
        465,
        ancho,
        195,
        "web (Django 5.2)",
        "Autorización por rol en cada vista · formularios validados · ORM con consultas parametrizadas · CSP y X-Frame-Options · sesión tras el segundo factor",
        AZUL,
    )
    wrk = c.caja(
        col[2],
        465,
        ancho,
        195,
        "worker",
        "Único cliente de GLPI (API REST) · bandeja de salida con reintentos e idempotencia · sincronización cada 5 minutos · exportación diaria de la auditoría",
        AZUL,
    )
    glpi = c.caja(
        col[3],
        465,
        ancho,
        195,
        "GLPI 11",
        "Los técnicos trabajan aquí · fuente de la verdad del estado de cada ticket · cuenta de servicio con perfil acotado",
        AZUL,
    )
    sop = c.caja(
        col[4],
        465,
        ancho,
        195,
        "Soportes en tránsito",
        "Volumen sin ejecución · solo PDF validado por firma · nombre aleatorio · se borra tras verificar el hash",
        GRIS,
    )
    insignias(c, auth, ["C-04"])
    insignias(c, web, ["C-05", "C-06"])
    insignias(c, wrk, ["C-14"])
    insignias(c, glpi, ["C-14"])
    insignias(c, sop, ["C-12"])
    # Capa 4: datos y secretos
    c.zona(10, 710, 1680, 250, "Datos y secretos (internos)")
    exp = c.caja(
        col[0],
        745,
        ancho,
        195,
        "Exportes y respaldos",
        "Auditoría diaria con su ancla en el volumen exportes · pg_dump y volcado de MariaDB · copia sin sobrescribir a un disco externo (365 y 30 días)",
        NARANJA,
    )
    pg = c.caja(
        col[1],
        745,
        2 * ancho + hueco,
        195,
        "PostgreSQL 17 local (base de la aplicación)",
        "Contenedor en la red interna pg_net, sin puertos publicados · esquema app con dueño separado del rol de la aplicación · RLS activo sin políticas en todas las tablas · disparador de inmutabilidad · índice único parcial de deduplicación · auditoría de solo inserción",
        VERDE,
        18,
    )
    maria = c.caja(
        col[3],
        745,
        ancho,
        195,
        "MariaDB (base de GLPI)",
        "Red db_net interna: solo GLPI la alcanza · sin TLS en ese tramo (hallazgo B-30)",
        GRIS,
    )
    sec = c.caja(
        col[4],
        745,
        ancho,
        195,
        "Docker secrets",
        "Generados en secrets/ (fuera de Git) y montados en /run/secrets solo donde se usan · nunca en el código, en GLPI ni en la base de datos",
        NARANJA,
    )
    insignias(c, pg, ["C-07", "C-08", "C-09", "C-10"])
    insignias(c, maria, ["C-13"])
    insignias(c, sec, ["C-11"])
    insignias(c, exp, ["C-08"])
    # Flechas (solo verticales y horizontales entre cajas adyacentes)
    c.flecha((col[1] + 150, 176), (col[1] + 150, 245), "HTTPS", (12, -14))
    c.flecha((col[2] + 150, 176), (col[2] + 150, 245), "bloqueado", (12, -14))
    c.flecha((1300, 315), (col[4] - 20, 315), "", (0, 0))
    c.flecha((col[1] + 150, 385), (col[1] + 150, 465), "HTTP interno", (12, 0))
    c.flecha((col[3] + 150, 385), (col[3] + 150, 465), "HTTP interno", (12, 0))
    c.flecha((col[1], 560), (col[0] + ancho, 560))
    c.flecha((col[2] + 70, 660), (col[2] + 70, 745), "SQL", (12, -14))
    c.flecha((col[1] + 150, 660), (col[1] + 150, 745), "SQL", (12, -14))
    c.flecha((col[2] + ancho, 560), (col[3], 560))
    c.flecha((col[3] + 150, 660), (col[3] + 150, 745), "SQL", (12, -14))
    c.flecha((col[1], 842), (col[0] + ancho, 842), "copia", (-10, -26))
    c.leyenda(
        24,
        1000,
        [
            ("Control de seguridad", VERDE),
            ("Componente de la aplicación", AZUL),
            ("Servicio externo, secretos o copias", NARANJA),
        ],
    )
    c.d.text(
        (24, 1030),
        "Las insignias C-nn remiten a la tabla de controles del documento.",
        fill=SUAVE,
        font=fuente(15),
    )
    c.guardar("figura-1-arquitectura-de-seguridad.png")


def autenticacion() -> None:
    c = Lienzo(1700, 450, "Figura 2. Autenticación de dos factores mediada por el servidor")
    pasos = [
        ("1. Credenciales", "La persona envía correo y contraseña al servidor, por el WAF.", GRIS),
        (
            "2. Primer factor",
            "El servidor consulta a Supabase Auth. Recibe un token de nivel AAL1 que solo vive en memoria.",
            NARANJA,
        ),
        (
            "3. Desafío opaco",
            "Se emite un identificador de 256 bits, válido 5 minutos y 5 intentos. No contiene el token.",
            VERDE,
        ),
        (
            "4. Segundo factor",
            "La persona envía el código TOTP de 6 dígitos. Un código usado no vuelve a servir.",
            GRIS,
        ),
        (
            "5. Verificación",
            "Supabase eleva la sesión a AAL2. El servidor comprueba el nivel y la identidad.",
            NARANJA,
        ),
        (
            "6. Sesión",
            "Se crea la sesión de Django con rotación del identificador: 30 minutos de inactividad o 8 horas. Se cierra la sesión de Supabase.",
            VERDE,
        ),
    ]
    x = 24
    for i, (t, d, color) in enumerate(pasos):
        c.caja(x, 80, 255, 175, t, d, color, 17)
        if i < len(pasos) - 1:
            c.flecha((x + 255, 168), (x + 275, 168))
        x += 275
    c.zona(24, 290, 1650, 130, "Propiedades que se verificaron con pruebas")
    c.d.text(
        (44, 326),
        "• Un desafío ajeno no entra.   • Un código TOTP repetido se rechaza.   • Los tokens de Supabase no se guardan ni en la sesión ni en el navegador.",
        fill=TINTA,
        font=fuente(17),
    )
    c.d.text(
        (44, 356),
        "• Los errores de inicio de sesión son genéricos: no distinguen entre «no existe» y «contraseña incorrecta».   • La sesión nace solo después del segundo factor.",
        fill=TINTA,
        font=fuente(17),
    )
    c.d.text(
        (44, 386),
        "• Limitación conocida (B-28): la aplicación lee los datos del token sin verificar su firma; el canal con Supabase va cifrado y verificado.",
        fill=SUAVE,
        font=fuente(16),
    )
    c.guardar("figura-2-autenticacion.png")


def auditoria() -> None:
    c = Lienzo(1700, 450, "Figura 3. Cadena de auditoría de solo inserción")
    c.caja(
        60,
        80,
        380,
        120,
        "Registro n − 1",
        "secuencia, fecha, actor, acción, objeto y datos\nhash(n − 1)",
        AZUL,
    )
    c.caja(
        560,
        80,
        380,
        120,
        "Registro n",
        "secuencia, fecha, actor, acción, objeto y datos\nhash(n) = SHA-256( hash(n − 1) ‖ contenido canónico )",
        VERDE,
    )
    c.caja(1060, 80, 380, 120, "Registro n + 1", "se encadena con hash(n)", AZUL)
    c.flecha((440, 140), (560, 140), "hash(n − 1)")
    c.flecha((940, 140), (1060, 140), "hash(n)")
    c.caja(
        60,
        250,
        520,
        160,
        "Dónde se impone",
        "La base de datos niega UPDATE y DELETE al rol de la aplicación sobre la auditoría, las decisiones y el historial de cuentas. Solo existe la escritura por el puerto de auditoría. Una solicitud aprobada no se modifica: un disparador lo impide.",
        VERDE,
    )
    c.caja(
        640,
        250,
        520,
        160,
        "Cómo se comprueba",
        "La persona con rol de auditoría recorre la cadena completa desde la interfaz y la verificación queda registrada. Alterar un registro rompe la verificación en ese punto. Tras restaurar un respaldo, la cadena conserva la misma cabeza.",
        AZUL,
    )
    c.caja(
        1220,
        250,
        440,
        160,
        "Copia fuera de la base",
        "Cada día se exporta el tramo del día con su hash y un ancla con la cabeza de toda la cadena, y se copia a un disco externo al equipo. Fuera de la base, el ancla delata una reescritura completa.",
        NARANJA,
    )
    c.guardar("figura-3-cadena-de-auditoria.png")


def restringidos() -> None:
    c = Lienzo(
        1700,
        480,
        "Figura 4. Recorrido de un dato restringido (motivo de retiro y descripción de una emergencia)",
    )
    c.caja(
        40,
        80,
        280,
        140,
        "Formulario de RRHH",
        "El campo viaja cifrado (TLS 1.3) hasta el WAF",
        GRIS,
    )
    c.caja(
        400,
        80,
        300,
        140,
        "WAF y aplicación",
        "El WAF termina el TLS. Dentro de la red «app» el campo viaja por HTTP hacia la aplicación",
        AZUL,
    )
    c.caja(
        780,
        80,
        320,
        140,
        "PostgreSQL",
        "Se guarda solo en la tabla solicitud_restringida. Es el único lugar donde existe",
        VERDE,
    )
    c.flecha((320, 150), (400, 150), "")
    c.flecha((700, 150), (780, 150), "")
    c.caja(
        1180,
        80,
        480,
        140,
        "Quién lo ve",
        "Solo el rol de RRHH, en el detalle de la solicitud. Cada lectura queda registrada en la auditoría. Un técnico que pide el detalle recibe 404, sin confirmar que existe.",
        VERDE,
    )
    c.flecha((1100, 150), (1180, 150), "")
    c.caja(
        40,
        270,
        520,
        160,
        "Lo que NO lleva el campo",
        "Tickets de GLPI (el contenido se limita a datos técnicos) · registros del servidor (el filtro oculta motivo, descripción, contraseña, token y TOTP, incluso con acentos) · dashboard, fichas y exportaciones · mensajes de error.",
        ROJO,
    )
    c.caja(
        640,
        270,
        520,
        160,
        "Cómo se comprobó",
        "Un valor centinela escrito en el campo se buscó en 31 240 tramas hacia GLPI: 0. Se buscó en el tramo cifrado: 0. Apareció en la base de datos y en el tramo interno WAF-aplicación, que es donde debe estar.",
        AZUL,
    )
    c.caja(
        1240,
        270,
        420,
        160,
        "Limitación",
        "En el tramo interno el campo viaja sin cifrar. La red «app» es de confianza media: el límite de confianza es el equipo, no el nombre de la red.",
        NARANJA,
    )
    c.guardar("figura-4-dato-restringido.png")


def puntos_de_captura() -> None:
    c = Lienzo(1700, 640, "Figura 5. Tramos de red y puntos de captura del tráfico")
    nav = c.caja(
        30,
        110,
        230,
        120,
        "Navegador",
        "Chromium (Playwright) o curl con una sesión de prueba",
        GRIS,
    )
    waf = c.caja(360, 110, 260, 120, "BunkerWeb", "termina TLS 1.3 y aplica el WAF", VERDE)
    web = c.caja(720, 110, 230, 120, "web (Django)", "vistas y casos de uso", AZUL)
    pg = c.caja(1050, 110, 260, 120, "PostgreSQL 17", "red interna pg_net", VERDE)
    wrk = c.caja(720, 380, 230, 120, "worker", "bandeja de salida y sincronización", AZUL)
    glpi = c.caja(1050, 380, 260, 120, "GLPI 11", "API REST en la red «app»", AZUL)
    maria = c.caja(1410, 380, 260, 120, "MariaDB", "red interna db_net", GRIS)
    c.flecha((260, 170), (360, 170), "HTTPS 8443", (-42, -28))
    c.flecha((620, 170), (720, 170), "HTTP 8000", (-30, -26))
    c.flecha((950, 170), (1050, 170), "SQL 5432", (-30, -26))
    c.flecha((835, 380), (1110, 230), "SQL 5432", (-10, 6))
    c.flecha((950, 440), (1050, 440), "HTTP 80", (-30, -26))
    c.flecha((1310, 440), (1410, 440), "SQL 3306", (-30, -26))
    insignias(c, waf, ["P1"])
    insignias(c, pg, ["P2"])
    insignias(c, glpi, ["P3"])
    _ = (nav, web, wrk, maria)
    c.zona(30, 540, 1640, 80, "Puntos de captura (tcpdump en el espacio de red de cada contenedor)")
    c.d.text(
        (50, 574),
        "P1: navegador ↔ WAF (cifrado) y WAF ↔ aplicación (HTTP interno)  ·  P2: aplicación y worker ↔ PostgreSQL  ·  P3: worker ↔ GLPI y GLPI ↔ MariaDB",
        fill=TINTA,
        font=fuente(17),
    )
    c.guardar("figura-5-puntos-de-captura.png")


def main() -> int:
    arquitectura()
    autenticacion()
    auditoria()
    restringidos()
    puntos_de_captura()
    for p in sorted(DESTINO.glob("*.png")):
        print(p.name, p.stat().st_size)
    return 0


if __name__ == "__main__":
    sys.exit(main())
