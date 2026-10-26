"""Documento 1: Resultados de pruebas funcionales (casos de uso)."""

from __future__ import annotations

import json
from pathlib import Path

from reportlab.lib.units import cm
from reportlab.platypus import PageBreak, Paragraph, Spacer

import comun as c

RAIZ = Path(__file__).resolve().parents[1]
EV = RAIZ / "evidencias" / "funcionales"
SAL = RAIZ / "Documento-1-Pruebas-funcionales.pdf"


def main() -> None:
    est = c.estilos()
    pasos = json.loads((EV / "casos-de-uso.json").read_text(encoding="utf-8"))
    total = len(pasos)
    fallas = sum(p["resultado"] == "FALLA" for p in pasos)
    h: list = c.portada(est, "1", "Resultados de pruebas funcionales",
                        "Pruebas de los casos de uso del sistema, ejecutadas a través del WAF")

    h.append(Paragraph("1. Resumen", est["h1"]))
    h.append(Paragraph(
        "Este documento reúne la evidencia de las pruebas funcionales del Sistema integrado de "
        "eventos laborales (JML). Se verifican dos niveles complementarios: la suite automatizada "
        "del repositorio (pruebas unitarias, de contrato, de propiedades y de extremo a extremo) y "
        "un recorrido manual de los casos de uso contra el sistema desplegado, atravesando el WAF "
        "BunkerWeb por HTTPS.", est["cuerpo"]))
    h.append(c.tabla([
        ["Indicador", "Resultado"],
        ["Suite automatizada (pytest)", "1581 pruebas · 0 fallos · 0 omitidas"],
        ["Capas cubiertas por la suite", "dominio, aplicación, contratos, escenarios, adaptadores"],
        ["Casos de uso ejercidos a través del WAF", f"{total} pasos · {total - fallas} correctos · {fallas} con desvío"],
        ["Flujos de negocio completos (ING, VAC, CDP, RET, EMG)", "Verificados de extremo a extremo con GLPI real"],
        ["Tickets generados en GLPI durante la prueba", "20 tickets en las 4 colas (worker + outbox)"],
    ], [6.5 * cm, 10.5 * cm], est))
    h.append(Paragraph(
        "No se registraron fallos. El único desvío del recorrido fue un código 429 "
        "(límite de peticiones del WAF, 2 req/s) en un paso ejecutado demasiado rápido; al repetir "
        "el mismo paso con la pausa correspondiente respondió 200. Es un artefacto del ritmo de la "
        "prueba, no un defecto del sistema, y se documenta como tal.", est["pie_tabla"]))

    h.append(Paragraph("2. Entorno y método", est["h2"]))
    h.append(Paragraph(
        "El sistema se levantó con <font face='Courier'>docker compose -f infra/compose.yaml -f "
        "infra/compose.local.yaml</font>: BunkerWeb (WAF) como único servicio con puertos "
        "publicados, la aplicación web y el worker, PostgreSQL 17 local (sustituye a Supabase, con "
        "los mismos roles y el dueño separado, ADR-028) y GLPI 11.0.11 con su MariaDB. Las "
        "peticiones se dirigieron a <font face='Courier'>https://app.localhost</font>, de modo que "
        "todo el tráfico pasó por el WAF en modo bloqueo.", est["cuerpo"]))
    h.append(Paragraph(
        "El ingreso real exige contraseña y un segundo factor TOTP contra Supabase Auth, que no se "
        "ejercita aquí por no disponer de cuentas de prueba en ese servicio de terceros. Ese flujo "
        "está cubierto por la suite automatizada (<font face='Courier'>test_ingreso_web.py</font>, "
        "<font face='Courier'>test_supabase_auth.py</font>, 8/8 contra el Supabase real). Para los "
        "demás casos de uso se crearon sesiones de prueba en la base local, una por rol, "
        "equivalentes a <font face='Courier'>force_login</font> del cliente de Django: autentican la "
        "identidad sin reemplazar ninguna regla de autorización, que se evalúa en cada vista.",
        est["cuerpo"]))
    h.append(Paragraph(
        "Evidencia cruda: <font face='Courier'>evidencias/funcionales/</font> "
        "(<font face='Courier'>casos-de-uso.json</font>, <font face='Courier'>casos-de-uso.txt</font>, "
        "<font face='Courier'>junit-suite.xml</font>, carpeta <font face='Courier'>pantallas/</font>). "
        "El guion del recorrido es <font face='Courier'>scripts/casos_de_uso.py</font>.", est["pie_tabla"]))

    h.append(Paragraph("3. Suite automatizada por capa", est["h2"]))
    h.append(c.tabla([
        ["Capa", "Pruebas", "Qué verifica"],
        ["dominio", "820", "Reglas puras: máquina de estados, tickets, auditoría encadenada, perfiles"],
        ["aplicación", "214", "Casos de uso con dobles en memoria; atomicidad de la unidad de trabajo"],
        ["contratos", "222", "Cada puerto con su doble y su adaptador real, sin cambiar la prueba"],
        ["escenarios", "12", "ING, VAC, CDP, CSU, RET y EMG completos en memoria"],
        ["adaptadores", "313", "Vistas, persistencia, GLPI, identidad, worker, infraestructura"],
    ], [3.2 * cm, 1.8 * cm, 12 * cm], est))
    h.append(Paragraph(
        "Ejecución: <font face='Courier'>.venv/Scripts/python.exe -m pytest tests/dominio "
        "tests/aplicacion tests/contratos tests/escenarios tests/adaptadores</font> → "
        "<b>1581 passed in 31.65s</b> (<font face='Courier'>junit-suite.xml</font>).", est["pie_tabla"]))
    h.append(PageBreak())

    h.append(Paragraph("4. Recorrido de casos de uso a través del WAF", est["h1"]))
    h.append(Paragraph(
        "Cada paso indica el caso de uso, el rol que lo ejecuta, el método y la ruta, el código HTTP "
        "esperado y el obtenido, y el requisito del SRS que cubre. «PASA» significa que el código y "
        "las comprobaciones de contenido (presencia del identificador generado, ausencia de los "
        "campos restringidos) coincidieron con lo esperado.", est["cuerpo"]))

    cu_titulos = {
        "CU-01": "Acceso público, TLS y protección de rutas",
        "CU-02": "Solicitante registra sus vacaciones",
        "CU-03": "Deduplicación de solicitudes abiertas",
        "CU-04": "Jefe registra un cambio de su subordinado",
        "CU-05": "RRHH aprueba y rechaza; control de rol",
        "CU-06": "RRHH emite un ingreso con soporte PDF",
        "CU-07": "RRHH emite un retiro con motivo restringido",
        "CU-08": "RRHH emite una emergencia",
        "CU-09": "Técnicos: dashboard, búsqueda, ficha y CSV",
        "CU-10": "Control de acceso por rol (denegaciones)",
        "CU-11": "Auditor consulta y verifica la cadena",
        "CU-12": "Administrador: matriz, usuarios, errores",
        "CU-13": "Cierre de sesión",
    }
    datos = [["CU", "Descripción", "Rol", "Método / ruta", "Esp.", "Obt.", "Requisitos"]]
    for p in pasos:
        datos.append([
            p["cu"].replace("-", "‑"), p["descripcion"], p["rol"],
            Paragraph(f"{p['metodo']} {p['ruta']}", est["celda_mono"]),
            p["esperado"], p["obtenido"], ", ".join(p["requisitos"]),
        ])
    h.append(c.tabla(datos, [1.3 * cm, 5.0 * cm, 1.3 * cm, 4.1 * cm, 1.0 * cm, 1.0 * cm, 2.3 * cm], est))
    h.append(Paragraph(
        "Los códigos obtenidos 403 y 404 son los esperados: 403 cuando el rol no tiene permiso "
        "(control de acceso), 404 cuando se oculta la existencia de un recurso restringido a quien "
        "no debe verlo (el técnico ante el detalle de un retiro). Fuente: "
        "<font face='Courier'>casos-de-uso.json</font>.", est["pie_tabla"]))
    h.append(PageBreak())

    h.append(Paragraph("5. Evidencia por caso de uso (capturas)", est["h1"]))
    h.append(Paragraph(
        "Capturas del sistema real tomadas durante el recorrido. La banda oscura superior de cada "
        "imagen indica el método, la ruta, el rol y el código HTTP de la petición que la generó. Los "
        "valores de token visibles en formularios están enmascarados.", est["cuerpo"]))
    figs = [
        ("01-ingreso.png", "CU-01. Página de ingreso servida por HTTPS a través del WAF. Pide correo y contraseña; el segundo factor TOTP es el paso siguiente."),
        ("03-nueva-vacaciones.png", "CU-02. Formulario de registro de vacaciones del solicitante, con validación de fechas en el servidor."),
        ("04-bandeja-rrhh.png", "CU-05. Bandeja de RRHH: solicitudes pendientes de aprobación y contratos próximos a vencer (RF-28)."),
        ("05-detalle-ret-rrhh.png", "CU-07. Detalle de un retiro visto por RRHH: el motivo restringido (centinela) es visible solo para este rol (RD-05)."),
        ("06-detalle-ret-tecnico-404.png", "CU-09. El mismo retiro solicitado por un técnico responde 404: no se confirma siquiera que el recurso exista."),
        ("07-dashboard-tecnico.png", "CU-09. Dashboard de TI con gráficos SVG generados en el servidor, sin JavaScript de terceros (RF-29, RF-30)."),
        ("08-ficha-colaborador.png", "CU-09. Ficha de un colaborador retirado: datos laborales y cuentas derivadas, sin el motivo restringido (CA-10)."),
        ("10-auditoria-verificada.png", "CU-11. Vista del Auditor: la cadena de hashes de la auditoría se verifica íntegra desde la interfaz (RF-36)."),
        ("09-solicitante-sin-permiso-403.png", "CU-10. Un solicitante que pide la bandeja de RRHH recibe 403: el control de acceso se evalúa en cada vista."),
        ("11-matriz-perfiles.png", "CU-12. Área de administración: matriz de perfiles de acceso, restringida al rol Administrador (RF-37)."),
    ]
    for arch, pie in figs:
        for fl in c.figura(str(EV / "pantallas" / arch), est, pie, ancho_cm=14.5):
            h.append(fl)
        h.append(Spacer(1, 0.2 * cm))

    h.append(PageBreak())
    h.append(Paragraph("6. Conclusión", est["h1"]))
    h.append(Paragraph(
        "El sistema cumple los casos de uso definidos en el SRS. La suite automatizada (1581 pruebas, "
        "sin fallos) respalda las reglas de negocio a nivel de unidad, contrato y escenario; el "
        "recorrido a través del WAF confirma que esas reglas se sostienen en el sistema desplegado, "
        "incluyendo el control de acceso por rol, la deduplicación garantizada por la base de datos, "
        "la confidencialidad de los campos restringidos y la generación de tickets en GLPI. Los "
        "flujos ING, VAC, CDP, RET y EMG se ejercieron de principio a fin.", est["cuerpo"]))
    c.construir(str(SAL), "Pruebas funcionales", h)


if __name__ == "__main__":
    main()
