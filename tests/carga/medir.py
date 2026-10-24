"""Medición de RNF-06: p95 por página con N usuarios concurrentes (20 por defecto).

    python -m tests.carga.medir http://web:8000 sesiones.json semilla.json [usuarios] [vueltas]

Cada usuario es un hilo con su propia sesión (técnico, RRHH o Auditor, repartidos) que recorre
sus páginas en bucle, sin pausas: es más exigente que 20 personas reales. Imprime un JSON con el
p50, el p95 y el máximo por página, más los errores.
"""

import json
import statistics
import sys
import threading
import time
from collections import defaultdict
from pathlib import Path

import httpx

UMBRAL_PAGINA_S = 0.8  # RNF-06
UMBRAL_DASHBOARD_S = 2.0


def paginas(semilla: dict[str, str]) -> dict[str, list[tuple[str, str]]]:
    colaborador, solicitud = semilla["colaborador_de_ejemplo"], semilla["solicitud_de_ejemplo"]
    return {
        "tecnico": [
            ("dashboard", "/dashboard"),
            ("cuentas", "/cuentas"),
            ("cuentas filtradas", "/cuentas?nombre=Ana&sede=Cali"),
            ("cuentas pagina 3", "/cuentas?estado_de_cuenta=activa&pagina=3"),
            ("ficha", f"/colaboradores/{colaborador}"),
        ],
        "rrhh": [
            ("solicitudes", "/solicitudes"),
            ("bandeja", "/bandeja"),
            ("detalle", f"/solicitudes/{solicitud}"),
        ],
        "auditor": [("auditoria", "/auditoria")],
    }


def percentil(valores: list[float], p: float) -> float:
    ordenados = sorted(valores)
    return ordenados[min(len(ordenados) - 1, round(p * (len(ordenados) - 1)))]


def medir(
    base: str, sesiones: dict[str, str], semilla: dict[str, str], usuarios: int, vueltas: int
) -> dict[str, object]:
    rutas = paginas(semilla)
    roles = ["tecnico"] * (usuarios // 2) + ["rrhh"] * (usuarios // 3)
    roles += ["auditor"] * (usuarios - len(roles))
    tiempos: dict[str, list[float]] = defaultdict(list)
    errores: dict[str, int] = defaultdict(int)
    candado = threading.Lock()
    barrera = threading.Barrier(usuarios)

    def usuario(rol: str) -> None:
        with httpx.Client(base_url=base, cookies={"sessionid": sesiones[rol]}, timeout=60) as c:
            barrera.wait()  # todos empiezan a la vez: 20 concurrentes de verdad
            for _ in range(vueltas):
                for nombre, ruta in rutas[rol]:
                    t0 = time.perf_counter()
                    r = c.get(ruta)
                    dt = time.perf_counter() - t0
                    with candado:
                        if r.status_code == 200:
                            tiempos[nombre].append(dt)
                        else:
                            errores[f"{nombre} HTTP {r.status_code}"] += 1

    hilos = [threading.Thread(target=usuario, args=(rol,)) for rol in roles]
    inicio = time.perf_counter()
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    total = time.perf_counter() - inicio
    resumen = {}
    for nombre, valores in sorted(tiempos.items()):
        umbral = UMBRAL_DASHBOARD_S if nombre == "dashboard" else UMBRAL_PAGINA_S
        p95 = percentil(valores, 0.95)
        resumen[nombre] = {
            "peticiones": len(valores),
            "p50_ms": round(statistics.median(valores) * 1000),
            "p95_ms": round(p95 * 1000),
            "max_ms": round(max(valores) * 1000),
            "umbral_ms": round(umbral * 1000),
            "cumple": p95 < umbral,
        }
    return {
        "usuarios_concurrentes": usuarios,
        "peticiones": sum(len(v) for v in tiempos.values()),
        "segundos": round(total, 1),
        "paginas": resumen,
        "errores": dict(errores),
    }


if __name__ == "__main__":
    base, ruta_sesiones, ruta_semilla = sys.argv[1:4]
    usuarios = int(sys.argv[4]) if len(sys.argv) > 4 else 20
    vueltas = int(sys.argv[5]) if len(sys.argv) > 5 else 10
    sesiones = json.loads(Path(ruta_sesiones).read_text(encoding="utf-8"))
    semilla = json.loads(Path(ruta_semilla).read_text(encoding="utf-8"))
    print(json.dumps(medir(base, sesiones, semilla, usuarios, vueltas), ensure_ascii=False))
