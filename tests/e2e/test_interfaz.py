"""Item 5.8: ING, VAC, RET y EMG por la interfaz, en un navegador real, a través del WAF y hasta GLPI.

Lo corre `infra/scripts/e2e-interfaz.sh` dentro de la red de Docker. Así llega al WAF como un
navegador y, a la vez, a la API de GLPI, que desde fuera está cerrada. Sin las variables se omite
(S-28).

El cierre de cada solicitud tras la sincronización ya lo cubre `tests/integracion/
test_flujos_glpi_real.py`. Aquí se prueba el camino real de la persona: formularios, CSRF, subida del
PDF por el WAF, bandeja de RRHH y tickets creados en GLPI. Además, en todas las páginas, que no haya
errores de consola, violaciones de la CSP ni websockets (invariante 11).
"""

import json
import os
import re
import time
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

SIN_E2E = "JML_E2E_DATOS" not in os.environ
pytestmark = pytest.mark.skipif(SIN_E2E, reason="S-28: sin el stack de pruebas (JML_E2E_*)")

BASE = "https://app.localhost"
HOY = date.today()


def _fecha(dias: int) -> str:
    return (HOY + timedelta(days=dias)).isoformat()


@pytest.fixture(scope="module")
def datos() -> dict[str, str]:
    leido: dict[str, str] = json.loads(
        Path(os.environ["JML_E2E_DATOS"]).read_text(encoding="utf-8")
    )
    return leido


@pytest.fixture(scope="module")
def navegador() -> Iterator[Any]:
    from playwright.sync_api import sync_playwright

    # app.localhost -> bunkerweb (por la red interna); el certificado local es autofirmado.
    with sync_playwright() as p:
        b = p.chromium.launch(
            args=[f"--host-resolver-rules=MAP app.localhost:443 {os.environ['JML_E2E_WAF']}"]
        )
        yield b
        b.close()


class Vigilada:
    """Una pestaña con la sesión de una persona y un registro de lo que no debe pasar."""

    def __init__(self, navegador: Any, sesion: str) -> None:
        self.contexto = navegador.new_context(ignore_https_errors=True)
        self.contexto.add_cookies(
            [{"name": "sessionid", "value": sesion, "domain": "app.localhost", "path": "/",
              "secure": True, "httpOnly": True}]
        )  # fmt: skip
        self.pagina = self.contexto.new_page()
        self.problemas: list[str] = []
        self.pagina.on(
            "console",
            lambda m: (
                self.problemas.append(f"consola {m.type}: {m.text}")
                if m.type == "error" or "Content Security Policy" in m.text
                else None
            ),
        )
        self.pagina.on("websocket", lambda w: self.problemas.append(f"websocket: {w.url}"))
        self.pagina.on("pageerror", lambda e: self.problemas.append(f"error de pagina: {e}"))
        self.respuestas: list[str] = []  # para el diagnóstico si una prueba falla
        self.pagina.on(
            "response",
            lambda r: self.respuestas.append(
                f"{r.request.method} {r.url} -> {r.status} {r.headers.get('location', '')}"
            ),
        )

    def ir(self, ruta: str) -> Any:
        r = self.pagina.goto(BASE + ruta)
        assert r is not None, ruta
        assert r.status == 200, (ruta, r.status)
        return self.pagina

    def mensaje(self) -> str:
        """El aviso tras enviar; si el formulario volvió con errores, falla mostrándolos."""
        aviso = self.pagina.locator("p.mensaje, ul.errorlist").first
        try:
            aviso.wait_for(timeout=30_000)
        except Exception:
            cuerpo = self.pagina.locator("body").inner_text()[:300]
            raise AssertionError((self.pagina.url, cuerpo[:120], self.respuestas[-6:])) from None
        errores = self.pagina.locator("ul.errorlist")
        assert errores.count() == 0, (self.pagina.url, errores.all_inner_texts())
        texto: str = aviso.inner_text()
        return texto

    def cerrar(self) -> None:
        self.contexto.close()
        assert self.problemas == [], (self.problemas, [r for r in self.respuestas if "static" in r])


@pytest.fixture
def rrhh(navegador: Any, datos: dict[str, str]) -> Iterator[Vigilada]:
    v = Vigilada(navegador, datos["sesion_rrhh"])
    yield v
    v.cerrar()


@pytest.fixture
def solicitante(navegador: Any, datos: dict[str, str]) -> Iterator[Vigilada]:
    v = Vigilada(navegador, datos["sesion_solicitante"])
    yield v
    v.cerrar()


@pytest.fixture(scope="module")
def glpi() -> Any:
    from tests.dobles.glpi_real import TecnicoGlpiReal

    return TecnicoGlpiReal(
        os.environ["JML_GLPI_API_URL"],
        os.environ["JML_GLPI_APP_TOKEN"],
        os.environ["JML_GLPI_ADMIN_TOKEN"],
    )


def tickets_en_glpi(
    glpi: Any, solicitud: str, cuantos: int, espera_s: float = 150
) -> list[dict[str, Any]]:
    """Espera a que el worker (bandeja cada 30 s) cree los tickets de la solicitud."""
    limite = time.monotonic() + espera_s
    while True:
        tickets = [
            t
            for t in glpi._pedir(
                "GET", "Ticket", params={"searchText[externalid]": solicitud, "range": "0-99"}
            )
            if str(t.get("externalid", "")).startswith(solicitud + ":")
        ]
        if len(tickets) >= cuantos or time.monotonic() > limite:
            assert len(tickets) >= cuantos, (solicitud, len(tickets))
            return tickets
        time.sleep(5)


def _id(mensaje: str) -> str:
    hallado = re.search(r"SOL-\d{4}-\d{6}", mensaje)
    assert hallado, mensaje
    return hallado.group(0)


def test_ING_por_el_navegador_con_el_pdf_llega_a_glpi(
    rrhh: Vigilada, datos: dict[str, str], glpi: Any, tmp_path: Path
) -> None:
    pdf = tmp_path / "vinculacion.pdf"
    pdf.write_bytes(b"%PDF-1.7\n" + b"0" * (2 * 1024 * 1024))  # 2 MB por el WAF
    p = rrhh.ir("/solicitudes/nueva/ING")
    p.fill("[name=fecha_efectiva]", _fecha(10))
    p.fill("[name=nombres]", "Persona")
    p.fill("[name=apellidos]", f"Interfaz {datos['marca']}")
    p.fill("[name=documento]", datos["documento_ing"])
    p.select_option("[name=vinculacion]", "empleado")
    p.fill("[name=departamento]", "Finanzas")
    p.fill("[name=cargo]", "Analista")
    p.fill("[name=sede]", "Bogotá")
    p.check("[name=requiere_equipo]")
    p.select_option("[name=tipo_equipo]", index=1)
    p.set_input_files("[name=soporte_pdf]", str(pdf))
    p.fill("[name=justificacion]", "Contratación aprobada (prueba de interfaz)")
    p.get_by_role("button", name="Enviar").click()
    assert "emitida" in rrhh.mensaje()
    tickets = tickets_en_glpi(glpi, _id(rrhh.mensaje()), 4)
    colas = {t["externalid"].split(":")[1] for t in tickets}
    assert colas >= {"AD", "COMUNICACIONES", "LICENCIAS", "INVENTARIO"}


def test_VAC_la_registra_el_colaborador_y_la_aprueba_RRHH_en_la_bandeja(
    solicitante: Vigilada, rrhh: Vigilada, glpi: Any
) -> None:
    p = solicitante.ir("/solicitudes/nueva/VAC")
    p.fill("[name=fecha_efectiva]", _fecha(12))
    p.fill("[name=fecha_regreso]", _fecha(20))
    p.get_by_role("button", name="Enviar").click()
    assert "pendiente de aprobación" in solicitante.mensaje()
    sid = _id(solicitante.mensaje())
    bandeja = rrhh.ir("/bandeja")
    fila = bandeja.locator("tr", has_text=sid)
    fila.get_by_role("button", name="Aprobar").click()
    assert "aprobada" in rrhh.mensaje()
    tickets_en_glpi(glpi, sid, 2)  # suspensión en AD y en Licencias, y su reactivación programada


def test_RET_emitido_por_RRHH_llega_a_glpi_sin_el_motivo(
    rrhh: Vigilada, datos: dict[str, str], glpi: Any
) -> None:
    motivo = f"CENTINELA-INTERFAZ-{datos['marca']}"
    p = rrhh.ir("/solicitudes/nueva/RET")
    p.fill("[name=fecha_efectiva]", _fecha(8))
    p.fill("[name=documento_del_colaborador]", datos["documento_ret"])
    p.select_option("[name=subtipo_elegido]", "fin_de_contrato")
    p.fill("[name=motivo]", motivo)
    p.fill("[name=justificacion]", "Fin de contrato (prueba de interfaz)")
    p.get_by_role("button", name="Enviar").click()
    assert "emitida" in rrhh.mensaje()
    sid = _id(rrhh.mensaje())
    tickets = tickets_en_glpi(glpi, sid, 4)
    assert all(motivo not in glpi.ticket(str(t["id"]))["content"] for t in tickets)  # CA-10


def test_EMG_emitida_por_RRHH_llega_a_glpi_con_prioridad_muy_alta(
    rrhh: Vigilada, datos: dict[str, str], glpi: Any
) -> None:
    p = rrhh.ir("/solicitudes/nueva/EMG")
    p.fill("[name=documento_del_colaborador]", datos["documento_emg"])
    p.select_option("[name=subtipo_elegido]", "fuga_detectada")
    p.fill("[name=reportado_por]", "Seguridad")
    p.fill("[name=hora_del_hecho]", (HOY - timedelta(days=0)).isoformat() + "T08:00")
    p.fill("[name=descripcion]", f"CENTINELA-EMG-{datos['marca']}")
    p.fill("[name=justificacion]", "Emergencia (prueba de interfaz)")
    p.get_by_role("button", name="Enviar").click()
    assert "emitida" in rrhh.mensaje()
    tickets = tickets_en_glpi(glpi, _id(rrhh.mensaje()), 4)
    inmediatos = [t for t in tickets if t["externalid"].split(":")[2] == "cierre_inmediato"]
    assert inmediatos
    assert all(int(t["priority"]) == 5 for t in inmediatos)  # CA-06
