"""Item 2.7: las vistas de negocio, con el cliente de Django contra el ORM (RF-07, RF-11, RF-12, RF-15).

Las vistas solo validan, verifican el rol y llaman a un caso; aqui se prueba esa frontera, no las
reglas del dominio (ya cubiertas). La base de pruebas es la de pytest-django.
"""

from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from jml.adaptadores.entrada.web import composicion
from jml.adaptadores.salida.persistencia.repositorios import RepositoriosDjango
from jml.dominio.valores import BOGOTA
from tests.fabricas import AHORA, HOY, SENTINELA
from tests.mundo import PDF_VALIDO, Mundo

pytestmark = pytest.mark.django_db


@pytest.fixture
def mundo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Mundo:
    m = Mundo.nuevo(repositorios=RepositoriosDjango)
    monkeypatch.setattr(composicion, "reloj", lambda: m.reloj)
    monkeypatch.setattr(composicion, "directorio_de_soportes", lambda: tmp_path)
    return m


def como(usuario: str | None, **opciones: bool) -> Client:
    cliente = Client(**opciones)  # type: ignore[arg-type]  # enforce_csrf_checks
    if usuario is not None:
        sesion = cliente.session
        sesion["usuario_id"] = usuario
        sesion["inicio"] = AHORA.timestamp()  # RF-04: ingreso reciente
        sesion.save()
    return cliente


def fecha(dias: int) -> str:
    return (HOY + timedelta(days=dias)).isoformat()


def texto(r: Any) -> str:  # la respuesta del cliente de pruebas no tiene un tipo publico comun
    return bytes(r.content).decode()


def id_de_la_unica(cliente: Client) -> str:
    """El id de la primera solicitud de la lista (se lee de la pagina, como lo haria la persona)."""
    pagina = texto(cliente.get("/solicitudes"))
    inicio = pagina.index("SOL-")
    return pagina[inicio : inicio + 15]


# --- acceso -----------------------------------------------------------------------------------


@pytest.mark.parametrize("ruta", ["/solicitudes", "/solicitudes/nueva", "/bandeja", "/"])
def test_sin_sesion_se_redirige_al_ingreso(mundo: Mundo, ruta: str) -> None:
    r = Client().get(ruta, follow=False)
    assert r.status_code == 302
    assert r["Location"] in ("/ingreso", "/solicitudes")  # "/" pasa primero por el inicio


def test_una_sesion_de_un_usuario_inexistente_se_cierra(mundo: Mundo) -> None:
    cliente = como("fantasma")
    r = cliente.get("/solicitudes")
    assert (r.status_code, r["Location"]) == (302, "/ingreso")
    assert "usuario_id" not in cliente.session


def test_las_vistas_de_negocio_exigen_el_metodo_correcto(mundo: Mundo) -> None:
    assert como("u-col").post("/solicitudes").status_code == 405
    assert como("u-rrhh").get(f"/solicitudes/SOL-{HOY.year}-000001/aprobar").status_code == 405


def test_el_post_sin_token_csrf_se_rechaza(mundo: Mundo) -> None:
    cliente = como("u-rrhh", enforce_csrf_checks=True)
    r = cliente.post(f"/solicitudes/SOL-{HOY.year}-000001/aprobar")
    assert r.status_code == 403


# --- solicitante -------------------------------------------------------------------------------


def test_el_colaborador_registra_sus_vacaciones_y_las_ve_pendientes(mundo: Mundo) -> None:
    c = como("u-col")
    r = c.post("/solicitudes/nueva/VAC", {"fecha_efectiva": fecha(10), "fecha_regreso": fecha(20)})
    assert (r.status_code, r["Location"]) == (302, "/solicitudes")
    pagina = texto(c.get("/solicitudes"))
    assert "Pendiente de aprobación" in pagina
    assert "María José Gómez Ramírez" in pagina
    assert "registrada: queda pendiente" in pagina  # el mensaje de exito se muestra una vez
    assert "registrada: queda pendiente" not in texto(c.get("/solicitudes"))


def test_una_solicitud_duplicada_se_explica_sin_detalles_tecnicos(mundo: Mundo) -> None:
    c = como("u-col")
    datos = {"fecha_efectiva": fecha(10), "fecha_regreso": fecha(20)}
    c.post("/solicitudes/nueva/VAC", datos)
    r = c.post("/solicitudes/nueva/VAC", datos)
    assert r.status_code == 200
    assert "Ya existe una solicitud abierta" in texto(r)
    assert "Traceback" not in texto(r)


def test_un_dato_que_viola_una_regla_del_dominio_vuelve_al_formulario(mundo: Mundo) -> None:
    r = como("u-col").post(
        "/solicitudes/nueva/VAC", {"fecha_efectiva": fecha(10), "fecha_regreso": fecha(5)}
    )
    assert r.status_code == 200
    assert "fecha_regreso" in texto(r)


def test_el_solicitante_cancela_la_suya_mientras_este_pendiente(mundo: Mundo) -> None:
    c = como("u-col")
    c.post("/solicitudes/nueva/VAC", {"fecha_efectiva": fecha(10), "fecha_regreso": fecha(20)})
    sid = id_de_la_unica(c)
    r = c.post(f"/solicitudes/{sid}/cancelar")
    assert (r.status_code, r["Location"]) == (302, "/solicitudes")
    assert "Cancelada" in texto(c.get("/solicitudes"))


def test_el_colaborador_solo_ofrece_vacaciones_y_renuncia(mundo: Mundo) -> None:
    pagina = texto(como("u-col").get("/solicitudes/nueva"))
    assert "/solicitudes/nueva/VAC" in pagina
    assert "/solicitudes/nueva/RET" in pagina
    assert "/solicitudes/nueva/ING" not in pagina
    assert "/solicitudes/nueva/CDP" not in pagina  # no tiene subordinados


def test_la_renuncia_no_pregunta_el_tipo_de_retiro_y_guarda_el_motivo_aparte(mundo: Mundo) -> None:
    c = como("u-col")
    assert "subtipo_elegido" not in texto(c.get("/solicitudes/nueva/RET"))
    r = c.post("/solicitudes/nueva/RET", {"fecha_efectiva": fecha(15), "motivo": SENTINELA})
    assert r.status_code == 302
    for ruta in ("/solicitudes", "/solicitudes/nueva"):
        assert SENTINELA not in texto(c.get(ruta))  # RD-05: el motivo no vuelve a ninguna lista


def test_el_jefe_pide_un_cambio_de_departamento_de_un_subordinado(mundo: Mundo) -> None:
    c = como("u-jefe")
    formulario = texto(c.get("/solicitudes/nueva/CDP"))
    assert "María José Gómez Ramírez" in formulario  # su subordinado directo
    r = c.post(
        "/solicitudes/nueva/CDP",
        {
            "fecha_efectiva": fecha(5),
            "colaborador": "col-1",
            "departamento_nuevo": "TI",
            "cargo_nuevo": "Desarrollador",
        },
    )
    assert r.status_code == 302
    assert "Cambio de departamento" in texto(c.get("/solicitudes"))


def test_el_jefe_no_puede_elegir_a_alguien_que_no_es_su_subordinado(mundo: Mundo) -> None:
    r = como("u-jefe").post(
        "/solicitudes/nueva/CSU",
        {"fecha_efectiva": fecha(5), "colaborador": "col-9", "sede_nueva": "Cali"},
    )
    assert r.status_code == 200  # ChoiceField: no es una opcion valida, vuelve al formulario
    assert "Cambio de sucursal" in texto(r)


@pytest.mark.parametrize(
    ("usuario", "ruta", "estado"),
    [
        ("u-col", "/solicitudes/nueva/ING", 403),
        ("u-col", "/solicitudes/nueva/EMG", 403),
        ("u-col", "/solicitudes/nueva/CDP", 403),
        ("u-col", "/bandeja", 403),
        ("u-jefe", "/bandeja", 403),
        ("u-tec-ad", "/bandeja", 403),
        ("u-tec-ad", "/solicitudes/nueva/VAC", 403),
        ("u-col", "/solicitudes/nueva/XXX", 404),
    ],
)
def test_el_rol_limita_lo_que_cada_persona_alcanza(
    mundo: Mundo, usuario: str, ruta: str, estado: int
) -> None:
    assert como(usuario).get(ruta).status_code == estado


# --- RRHH --------------------------------------------------------------------------------------


def registrar_vacaciones_de_col1(mundo: Mundo) -> str:
    c = como("u-col")
    c.post("/solicitudes/nueva/VAC", {"fecha_efectiva": fecha(10), "fecha_regreso": fecha(20)})
    return id_de_la_unica(c)


def test_rrhh_ve_la_bandeja_y_aprueba(mundo: Mundo) -> None:
    sid = registrar_vacaciones_de_col1(mundo)
    rrhh = como("u-rrhh")
    pagina = texto(rrhh.get("/bandeja"))
    assert sid in pagina
    assert "María José Gómez Ramírez" in pagina
    r = rrhh.post(f"/solicitudes/{sid}/aprobar")
    assert (r.status_code, r["Location"]) == (302, "/bandeja")
    bandeja = texto(rrhh.get("/bandeja"))
    assert "aprobada" in bandeja  # el mensaje de exito
    assert "No hay solicitudes pendientes" in bandeja
    # Aprobada, no "En ejecución": los tickets los crea el worker al procesar la bandeja.
    assert "Aprobada" in texto(como("u-col").get("/solicitudes"))


def test_rechazar_exige_justificacion_y_la_vista_lo_explica(mundo: Mundo) -> None:
    sid = registrar_vacaciones_de_col1(mundo)
    rrhh = como("u-rrhh")
    r = rrhh.post(f"/solicitudes/{sid}/rechazar", {"justificacion": ""}, follow=True)
    assert "Escriba la justificación" in texto(r)
    r = rrhh.post(f"/solicitudes/{sid}/rechazar", {"justificacion": "Sin cupo"}, follow=True)
    assert "rechazada" in texto(r)


def test_quien_no_es_rrhh_no_aprueba_aunque_conozca_el_id(mundo: Mundo) -> None:
    sid = registrar_vacaciones_de_col1(mundo)
    r = como("u-col").post(f"/solicitudes/{sid}/aprobar", follow=True)
    assert "No tiene permiso" in texto(r)
    assert "Pendiente de aprobación" in texto(como("u-col").get("/solicitudes"))


def test_un_id_de_solicitud_inexistente_no_revela_nada(mundo: Mundo) -> None:
    r = como("u-rrhh").post(f"/solicitudes/SOL-{HOY.year}-999999/aprobar", follow=True)
    assert "No se encontró" in texto(r)
    assert como("u-rrhh").post("/solicitudes/cualquiera/aprobar").status_code == 404


def test_rrhh_emite_un_retiro_por_documento_sin_exponer_el_motivo(mundo: Mundo) -> None:
    rrhh = como("u-rrhh")
    r = rrhh.post(
        "/solicitudes/nueva/RET",
        {
            "fecha_efectiva": fecha(10),
            "documento_del_colaborador": "10203040",
            "subtipo_elegido": "fin_de_contrato",
            "motivo": SENTINELA,
            "justificacion": "Cierre de contrato",
        },
    )
    assert (r.status_code, r["Location"]) == (302, "/solicitudes")
    pagina = texto(rrhh.get("/solicitudes"))
    assert "emitida" in pagina
    assert SENTINELA not in pagina + texto(rrhh.get("/bandeja"))


def test_un_documento_inexistente_se_marca_en_el_campo(mundo: Mundo) -> None:
    r = como("u-rrhh").post(
        "/solicitudes/nueva/VAC",
        {
            "fecha_efectiva": fecha(10),
            "fecha_regreso": fecha(12),
            "documento_del_colaborador": "99999999",
            "justificacion": "x",
        },
    )
    assert r.status_code == 200
    assert "No hay un colaborador con ese documento" in texto(r)


def test_rrhh_no_emite_sobre_su_propia_persona(mundo: Mundo) -> None:
    r = como("u-rrhh").post(
        "/solicitudes/nueva/VAC",
        {
            "fecha_efectiva": fecha(10),
            "fecha_regreso": fecha(12),
            "documento_del_colaborador": "70000001",
            "justificacion": "x",
        },
    )
    assert "RRHH no puede aprobar ni emitir" in texto(r)


def test_la_emergencia_toma_la_fecha_de_hoy_y_no_la_pregunta(mundo: Mundo) -> None:
    rrhh = como("u-rrhh")
    assert "fecha_efectiva" not in texto(rrhh.get("/solicitudes/nueva/EMG"))
    hora = (AHORA.astimezone(BOGOTA) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
    r = rrhh.post(
        "/solicitudes/nueva/EMG",
        {
            "documento_del_colaborador": "10203040",
            "subtipo_elegido": "fuga_detectada",
            "reportado_por": "Seguridad",
            "hora_del_hecho": hora,
            "descripcion": SENTINELA,
            "justificacion": "Alerta de seguridad",
        },
    )
    assert r.status_code == 302
    assert SENTINELA not in texto(rrhh.get("/solicitudes"))


def ingreso(**cambios: object) -> dict[str, object]:
    base: dict[str, object] = {
        "fecha_efectiva": fecha(14),
        "nombres": "Camila",
        "apellidos": "Torres Vega",
        "documento": "80000001",
        "vinculacion": "empleado",
        "departamento": "Finanzas",
        "cargo": "Analista",
        "sede": "Bogotá",
        "requiere_equipo": "on",
        "tipo_equipo": "Portátil",
        "justificacion": "Contratación aprobada",
        "soporte_pdf": SimpleUploadedFile("acta.pdf", PDF_VALIDO, "application/pdf"),
    }
    return base | cambios


def test_rrhh_emite_un_ingreso_con_su_soporte_en_pdf(mundo: Mundo, tmp_path: Path) -> None:
    r = como("u-rrhh").post("/solicitudes/nueva/ING", ingreso())
    assert (r.status_code, r["Location"]) == (302, "/solicitudes")
    assert len(list(tmp_path.iterdir())) == 1  # una copia con nombre aleatorio, sin extension
    assert "." not in next(tmp_path.iterdir()).name


def test_un_soporte_que_no_es_pdf_se_rechaza_por_su_contenido(mundo: Mundo, tmp_path: Path) -> None:
    falso = SimpleUploadedFile("acta.pdf", b"MZ\x90\x00 ejecutable", "application/pdf")
    r = como("u-rrhh").post("/solicitudes/nueva/ING", ingreso(soporte_pdf=falso))
    assert r.status_code == 200
    assert "soporte de vinculación no es válido" in texto(r)
    assert list(tmp_path.iterdir()) == []


def test_el_ingreso_no_acepta_equipo_sin_tipo(mundo: Mundo) -> None:
    r = como("u-rrhh").post("/solicitudes/nueva/ING", ingreso(tipo_equipo=""))
    assert r.status_code == 200
    assert "tipo_equipo" in texto(r)


def test_el_administrador_no_ve_el_ingreso_ni_su_soporte(mundo: Mundo) -> None:
    """Invariante 12: el soporte solo lo sube RRHH. Un ingreso nunca es excepcion del
    Administrador (la persona aun no existe, luego no es de RRHH: S-08), asi que la interfaz no
    le ofrece el formulario ni el campo del PDF (auditoria del 12/10/2026)."""
    admin = como("u-admin")
    assert "/solicitudes/nueva/ING" not in texto(admin.get("/solicitudes/nueva"))
    assert "/solicitudes/nueva/VAC" in texto(admin.get("/solicitudes/nueva"))
    assert admin.get("/solicitudes/nueva/ING").status_code == 403
    assert "soporte_pdf" not in texto(como("u-admin").get("/solicitudes/nueva/RET"))


def test_el_administrador_emite_por_excepcion_solo_sobre_rrhh(mundo: Mundo) -> None:
    admin = como("u-admin")
    base = {
        "fecha_efectiva": fecha(10),
        "fecha_regreso": fecha(12),
        "justificacion": "Rosa está de viaje y no puede emitirla",
    }
    ajena = admin.post("/solicitudes/nueva/VAC", base | {"documento_del_colaborador": "10203040"})
    assert ajena.status_code == 403  # el sujeto no es de RRHH: no es una excepcion valida
    propia = admin.post("/solicitudes/nueva/VAC", base | {"documento_del_colaborador": "70000001"})
    assert propia.status_code == 302


def test_las_plantillas_escapan_el_contenido(mundo: Mundo) -> None:
    r = como("u-rrhh").post(
        "/solicitudes/nueva/VAC",
        {
            "fecha_efectiva": fecha(10),
            "fecha_regreso": fecha(12),
            "documento_del_colaborador": "<script>alert(1)</script>",
            "justificacion": "x",
        },
    )
    assert "<script>alert(1)</script>" not in texto(r)
