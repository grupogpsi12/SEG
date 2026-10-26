"""F6-05: cruza los logs del WAF de cada rol con las rutas de `config.urls` y calcula la cobertura.

    python auditoria/scripts/cobertura-superficie.py <carpeta con waf-<rol>.log>

Una ruta cuenta como VISTA si el escáner llegó a la aplicación con ella (200, 302, 404 o 405): un 403 o
un 429 del WAF no es haber visto la ruta. Imprime, por rol, qué rutas vio y cuáles no.
"""

import os
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.adaptadores.ajustes")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
django.setup()

from django.urls import Resolver404, resolve  # noqa: E402
from tests.seguridad.rutas import rutas  # noqa: E402

LLEGAN = {"200", "302", "404", "405"}
LINEA = re.compile(r'"(?P<metodo>[A-Z]+) (?P<ruta>\S+) HTTP/[\d.]+" (?P<estado>\d{3})')


def vistas_por_rol(carpeta: Path) -> dict[str, set[str]]:
    resultado: dict[str, set[str]] = {}
    for log in sorted(carpeta.glob("waf-*.log")):
        rol = log.stem.removeprefix("waf-")
        nombres: set[str] = set()
        for linea in log.read_text(encoding="utf-8", errors="replace").splitlines():
            m = LINEA.search(linea)
            if not m or m["estado"] not in LLEGAN:
                continue
            try:
                nombres.add(resolve(urlsplit(m["ruta"]).path).url_name)
            except Resolver404:
                continue
        resultado[rol] = nombres
    return resultado


def main(carpeta: str) -> int:
    todas = set(rutas())
    por_rol = vistas_por_rol(Path(carpeta))
    unidas: set[str] = set()
    for rol, vistas in por_rol.items():
        unidas |= vistas
        print(
            f"{rol:14} {len(vistas & todas):2}/{len(todas)} rutas · no vistas: {sorted(todas - vistas)}"
        )
    pct = 100 * len(unidas & todas) / len(todas)
    print(
        f"\nUNIDOS (todos los roles): {len(unidas & todas)}/{len(todas)} = {pct:.1f} % · no vistas por ningún rol: {sorted(todas - unidas)}"
    )
    return 0 if pct >= 95 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
