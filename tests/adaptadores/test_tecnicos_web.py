"""Fase 4 por la web: dashboard (RF-29 a RF-31, CA-15), busqueda, ficha (RF-32, RF-33, CA-16),
CSV (RF-34) y graficos SVG (4.2). Datos: la misma semilla de las pruebas de consultas, sobre el ORM.
"""

import csv
import io
from typing import Any

import pytest
from django.test import Client

from jml.adaptadores.entrada.web import composicion
from jml.adaptadores.entrada.web.graficos import barras
from jml.adaptadores.entrada.web.tecnicos import _celda
from jml.adaptadores.salida.persistencia.repositorios import RepositoriosDjango
from tests.aplicacion.test_consultas import semilla
from tests.fabricas import AHORA, SENTINELA
from tests.mundo import Mundo

pytestmark = pytest.mark.django_db

RUTAS = ["/dashboard", "/cuentas", "/cuentas.csv", "/colaboradores/col-1"]


@pytest.fixture
def mundo(monkeypatch: pytest.MonkeyPatch) -> Mundo:
    m, _ = semilla(RepositoriosDjango)
    monkeypatch.setattr(composicion, "reloj", lambda: m.reloj)
    return m


def como(usuario: str) -> Client:
    c = Client()
    s = c.session
    s["usuario_id"], s["inicio"] = usuario, AHORA.timestamp()
    s.save()
    return c


def texto(r: Any) -> str:
    return bytes(r.content).decode()


@pytest.mark.parametrize("usuario", ["u-rrhh", "u-col", "u-jefe", "u-aud", "u-admin"])
def test_CA_15_solo_los_roles_tecnicos_entran(mundo: Mundo, usuario: str) -> None:
    for ruta in RUTAS:
        assert como(usuario).get(ruta).status_code == 403, ruta


def test_el_menu_muestra_el_dashboard_solo_a_tecnicos(mundo: Mundo) -> None:
    assert "/dashboard" in texto(como("u-tec-com").get("/solicitudes"))
    assert "/dashboard" not in texto(como("u-rrhh").get("/solicitudes"))


def test_CA_15_el_dashboard_muestra_la_hora_y_no_se_recarga_solo(mundo: Mundo) -> None:
    r = como("u-tec-ad").get("/dashboard")
    pagina = texto(r)
    assert r.status_code == 200
    assert "Consultado: 2026-10-" in pagina
    assert 'href="/dashboard">Actualizar' in pagina  # RF-29: actualizar = volver a pedir
    for prohibido in ("<script", "http-equiv", "WebSocket", "EventSource"):
        assert prohibido not in pagina  # invariante 11
    assert r["Content-Security-Policy"].startswith("default-src 'self'")
    for letra in "abcdefgh":
        assert f"({letra})" in pagina
    assert SENTINELA not in pagina


def test_RF_31_cada_tecnico_ve_su_cola_resaltada(mundo: Mundo) -> None:
    pagina = texto(como("u-tec-ad").get("/dashboard"))
    assert 'class="barra resaltada"' in pagina
    assert '<tr class="resaltada"><td>AD</td>' in pagina


def test_4_2_los_graficos_son_svg_del_servidor_y_escapan_las_etiquetas() -> None:
    svg = str(barras("Título <b>", [("<script>alert(1)</script>", 3), ("AD", 7)], resaltar="AD"))
    assert svg.startswith("<svg")
    assert "<script>" not in svg
    assert "&lt;script&gt;" in svg
    assert 'class="barra resaltada"' in svg
    assert "<title>Título &lt;b&gt;</title>" in svg
    assert "Sin datos" in str(barras("Vacío", []))


def test_RF_32_la_busqueda_filtra_y_pagina(mundo: Mundo) -> None:
    c = como("u-tec-lic")
    pagina = texto(c.get("/cuentas", {"departamento": "finanzas"}))
    assert "María José Gómez Ramírez" in pagina
    assert "Otto Nieto" not in pagina
    primera = texto(c.get("/cuentas", {"nombre": "", "pagina": "1"}))
    assert "página 1 de" in primera


@pytest.mark.parametrize("malo", [{"sistema": "LDAP"}, {"pagina": "0"}, {"pagina": "x"}])
def test_parametros_manipulados_dan_404(mundo: Mundo, malo: dict[str, str]) -> None:
    assert como("u-tec-ad").get("/cuentas", malo).status_code == 404


def test_RF_34_el_csv_trae_todas_las_filas_y_queda_auditado(mundo: Mundo) -> None:
    r = como("u-tec-inv").get("/cuentas.csv", {"departamento": "finanzas"})
    assert r["Content-Type"].startswith("text/csv")
    assert "attachment" in r["Content-Disposition"]
    filas = list(csv.reader(io.StringIO(texto(r).lstrip("﻿"))))
    assert filas[0][0] == "Colaborador"
    assert {f[3] for f in filas[1:]} == {"Finanzas"}
    assert SENTINELA not in texto(r)
    with RepositoriosDjango(mundo.reloj).unidad_de_trabajo() as u:
        assert [x.accion for x in u.auditoria.registros()][-1] == "cuentas.exportadas"


@pytest.mark.parametrize("peligroso", ["=HYPERLINK(1)", "+1", "-2", "@SUM(A1)", "\tx"])
def test_el_csv_neutraliza_formulas(peligroso: str) -> None:
    assert _celda(peligroso) == "'" + peligroso
    assert _celda("Ana") == "Ana"
    assert _celda(None) == ""


def test_CA_16_la_ficha_muestra_lo_tecnico_sin_restringidos_y_se_audita(mundo: Mundo) -> None:
    pagina = texto(como("u-tec-ad").get("/colaboradores/col-1"))
    assert "María José Gómez Ramírez" in pagina
    for seccion in ("Cuentas", "Equipos", "Licencias", "Solicitudes", "Tickets"):
        assert f"<h2>{seccion}</h2>" in pagina
    assert SENTINELA not in pagina
    with RepositoriosDjango(mundo.reloj).unidad_de_trabajo() as u:
        ultimo = u.auditoria.registros()[-1]
    assert (ultimo.accion, ultimo.objeto, ultimo.actor) == ("ficha.consultada", "col-1", "u-tec-ad")


def test_una_ficha_inexistente_es_404(mundo: Mundo) -> None:
    assert como("u-tec-ad").get("/colaboradores/no-existe").status_code == 404
