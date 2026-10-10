"""Contratos de AlmacenDeSoportes (RD-12, T17), ProveedorDeIdentidad (RF-01, RF-02, RS-08) y Reloj."""

from datetime import timedelta

import pytest

from jml.aplicacion.puertos import CredencialesInvalidas, SoporteNoDisponible
from tests.contratos.conftest import EntornoDeContrato

# --- AlmacenDeSoportes ------------------------------------------------------------------------


def test_guardar_y_leer(entorno: EntornoDeContrato) -> None:
    nombre = entorno.soportes.guardar(b"%PDF-1.4 abc")
    assert entorno.soportes.leer(nombre) == b"%PDF-1.4 abc"
    assert entorno.soportes.existe(nombre)


def test_los_nombres_son_distintos_y_no_revelan_el_contenido_RD_12(
    entorno: EntornoDeContrato,
) -> None:
    contenido = b"%PDF-1.4 mismo contenido"
    nombres = {entorno.soportes.guardar(contenido) for _ in range(20)}
    assert len(nombres) == 20  # el mismo contenido no da el mismo nombre
    for n in nombres:
        assert "/" not in n
        assert "\\" not in n
        assert ".." not in n
        assert "." not in n  # sin extension: el volumen es noexec y nada se ejecuta por nombre
        assert "PDF" not in n.upper()


def test_borrar_es_idempotente(entorno: EntornoDeContrato) -> None:
    nombre = entorno.soportes.guardar(b"%PDF-x")
    entorno.soportes.borrar(nombre)
    entorno.soportes.borrar(nombre)
    entorno.soportes.borrar("nunca-existio")
    assert not entorno.soportes.existe(nombre)


def test_leer_lo_borrado_o_perdido_falla(entorno: EntornoDeContrato) -> None:
    nombre = entorno.soportes.guardar(b"%PDF-x")
    entorno.soportes.borrar(nombre)
    with pytest.raises(SoporteNoDisponible):
        entorno.soportes.leer(nombre)
    with pytest.raises(SoporteNoDisponible):
        entorno.soportes.leer("nunca-existio")


# --- ProveedorDeIdentidad ---------------------------------------------------------------------


def _registrar(e: EntornoDeContrato) -> None:
    e.registrar_credenciales("ana@andina.example", "una-clave-larga-123", "u-ana")


def test_contrasena_y_totp_llevan_a_AAL2_RF_01(entorno: EntornoDeContrato) -> None:
    _registrar(entorno)
    primer = entorno.identidad.autenticar("ana@andina.example", "una-clave-larga-123")
    assert primer.usuario_id == "u-ana"
    entorno.identidad.inscribir_totp(primer.desafio_id)
    identidad = entorno.identidad.verificar_totp(primer.desafio_id, entorno.codigo_totp_valido)
    assert (identidad.usuario_id, identidad.nivel) == ("u-ana", 2)


def test_el_primer_ingreso_exige_inscribir_el_totp_RF_02(entorno: EntornoDeContrato) -> None:
    _registrar(entorno)
    primero = entorno.identidad.autenticar("ana@andina.example", "una-clave-larga-123")
    assert primero.requiere_inscripcion is True
    # sin inscribir no se llega a AAL2 aunque el codigo sea el valido
    with pytest.raises(CredencialesInvalidas):
        entorno.identidad.verificar_totp(primero.desafio_id, entorno.codigo_totp_valido)
    secreto = entorno.identidad.inscribir_totp(primero.desafio_id)
    assert secreto
    entorno.identidad.verificar_totp(primero.desafio_id, entorno.codigo_totp_valido)
    # ya inscrito: el siguiente ingreso solo pide el codigo
    segundo = entorno.identidad.autenticar("ana@andina.example", "una-clave-larga-123")
    assert segundo.requiere_inscripcion is False
    assert (
        entorno.identidad.verificar_totp(segundo.desafio_id, entorno.codigo_totp_valido).nivel == 2
    )


def test_contrasena_correcta_sin_totp_no_da_identidad_CA_14(entorno: EntornoDeContrato) -> None:
    _registrar(entorno)
    primer = entorno.identidad.autenticar("ana@andina.example", "una-clave-larga-123")
    entorno.identidad.inscribir_totp(primer.desafio_id)
    with pytest.raises(CredencialesInvalidas):
        entorno.identidad.verificar_totp(primer.desafio_id, "000000")


def test_el_error_es_generico_RS_08(entorno: EntornoDeContrato) -> None:
    """Correo desconocido y contrasena incorrecta son indistinguibles."""
    _registrar(entorno)
    with pytest.raises(CredencialesInvalidas) as desconocido:
        entorno.identidad.autenticar("nadie@andina.example", "x")
    with pytest.raises(CredencialesInvalidas) as mala:
        entorno.identidad.autenticar("ana@andina.example", "incorrecta")
    assert type(desconocido.value) is type(mala.value)
    assert str(desconocido.value) == str(mala.value)
    assert "ana" not in str(mala.value)


def test_un_desafio_se_usa_una_sola_vez_y_los_desconocidos_fallan(
    entorno: EntornoDeContrato,
) -> None:
    _registrar(entorno)
    primer = entorno.identidad.autenticar("ana@andina.example", "una-clave-larga-123")
    entorno.identidad.inscribir_totp(primer.desafio_id)
    entorno.identidad.verificar_totp(primer.desafio_id, entorno.codigo_totp_valido)
    with pytest.raises(CredencialesInvalidas):
        entorno.identidad.verificar_totp(primer.desafio_id, entorno.codigo_totp_valido)
    with pytest.raises(CredencialesInvalidas):
        entorno.identidad.verificar_totp("desafio-falso", entorno.codigo_totp_valido)
    with pytest.raises(CredencialesInvalidas):
        entorno.identidad.inscribir_totp("desafio-falso")


# --- Reloj ------------------------------------------------------------------------------------


def test_el_reloj_entrega_instantes_con_zona_y_avanza(entorno: EntornoDeContrato) -> None:
    antes = entorno.reloj.ahora()
    assert antes.tzinfo is not None
    entorno.reloj.avanzar(timedelta(minutes=5))
    assert entorno.reloj.ahora() - antes == timedelta(minutes=5)
    assert entorno.reloj.ahora() == entorno.reloj.ahora()  # fijo entre dos lecturas
