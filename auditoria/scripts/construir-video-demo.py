"""Arma un video de demostración del prototipo SSGUI a partir de capturas reales de la aplicación
(por el WAF) y tarjetas de rótulo/resultado. Une los fotogramas con ffmpeg. Sin grabación de pantalla:
cada fotograma es una imagen real del sistema o una tarjeta con texto. Lee la cookie de un archivo."""

import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

BASE = "https://app.localhost"
W, H = 1280, 720
NOCHE = (27, 20, 99)
ACENTO = (91, 47, 214)
PAPEL = (250, 246, 240)
OK = (27, 94, 42)
TINTA = (23, 18, 46)
ses = dict(x.split() for x in Path(sys.argv[1]).read_text().splitlines() if len(x.split()) == 2)
V = Path(sys.argv[2])
COOKIE = ses.pop("COOKIE")
frames_dir = V / "frames"
frames_dir.mkdir(parents=True, exist_ok=True)


def fuente(tam, negrita=False):
    for n in ("arialbd.ttf", "DejaVuSans-Bold.ttf") if negrita else ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(n, tam)
        except OSError:
            continue
    return ImageFont.load_default()


def tarjeta(nombre, titulo, lineas, color_fondo=NOCHE, color_titulo="white", bullets=None):
    img = Image.new("RGB", (W, H), color_fondo)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 14, H], fill=ACENTO)
    d.text(
        (70, 90),
        "SSGUI · Sistema de Solicitud de Gestión de Usuarios Interno",
        font=fuente(22),
        fill=(200, 196, 230) if color_fondo == NOCHE else (90, 86, 112),
    )
    d.text((70, 150), titulo, font=fuente(52, True), fill=color_titulo)
    y = 280
    for ln in lineas:
        es_ok = bullets == "ok"
        if es_ok:
            d.ellipse([70, y + 10, 92, y + 32], fill=OK)
            d.text((110, y), ln, font=fuente(30), fill="white" if color_fondo == NOCHE else TINTA)
        else:
            d.text(
                (70, y),
                ln,
                font=fuente(30),
                fill=(220, 216, 240) if color_fondo == NOCHE else TINTA,
            )
        y += 58
    img.save(frames_dir / f"{nombre}.png")


def rotulo_sobre(nombre, captura_png, texto):
    """Pone una barra de rótulo arriba de una captura real."""
    base = Image.open(captura_png).convert("RGB").resize((W, H - 80))
    img = Image.new("RGB", (W, H), NOCHE)
    img.paste(base, (0, 80))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 14, H], fill=ACENTO)
    d.text((70, 22), texto, font=fuente(34, True), fill="white")
    img.save(frames_dir / f"{nombre}.png")


# --- capturas reales de la aplicación ---------------------------------------------------------
caps = V / "caps"
caps.mkdir(exist_ok=True)
with sync_playwright() as p:
    b = p.chromium.launch()
    # login sin sesión
    c0 = b.new_context(ignore_https_errors=True, viewport={"width": W, "height": H - 80})
    pg = c0.new_page()
    pg.goto(BASE + "/ingreso")
    pg.wait_for_timeout(500)
    pg.screenshot(path=str(caps / "login.png"))
    c0.close()
    # con sesión de administrador
    c1 = b.new_context(ignore_https_errors=True, viewport={"width": W, "height": H - 80})
    c1.add_cookies([{"name": COOKIE, "value": ses["administrador"], "url": BASE + "/"}])
    pg = c1.new_page()
    for nombre, ruta in [
        ("nueva", "/solicitudes/nueva"),
        ("ingreso_form", "/solicitudes/nueva/ING"),
        ("tickets", "/tickets"),
        ("dashboard", "/dashboard"),
        ("usuarios", "/administracion/usuarios"),
    ]:
        pg.goto(BASE + ruta)
        pg.wait_for_timeout(900)
        pg.screenshot(path=str(caps / f"{nombre}.png"))
    c1.close()
    b.close()

# --- guion de fotogramas (nombre, duración en segundos) ---------------------------------------
tarjeta(
    "00_portada",
    "Demostración del prototipo",
    [
        "Gestión segura de eventos laborales (ingreso, retiro, vacaciones…)",
        "Arquitectura hexagonal · Django · GLPI 11 · WAF BunkerWeb",
        "Pruebas de implementación, funcionamiento y ataque",
    ],
)
tarjeta(
    "01_impl",
    "1. Implementación",
    [
        "Todo el sistema en Docker: WAF, aplicación, PostgreSQL 17, GLPI 11",
        "Solo el WAF publica puertos · HTTPS con TLS 1.2/1.3",
        "docker compose ... up -d  ·  11 servicios sanos",
    ],
)
rotulo_sobre("02_login", caps / "login.png", "Inicio de sesión (contraseña + TOTP, por el WAF)")
rotulo_sobre("03_nueva", caps / "nueva.png", "2. Crear eventos: los seis tipos (Administrador)")
rotulo_sobre("04_ing", caps / "ingreso_form.png", "3. Formulario de Ingreso (genera los tickets)")
rotulo_sobre(
    "05_tickets", caps / "tickets.png", "4. Consulta de tickets (solo lectura, enlace a GLPI)"
)
rotulo_sobre("06_dash", caps / "dashboard.png", "5. Dashboard de TI (sin tiempo real)")
rotulo_sobre(
    "07_users", caps / "usuarios.png", "6. Administración de usuarios (CRUD, servicio interno)"
)
tarjeta(
    "08_ataque",
    "7. Pruebas de ataque",
    [
        "Se atacan las tres propiedades de la información:",
        "confidencialidad · autenticidad · integridad",
    ],
)
tarjeta(
    "09_sqli",
    "Inyección SQL",
    [
        "sqlmap nivel 5: 0 parámetros inyectables",
        "El WAF bloquea 5 de 5 cargas clásicas (403)",
        "El ORM trata la carga como dato literal (200)",
        "Las 26 tablas intactas · auditoría íntegra",
    ],
    color_fondo=PAPEL,
    color_titulo=NOCHE,
    bullets="ok",
)
tarjeta(
    "10_mitm",
    "Hombre en el medio (MitM)",
    [
        "Certificado falso: rechazado por el cliente que valida",
        "No se puede degradar TLS (solo 1.2/1.3)",
        "Puerto 80 → 443 + HSTS (anti-SSL-strip)",
        "Cookie Secure/HttpOnly/SameSite · contraseña cifrada",
    ],
    color_fondo=PAPEL,
    color_titulo=NOCHE,
    bullets="ok",
)
tarjeta(
    "11_cierre",
    "Solución verificada",
    [
        "0 inyectables · interceptación detectada · credenciales cifradas",
        "Evidencia reproducible: auditoria/evidencia/  +  manifiesto de hashes",
        "Entregable 5 de Desarrollo Seguro",
    ],
)

guion = [
    ("00_portada", 4),
    ("01_impl", 4),
    ("02_login", 4),
    ("03_nueva", 4),
    ("04_ing", 4),
    ("05_tickets", 4),
    ("06_dash", 4),
    ("07_users", 4),
    ("08_ataque", 3),
    ("09_sqli", 6),
    ("10_mitm", 6),
    ("11_cierre", 5),
]
lista = V / "lista.txt"
with lista.open("w", encoding="utf-8") as f:
    for nombre, dur in guion:
        ruta = (frames_dir / f"{nombre}.png").as_posix()
        f.write(f"file '{ruta}'\nduration {dur}\n")
    f.write(f"file '{(frames_dir / guion[-1][0]).as_posix()}.png'\n")  # último fotograma (ffmpeg)

salida = V / "demostracion-ssgui.mp4"
cmd = [
    "ffmpeg",
    "-y",
    "-f",
    "concat",
    "-safe",
    "0",
    "-i",
    str(lista),
    "-vf",
    "fps=25,format=yuv420p,scale=1280:720",
    "-c:v",
    "libx264",
    "-preset",
    "medium",
    "-movflags",
    "+faststart",
    str(salida),
]
r = subprocess.run(cmd, capture_output=True, text=True)
print("ffmpeg rc:", r.returncode)
if r.returncode != 0:
    print(r.stderr[-800:])
else:
    print("video:", salida, salida.stat().st_size, "bytes")
