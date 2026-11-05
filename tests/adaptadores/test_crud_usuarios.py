"""ADR-035: CRUD de usuarios del Administrador. El puerto `AdministradorDeCuentas` tiene una suite de
contrato (doble y cliente real contra el servicio real), y `service_role` nunca llega a `web`."""

import json
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from django.test import Client

from jml.adaptadores.entrada.web import composicion
from jml.adaptadores.entrada.web.servicio_cuentas import MAXIMO_CUERPO, crear_servidor
from jml.adaptadores.salida.identidad.administracion import AdministradorSupabase
from jml.adaptadores.salida.identidad.cuentas import ClienteDeCuentas
from jml.adaptadores.salida.persistencia.repositorios import RepositoriosDjango
from jml.aplicacion.casos.administracion import (
    CambiarColaborador,
    ConsultarUsuarios,
    CrearUsuario,
    DesactivarUsuario,
    EliminarUsuario,
    ReactivarUsuario,
    VincularUsuario,
)
from jml.aplicacion.puertos import AdministradorDeCuentas, CuentaRechazada, IdentidadNoDisponible
from jml.dominio.errores import (
    DatoInvalido,
    NoAutorizado,
    NoEncontrado,
    OperacionNoPermitida,
    RolesIncompatibles,
)
from jml.dominio.tipos import Rol
from tests.dobles.cuentas import CuentasEnMemoria
from tests.dobles.gotrue import CLAVE_SERVICIO, GoTrueSimulado
from tests.fabricas import AHORA
from tests.mundo import Mundo

RAIZ = Path(__file__).resolve().parents[2]
COMPOSE = yaml.safe_load((RAIZ / "infra/compose.yaml").read_text(encoding="utf-8"))
SERVICIOS = COMPOSE["services"]
TOKEN = "token-de-prueba"
ID = "11111111-2222-3333-4444-555555555555"
RRHH = frozenset({Rol.RRHH})


# --- suite de contrato del puerto ---------------------------------------------------------------


@pytest.fixture
def servicio() -> Iterator[tuple[str, GoTrueSimulado]]:
    g = GoTrueSimulado()
    admin = AdministradorSupabase("https://x.supabase.co", CLAVE_SERVICIO, g.cliente())
    s = crear_servidor("127.0.0.1", 0, admin, TOKEN)
    hilo = threading.Thread(target=s.serve_forever, daemon=True)
    hilo.start()
    yield f"http://127.0.0.1:{s.server_address[1]}", g
    s.shutdown()
    s.server_close()


@pytest.fixture(params=["memoria", "real"])
def puerto(request: pytest.FixtureRequest) -> AdministradorDeCuentas:
    if request.param == "memoria":
        return CuentasEnMemoria()
    url, _ = request.getfixturevalue("servicio")
    return ClienteDeCuentas(url, TOKEN)


def test_contrato_crea_lista_y_rechaza_el_correo_repetido(puerto: AdministradorDeCuentas) -> None:
    c = puerto.crear("Ana@Andina.example")
    assert c.id
    assert len(c.contrasena_inicial) >= 12
    assert puerto.correos()[c.id] == "ana@andina.example"
    with pytest.raises(CuentaRechazada) as e:
        puerto.crear("ana@andina.example")
    assert e.value.codigo == "email_exists"


def test_contrato_desactiva_reactiva_y_elimina(puerto: AdministradorDeCuentas) -> None:
    uid = puerto.crear("b@andina.example").id
    puerto.desactivar(uid)
    puerto.reactivar(uid)
    puerto.eliminar(uid)
    assert uid not in puerto.correos()
    with pytest.raises(CuentaRechazada):
        puerto.reactivar(uid)


# --- el servicio ------------------------------------------------------------------------------


def _pedir(
    url: str, metodo: str, ruta: str, token: str | None = TOKEN, **kw: Any
) -> httpx.Response:
    cab = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.request(metodo, url + ruta, headers=cab, trust_env=False, **kw)


def test_el_servicio_exige_el_token_salvo_en_salud(servicio: tuple[str, GoTrueSimulado]) -> None:
    url, g = servicio
    assert _pedir(url, "GET", "/salud", token=None).status_code == 200
    assert _pedir(url, "GET", "/cuentas", token=None).status_code == 401
    assert _pedir(url, "GET", "/cuentas", token="otro").status_code == 401
    assert _pedir(url, "POST", "/cuentas", token=None, json={"correo": "x@y.z"}).status_code == 401
    assert g.usuarios == {}


def test_el_servicio_rechaza_lo_que_no_conoce(servicio: tuple[str, GoTrueSimulado]) -> None:
    url, _ = servicio
    assert _pedir(url, "POST", "/cuentas", json={"correo": "sin-arroba"}).status_code == 400
    assert _pedir(url, "POST", "/cuentas", content=b"no es json").status_code == 400
    grande = b'{"correo":"' + b"a" * MAXIMO_CUERPO + b'"}'
    assert _pedir(url, "POST", "/cuentas", content=grande).status_code == 400
    assert _pedir(url, "POST", "/cuentas/no-es-un-id/eliminar").status_code == 404
    assert _pedir(url, "POST", f"/cuentas/{ID}/otra-cosa").status_code == 404
    assert _pedir(url, "GET", f"/cuentas/{ID}/eliminar").status_code == 404


def test_sin_la_clave_el_servicio_responde_503_y_sigue_vivo() -> None:
    s = crear_servidor("127.0.0.1", 0, None, TOKEN)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{s.server_address[1]}"
    try:
        assert _pedir(url, "GET", "/salud", token=None).status_code == 200
        with pytest.raises(IdentidadNoDisponible):
            ClienteDeCuentas(url, TOKEN).crear("a@b.example")
    finally:
        s.shutdown()
        s.server_close()


def test_sin_token_el_cliente_no_llama_a_nadie() -> None:
    llamadas = []

    def manejar(r: httpx.Request) -> httpx.Response:
        llamadas.append(r)
        return httpx.Response(200, json={})

    cliente = ClienteDeCuentas("http://x", "", httpx.Client(transport=httpx.MockTransport(manejar)))
    with pytest.raises(IdentidadNoDisponible):
        cliente.correos()
    assert llamadas == []


def test_una_respuesta_ilegible_o_una_red_caida_no_se_confunden_con_un_exito() -> None:
    def ilegible(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>")

    def caida(r: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin red", request=r)

    for manejar in (ilegible, caida):
        c = ClienteDeCuentas(
            "http://x", TOKEN, httpx.Client(transport=httpx.MockTransport(manejar))
        )
        with pytest.raises(IdentidadNoDisponible):
            c.desactivar(ID)


# --- casos de uso --------------------------------------------------------------------------------


@pytest.fixture
def m() -> Mundo:
    return Mundo.nuevo()


@pytest.fixture
def cuentas() -> CuentasEnMemoria:
    return CuentasEnMemoria()


def _eventos(m: Mundo, tipo: str) -> list[Any]:
    with m.puerto.unidad_de_trabajo() as u:
        return [r for r in u.auditoria.registros() if r.accion == tipo]


def _usuario(m: Mundo, uid: str) -> Any:
    with m.puerto.unidad_de_trabajo() as u:
        return next(x for x in u.usuarios.todos() if x.id == uid)


def test_crear_guarda_roles_y_audita_sin_la_contrasena(m: Mundo, cuentas: CuentasEnMemoria) -> None:
    CambiarColaborador(m.puerto).ejecutar("u-admin", "u-col", None)  # deja libre a col-1
    c = CrearUsuario(m.puerto, cuentas).ejecutar("u-admin", "n@andina.example", RRHH, "col-1")
    u = _usuario(m, c.id)
    assert (u.roles, u.colaborador_id, u.activo) == (RRHH, "col-1", True)
    evento = _eventos(m, "usuario.creado")[-1]
    assert c.contrasena_inicial not in json.dumps(dict(evento.datos))
    assert "n@andina.example" not in json.dumps(dict(evento.datos))


@pytest.mark.parametrize("usuario", ["u-rrhh", "u-col", "u-tec-ad", "u-aud", "fantasma"])
def test_solo_el_administrador_opera_cuentas(
    m: Mundo, cuentas: CuentasEnMemoria, usuario: str
) -> None:
    with pytest.raises(NoAutorizado):
        CrearUsuario(m.puerto, cuentas).ejecutar(usuario, "x@y.example", RRHH, None)
    with pytest.raises(NoAutorizado):
        VincularUsuario(m.puerto).ejecutar(usuario, ID, RRHH, None)
    with pytest.raises(NoAutorizado):
        CambiarColaborador(m.puerto).ejecutar(usuario, "u-col", None)
    for caso in (DesactivarUsuario, ReactivarUsuario):
        with pytest.raises(NoAutorizado):
            caso(m.puerto, cuentas).ejecutar(usuario, "u-col")
    with pytest.raises(NoAutorizado):
        EliminarUsuario(m.puerto, cuentas).ejecutar(usuario, "u-col")
    assert cuentas.correo_de == {}


def test_crear_valida_antes_de_tocar_supabase(m: Mundo, cuentas: CuentasEnMemoria) -> None:
    caso = CrearUsuario(m.puerto, cuentas)
    with pytest.raises(RolesIncompatibles):
        caso.ejecutar("u-admin", "a@b.example", frozenset({Rol.RRHH, Rol.ADMINISTRADOR}), None)
    with pytest.raises(DatoInvalido):
        caso.ejecutar("u-admin", "a@b.example", frozenset(), None)
    with pytest.raises(DatoInvalido):
        caso.ejecutar("u-admin", "a@b.example", RRHH, "no-existe")
    assert cuentas.correo_de == {}


def test_crear_no_deja_una_cuenta_huerfana_si_la_base_falla(
    m: Mundo, cuentas: CuentasEnMemoria, monkeypatch: pytest.MonkeyPatch
) -> None:
    caso = CrearUsuario(m.puerto, cuentas)
    original = m.puerto.unidad_de_trabajo
    llamadas = {"n": 0}

    def fallar() -> Any:
        llamadas["n"] += 1
        if llamadas["n"] == 2:  # la primera valida; la segunda guarda
            raise RuntimeError("base caida")
        return original()

    monkeypatch.setattr(m.puerto, "unidad_de_trabajo", fallar)
    with pytest.raises(RuntimeError):
        caso.ejecutar("u-admin", "h@andina.example", RRHH, None)
    assert cuentas.correo_de == {}


def test_un_colaborador_tiene_una_sola_cuenta_activa(m: Mundo, cuentas: CuentasEnMemoria) -> None:
    with pytest.raises(OperacionNoPermitida):
        CrearUsuario(m.puerto, cuentas).ejecutar("u-admin", "d@b.example", RRHH, "col-1")  # u-col
    assert cuentas.correo_de == {}


def test_vincular_no_usa_supabase_y_no_pisa_una_existente(m: Mundo) -> None:
    VincularUsuario(m.puerto).ejecutar("u-admin", ID, RRHH, None)
    assert _usuario(m, ID).roles == RRHH
    assert _eventos(m, "usuario.vinculado")
    with pytest.raises(OperacionNoPermitida):
        VincularUsuario(m.puerto).ejecutar("u-admin", ID, RRHH, None)


def test_cambiar_colaborador_audita_y_nadie_se_cambia_a_si_mismo(m: Mundo) -> None:
    caso = CambiarColaborador(m.puerto)
    caso.ejecutar("u-admin", "u-col", None)
    assert _usuario(m, "u-col").colaborador_id is None
    assert _eventos(m, "usuario.colaborador_cambiado")
    with pytest.raises(OperacionNoPermitida):
        caso.ejecutar("u-admin", "u-admin", None)
    with pytest.raises(NoEncontrado):
        caso.ejecutar("u-admin", "nadie", None)
    with pytest.raises(DatoInvalido):
        caso.ejecutar("u-admin", "u-col", "no-existe")


def test_desactivar_y_reactivar(m: Mundo, cuentas: CuentasEnMemoria) -> None:
    uid = CrearUsuario(m.puerto, cuentas).ejecutar("u-admin", "e@b.example", RRHH, None).id
    DesactivarUsuario(m.puerto, cuentas).ejecutar("u-admin", uid)
    assert uid in cuentas.baneadas
    assert _usuario(m, uid).activo is False
    ReactivarUsuario(m.puerto, cuentas).ejecutar("u-admin", uid)
    assert uid not in cuentas.baneadas
    assert _usuario(m, uid).activo is True
    assert _eventos(m, "usuario.desactivado")
    assert _eventos(m, "usuario.reactivado")


def test_si_supabase_falla_el_acceso_local_no_cambia(m: Mundo, cuentas: CuentasEnMemoria) -> None:
    uid = CrearUsuario(m.puerto, cuentas).ejecutar("u-admin", "f@b.example", RRHH, None).id
    cuentas.caido = True
    with pytest.raises(IdentidadNoDisponible):
        DesactivarUsuario(m.puerto, cuentas).ejecutar("u-admin", uid)
    assert _usuario(m, uid).activo is True


def test_una_cuenta_que_ya_no_existe_en_supabase_se_puede_desactivar(
    m: Mundo, cuentas: CuentasEnMemoria
) -> None:
    VincularUsuario(m.puerto).ejecutar("u-admin", ID, RRHH, None)
    DesactivarUsuario(m.puerto, cuentas).ejecutar("u-admin", ID)
    assert _usuario(m, ID).activo is False
    with pytest.raises(CuentaRechazada):
        ReactivarUsuario(m.puerto, cuentas).ejecutar("u-admin", ID)
    assert _usuario(m, ID).activo is False


def test_nadie_se_desactiva_ni_se_elimina_a_si_mismo(m: Mundo, cuentas: CuentasEnMemoria) -> None:
    with pytest.raises(OperacionNoPermitida):
        DesactivarUsuario(m.puerto, cuentas).ejecutar("u-admin", "u-admin")
    with pytest.raises(OperacionNoPermitida):
        EliminarUsuario(m.puerto, cuentas).ejecutar("u-admin", "u-admin")


def test_eliminar_exige_desactivar_antes_y_conserva_el_rastro(
    m: Mundo, cuentas: CuentasEnMemoria
) -> None:
    uid = CrearUsuario(m.puerto, cuentas).ejecutar("u-admin", "g@b.example", RRHH, None).id
    with pytest.raises(OperacionNoPermitida):
        EliminarUsuario(m.puerto, cuentas).ejecutar("u-admin", uid)
    DesactivarUsuario(m.puerto, cuentas).ejecutar("u-admin", uid)
    EliminarUsuario(m.puerto, cuentas).ejecutar("u-admin", uid)
    assert uid not in cuentas.correo_de
    assert _usuario(m, uid).activo is False  # la auditoria y las decisiones siguen apuntando aqui
    assert _eventos(m, "usuario.eliminado")
    EliminarUsuario(m.puerto, cuentas).ejecutar("u-admin", uid)  # repetir no falla


def test_la_lista_trae_correos_y_sobrevive_al_servicio_caido(
    m: Mundo, cuentas: CuentasEnMemoria
) -> None:
    uid = CrearUsuario(m.puerto, cuentas).ejecutar("u-admin", "h@b.example", RRHH, None).id
    filas = ConsultarUsuarios(m.puerto, cuentas).ejecutar("u-admin")
    assert next(f for f in filas if f.usuario_id == uid).correo == "h@b.example"
    cuentas.caido = True
    assert all(f.correo is None for f in ConsultarUsuarios(m.puerto, cuentas).ejecutar("u-admin"))


# --- web ------------------------------------------------------------------------------------------


@pytest.fixture
def web(monkeypatch: pytest.MonkeyPatch) -> tuple[Mundo, CuentasEnMemoria]:
    mundo = Mundo.nuevo(repositorios=RepositoriosDjango)
    doble = CuentasEnMemoria()
    monkeypatch.setattr(composicion, "reloj", lambda: mundo.reloj)
    monkeypatch.setattr(composicion, "administrador_de_cuentas", lambda: doble)
    return mundo, doble


def como(usuario: str) -> Client:
    c = Client()
    s = c.session
    s["usuario_id"], s["inicio"] = usuario, AHORA.timestamp()
    s.save()
    return c


def texto(r: Any) -> str:
    return bytes(r.content).decode()


@pytest.mark.django_db
def test_web_crear_muestra_la_contrasena_una_vez_y_sin_cache(
    web: tuple[Mundo, CuentasEnMemoria],
) -> None:
    _, doble = web
    c = como("u-admin")
    r = c.post(
        "/administracion/usuarios/crear",
        {"correo": "nueva@andina.example", "roles": ["rrhh"], "colaborador": ""},
    )
    assert r.status_code == 200
    assert r["Cache-Control"] == "no-store"
    uid = next(iter(doble.correo_de))
    assert f"contrasena-inicial-{uid[:8]}" in texto(r)
    lista = texto(c.get("/administracion/usuarios"))
    assert "nueva@andina.example" in lista
    assert f"contrasena-inicial-{uid[:8]}" not in lista


@pytest.mark.django_db
def test_web_crear_traduce_los_rechazos(web: tuple[Mundo, CuentasEnMemoria]) -> None:
    _, doble = web
    doble.crear("rep@andina.example")
    c = como("u-admin")
    datos = {"correo": "rep@andina.example", "roles": ["rrhh"], "colaborador": ""}
    assert "Ya existe una cuenta" in texto(c.post("/administracion/usuarios/crear", datos))
    doble.caido = True
    datos["correo"] = "otra@andina.example"
    assert "no está disponible" in texto(c.post("/administracion/usuarios/crear", datos))
    assert "Correo" in texto(c.post("/administracion/usuarios/crear", {"correo": "malo"}))


@pytest.mark.django_db
def test_web_vincular_exige_un_uuid(web: tuple[Mundo, CuentasEnMemoria]) -> None:
    c = como("u-admin")
    r = c.post("/administracion/usuarios/vincular", {"usuario": "x", "roles": ["rrhh"]})
    assert r.status_code == 200
    assert "UUID" in texto(r)
    r = c.post("/administracion/usuarios/vincular", {"usuario": ID, "roles": ["rrhh"]})
    assert r.status_code == 302
    assert ID in texto(c.get("/administracion/usuarios"))


@pytest.mark.django_db
def test_web_desactivar_reactivar_y_eliminar(web: tuple[Mundo, CuentasEnMemoria]) -> None:
    mundo, doble = web
    uid = CrearUsuario(mundo.puerto, doble).ejecutar("u-admin", "z@b.example", RRHH, None).id
    c = como("u-admin")
    base = f"/administracion/usuarios/{uid}"
    assert c.post(f"{base}/desactivar").status_code == 302
    assert uid in doble.baneadas
    assert c.post(f"{base}/reactivar").status_code == 302
    assert uid not in doble.baneadas
    c.post(f"{base}/desactivar")
    c.post(f"{base}/eliminar")  # sin confirmar
    assert uid in doble.correo_de
    c.post(f"{base}/eliminar", {"confirmar": "si"})
    assert uid not in doble.correo_de


@pytest.mark.django_db
def test_web_cambiar_colaborador(web: tuple[Mundo, CuentasEnMemoria]) -> None:
    mundo, _ = web
    c = como("u-admin")
    c.post("/administracion/usuarios/u-otro/colaborador", {"colaborador": ""})  # deja libre a col-9
    r = c.post("/administracion/usuarios/u-aud/colaborador", {"colaborador": "col-9"})
    assert r.status_code == 302
    assert _usuario(mundo, "u-aud").colaborador_id == "col-9"


@pytest.mark.django_db
def test_web_la_lista_sigue_si_el_servicio_esta_caido(web: tuple[Mundo, CuentasEnMemoria]) -> None:
    _, doble = web
    doble.caido = True
    r = como("u-admin").get("/administracion/usuarios")
    assert r.status_code == 200
    assert "no está disponible" in texto(r)


# --- infraestructura: invariante 8 ------------------------------------------------------------------


def test_invariante_8_web_tiene_el_token_y_nunca_la_clave() -> None:
    for nombre, s in SERVICIOS.items():
        secretos = s.get("secrets", [])
        if nombre != "admin-usuarios":
            assert "supabase_service_role" not in secretos, nombre
        assert ("admin_servicio_token" in secretos) == (nombre in {"web", "admin-usuarios"}), nombre


def test_ADR_035_el_servicio_solo_es_alcanzable_desde_web_por_una_red_interna() -> None:
    red = COMPOSE["networks"]["admin_net"]
    assert red["internal"] is True
    en_red = {n for n, s in SERVICIOS.items() if "admin_net" in s.get("networks", [])}
    assert en_red == {"web", "admin-usuarios"}
    servicio = SERVICIOS["admin-usuarios"]
    assert "ports" not in servicio
    assert "profiles" not in servicio
    assert servicio["command"] == ["servir"]
    assert servicio["networks"]["admin_net"]["aliases"] == ["servicio-cuentas"]
    assert servicio["read_only"] is True
    assert "healthcheck" in servicio


def test_ADR_035_el_entorno_crea_el_token() -> None:
    guion = (RAIZ / "infra/scripts/preparar-entorno.sh").read_text(encoding="utf-8")
    assert "asegurar admin_servicio_token" in guion
    assert COMPOSE["secrets"]["admin_servicio_token"]["file"] == "../secrets/admin_servicio_token"


def test_preparar_entorno_no_vacia_el_env_si_falta_un_valor() -> None:
    """Corrido sin `secretos.sh descifrar`, truncaba infra/.env y luego fallaba (04/11/2026)."""
    guion = (RAIZ / "infra/scripts/preparar-entorno.sh").read_text(encoding="utf-8")
    assert '> "$ENV_SALIDA.tmp"' in guion
    assert '} > "$ENV_SALIDA"' not in guion
    assert guion.index("_del_env JML_SUPABASE_URL") < guion.index('> "$ENV_SALIDA.tmp"')
