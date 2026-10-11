"""Item 2.1: secretos desde /run/secrets y ajustes de seguridad (ADR-009, RS-04, RS-07, invariante 10)."""

from pathlib import Path

import pytest
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from config.secretos import leer_secreto, lista_de_entorno


def test_lee_el_secreto_sin_espacios_ni_saltos_de_linea(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "glpi_token").write_text("  abc123\n", encoding="utf-8")
    monkeypatch.setenv("JML_SECRETOS_DIR", str(tmp_path))
    assert leer_secreto("glpi_token") == "abc123"


def test_el_directorio_por_defecto_es_run_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JML_SECRETOS_DIR", raising=False)
    with pytest.raises(ImproperlyConfigured, match=r"/run/secrets/no_existe"):
        leer_secreto("no_existe")


def test_un_secreto_que_falta_nombra_el_archivo_pero_no_revela_nada(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JML_SECRETOS_DIR", str(tmp_path))
    with pytest.raises(ImproperlyConfigured, match="falta el secreto 'db_password'"):
        leer_secreto("db_password")


def test_un_secreto_vacio_es_un_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "vacio").write_text(" \n", encoding="utf-8")
    monkeypatch.setenv("JML_SECRETOS_DIR", str(tmp_path))
    with pytest.raises(ImproperlyConfigured, match="vacio"):
        leer_secreto("vacio")


@pytest.mark.parametrize(
    "nombre", ["../etc/passwd", "a/b", "a\\b", "", ".oculto", "MAYUS", "con espacio"]
)
def test_el_nombre_del_secreto_no_permite_recorrer_rutas(nombre: str) -> None:
    with pytest.raises(ImproperlyConfigured, match="nombre de secreto invalido"):
        leer_secreto(nombre)


def test_la_lista_de_entorno_ignora_vacios(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("X_LISTA", " a.localhost , ,b.localhost ")
    assert lista_de_entorno("X_LISTA") == ["a.localhost", "b.localhost"]
    monkeypatch.delenv("X_LISTA")
    assert lista_de_entorno("X_LISTA") == []


def test_la_clave_de_django_sale_del_archivo_de_secretos() -> None:
    assert settings.SECRET_KEY.startswith("clave-de-prueba-")


def test_debug_esta_apagado_y_los_hosts_son_explicitos() -> None:
    from config import settings as produccion  # pytest-django agrega "testserver" en caliente

    assert settings.DEBUG is False
    assert produccion.ALLOWED_HOSTS == ["testserver", "app.localhost"]
    assert "*" not in settings.ALLOWED_HOSTS


def test_cookies_seguras_RS_04() -> None:
    assert settings.SESSION_COOKIE_SECURE is True
    assert settings.CSRF_COOKIE_SECURE is True
    assert settings.SESSION_COOKIE_HTTPONLY is True
    assert settings.CSRF_COOKIE_HTTPONLY is True
    assert settings.SESSION_COOKIE_SAMESITE == "Lax"
    assert settings.CSRF_COOKIE_SAMESITE == "Lax"


def test_django_no_duplica_las_cabeceras_que_pone_bunkerweb_RS_07() -> None:
    assert settings.SECURE_HSTS_SECONDS == 0
    assert settings.SECURE_CONTENT_TYPE_NOSNIFF is False
    assert settings.SECURE_REFERRER_POLICY is None
    assert settings.X_FRAME_OPTIONS == "DENY"


def test_la_base_de_produccion_es_postgresql_con_tls_y_esquema_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from config import settings as produccion

    db = produccion.DATABASES["default"]
    assert db["ENGINE"] == "django.db.backends.postgresql"
    assert db["PORT"] == "5432"  # session pooler de Supabase (lessons n.9)
    assert db["USER"] == "app_backend"
    opciones = db["OPTIONS"]
    assert isinstance(opciones, dict)
    assert opciones["sslmode"] == "verify-full"
    assert opciones["options"] == "-c search_path=app"
    assert str(opciones["sslrootcert"]).endswith("supabase_ca_crt")
    assert db["PASSWORD"] == "no-se-usa-en-pruebas"  # tambien viene de /run/secrets


def test_zona_horaria_e_idioma() -> None:
    assert settings.USE_TZ is True
    assert settings.TIME_ZONE == "America/Bogota"
    assert settings.LANGUAGE_CODE == "es-co"


def test_check_deploy_solo_silencia_lo_que_resuelve_bunkerweb() -> None:
    assert sorted(settings.SILENCED_SYSTEM_CHECKS) == [
        "security.W004",  # HSTS
        "security.W006",  # X-Content-Type-Options
        "security.W008",  # redireccion a HTTPS
        "security.W022",  # Referrer-Policy
    ]


def test_check_deploy_no_reporta_nada_con_una_clave_real() -> None:
    from django.core.management import call_command

    call_command("check", "--deploy", "--fail-level", "WARNING")
