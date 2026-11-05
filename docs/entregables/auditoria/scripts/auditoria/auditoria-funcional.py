# ruff: noqa: B023, RUF100
"""Auditoria funcional por el WAF con navegador real: recorre cada rol siguiendo sus enlaces, usa
sus formularios sin efectos y anota toda respuesta >= 400, errores de consola y desbordes.
Lee las cookies de un archivo temporal; no las imprime. No crea cuentas en Supabase."""

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "https://app.localhost"
lineas = Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
SALIDA = Path(sys.argv[2])
sesiones = dict(x.split() for x in lineas if len(x.split()) == 2)
COOKIE = sesiones.pop("COOKIE")
PROHIBIDAS = ("/salir", "/aprobar", "/rechazar", "/cancelar", "/reintentar", ".csv")
hallazgos = []
resumen = {}


def patron(ruta):
    r = re.sub(r"SOL-\d{4}-\d{6}", "SOL", ruta)
    r = re.sub(r"/colaboradores/[^/?]+", "/colaboradores/X", r)
    r = re.sub(r"\d+", "N", r)
    return r


def anotar(rol, pagina, tipo, detalle):
    hallazgos.append({"rol": rol, "pagina": pagina, "tipo": tipo, "detalle": detalle})


with sync_playwright() as p:
    nav = p.chromium.launch()
    for rol, clave in sesiones.items():
        ctx = nav.new_context(ignore_https_errors=True, viewport={"width": 1360, "height": 900})
        ctx.add_cookies([{"name": COOKIE, "value": clave, "url": BASE + "/"}])
        pag = ctx.new_page()
        actual = {"ruta": ""}
        pag.on(
            "response",
            lambda r: (
                anotar(rol, actual["ruta"], f"HTTP {r.status}", r.url.replace(BASE, "")[:90])
                if r.status >= 400 and "localhost" in r.url
                else None
            ),
        )
        pag.on(
            "console",
            lambda m: (
                anotar(rol, actual["ruta"], "consola", m.text[:140]) if m.type == "error" else None
            ),
        )
        pag.on("pageerror", lambda e: anotar(rol, actual["ruta"], "js", str(e)[:140]))
        cola, vistos, patrones = ["/solicitudes"], set(), Counter()
        while cola and len(vistos) < 70:
            ruta = cola.pop(0)
            if ruta in vistos:
                continue
            vistos.add(ruta)
            actual["ruta"] = ruta
            pag.wait_for_timeout(650)
            r = pag.goto(BASE + ruta)
            if r.status != 200:
                continue
            if pag.evaluate("document.documentElement.scrollWidth - innerWidth") > 0:
                anotar(rol, ruta, "desborde", "")
            if not pag.locator("h1").count():
                anotar(rol, ruta, "sin h1", "")
            for h in pag.eval_on_selector_all("a[href]", "e => e.map(x => x.getAttribute('href'))"):
                if h.startswith("?"):
                    h = ruta.split("?")[0] + h
                if (
                    not h.startswith("/")
                    or any(x in h for x in PROHIBIDAS)
                    or h.startswith("/static")
                ):
                    continue
                pt = patron(h)
                if patrones[pt] < 2:
                    patrones[pt] += 1
                    cola.append(h)
        # Formularios sin efectos: filtros GET y POST vacios o invalidos.
        pruebas = []
        if "/tickets" in vistos:
            pruebas.append(("/tickets", "get"))
        if "/cuentas" in vistos:
            pruebas.append(("/cuentas", "get"))
        for ruta in sorted(vistos):
            if re.fullmatch(r"/solicitudes/nueva/[A-Z]{3}", ruta) or ruta in (
                "/administracion/usuarios/crear",
                "/administracion/usuarios/vincular",
                "/administracion/perfil",
            ):
                pruebas.append((ruta, "post"))
        for ruta, tipo in pruebas:
            actual["ruta"] = ruta + " [formulario]"
            pag.wait_for_timeout(650)
            pag.goto(BASE + ruta)
            pag.evaluate(
                "document.querySelectorAll('[required]').forEach(e => e.removeAttribute('required'))"
            )
            pag.wait_for_timeout(250)
            boton = pag.locator("main form button[type=submit]").first
            with pag.expect_navigation() as n:
                boton.click()
            if n.value.status not in (200, 302):
                anotar(rol, ruta, f"formulario {n.value.status}", "")
            if tipo == "post" and not pag.locator(".errorlist").count():
                anotar(rol, ruta, "POST vacio sin errores visibles", pag.url.replace(BASE, ""))
        # Filtros seguidos, sin pausa: el 429 de ADR-034.
        if "/tickets" in vistos:
            actual["ruta"] = "/tickets [rafaga]"
            pag.goto(BASE + "/tickets")
            for v in ("LICENCIAS", "AD", "INVENTARIO", "COMUNICACIONES"):
                pag.select_option("#id_cola", v)
                with pag.expect_navigation():
                    pag.click("main button[type=submit]")
        # Movil
        pag.set_viewport_size({"width": 390, "height": 800})
        for ruta in list(sorted(vistos))[:12]:
            actual["ruta"] = ruta + " [movil]"
            pag.wait_for_timeout(650)
            r = pag.goto(BASE + ruta)
            if (
                r.status == 200
                and pag.evaluate("document.documentElement.scrollWidth - innerWidth") > 0
            ):
                anotar(rol, ruta, "desborde movil", "")
        resumen[rol] = sorted(vistos)
        ctx.close()
    nav.close()

por = defaultdict(list)
for h in hallazgos:
    por[(h["tipo"], patron(h["detalle"] or h["pagina"]))].append(h["rol"])
SALIDA.write_text(
    json.dumps({"paginas": resumen, "hallazgos": hallazgos}, ensure_ascii=False, indent=1),
    encoding="utf-8",
)
for rol, v in resumen.items():
    print(rol, len(v), "paginas")
print("--- hallazgos:", len(hallazgos))
for (t, d), roles in sorted(por.items()):
    print(t, "|", d, "|", dict(Counter(roles)))
