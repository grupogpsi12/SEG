"""Consultas SQL y tiempo por página con un solo usuario (item 4.1), sobre la base de carga.

python -m tests.carga.perfilar sesiones.json semilla.json
"""

import json
import sys
import time
from pathlib import Path

import django

django.setup()

from django.db import connection  # noqa: E402
from django.test import Client  # noqa: E402
from django.test.utils import CaptureQueriesContext  # noqa: E402

from tests.carga.medir import paginas  # noqa: E402

sesiones = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
semilla = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
for rol, rutas in paginas(semilla).items():
    cliente = Client(HTTP_HOST="web")
    cliente.cookies["sessionid"] = sesiones[rol]
    for nombre, ruta in rutas:
        cliente.get(ruta)  # calienta
        with CaptureQueriesContext(connection) as c:
            t0 = time.perf_counter()
            r = cliente.get(ruta)
            dt = time.perf_counter() - t0
        lentas = sorted(c.captured_queries, key=lambda q: -float(q["time"]))[:2]
        print(
            f"{nombre:18} HTTP {r.status_code} {dt * 1000:6.0f} ms {len(c.captured_queries):5} consultas"
            f" | mas lenta: {lentas[0]['time'] if lentas else '-'} s {lentas[0]['sql'][:110] if lentas else ''}"
        )
