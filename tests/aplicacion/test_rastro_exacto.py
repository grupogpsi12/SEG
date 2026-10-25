"""F8-02 (B-09): el rastro de auditoria de un ciclo completo se compara EXACTO.

La mutacion de `aplicacion` mostro que las pruebas miraban las ACCIONES de la cadena pero no su
contenido: cambiar `cantidad` por `CANTIDAD` o `id_externo` por `ID_EXTERNO` no rompia nada. La cadena
(invariante 4) es el registro que revisa el Auditor; sus claves y valores son parte del contrato.
Los valores salen de una corrida revisada contra RF-35 y el glosario; son una prueba de caracterizacion:
si cambia el contenido de la cadena, el cambio debe ser deliberado y llevar su ADR.
"""

import json
from datetime import timedelta

from jml.aplicacion.bandeja import (
    ESPERAS_DE_REINTENTO,
    MAX_INTENTOS,
    EntradaDeBandeja,
    EstadoDeEntrada,
)
from jml.aplicacion.casos.auditoria import ExportarAuditoria, VerificarAuditoria
from jml.dominio.tickets import generar_tickets
from jml.dominio.tipos import Subtipo, TipoEvento
from jml.dominio.valores import CalendarioHabil
from tests.fabricas import AHORA, HOY, caso
from tests.mundo import Mundo, cambio_de_departamento, ingreso, retiro

SOL = "SOL-2026-000001"
SHA_DEL_SOPORTE = "151a1dd40bfffaa2cfe244423e54f6d8b865cab8c04f2e83dcc0843d7c78f0f9"


def _rastro(m: Mundo) -> list[tuple[str, str, dict[str, object]]]:
    with m.puerto.unidad_de_trabajo() as u:
        return [(r.accion, r.objeto, dict(r.datos)) for r in u.auditoria.registros()]


def _ciclo(m: Mundo, e):  # type: ignore[no-untyped-def]  # NuevaSolicitud
    r = m.emitir(e)
    m.correr_bandeja_hasta_vaciar()
    m.tecnico_resuelve_todo(r.solicitud_id)
    m.sincronizar()


def _ticket(cola: str, tipo: str, id_externo: str) -> tuple[str, str, dict[str, object]]:
    return ("ticket.creado", f"{SOL}:{cola}:{tipo}:1", {"cola": cola, "id_externo": id_externo})


def _sincronizado(cola: str, tipo: str, documentos: int = 0) -> tuple[str, str, dict[str, object]]:
    return (
        "ticket.estado_sincronizado",
        f"{SOL}:{cola}:{tipo}:1",
        {"estado": "RESUELTO", "tiene_solucion": True, "documentos": documentos},
    )


def test_el_ciclo_de_un_ingreso_deja_este_rastro_exacto() -> None:
    m = Mundo.nuevo()
    _ciclo(m, ingreso())

    def cuenta(sistema: str, cola: str) -> tuple[str, str, dict[str, object]]:
        return (
            "cuenta.estado_derivado",
            "col-n1",
            {
                "sistema": sistema,
                "ticket": f"{SOL}:{cola}:cierre_inmediato:1",
                "anterior": None,
                "nuevo": "activa",
                "marca": None,
            },
        )

    assert _rastro(m) == [
        ("solicitud.registrada", SOL, {"tipo": "ING", "estado": "aprobada", "colaborador_id": "col-n1", "via": "rrhh"}),
        ("solicitud.emitida", SOL, {"tipo": "ING", "estado": "aprobada", "colaborador_id": "col-n1", "justificada": True}),
        ("solicitud.tickets_encolados", SOL, {"cantidad": 4}),
        ("soporte.subido", SOL, {"sha256": SHA_DEL_SOPORTE}),
        _ticket("AD", "cierre_inmediato", "G-00001"),
        _ticket("COMUNICACIONES", "cierre_inmediato", "G-00002"),
        _ticket("INVENTARIO", "cierre_inmediato", "G-00003"),
        _ticket("LICENCIAS", "cierre_inmediato", "G-00004"),
        ("solicitud.en_ejecucion", SOL, {"tipo": "ING", "estado": "en_ejecucion", "colaborador_id": "col-n1"}),
        _sincronizado("AD", "cierre_inmediato"),
        cuenta("AD", "AD"),
        _sincronizado("COMUNICACIONES", "cierre_inmediato"),
        cuenta("Red", "COMUNICACIONES"),
        _sincronizado("INVENTARIO", "cierre_inmediato", documentos=1),
        _sincronizado("LICENCIAS", "cierre_inmediato"),
        cuenta("M365", "LICENCIAS"),
        ("colaborador.estado_derivado", "col-n1", {"anterior": "por_ingresar", "nuevo": "activo"}),
        ("solicitud.cerrada", SOL, {"tipo": "ING", "estado": "cerrada", "colaborador_id": "col-n1"}),
    ]  # fmt: skip


def test_el_ciclo_de_un_retiro_deja_este_rastro_exacto() -> None:
    m = Mundo.nuevo()
    _ciclo(m, retiro())

    def inexistente(sistema: str, cola: str, tipo: str) -> tuple[str, str, dict[str, object]]:
        return (
            "cuenta.inexistente",
            "col-1",
            {"sistema": sistema, "ticket": f"{SOL}:{cola}:{tipo}:1"},
        )

    assert _rastro(m) == [
        ("solicitud.registrada", SOL, {"tipo": "RET", "estado": "aprobada", "colaborador_id": "col-1", "via": "rrhh"}),
        ("solicitud.emitida", SOL, {"tipo": "RET", "estado": "aprobada", "colaborador_id": "col-1", "justificada": True}),
        ("solicitud.tickets_encolados", SOL, {"cantidad": 6}),
        _ticket("AD", "cierre_inmediato", "G-00001"),
        _ticket("AD", "posterior", "G-00002"),
        _ticket("COMUNICACIONES", "cierre_inmediato", "G-00003"),
        _ticket("INVENTARIO", "cierre_inmediato", "G-00004"),
        _ticket("LICENCIAS", "cierre_inmediato", "G-00005"),
        _ticket("LICENCIAS", "posterior", "G-00006"),
        ("solicitud.en_ejecucion", SOL, {"tipo": "RET", "estado": "en_ejecucion", "colaborador_id": "col-1"}),
        _sincronizado("AD", "cierre_inmediato"),
        inexistente("AD", "AD", "cierre_inmediato"),
        _sincronizado("COMUNICACIONES", "cierre_inmediato"),
        inexistente("Red", "COMUNICACIONES", "cierre_inmediato"),
        _sincronizado("INVENTARIO", "cierre_inmediato", documentos=1),
        _sincronizado("LICENCIAS", "cierre_inmediato"),
        inexistente("M365", "LICENCIAS", "cierre_inmediato"),
        _sincronizado("AD", "posterior"),
        inexistente("AD", "AD", "posterior"),
        _sincronizado("LICENCIAS", "posterior"),
        inexistente("M365", "LICENCIAS", "posterior"),
        ("colaborador.estado_derivado", "col-1", {"anterior": "activo", "nuevo": "retirado"}),
        ("solicitud.cerrada", SOL, {"tipo": "RET", "estado": "cerrada", "colaborador_id": "col-1"}),
    ]  # fmt: skip


def test_un_cambio_de_departamento_sin_diferencia_deja_su_rastro_con_el_supuesto() -> None:
    m = Mundo.nuevo()
    m.aprobar("u-rrhh", m.registrar(cambio_de_departamento(destino="Finanzas")).solicitud_id)
    sin_tickets = [r for r in _rastro(m) if r[0] == "solicitud.sin_tickets"]
    assert sin_tickets == [("solicitud.sin_tickets", SOL, {"supuesto": "S-05"})]


def test_verificar_la_cadena_deja_su_resultado_en_la_cadena() -> None:
    m = Mundo.nuevo()
    VerificarAuditoria(m.puerto).ejecutar("u-aud")
    assert _rastro(m)[-1] == (
        "auditoria.verificada",
        "cadena",
        {"valida": True, "primer_afectado": 0},
    )


def test_la_exportacion_es_json_canonico_con_acentos_legibles() -> None:
    m = Mundo.nuevo()
    m.emitir(ingreso(nombres="María José"))
    exp = ExportarAuditoria(m.puerto).ejecutar(HOY)
    for linea in exp.lineas:
        d = json.loads(linea)
        assert list(d) == sorted(d)  # claves ordenadas
        assert linea == json.dumps(d, sort_keys=True, ensure_ascii=False)
    with m.puerto.unidad_de_trabajo() as u:
        ultimo = u.auditoria.registros()[-1]
    assert (exp.ancla_secuencia, exp.ancla_hash) == (ultimo.secuencia, ultimo.hash)
    assert exp.ancla_secuencia > 0


def test_una_cadena_vacia_se_exporta_con_el_ancla_en_cero_y_el_genesis() -> None:
    from jml.dominio.auditoria import HASH_GENESIS

    m = Mundo.nuevo()
    exp = ExportarAuditoria(m.puerto).ejecutar(HOY)
    assert (exp.lineas, exp.ancla_secuencia, exp.ancla_hash) == ((), 0, HASH_GENESIS)


# --- la entrada de la bandeja (RF-18, RF-38) ----------------------------------------------------


def _entrada() -> EntradaDeBandeja:
    c = caso(TipoEvento.RET, Subtipo.RENUNCIA)
    ts = generar_tickets(c.solicitud, c.actual, c.nuevo, c.colaborador, CalendarioHabil(), AHORA)
    return EntradaDeBandeja.nueva(ts[0], AHORA)


def test_una_entrada_nueva_nace_pendiente_sin_intentos_y_lista_ya() -> None:
    e = _entrada()
    assert (e.estado, e.intentos, e.proximo_intento, e.ultimo_error) == (
        EstadoDeEntrada.PENDIENTE,
        0,
        AHORA,
        None,
    )


def test_un_fallo_suma_un_intento_espera_lo_que_toca_y_guarda_el_codigo() -> None:
    e = _entrada().fallo("glpi_caido", AHORA)
    assert (e.estado, e.intentos, e.ultimo_error) == (EstadoDeEntrada.PENDIENTE, 1, "glpi_caido")
    assert e.proximo_intento == AHORA + ESPERAS_DE_REINTENTO[0]
    e2 = e.fallo("glpi_caido", AHORA)
    assert (e2.intentos, e2.proximo_intento) == (2, AHORA + ESPERAS_DE_REINTENTO[1])


def test_el_decimo_fallo_deja_la_entrada_fallida_con_el_codigo_y_el_conteo() -> None:
    e = _entrada()
    for i in range(MAX_INTENTOS - 1):
        e = e.fallo(f"c{i}", AHORA)
        assert e.estado is EstadoDeEntrada.PENDIENTE
    e = e.fallo("ultimo", AHORA)
    assert (e.estado, e.intentos, e.ultimo_error) == (
        EstadoDeEntrada.FALLIDA,
        MAX_INTENTOS,
        "ultimo",
    )


def test_enviar_borra_el_ultimo_error_y_reiniciar_vuelve_a_empezar() -> None:
    fallida = _entrada().fallo("x", AHORA)
    enviada = fallida.enviada()
    assert (enviada.estado, enviada.ultimo_error, enviada.intentos) == (
        EstadoDeEntrada.ENVIADA,
        None,
        1,
    )
    despues = AHORA + timedelta(hours=2)
    r = fallida.reiniciada(despues)
    assert (r.estado, r.intentos, r.proximo_intento, r.ultimo_error) == (
        EstadoDeEntrada.PENDIENTE,
        0,
        despues,
        None,
    )
