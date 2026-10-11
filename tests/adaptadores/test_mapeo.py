"""Mapeo modelo <-> entidad (2.3): ida y vuelta sin perdida, y datos corruptos con error tipado."""

from dataclasses import replace

import pytest

from jml.adaptadores.salida.persistencia import mapeo as mp
from jml.adaptadores.salida.persistencia import models as m
from jml.dominio.errores import DatoInvalido
from jml.dominio.tickets import Observacion, TicketSeguido
from jml.dominio.tipos import EstadoDeTicket, Subtipo, TipoDeVinculacion, TipoEvento
from tests.dominio.golden_tickets import CASOS, generar
from tests.fabricas import AHORA, caso

TIPOS = [
    (TipoEvento.ING, None, {}),
    (
        TipoEvento.ING,
        None,
        {"vinculacion": TipoDeVinculacion.CONTRATISTA, "requiere_equipo": False},
    ),
    (TipoEvento.VAC, None, {}),
    (TipoEvento.CDP, None, {}),
    (TipoEvento.CSU, None, {"traslada_equipo": True}),
    (TipoEvento.RET, Subtipo.RENUNCIA, {}),
    (TipoEvento.EMG, Subtipo.FUGA_DETECTADA, {}),
]


@pytest.mark.parametrize(("tipo", "sub", "opciones"), TIPOS)
def test_los_datos_de_cada_evento_van_y_vuelven(
    tipo: TipoEvento, sub: Subtipo | None, opciones: dict[str, object]
) -> None:
    datos = caso(tipo, sub, **opciones).solicitud.datos  # type: ignore[arg-type]  # opciones nombradas
    assert mp.datos_de_json(tipo, mp.datos_a_json(datos)) == datos


@pytest.mark.parametrize(("tipo", "sub", "opciones"), TIPOS)
def test_la_solicitud_va_y_vuelve_con_su_restringido(
    tipo: TipoEvento, sub: Subtipo | None, opciones: dict[str, object]
) -> None:
    s = replace(caso(tipo, sub, **opciones).solicitud, tickets=("k1", "k2"), para_revision=True)  # type: ignore[arg-type]
    fila = m.Solicitud(id=s.id.valor, **mp.solicitud_a_campos(s))
    restringido = None if s.restringido is None else s.restringido.revelar()
    assert mp.solicitud_de_modelo(fila, restringido) == s


def test_el_colaborador_va_y_vuelve() -> None:
    c = caso(TipoEvento.RET, Subtipo.RENUNCIA).colaborador
    for variante in (c, replace(c, usuario=None, jefe_id=None, id_usuario_glpi="u-7")):
        fila = m.Colaborador(id=variante.id, **mp.colaborador_a_campos(variante))
        assert mp.colaborador_de_modelo(fila) == variante


@pytest.mark.parametrize("nombre", sorted(CASOS))
def test_cada_ticket_de_la_prueba_dorada_va_y_vuelve(nombre: str) -> None:
    for t in generar(caso(**CASOS[nombre])):  # type: ignore[arg-type]  # parametros nombrados
        assert mp.ticket_de_json(mp.ticket_a_json(t)) == t
        for seguido in (
            TicketSeguido(t),
            TicketSeguido(
                t, "G-1", Observacion(EstadoDeTicket.RESUELTO, True, 2, AHORA), reabierto=True
            ),
        ):
            fila = m.Ticket(clave=t.clave_de_idempotencia, **mp.ticket_a_campos(seguido))
            assert mp.seguido_de_modelo(fila) == seguido


@pytest.mark.parametrize(
    ("llamada", "que"),
    [
        (lambda: mp.datos_de_json(TipoEvento.VAC, {"fecha_regreso": None}), "fecha_regreso"),
        (
            lambda: mp.solicitud_de_modelo(
                m.Solicitud(id="SOL-2026-000001", tipo="VAC", datos=[1]), None
            ),
            "solicitud.datos",
        ),
        (
            lambda: mp.perfil_de_modelo(
                m.PerfilDeAcceso(departamento="TI", sede="Cali", grupos_ad="x")
            ),
            "lista",
        ),
        (lambda: mp.ticket_de_json({"datos": "x"}), "ticket.datos"),
        (lambda: mp.ticket_de_json({"datos": {"fecha_efectiva": None}}), "ticket.fecha_efectiva"),
        (
            lambda: mp.ticket_de_json({"datos": {"fecha_efectiva": "2026-01-01"}, "ordinal": "1"}),
            "ticket.ordinal",
        ),
        (lambda: mp.seguido_de_modelo(m.Ticket(definicion="x")), "ticket.definicion"),
    ],
)
def test_un_dato_corrupto_en_la_base_se_rechaza_con_error_tipado(llamada: object, que: str) -> None:
    with pytest.raises(DatoInvalido) as e:
        llamada()  # type: ignore[operator]  # lambdas de prueba
    assert e.value.campo == "persistencia"
    assert que in e.value.motivo
