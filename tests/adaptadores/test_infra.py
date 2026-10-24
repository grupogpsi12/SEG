"""Item 2.2: invariantes de infra/compose.yaml que se pueden comprobar sin Docker.

No reemplaza la verificacion con contenedores (todos healthy, pruebas.sh en verde): impide que un
cambio al compose rompa en silencio RS-02, RS-03, RS-18, RS-19 o los invariantes 8 y 14.
"""

import re
from pathlib import Path
from typing import Any

import yaml

RAIZ = Path(__file__).resolve().parents[2]
COMPOSE: dict[str, Any] = yaml.safe_load(
    (RAIZ / "infra" / "compose.yaml").read_text(encoding="utf-8")
)
SERVICIOS: dict[str, Any] = COMPOSE["services"]


def _entorno(servicio: str) -> str:
    e = SERVICIOS[servicio].get("environment", {})
    return "\n".join(e) if isinstance(e, list) else "\n".join(f"{k}={v}" for k, v in e.items())


def test_RS_02_solo_bunkerweb_publica_puertos() -> None:
    con_puertos = {n for n, s in SERVICIOS.items() if s.get("ports")}
    assert con_puertos == {"bunkerweb"}
    assert {str(p).split(":")[0] for p in SERVICIOS["bunkerweb"]["ports"]} == {"80", "443"}


def test_RS_03_la_red_de_la_base_de_glpi_es_interna() -> None:
    assert COMPOSE["networks"]["db_net"]["internal"] is True
    assert SERVICIOS["mariadb"]["networks"] == ["db_net"]


def test_invariante_8_service_role_solo_en_admin_usuarios() -> None:
    con_clave = {n for n, s in SERVICIOS.items() if "supabase_service_role" in s.get("secrets", [])}
    assert con_clave == {"admin-usuarios"}
    assert SERVICIOS["admin-usuarios"]["profiles"] == ["admin"]  # no arranca con `up`


def test_RS_18_imagenes_de_terceros_fijadas_por_digest() -> None:
    for nombre, s in SERVICIOS.items():
        imagen = s.get("image", "")
        if "jml-app" in imagen:  # la propia: se construye aqui o se publica en GHCR
            continue
        assert re.search(r"@sha256:[0-9a-f]{64}$", imagen), nombre
    assert re.search(r"^FROM \S+@sha256:[0-9a-f]{64}$", (RAIZ / "Dockerfile").read_text(), re.M)
    assert "bunkerweb:1.6.15@" in SERVICIOS["bunkerweb"]["image"]  # >= 1.6.15 (R13)


def test_invariante_14_waf_en_bloqueo_con_crs_y_api_token() -> None:
    entorno = _entorno("bw-scheduler")
    for ajuste in (
        "SECURITY_MODE=${SECURITY_MODE:-block}",
        "USE_MODSECURITY=yes",
        "USE_MODSECURITY_CRS=yes",
    ):
        assert ajuste in entorno
    assert "API_TOKEN=${BW_API_TOKEN:?" in entorno
    assert "API_TOKEN" in _entorno("bunkerweb")
    assert not {"bw-ui", "bw-db"} & set(SERVICIOS)  # sin interfaz ni su base (RS-19)


def test_RS_08_y_RS_17_limites_del_sitio_de_la_aplicacion() -> None:
    entorno = _entorno("bw-scheduler")
    assert "_MAX_CLIENT_SIZE=21m" in entorno
    assert "_LIMIT_REQ_RATE_1=5r/m" in entorno
    assert "_LIMIT_REQ_URL_1=^/ingreso" in entorno
    assert "BAD_BEHAVIOR_BAN_TIME=3600" in entorno


def test_RS_05_django_confia_solo_en_la_ip_fija_de_bunkerweb() -> None:
    ip = SERVICIOS["bunkerweb"]["networks"]["app"]["ipv4_address"]
    for servicio in ("web", "worker"):
        assert f"JML_PROXIES_CONFIABLES={ip}" in _entorno(servicio)


def test_web_y_worker_tienen_chequeo_de_salud_y_corren_sin_root_ni_escritura() -> None:
    for servicio in ("web", "worker"):
        s = SERVICIOS[servicio]
        assert s["healthcheck"]["test"]
        assert s["read_only"] is True
        assert s["cap_drop"] == ["ALL"]
    assert "USER jml" in (RAIZ / "Dockerfile").read_text()


def test_ningun_env_con_valores_esta_versionado() -> None:
    assert not (RAIZ / "infra" / ".env").exists() or ".env" in (RAIZ / ".gitignore").read_text()
    assert "infra/.env" in (RAIZ / ".gitignore").read_text()


LOCAL: dict[str, Any] = yaml.safe_load(
    (RAIZ / "infra" / "compose.local.yaml").read_text(encoding="utf-8")
)


def test_el_modo_local_no_publica_puertos_y_su_base_es_interna() -> None:
    """Invariante 14 tambien en las pruebas del equipo: BunkerWeb sigue siendo la unica entrada."""
    assert not {n for n, s in LOCAL["services"].items() if s.get("ports")}
    assert LOCAL["networks"]["pg_net"]["internal"] is True
    assert re.search(r"@sha256:[0-9a-f]{64}$", LOCAL["services"]["postgres"]["image"])
    assert LOCAL["services"]["migrar"]["environment"]["JML_DB_USUARIO"] == "app_owner"


def test_produccion_nunca_desactiva_tls_hacia_la_base() -> None:
    texto = (RAIZ / "infra" / "compose.yaml").read_text(encoding="utf-8")
    assert "JML_DB_SSLMODE" not in texto  # solo el modo local lo cambia


def test_ADR_028_migrar_es_el_unico_con_la_clave_del_duenio() -> None:
    con_clave = {
        n
        for n, s in SERVICIOS.items()
        for x in s.get("secrets", [])
        if (x if isinstance(x, str) else x["source"]) == "db_owner_password"
    }
    assert con_clave == {"migrar"}
    assert SERVICIOS["migrar"]["profiles"] == ["admin"]


def _con_secreto(nombre: str) -> set[str]:
    return {
        n
        for n, s in SERVICIOS.items()
        for x in s.get("secrets", [])
        if (x if isinstance(x, str) else x["source"]) == nombre
    }


def test_solo_el_worker_opera_glpi_y_solo_el_configurador_lo_administra() -> None:
    """CLAUDE.md: el worker es el unico cliente de GLPI en operacion; la web nunca lo llama."""
    assert _con_secreto("glpi_user_token") == {"worker"}
    assert _con_secreto("glpi_admin_user_token") == {"configurar-glpi"}
    assert SERVICIOS["configurar-glpi"]["profiles"] == ["admin"]
    assert "web" not in _con_secreto("glpi_app_token")


# --- 5.5 Reportería del WAF (infra/compose.reporteria.yaml, revisión del 24/10/2026) ----------

REPORTERIA: dict[str, Any] = yaml.safe_load(
    (RAIZ / "infra" / "compose.reporteria.yaml").read_text(encoding="utf-8")
)
PROPIOS_DE_LA_REPORTERIA = {"fluent-bit", "loki", "grafana"}


def test_RS_18_la_reporteria_fija_sus_imagenes_por_digest() -> None:
    for nombre in PROPIOS_DE_LA_REPORTERIA:
        assert re.search(r"@sha256:[0-9a-f]{64}$", REPORTERIA["services"][nombre]["image"]), nombre


def test_RS_02_la_reporteria_solo_escucha_en_el_equipo() -> None:
    """Grafana y la entrada de Fluent Bit solo en 127.0.0.1 (SRS §627); Loki, en ninguno."""
    con_puertos = {n for n, s in REPORTERIA["services"].items() if s.get("ports")}
    assert con_puertos == {"fluent-bit", "grafana"}
    for nombre in con_puertos:
        for puerto in REPORTERIA["services"][nombre]["ports"]:
            assert str(puerto).startswith("127.0.0.1:"), (nombre, puerto)
    for nombre in PROPIOS_DE_LA_REPORTERIA:
        assert REPORTERIA["services"][nombre]["networks"] == ["waf-logs"], nombre


def test_RS_20_grafana_lee_su_clave_de_un_secreto() -> None:
    grafana = REPORTERIA["services"]["grafana"]
    assert grafana["environment"]["GF_SECURITY_ADMIN_PASSWORD__FILE"].startswith("/run/secrets/")
    assert "GF_SECURITY_ADMIN_PASSWORD" not in grafana["environment"]
    assert grafana["environment"]["GF_USERS_ALLOW_SIGN_UP"] == "false"


def test_RNF_16_sin_reporteria_los_logs_de_docker_rotan() -> None:
    """S-36: cada contenedor guarda sus logs con tope de tamaño y de archivos. Se revisan todos los
    del compose base y los que solo existen en el modo local o en la reportería (las
    sobrescrituras heredan el del base; con la reportería, el WAF pasa a fluentd)."""
    propios = {
        **SERVICIOS,
        **{n: s for n, s in LOCAL["services"].items() if n not in SERVICIOS},
        **{n: s for n, s in REPORTERIA["services"].items() if n not in SERVICIOS},
    }
    for nombre, servicio in propios.items():
        logging = servicio.get("logging", {})
        assert logging.get("driver") == "json-file", nombre
        assert {"max-size", "max-file"} <= set(logging.get("options", {})), nombre
    for nombre in ("bunkerweb", "bw-scheduler"):
        assert REPORTERIA["services"][nombre]["logging"]["driver"] == "fluentd"
