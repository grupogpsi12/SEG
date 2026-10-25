"""F5-03 (T3, T4): IDOR, asignación masiva y CSRF cruzado.

- IDOR: pedir la solicitud de otra persona se responde igual que un id que no existe.
- Asignación masiva: campos de más en el formulario (estado, solicitante, colaborador) se ignoran.
- CSRF: sin token, o con el token de otra sesión, ninguna acción que cambia estado se ejecuta.
"""

import re
from datetime import timedelta
from pathlib import Path

import pytest
from django.contrib.auth.models import User
from django.test import Client

from jml.adaptadores.entrada.web import composicion
from jml.adaptadores.salida.persistencia import models as mod
from jml.adaptadores.salida.persistencia.repositorios import RepositoriosDjango
from jml.dominio.valores import SolicitudId
from tests.fabricas import AHORA, HOY
from tests.mundo import Mundo, vacaciones

pytestmark = [pytest.mark.seguridad, pytest.mark.django_db]


@pytest.fixture
def mundo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Mundo:
    m = Mundo.nuevo(repositorios=RepositoriosDjango)
    monkeypatch.setattr(composicion, "reloj", lambda: m.reloj)
    monkeypatch.setattr(composicion, "directorio_de_soportes", lambda: tmp_path)
    return m


def como(usuario: str, **opciones: bool) -> Client:
    cliente = Client(**opciones)  # type: ignore[arg-type]  # enforce_csrf_checks
    sesion = cliente.session
    sesion["usuario_id"] = usuario
    sesion["inicio"] = AHORA.timestamp()
    sesion.save()
    return cliente


def fecha(dias: int) -> str:
    return (HOY + timedelta(days=dias)).isoformat()


def texto(r: object) -> str:
    return bytes(r.content).decode()  # type: ignore[attr-defined]


def normalizar(pagina: str) -> str:
    """Quita lo que varía por petición (token CSRF, nonce) para comparar respuestas."""
    return re.sub(r'(csrfmiddlewaretoken" value|nonce)="[^"]*"', r'\1=""', pagina)


def test_IDOR_la_solicitud_ajena_se_responde_igual_que_una_inexistente(mundo: Mundo) -> None:
    ajena = mundo.registrar(vacaciones()).solicitud_id.valor  # de u-col
    inexistente = SolicitudId.de(2026, 999999).valor
    for espectador in ("u-jefe", "u-tec-ad", "u-aud", "u-admin"):
        c = como(espectador)
        r1, r2 = c.get(f"/solicitudes/{ajena}"), c.get(f"/solicitudes/{inexistente}")
        assert (r1.status_code, r2.status_code) == (404, 404), espectador
        assert normalizar(texto(r1)) == normalizar(texto(r2)), espectador
        assert ajena not in texto(r1)
        assert inexistente not in texto(r1)


def test_IDOR_decidir_o_cancelar_la_solicitud_de_otro_no_la_cambia(mundo: Mundo) -> None:
    ajena = mundo.registrar(vacaciones()).solicitud_id.valor
    antes = mod.Solicitud.objects.get(pk=ajena).estado
    for usuario in ("u-jefe", "u-tec-ad", "u-aud", "u-admin"):
        for accion in ("aprobar", "rechazar", "cancelar"):
            como(usuario).post(f"/solicitudes/{ajena}/{accion}", {"justificacion": "x"})
    assert mod.Solicitud.objects.get(pk=ajena).estado == antes == "pendiente_aprobacion"


def test_asignacion_masiva_los_campos_de_mas_se_ignoran(mundo: Mundo) -> None:
    c = como("u-col")
    c.post(
        "/solicitudes/nueva/VAC",
        {
            "fecha_efectiva": fecha(10),
            "fecha_regreso": fecha(20),
            "estado": "aprobada",
            "solicitante_id": "u-rrhh",
            "colaborador_id": "col-rrhh",
            "tipo": "RET",
            "id": "SOL-2026-000777",
        },
    )
    (s,) = mod.Solicitud.objects.all()
    assert (s.estado, s.solicitante_id, s.colaborador_id, s.tipo) == (
        "pendiente_aprobacion",
        "u-col",
        "col-1",
        "VAC",
    )
    assert s.pk != "SOL-2026-000777"


def test_asignacion_masiva_los_roles_nuevos_solo_los_cambia_el_administrador(mundo: Mundo) -> None:
    def grupos() -> list[str]:
        return sorted(User.objects.get(username="u-col").groups.values_list("name", flat=True))

    antes = grupos()
    como("u-col").post("/administracion/usuarios/u-col/roles", {"roles": ["administrador"]})
    assert grupos() == antes


@pytest.mark.parametrize(
    "ruta",
    ["/solicitudes/{sid}/aprobar", "/solicitudes/{sid}/rechazar", "/solicitudes/{sid}/cancelar"],
)
def test_CSRF_sin_token_no_se_ejecuta_ninguna_decision(mundo: Mundo, ruta: str) -> None:
    sid = mundo.registrar(vacaciones()).solicitud_id.valor
    r = como("u-rrhh", enforce_csrf_checks=True).post(ruta.format(sid=sid), {"justificacion": "x"})
    assert r.status_code == 403
    assert mod.Solicitud.objects.get(pk=sid).estado == "pendiente_aprobacion"


def test_CSRF_el_token_de_otra_sesion_tampoco_sirve(mundo: Mundo) -> None:
    sid = mundo.registrar(vacaciones()).solicitud_id.valor
    atacante = como("u-col", enforce_csrf_checks=True)
    pagina = texto(atacante.get("/solicitudes/nueva/VAC"))
    token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', pagina)
    assert token, "el formulario debe llevar token"
    victima = como("u-rrhh", enforce_csrf_checks=True)  # su cookie CSRF es otra
    victima.get("/bandeja")
    r = victima.post(
        f"/solicitudes/{sid}/aprobar",
        {"csrfmiddlewaretoken": token.group(1), "justificacion": "x"},
    )
    assert r.status_code == 403
    assert mod.Solicitud.objects.get(pk=sid).estado == "pendiente_aprobacion"


def test_CSRF_con_su_propio_token_la_misma_accion_si_funciona(mundo: Mundo) -> None:
    """Control positivo: el bloqueo anterior no es porque la acción esté rota."""
    sid = mundo.registrar(vacaciones()).solicitud_id.valor
    c = como("u-rrhh", enforce_csrf_checks=True)
    pagina = texto(c.get(f"/solicitudes/{sid}"))
    token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', pagina)
    assert token, "el detalle de RRHH debe tener el formulario de decisión con token"
    r = c.post(
        f"/solicitudes/{sid}/aprobar",
        {"csrfmiddlewaretoken": token.group(1), "justificacion": "ok"},
    )
    assert r.status_code == 302
    assert mod.Solicitud.objects.get(pk=sid).estado != "pendiente_aprobacion"
