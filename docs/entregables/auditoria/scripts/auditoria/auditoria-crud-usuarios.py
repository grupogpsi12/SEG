# ruff: noqa: B023, RUF100
"""CRUD de usuarios por el WAF con navegador real. No crea ni borra nada en Supabase: usa un id
inventado que solo existe en la base local. Lee cookies de un archivo; no las imprime."""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "https://app.localhost"
sesiones = dict(
    x.split()
    for x in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
    if len(x.split()) == 2
)
V = Path(sys.argv[2])
COOKIE = sesiones.pop("COOKIE")
ID = "00000000-0000-4000-8000-0000000000aa"
fallos = []


def ok(nombre, cond, extra=""):
    print("OK   " if cond else "FALLA", nombre, extra)
    if not cond:
        fallos.append(nombre)


with sync_playwright() as p:
    nav = p.chromium.launch()
    ctx = nav.new_context(ignore_https_errors=True, viewport={"width": 1360, "height": 900})
    ctx.add_cookies([{"name": COOKIE, "value": sesiones["administrador"], "url": BASE + "/"}])
    pag = ctx.new_page()
    malas = []
    pag.on(
        "response",
        lambda r: (
            malas.append((r.status, r.url.replace(BASE, "")[:70])) if r.status >= 400 else None
        ),
    )

    def fila():
        return pag.locator("tbody tr", has_text=ID)

    pag.goto(BASE + "/administracion/usuarios")
    ok("lista: abre", pag.locator("h1").inner_text() == "Usuarios y roles")
    ok("lista: muestra correos reales", pag.locator("tbody td", has_text="@").count() > 0)
    ok("lista: sin aviso de servicio caido", pag.locator("text=no está disponible").count() == 0)

    pag.wait_for_timeout(300)
    pag.click("text=Crear usuario")
    pag.fill("#id_correo", "correo-malo")
    pag.evaluate("document.querySelector('main form').noValidate = true")
    pag.click("main button[type=submit]")
    ok(
        "crear: correo invalido se rechaza sin llamar a Supabase",
        pag.locator(".errorlist").count() > 0,
    )

    pag.goto(BASE + "/administracion/usuarios/vincular")
    pag.evaluate("document.querySelector('main form').noValidate = true")
    pag.fill("#id_usuario", "no-es-uuid")
    pag.click("main button[type=submit]")
    ok("vincular: id invalido se rechaza", "UUID" in pag.locator("main").inner_text())
    pag.fill("#id_usuario", ID)
    pag.check("input[name=roles][value=auditor]")
    pag.click("main button[type=submit]")
    ok("vincular: crea la fila", fila().count() == 1, pag.url.replace(BASE, ""))
    pag.screenshot(path=str(V / "usuarios.png"), full_page=True)

    pag.wait_for_timeout(300)
    f = fila()
    f.locator("input[name=roles][value=rrhh]").check()
    f.locator("button", has_text="Guardar roles").click()
    ok(
        "roles: incompatibles se rechazan",
        pag.locator(".mensaje.error").count() == 1,
        pag.locator(".mensaje").first.inner_text()[:70],
    )

    pag.wait_for_timeout(300)
    f = fila()
    f.locator("input[name=colaborador]").fill("no-existe")
    f.locator("button", has_text="Guardar").first.click()
    ok("colaborador: inexistente se rechaza", pag.locator(".mensaje.error").count() == 1)

    pag.wait_for_timeout(300)
    fila().locator("button", has_text="Desactivar").click()
    ok(
        "desactivar: cuenta sin Supabase queda inactiva",
        fila().locator(".pildora", has_text="Inactivo").count() == 1,
        pag.locator(".mensaje").first.inner_text()[:60],
    )

    pag.wait_for_timeout(300)
    fila().locator("button", has_text="Reactivar").click()
    ok(
        "reactivar: sin cuenta en Supabase lo explica",
        pag.locator(".mensaje.error").count() == 1,
        pag.locator(".mensaje").first.inner_text()[:60],
    )

    propia = pag.locator("tbody tr", has_text="Es su cuenta")
    ok("su propia cuenta no ofrece acciones", propia.locator("button").count() == 0)
    print("respuestas >= 400:", malas)
    ok("sin respuestas >= 400", malas == [])

    pag.goto(BASE + "/tickets")
    pag.screenshot(path=str(V / "tickets-admin.png"))
    ctx.close()

    ctx = nav.new_context(ignore_https_errors=True, viewport={"width": 1360, "height": 900})
    ctx.add_cookies([{"name": COOKIE, "value": sesiones["rrhh"], "url": BASE + "/"}])
    pag = ctx.new_page()
    pag.goto(BASE + "/solicitudes")
    ok(
        "mis solicitudes: muestra avance",
        pag.locator("text=de 4 tickets").count() > 0 or pag.locator("text=tickets").count() > 0,
    )
    pag.screenshot(path=str(V / "mis-solicitudes.png"))
    enlace = pag.locator("tbody a").first
    if enlace.count():
        pag.wait_for_timeout(200)
        enlace.click()
        ok("detalle: abre con avance", pag.locator("h2", has_text="Avance").count() == 1)
        pag.screenshot(path=str(V / "detalle.png"))
    pag.wait_for_timeout(200)
    pag.goto(BASE + "/bandeja")
    pag.click("a.boton")
    ok("Crear usuario abre el ingreso", pag.url.endswith("/solicitudes/nueva/ING"))
    ctx.close()
    nav.close()
print("fallos:", fallos)
sys.exit(1 if fallos else 0)
