"""Casos y serializacion de la prueba dorada de tickets (ver test_tickets_golden.py).

Ejecutar `python -m tests.dominio.golden_tickets` REGENERA `golden_tickets.json`. Hacerlo solo
cuando un cambio de texto este aprobado: el diff del JSON es lo que el equipo revisa.
"""

import json
from pathlib import Path

from jml.dominio.tickets import TicketDeCola, generar_tickets
from jml.dominio.tipos import Subtipo, TipoDeVinculacion, TipoEvento
from jml.dominio.valores import CalendarioHabil
from tests.fabricas import AHORA, Caso, caso

RUTA = Path(__file__).with_name("golden_tickets.json")
ING, VAC, CDP, CSU, RET, EMG = TipoEvento
CASOS: dict[str, dict[str, object]] = {
    "ING empleado con equipo": dict(tipo=ING),
    "ING contratista con equipo": dict(tipo=ING, vinculacion=TipoDeVinculacion.CONTRATISTA),
    "ING sin equipo": dict(tipo=ING, requiere_equipo=False),
    "ING en Operaciones, Medellin": dict(tipo=ING, departamento="Operaciones", sede="Medellín"),
    "VAC": dict(tipo=VAC),
    "CDP Finanzas->TI": dict(tipo=CDP, departamento="Finanzas", destino="TI"),
    "CDP Operaciones->Finanzas": dict(tipo=CDP, departamento="Operaciones", destino="Finanzas"),
    "CDP Comercial->Operaciones": dict(tipo=CDP, departamento="Comercial", destino="Operaciones"),
    "CDP sin diferencia": dict(tipo=CDP, departamento="Finanzas", destino="Finanzas"),
    "CSU con traslado": dict(tipo=CSU, traslada_equipo=True),
    "CSU sin traslado": dict(tipo=CSU, traslada_equipo=False),
    "RET renuncia": dict(tipo=RET, subtipo=Subtipo.RENUNCIA),
    "RET fin de contrato": dict(tipo=RET, subtipo=Subtipo.FIN_DE_CONTRATO, departamento="TI"),
    "EMG despido": dict(tipo=EMG, subtipo=Subtipo.DESPIDO_CON_JUSTA_CAUSA),
    "EMG fuga": dict(tipo=EMG, subtipo=Subtipo.FUGA_DETECTADA, departamento="Gerencia"),
}


def generar(c: Caso) -> tuple[TicketDeCola, ...]:
    return generar_tickets(c.solicitud, c.actual, c.nuevo, c.colaborador, CalendarioHabil(), AHORA)


def serializar(t: TicketDeCola) -> dict[str, object]:
    return {
        "cola": t.cola.value,
        "clase": t.clase.value,
        "accion": t.accion.value,
        "categoria": t.categoria,
        "prioridad": t.prioridad.value,
        "titulo": t.titulo,
        "estado_inicial": t.estado_inicial.value,
        "emitido_en": t.emitido_en.isoformat(),
        "vence_en": t.vence_en.isoformat(),
        "activo_desde": t.activo_desde.isoformat(),
        "clave": t.clave_de_idempotencia,
        "adjunta_soporte": t.adjunta_soporte,
        "ordinal": t.ordinal,
        "datos": {
            "colaborador": t.datos.colaborador,
            "usuario": t.datos.usuario,
            "perfil": t.datos.perfil,
            "fecha_efectiva": t.datos.fecha_efectiva.isoformat(),
            "solicitud": t.datos.solicitud,
        },
        "lista": list(t.lista_de_verificacion),
        "texto": t.como_texto(),
    }


def todo() -> dict[str, list[dict[str, object]]]:
    return {
        nombre: [serializar(t) for t in generar(caso(**params))]  # type: ignore[arg-type]  # parametros nombrados
        for nombre, params in CASOS.items()
    }


if __name__ == "__main__":
    RUTA.write_text(json.dumps(todo(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"escrito {RUTA}")
