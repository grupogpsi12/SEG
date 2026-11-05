"""Capturas de pantalla de los casos de uso (entregable 5.7).

Descarga cada pagina a traves de BunkerWeb con la sesion de prueba del rol, incrusta la hoja de
estilos y la renderiza con Edge sin interfaz. Las claves de sesion no se escriben en los archivos.

    python pantallas.py <archivo-de-sesiones> <carpeta-de-salida>
"""

import re
import subprocess
import sys
import time
from pathlib import Path

import httpx

BASE = "https://app.localhost"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PERFIL = str(Path.home() / "AppData/Local/Temp/jml-edge-capturas")  # perfil aislado: no toca el del usuario
PANTALLAS = [
    ("01-ingreso", "anonimo", "GET", "/ingreso"),
    ("02-mis-solicitudes", "sol", "GET", "/solicitudes"),
    ("03-nueva-vacaciones", "sol", "GET", "/solicitudes/nueva/VAC"),
    ("04-bandeja-rrhh", "rrhh", "GET", "/bandeja"),
    ("05-detalle-ret-rrhh", "rrhh", "GET", "/solicitudes/SOL-2026-000004"),
    ("06-detalle-ret-tecnico-404", "tec_ad", "GET", "/solicitudes/SOL-2026-000004"),
    ("07-dashboard-tecnico", "tec_ad", "GET", "/dashboard"),
    ("08-ficha-colaborador", "tec_ad", "GET", "/colaboradores/col-014"),
    ("09-solicitante-sin-permiso-403", "sol", "GET", "/bandeja"),
    ("10-auditoria-verificada", "auditor", "POST", "/auditoria"),
    ("11-matriz-perfiles", "admin", "GET", "/administracion/perfiles"),
    ("12-solicitudes-en-error", "admin", "GET", "/errores"),
]


def main(sesiones_txt: str, salida: str) -> None:
    sesiones = dict(l.strip().split("=", 1) for l in open(sesiones_txt) if "=" in l)
    destino = Path(salida).resolve()
    destino.mkdir(parents=True, exist_ok=True)
    css_cache: dict[str, str] = {}
    for nombre, rol, metodo, ruta in PANTALLAS:
        c = httpx.Client(base_url=BASE, verify=False, headers={"Referer": BASE + "/"})
        if rol != "anonimo":
            c.cookies.set("sessionid", sesiones[rol], domain="app.localhost")
        time.sleep(1.2)
        if metodo == "POST":
            token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', c.get(ruta).text)
            time.sleep(1.2)
            r = c.post(ruta, data={"csrfmiddlewaretoken": token.group(1) if token else ""})
        else:
            r = c.get(ruta)
        html = r.text
        for href in set(re.findall(r'<link rel="stylesheet" href="([^"]+)"', html)):
            if href not in css_cache:
                time.sleep(1.2)
                css_cache[href] = c.get(href).text
            html = html.replace(f'<link rel="stylesheet" href="{href}">', f"<style>{css_cache[href]}</style>")
        html = re.sub(r'value="[A-Za-z0-9]{32,}"', 'value="&lt;oculto&gt;"', html)
        banda = (f'<div style="font:12px monospace;background:#222;color:#eee;padding:4px 8px">'
                 f'{metodo} {BASE}{ruta} · rol: {rol} · HTTP {r.status_code}</div>')
        html = html.replace("<body>", "<body>" + banda, 1) if "<body>" in html else banda + html
        archivo = destino / f"{nombre}.html"
        archivo.write_text(html, encoding="utf-8")
        subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--user-data-dir=" + PERFIL, "--hide-scrollbars", "--window-size=1280,900",
                        f"--screenshot={destino / (nombre + '.png')}", archivo.resolve().as_uri()],
                       capture_output=True, check=False, timeout=60)
        archivo.unlink()
        print(nombre, r.status_code)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
