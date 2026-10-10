"""Item 1.8: auditoria encadenada (RD-03, RF-35, RF-36, CA-09, P3)."""

import hashlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from itertools import zip_longest

import pytest
from hypothesis import given
from hypothesis import strategies as st

from jml.dominio.auditoria import (
    HASH_GENESIS,
    EventoDeAuditoria,
    RegistroDeAuditoria,
    calcular_hash,
    contenido_canonico,
    encadenar,
    formatear_fecha,
    verificar_cadena,
)
from jml.dominio.errores import CampoRestringidoProhibido, DatoInvalido
from jml.dominio.valores import CampoRestringido
from tests.fabricas import AHORA


def alterar(reg: RegistroDeAuditoria, campo: str, valor: object) -> RegistroDeAuditoria:
    return replace(reg, **{campo: valor})  # type: ignore[arg-type]  # replace dinamico por campo


def cadena(n: int) -> list[RegistroDeAuditoria]:
    registros: list[RegistroDeAuditoria] = []
    previo: RegistroDeAuditoria | None = None
    for i in range(n):
        ev = EventoDeAuditoria(f"accion.{i}", f"obj-{i}", {"n": i, "ok": True, "lista": ("a", "b")})
        previo = encadenar(previo, AHORA + timedelta(seconds=i), f"actor-{i % 3}", ev)
        registros.append(previo)
    return registros


def test_formato_canonico_golden_RD_03() -> None:
    """Vector fijo escrito a mano: si cambia el formato, cambia el hash y esta prueba falla."""
    ev = EventoDeAuditoria("solicitud.aprobada", "SOL-2026-000001", {"b": 2, "a": "ñ", "c": None})
    reg = encadenar(None, datetime(2026, 10, 12, 15, 0, 0, 123456, tzinfo=UTC), "u-1", ev)
    esperado = (
        '{"accion":"solicitud.aprobada","actor":"u-1","datos":{"a":"ñ","b":2,"c":null},'
        '"fecha":"2026-10-12T15:00:00.123456Z","objeto":"SOL-2026-000001","secuencia":1}'
    )
    assert reg.contenido() == esperado.encode("utf-8")
    assert reg.hash_anterior == "0" * 64 == HASH_GENESIS
    assert reg.hash == hashlib.sha256(b"0" * 64 + esperado.encode("utf-8")).hexdigest()


def test_el_encadenado_une_con_el_hash_anterior() -> None:
    a, b = cadena(2)
    assert b.hash_anterior == a.hash
    assert b.secuencia == 2
    assert b.hash == calcular_hash(a.hash, b.contenido())


def test_la_fecha_siempre_va_en_utc() -> None:
    bogota = datetime(2026, 10, 12, 10, 0, tzinfo=timezone(timedelta(hours=-5)))
    assert formatear_fecha(bogota) == "2026-10-12T15:00:00.000000Z"
    with pytest.raises(DatoInvalido):
        formatear_fecha(datetime(2026, 10, 12, 10, 0))


def test_cadena_valida_y_vacia() -> None:
    assert verificar_cadena([]).valida
    r = verificar_cadena(cadena(5))
    assert r.valida
    assert r.primer_afectado is None


def test_CA_09_alterar_un_registro_indica_el_primer_afectado() -> None:
    reg = cadena(6)
    reg[3] = alterar(reg[3], "actor", "intruso")
    r = verificar_cadena(reg)
    assert (r.valida, r.primer_afectado, r.motivo) == (False, 4, "hash")


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("actor", "x"),
        ("accion", "x"),
        ("objeto", "x"),
        ("fecha", AHORA + timedelta(days=1)),
        ("datos", {"n": 999}),
        ("hash", "f" * 64),
    ],
)
def test_alterar_cualquier_campo_rompe_la_cadena_en_ese_registro(campo: str, valor: object) -> None:
    reg = cadena(5)
    reg[2] = alterar(reg[2], campo, valor)
    r = verificar_cadena(reg)
    assert (r.valida, r.primer_afectado) == (False, 3)


def test_alterar_el_enlace_o_la_secuencia() -> None:
    reg = cadena(5)
    reg[2] = alterar(reg[2], "hash_anterior", "a" * 64)
    assert verificar_cadena(reg).motivo == "enlace"
    reg = cadena(5)
    reg[2] = alterar(reg[2], "secuencia", 99)
    assert verificar_cadena(reg).motivo == "secuencia"


def test_quitar_duplicar_y_reordenar() -> None:
    base = cadena(6)
    quitado = base[:2] + base[3:]
    assert verificar_cadena(quitado).primer_afectado == 3
    duplicado = [*base[:3], base[2], *base[3:]]
    assert verificar_cadena(duplicado).primer_afectado == 4
    reordenado = [*base[:2], base[3], base[2], *base[4:]]
    assert verificar_cadena(reordenado).primer_afectado == 3
    sin_inicio = base[1:]
    assert verificar_cadena(sin_inicio).primer_afectado == 1


def test_recalcular_el_hash_del_registro_alterado_se_detecta_en_el_siguiente() -> None:
    """Un atacante que recompone el hash de un registro rompe el enlace del que sigue."""
    reg = cadena(5)
    falso = replace(reg[1], actor="intruso")
    falso = replace(falso, hash=calcular_hash(falso.hash_anterior, falso.contenido()))
    reg[1] = falso
    assert verificar_cadena(reg).primer_afectado == 3


def test_quitar_el_ultimo_registro_no_lo_detecta_la_cadena_sola_RD_04() -> None:
    """Limite documentado: para eso existe la copia inmutable en Blob."""
    assert verificar_cadena(cadena(5)[:-1]).valida


# --- campos restringidos fuera de la auditoria (RD-05) ----------------------------------------


def test_la_auditoria_rechaza_campos_restringidos() -> None:
    with pytest.raises(CampoRestringidoProhibido):
        EventoDeAuditoria("a", "o", {"x": CampoRestringido("secreto")})  # type: ignore[dict-item]  # tipo vetado a proposito
    with pytest.raises(CampoRestringidoProhibido):
        EventoDeAuditoria("a", "o", {"x": (CampoRestringido("secreto"),)})  # type: ignore[dict-item]
    for clave in ("motivo", "descripcion", "password", "token", "totp", "secret", "Motivo"):
        with pytest.raises(CampoRestringidoProhibido):
            EventoDeAuditoria("a", "o", {clave: "algo"})


def test_la_auditoria_rechaza_tipos_no_auditables() -> None:
    with pytest.raises(DatoInvalido):
        EventoDeAuditoria("a", "o", {"x": 1.5})  # type: ignore[dict-item]
    with pytest.raises(DatoInvalido):
        EventoDeAuditoria("a", "o", {"x": {"y": 1}})  # type: ignore[dict-item]
    with pytest.raises(DatoInvalido):
        EventoDeAuditoria("a", "o", {"x": (1.5,)})  # type: ignore[dict-item]
    with pytest.raises(DatoInvalido):
        EventoDeAuditoria(" ", "o", {})
    with pytest.raises(DatoInvalido):
        EventoDeAuditoria("a", " ", {})


def test_los_datos_del_evento_son_de_solo_lectura() -> None:
    ev = EventoDeAuditoria("a", "o", {"x": 1})
    with pytest.raises(TypeError):
        ev.datos["x"] = 2  # type: ignore[index]


def test_contenido_canonico_acepta_tuplas() -> None:
    c = contenido_canonico(1, AHORA, "u", "a", "o", {"t": ("x", 1, None)})
    assert b'"t":["x",1,null]' in c


# --- P3 ---------------------------------------------------------------------------------------


@given(st.integers(2, 12), st.data())
def test_P3_cualquier_alteracion_se_detecta_en_el_primer_afectado(
    n: int, data: st.DataObject
) -> None:
    original = cadena(n)
    i = data.draw(st.integers(0, n - 1))
    operacion = data.draw(st.sampled_from(["campo", "quitar", "duplicar", "reordenar"]))
    tocada = list(original)
    if operacion == "campo":
        campo = data.draw(st.sampled_from(["actor", "accion", "objeto", "hash_anterior", "hash"]))
        tocada[i] = alterar(
            tocada[i], campo, "zz" if campo in ("actor", "accion", "objeto") else "e" * 64
        )
    elif operacion == "quitar":
        if i == n - 1:
            return  # quitar la cola no lo detecta la cadena (RD-04)
        del tocada[i]
    elif operacion == "duplicar":
        tocada.insert(i, tocada[i])
    else:
        if i == n - 1:
            return
        tocada[i], tocada[i + 1] = tocada[i + 1], tocada[i]
    primero_distinto = next(
        (k for k, (a, b) in enumerate(zip_longest(original, tocada)) if a != b), None
    )
    assert primero_distinto is not None
    r = verificar_cadena(tocada)
    assert not r.valida
    assert r.primer_afectado == primero_distinto + 1


@given(st.integers(0, 15))
def test_P3_una_cadena_intacta_siempre_verifica(n: int) -> None:
    assert verificar_cadena(cadena(n)).valida
