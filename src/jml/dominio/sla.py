"""Vencimientos y prioridades (SRS 4.1, S-01, S-02, S-03, S-16, S-17). Funciones puras.

Convencion de S-02/S-16: "antes de la fecha X" vence a las 00:00 de X (Bogota); "el dia X" o
"el final del dia X" vence a las 23:59:59 de X. Todo se devuelve en UTC.
"""

from datetime import date, datetime, timedelta

from jml.dominio.tipos import Prioridad, TipoEvento
from jml.dominio.valores import CalendarioHabil, a_utc, fin_del_dia, hoy_en_bogota, inicio_del_dia

DIAS_HASTA_ELIMINACION = 90
HORAS_DE_EMERGENCIA = 1


def prioridad_del_evento(tipo: TipoEvento) -> Prioridad:
    """SRS 4.1: RET alta, EMG muy alta, el resto media."""
    if tipo is TipoEvento.EMG:
        return Prioridad.MUY_ALTA
    if tipo is TipoEvento.RET:
        return Prioridad.ALTA
    return Prioridad.MEDIA


def vence_el_ingreso(fecha_ingreso: date) -> datetime:
    """ING: resuelto ANTES de la fecha de ingreso -> 00:00 del dia de ingreso (S-02)."""
    return inicio_del_dia(fecha_ingreso)


def vence_la_suspension(inicio: date) -> datetime:
    """VAC: suspension resuelta el dia de inicio (S-16)."""
    return fin_del_dia(inicio)


def vence_la_reactivacion(regreso: date) -> datetime:
    """VAC: reactivacion el dia de regreso (S-16)."""
    return fin_del_dia(regreso)


def vence_el_cambio(fecha_efectiva: date, calendario: CalendarioHabil) -> datetime:
    """CDP y CSU: 1 dia habil desde la fecha efectiva (S-01)."""
    return fin_del_dia(calendario.sumar_dias_habiles(fecha_efectiva, 1))


def vence_la_baja(ultimo_dia: date) -> datetime:
    """RET: al final del ultimo dia laborado (S-02)."""
    return fin_del_dia(ultimo_dia)


def vence_la_emergencia(ahora: datetime) -> datetime:
    """EMG: 1 hora desde la emision."""
    return a_utc(ahora, "ahora") + timedelta(hours=HORAS_DE_EMERGENCIA)


def fecha_base_de_eliminacion(tipo: TipoEvento, fecha_efectiva: date, ahora: datetime) -> date:
    """S-03: RET cuenta desde el ultimo dia laborado; EMG, desde la emision."""
    return hoy_en_bogota(ahora) if tipo is TipoEvento.EMG else fecha_efectiva


def vence_la_eliminacion(base: date) -> datetime:
    return fin_del_dia(base + timedelta(days=DIAS_HASTA_ELIMINACION))


def activo_desde_la_eliminacion(base: date) -> datetime:
    """Un ticket posterior cuenta como pendiente solo cuando llega su fecha (SRS 4.3)."""
    return inicio_del_dia(base + timedelta(days=DIAS_HASTA_ELIMINACION))
