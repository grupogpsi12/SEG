"""Items 1.5 (perfiles, ADR-022, CA-19), usuario sugerido (4.10, P6), soporte (RF-39) y colaborador."""

from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from jml.dominio.colaborador import TRANSICIONES_DE_COLABORADOR, Colaborador
from jml.dominio.errores import DatoInvalido, OperacionNoPermitida, SoporteInvalido
from jml.dominio.perfiles import (
    AccesoARecurso,
    PerfilDeAcceso,
    RecursoCompartido,
    aplicar,
    diferencia,
    nombre_de_sede,
)
from jml.dominio.soporte import Soporte, validar_soporte
from jml.dominio.tipos import (
    EstadoColaborador,
    EstadoDeSoporte,
    PerfilDeRecurso,
    TipoDeEquipo,
)
from jml.dominio.usuarios import usuario_sugerido
from jml.dominio.valores import MAX_SOPORTE_BYTES, SolicitudId, Usuario
from tests.estrategias import perfiles
from tests.fabricas import MATRIZ, SEDES, colaborador, datos_ingreso, perfil

# --- perfiles ---------------------------------------------------------------------------------


def test_la_matriz_del_SRS_4_9_se_carga_completa() -> None:
    assert set(MATRIZ) == {"Gerencia", "RRHH", "Finanzas", "Comercial", "TI", "Operaciones"}
    p = perfil("Finanzas", "Medellín")
    assert "GG-Sede-Medellin" in p.grupos_ad
    assert "NET-VLAN-Medellin" in p.grupos_red
    assert p.tipo_equipo is TipoDeEquipo.ESCRITORIO
    assert {r.grupo for r in p.recursos} == {"FS-Comun-RO", "FS-Finanzas-RW", "FS-Presupuesto-RO"}


def test_nombre_de_sede() -> None:
    assert [nombre_de_sede(s) for s in SEDES] == ["Bogota", "Medellin", "Cali"]
    with pytest.raises(DatoInvalido):
        nombre_de_sede(" ")


def test_retiro_de_accesos_no_se_configura_en_la_matriz_ADR_022() -> None:
    with pytest.raises(DatoInvalido):
        RecursoCompartido("\\\\x\\y", "s", PerfilDeRecurso.RETIRO_DE_ACCESOS, "G")
    r = RecursoCompartido("\\\\x\\y", "s", PerfilDeRecurso.EDICION, "G")
    assert AccesoARecurso.retiro(r).perfil is PerfilDeRecurso.RETIRO_DE_ACCESOS
    assert AccesoARecurso.aplicar(r).perfil is PerfilDeRecurso.EDICION


def test_acceso_como_texto_lleva_ruta_serie_perfil_y_grupo_CA_19() -> None:
    r = perfil("Finanzas").recursos[1]
    linea = AccesoARecurso.aplicar(r).como_texto()
    for parte in (r.ruta, r.serie, r.perfil.value, r.grupo):
        assert parte in linea


def test_recursos_de_retiro_cubren_todos_CA_19() -> None:
    p = perfil("Finanzas")
    retiros = p.accesos_de_retiro()
    assert len(retiros) == len(p.recursos) == 3
    assert all(a.perfil is PerfilDeRecurso.RETIRO_DE_ACCESOS for a in retiros)
    assert {a.ruta for a in retiros} == {r.ruta for r in p.recursos}
    assert [a.perfil for a in p.accesos_a_aplicar()] == [r.perfil for r in p.recursos]


def test_ruta_repetida_en_un_perfil_se_rechaza() -> None:
    r = perfil("TI").recursos[0]
    with pytest.raises(DatoInvalido, match="recursos"):
        PerfilDeAcceso("TI", "Cali", (), (), (), (), TipoDeEquipo.PORTATIL, (r, r))


def test_el_orden_de_los_grupos_no_cambia_la_igualdad() -> None:
    a = PerfilDeAcceso("TI", "Cali", ("b", "a"), (), (), (), TipoDeEquipo.PORTATIL, ())
    b = PerfilDeAcceso("TI", "Cali", ("a", "b", "a"), (), (), (), TipoDeEquipo.PORTATIL, ())
    assert a == b


def test_cdp_finanzas_a_ti_CA_19() -> None:
    """CDP: recursos nuevos con su perfil y 'Retiro de accesos' en los que ya no corresponden."""
    d = diferencia(perfil("Finanzas"), perfil("TI"))
    aplicar_ = {(a.ruta.split("\\")[-1], a.perfil) for a in d.recursos_a_aplicar}
    retirar = {(a.ruta.split("\\")[-1], a.perfil) for a in d.recursos_a_retirar}
    assert ("comun", PerfilDeRecurso.EDICION) in aplicar_  # Consulta -> Edicion: se reaplica
    assert ("TI", PerfilDeRecurso.EDICION) in aplicar_
    assert retirar == {
        ("Contabilidad", PerfilDeRecurso.RETIRO_DE_ACCESOS),
        ("Presupuesto", PerfilDeRecurso.RETIRO_DE_ACCESOS),
    }
    assert "GG-TI" in d.grupos_ad_agregar
    assert "GG-Finanzas" in d.grupos_ad_quitar
    assert "NET-VPN" in d.grupos_red_agregar
    assert d.equipo_nuevo is TipoDeEquipo.PORTATIL
    assert d.cambia_ad
    assert d.cambia_red
    assert d.cambia_m365
    assert not d.esta_vacia


def test_csu_solo_cambia_los_grupos_de_sede() -> None:
    d = diferencia(perfil("TI", "Bogotá"), perfil("TI", "Cali"))
    assert d.grupos_ad_agregar == ("GG-Sede-Cali",)
    assert d.grupos_ad_quitar == ("GG-Sede-Bogota",)
    assert d.grupos_red_agregar == ("NET-VLAN-Cali",)
    assert d.grupos_red_quitar == ("NET-VLAN-Bogota",)
    assert not d.cambia_m365
    assert d.equipo_nuevo is None
    assert not d.recursos_a_aplicar
    assert not d.recursos_a_retirar


def test_diferencia_vacia_para_el_mismo_perfil() -> None:
    d = diferencia(perfil("TI"), perfil("TI"))
    assert d.esta_vacia
    assert not d.cambia_ad
    assert not d.cambia_red
    assert not d.cambia_m365


@given(perfiles())
def test_P5_diferencia_de_un_perfil_consigo_mismo_es_vacia(a: PerfilDeAcceso) -> None:
    assert diferencia(a, a).esta_vacia


@given(perfiles(), perfiles())
def test_P5_aplicar_la_diferencia_reconstruye_el_destino(
    a: PerfilDeAcceso, b: PerfilDeAcceso
) -> None:
    assert aplicar(diferencia(a, b), a) == b


@given(perfiles(), perfiles())
def test_P5_retirados_y_nuevos_cubren_exactamente_la_diferencia_de_recursos(
    a: PerfilDeAcceso, b: PerfilDeAcceso
) -> None:
    d = diferencia(a, b)
    rutas_dif = {r.ruta for r in set(a.recursos) ^ set(b.recursos)}
    cubiertas = {x.ruta for x in d.recursos_a_aplicar} | {x.ruta for x in d.recursos_a_retirar}
    assert cubiertas == rutas_dif
    # nunca se retira y se aplica la misma ruta
    assert not {x.ruta for x in d.recursos_a_aplicar} & {x.ruta for x in d.recursos_a_retirar}
    assert all(x.perfil is PerfilDeRecurso.RETIRO_DE_ACCESOS for x in d.recursos_a_retirar)


# --- usuario sugerido (P6) --------------------------------------------------------------------


def test_usuario_sugerido_ejemplos_del_SRS_4_10() -> None:
    assert usuario_sugerido("María José", "Gómez Ramírez", []).valor == "maria.gomez"
    assert usuario_sugerido("María", "Gómez Ramírez", ["maria.gomez"]).valor == "maria.gomez.r"
    assert usuario_sugerido("María", "Gómez Ramírez", ["maria.gomez", "maria.gomez.r"]).valor == (
        "maria.gomez2"
    )
    assert usuario_sugerido("María", "Gómez", ["maria.gomez"]).valor == "maria.gomez2"
    assert usuario_sugerido("María", "Gómez", ["maria.gomez", "maria.gomez2"]).valor == (
        "maria.gomez3"
    )


def test_usuario_sugerido_enie_tildes_y_mayusculas_S_23() -> None:
    assert usuario_sugerido("ÑANDÚ", "Muñoz", []).valor == "nandu.munoz"
    assert usuario_sugerido("Ana", "O'Brien", []).valor == "ana.obrien"


def test_usuario_sugerido_compara_sin_distinguir_mayusculas() -> None:
    assert usuario_sugerido("Ana", "Pérez Rojas", ["ANA.PEREZ"]).valor == "ana.perez.r"


def test_usuario_sugerido_trunca_a_20_sin_punto_al_borde_S_23() -> None:
    assert usuario_sugerido("Maximiliano", "Fernandezgarciaalvarez", []).valor == (
        "maximiliano.fernande"
    )
    # el corte cae justo sobre el punto: no puede quedar un punto al final
    u = usuario_sugerido("abcdefghijklmnopqrs", "pe", [])
    assert u.valor == "abcdefghijklmnopqrs"


def test_usuario_sugerido_con_sufijo_cabe_en_20() -> None:
    u = usuario_sugerido("Maximiliano", "Fernandezgarcia", ["maximiliano.fernandez"[:20]])
    assert len(u.valor) <= 20
    assert u.valor != "maximiliano.fernandez"[:20]


def test_usuario_sugerido_rechaza_nombres_sin_letras() -> None:
    with pytest.raises(DatoInvalido, match="nombres"):
        usuario_sugerido("---", "Gomez", [])
    with pytest.raises(DatoInvalido, match="apellidos"):
        usuario_sugerido("Ana", "  ", [])


_nombres = st.text(
    alphabet=st.sampled_from(list("abcdefghijklmnñopqrstuvwxyzáéíóúüABCDEFGHIÑ'-")),
    min_size=1,
    max_size=30,
).filter(lambda t: any(c.isalpha() for c in t))


@given(
    _nombres,
    _nombres,
    st.sets(st.from_regex(r"[a-z]{1,8}\.[a-z]{1,8}[0-9]?", fullmatch=True), max_size=30),
)
def test_P6_usuario_unico_ascii_minuscula_y_corto(
    nombres: str, apellidos: str, existentes: set[str]
) -> None:
    try:
        u = usuario_sugerido(nombres, apellidos, existentes)
    except DatoInvalido:
        return  # nombres sin ninguna letra ASCII tras limpiar (p. ej. solo 'ñ' sueltas)
    assert u.valor not in {e.lower() for e in existentes}
    assert len(u.valor) <= 20
    assert u.valor.isascii()
    assert u.valor == u.valor.lower()
    assert usuario_sugerido(nombres, apellidos, existentes) == u  # determinista


@given(_nombres, _nombres)
def test_P6_unico_incluso_si_existen_todos_los_candidatos(nombres: str, apellidos: str) -> None:
    ocupados: set[str] = set()
    vistos = []
    for _ in range(6):
        try:
            u = usuario_sugerido(nombres, apellidos, ocupados)
        except DatoInvalido:
            return
        assert u.valor not in ocupados
        ocupados.add(u.valor)
        vistos.append(u.valor)
    assert len(set(vistos)) == 6


# --- soporte (RF-39, CA-18, S-12) ---------------------------------------------------------------

PDF = b"%PDF-1.7\n" + b"x" * 100


def test_soporte_valido() -> None:
    v = validar_soporte(PDF, "C:\\tmp\\Acta de inicio.PDF")
    assert v.nombre.valor == "Acta de inicio.PDF"
    assert v.tamano == len(PDF)
    assert len(v.sha256.valor) == 64


def test_soporte_exactamente_20_MiB_se_acepta_y_un_byte_mas_se_rechaza_S_12() -> None:
    base = b"%PDF-" + b"0" * (MAX_SOPORTE_BYTES - 5)
    assert validar_soporte(base, "a.pdf").tamano == MAX_SOPORTE_BYTES
    with pytest.raises(SoporteInvalido, match="20 MB"):
        validar_soporte(base + b"0", "a.pdf")


@pytest.mark.parametrize(
    ("contenido", "nombre", "motivo"),
    [
        (b"MZ\x90\x00" + b"x" * 50, "falso.pdf", "no es un PDF"),  # ejecutable renombrado
        (b"%PD", "a.pdf", "no es un PDF"),
        (b" %PDF-1.4", "a.pdf", "no es un PDF"),
        (b"", "a.pdf", "vacio"),
        (PDF, "a.exe", "extension"),
        (PDF, "a.pdf.exe", "extension"),
        (PDF, "pdf", "extension"),
        (PDF, "", "extension"),  # nombre vacio -> 'soporte.pdf' seria un nombre inventado
    ],
)
def test_soporte_invalido_CA_18(contenido: bytes, nombre: str, motivo: str) -> None:
    if nombre == "":
        # el saneado entrega un nombre por defecto con extension .pdf: el contenido decide
        assert validar_soporte(contenido, nombre).nombre.valor == "soporte.pdf"
        return
    with pytest.raises(SoporteInvalido, match=motivo):
        validar_soporte(contenido, nombre)


def test_ciclo_de_vida_del_soporte_RF_40() -> None:
    v = validar_soporte(PDF, "a.pdf")
    s = Soporte.pendiente(SolicitudId.de(2026, 1), v, "alea-123")
    assert s.estado is EstadoDeSoporte.PENDIENTE
    assert s.nombre_almacenado == "alea-123"
    subido = s.subido("DOC-9")
    assert (subido.estado, subido.id_documento_glpi) == (EstadoDeSoporte.SUBIDO, "DOC-9")
    with pytest.raises(OperacionNoPermitida):
        subido.subido("DOC-10")
    with pytest.raises(OperacionNoPermitida):
        subido.descartado()
    assert s.descartado().estado is EstadoDeSoporte.DESCARTADO
    with pytest.raises(OperacionNoPermitida):
        s.descartado().subido("x")
    assert s.estado is EstadoDeSoporte.PENDIENTE  # inmutable


# --- colaborador ------------------------------------------------------------------------------


def test_colaborador_por_ingresar_S_06() -> None:
    c = Colaborador.por_ingresar("c1", datos_ingreso(), date(2026, 11, 2), Usuario("maria.gomez"))
    assert c.estado is EstadoColaborador.POR_INGRESAR
    assert c.usuario == Usuario("maria.gomez")
    assert c.nombre_completo == "María José Gómez Ramírez"
    with pytest.raises(DatoInvalido):
        Colaborador.por_ingresar(" ", datos_ingreso(), date(2026, 11, 2), Usuario("a.b"))


_E = EstadoColaborador


@pytest.mark.parametrize("desde", list(_E))
@pytest.mark.parametrize("hacia", list(_E))
def test_transiciones_del_colaborador_S_07(
    desde: EstadoColaborador, hacia: EstadoColaborador
) -> None:
    from dataclasses import replace

    c = replace(colaborador(), estado=desde)
    if desde == hacia:
        assert c.con_estado(hacia) is c
    elif hacia in TRANSICIONES_DE_COLABORADOR[desde]:
        assert c.con_estado(hacia).estado is hacia
    else:
        with pytest.raises(OperacionNoPermitida):
            c.con_estado(hacia)


def test_retirado_es_absorbente() -> None:
    assert TRANSICIONES_DE_COLABORADOR[_E.RETIRADO] == frozenset()


def test_cambios_de_departamento_sede_y_glpi_S_20() -> None:
    c = colaborador()
    n = c.con_cambio_de_departamento("TI", "Dev", "jefe-9")
    assert (n.departamento, n.cargo, n.jefe_id) == ("TI", "Dev", "jefe-9")
    assert c.con_cambio_de_sede("Cali").sede == "Cali"
    assert c.con_usuario_glpi("77").id_usuario_glpi == "77"
    with pytest.raises(DatoInvalido):
        c.con_cambio_de_departamento(" ", "x", None)
    with pytest.raises(DatoInvalido):
        c.con_cambio_de_departamento("x", " ", None)
    with pytest.raises(DatoInvalido):
        c.con_cambio_de_sede(" ")
    with pytest.raises(DatoInvalido):
        c.con_usuario_glpi(" ")
