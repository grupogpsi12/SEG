"""Genera los DEFECTOS SEMBRADOS del control positivo estático (plan §10, fila 1) en una carpeta.

    python auditoria/controles-positivos/generar.py <carpeta-destino>

Escribe tres archivos que cada herramienta estática DEBE marcar; si alguna no los marca, su
resultado sobre el repositorio real no cuenta (un escáner que no ve el defecto sembrado no ve nada):

  vulnerable.py                 SQL por f-string, SQL con una cabecera, `mark_safe` de entrada del
                                usuario, `subprocess(shell=True)` y un secreto embebido  -> bandit, ruff(S), gitleaks
  requirements-vulnerable.txt   una dependencia con vulnerabilidades conocidas              -> pip-audit, trivy
  Dockerfile.vulnerable         imagen que corre como root y descarga con `ADD` de una URL  -> trivy config
  app_vulnerable.py             aplicacion de laboratorio con SQLi, XSS y sin cabeceras -> sqlmap, ZAP (F6-00)

El secreto falso se ARMA aquí a partir de trozos: este archivo no contiene ninguna cadena con forma
de secreto (gitleaks de la CI revisa todo el historial). El resultado se escribe SOLO en la carpeta
temporal que se pasa; no se versiona jamás.
"""

import sys
from pathlib import Path

VULNERABLE = '''"""Defectos sembrados. NO es código del proyecto: solo existe para probar a los escáneres."""

import subprocess

from django.db import connection
from django.utils.safestring import mark_safe

# 5. secreto embebido (forma de un token personal de GitHub)
TOKEN_DE_SERVICIO = "{secreto}"


def buscar_por_documento(documento: str) -> list[tuple[str]]:
    with connection.cursor() as cursor:
        # 1. SQL por f-string con entrada del usuario
        cursor.execute(f"SELECT nombres FROM colaborador WHERE documento = '{{documento}}'")
        return cursor.fetchall()


def registrar_agente(request) -> None:
    with connection.cursor() as cursor:
        # 2. cabecera HTTP concatenada a SQL
        cursor.execute("INSERT INTO log(agente) VALUES ('" + request.META["HTTP_USER_AGENT"] + "')")


def mostrar(request):
    # 3. entrada del usuario marcada como segura (XSS)
    return mark_safe(request.GET["q"])


def diagnosticar(host: str) -> None:
    # 4. shell=True con entrada del usuario (inyeccion de comandos)
    subprocess.run(f"ping -c 1 {{host}}", shell=True, check=False)
'''

APP_VULNERABLE = '''"""Aplicación de laboratorio con DEFECTOS A PROPÓSITO (control positivo de sqlmap y ZAP).

Solo corre en la red Docker `jml-lab`, sin puertos publicados. NO es código del proyecto.
"""

import html
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

BASE = sqlite3.connect(":memory:", check_same_thread=False)
BASE.executescript(
    "create table usuario(id integer primary key, nombre text);"
    "insert into usuario values (1, 'ana'), (2, 'beto'), (3, 'carla');"
)


class Manejador(BaseHTTPRequestHandler):
    def do_GET(self):
        ruta = urlparse(self.path)
        q = parse_qs(ruta.query)
        if ruta.path == "/buscar":
            # DEFECTO 1: SQL concatenado con la entrada del usuario
            try:
                filas = BASE.execute(
                    "select nombre from usuario where id = " + q.get("id", ["1"])[0]
                ).fetchall()
                cuerpo = "<p>" + ", ".join(f[0] for f in filas) + "</p>"
            except sqlite3.Error as error:  # DEFECTO 1b: el error de la base llega al navegador
                cuerpo = "<p>Error SQL: " + str(error) + "</p>"
        elif ruta.path == "/eco":
            # DEFECTO 2: la entrada vuelve al HTML sin escapar (XSS reflejado)
            cuerpo = "<p>Usted escribio: " + q.get("x", [""])[0] + "</p>"
        else:
            cuerpo = "<a href='/buscar?id=1'>buscar</a> <a href='/eco?x=hola'>eco</a>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")  # DEFECTO 3: sin cabeceras de seguridad
        self.end_headers()
        self.wfile.write(("<html><body>" + cuerpo + "</body></html>").encode())

    def log_message(self, *args):
        pass


ThreadingHTTPServer(("0.0.0.0", 8000), Manejador).serve_forever()
'''

REQUIREMENTS = """# Dependencia con vulnerabilidades publicadas: pip-audit y trivy deben reportarla.
urllib3==1.24.1
requests==2.19.0
"""

DOCKERFILE = """FROM python:3.12
ADD https://example.com/instalador.sh /instalador.sh
RUN chmod 777 /instalador.sh
# sin USER: corre como root
CMD ["python"]
"""


def generar(destino: Path) -> list[Path]:
    destino.mkdir(parents=True, exist_ok=True)
    # Se arma en ejecucion: ni este archivo ni el repositorio contienen la cadena completa.
    secreto = "ghp_" + "".join(chr(97 + (i * 7) % 26) if i % 2 else str(i % 10) for i in range(36))
    archivos = {
        "vulnerable.py": VULNERABLE.format(secreto=secreto),
        "requirements-vulnerable.txt": REQUIREMENTS,
        "Dockerfile.vulnerable": DOCKERFILE,
        "app_vulnerable.py": APP_VULNERABLE,
    }
    rutas = []
    for nombre, contenido in archivos.items():
        ruta = destino / nombre
        ruta.write_text(contenido, encoding="utf-8", newline="\n")
        rutas.append(ruta)
    return rutas


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("uso: generar.py <carpeta-destino>")
    for r in generar(Path(sys.argv[1])):
        print("generado:", r)
