"""Item 2.11: el Auditor consulta y verifica la cadena desde la interfaz (RF-36, CA-09)."""

from typing import Any

import pytest
from django.db import connection
from django.test import Client

from jml.adaptadores.entrada.web import composicion
from jml.adaptadores.salida.persistencia.repositorios import RepositoriosDjango
from jml.aplicacion.casos.auditoria import TAMANO_DE_PAGINA, ConsultarAuditoria
from jml.dominio.errores import DatoInvalido
from tests.fabricas import AHORA
from tests.mundo import Mundo, vacaciones

pytestmark = pytest.mark.django_db


@pytest.fixture
def mundo(monkeypatch: pytest.MonkeyPatch) -> Mundo:
    m = Mundo.nuevo(repositorios=RepositoriosDjango)
    m.registrar(vacaciones())  # algunos registros en la cadena
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


@pytest.mark.parametrize("usuario", ["u-rrhh", "u-admin", "u-tec-ad", "u-col"])
def test_solo_el_auditor_entra(mundo: Mundo, usuario: str) -> None:
    assert como(usuario).get("/auditoria").status_code == 403
    assert como(usuario).post("/auditoria").status_code == 403


def test_el_auditor_ve_los_registros_del_mas_reciente_al_mas_antiguo(mundo: Mundo) -> None:
    pagina = texto(como("u-aud").get("/auditoria"))
    assert "solicitud.registrada" in pagina or "solicitud." in pagina
    assert "Auditoría" in pagina


def test_CA_09_una_cadena_integra_se_informa_y_la_verificacion_queda_auditada(mundo: Mundo) -> None:
    r = como("u-aud").post("/auditoria")
    assert "La cadena es íntegra" in texto(r)
    with RepositoriosDjango(mundo.reloj).unidad_de_trabajo() as u:
        ultimo = u.auditoria.registros()[-1]
    assert (ultimo.accion, dict(ultimo.datos)["valida"]) == ("auditoria.verificada", True)


def test_CA_09_alterar_un_registro_en_la_base_rompe_la_cadena_y_se_ve_el_primero(
    mundo: Mundo,
) -> None:
    with connection.cursor() as c:  # lo que haria alguien con acceso directo a la base
        c.execute("UPDATE auditoria SET actor = %s WHERE secuencia = %s", ["intruso", 1])
        assert c.rowcount == 1
    pagina = texto(como("u-aud").post("/auditoria"))
    assert "La cadena está ROTA" in pagina
    assert "posición 1" in pagina


def test_la_paginacion_cubre_todo_sin_repetir(mundo: Mundo) -> None:
    caso = ConsultarAuditoria(mundo.puerto)
    primera = caso.ejecutar("u-aud", 1)
    vistos = [r.secuencia for r in primera.registros]
    assert vistos == sorted(vistos, reverse=True)
    assert len(vistos) == min(primera.total, TAMANO_DE_PAGINA)
    assert caso.ejecutar("u-aud", 99).registros == ()
    with pytest.raises(DatoInvalido):
        caso.ejecutar("u-aud", 0)


@pytest.mark.parametrize("pagina", ["0", "x", "-1"])
def test_una_pagina_invalida_es_404(mundo: Mundo, pagina: str) -> None:
    assert como("u-aud").get("/auditoria", {"pagina": pagina}).status_code == 404
