"""Consultas de lectura calculadas en Python simple y claro: el ORACULO de la consulta SQL.

Cada indicador (a) a (h) del SRS RF-30 esta escrito para que cualquiera lo lea y lo compare con
la expectativa hecha a mano (CA-15). Si la consulta SQL de la Fase 4 difiere de esto, el error
esta en el SQL. Ninguna consulta toca el motivo ni la descripcion (RD-05): sus DTOs no los tienen.
"""

from collections import Counter
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from jml.aplicacion.dtos import (
    FichaDeColaborador,
    FilaCuentas,
    FilaDeColaborador,
    FilaExposicion,
    FilaIncompleto,
    FilaPendientes,
    FilaProgramado,
    FilaSolicitudesDelMes,
    FilaVencidos,
    FiltroDeCuentas,
    IndicadorDeEquipos,
    Indicadores,
    PaginaDeCuentas,
    ResumenDeCuenta,
    ResumenDeSolicitud,
    ResumenDeTicket,
)
from jml.dominio.catalogo import ColaboradorId
from jml.dominio.cuentas import Cuenta
from jml.dominio.resolucion import cierre_incompleto, ticket_resuelto
from jml.dominio.tickets import TicketSeguido
from jml.dominio.tipos import (
    AccionDeTicket,
    ClaseTicket,
    Cola,
    EstadoColaborador,
    EstadoDeCuenta,
    EstadoDeTicket,
    EstadoSolicitud,
    Prioridad,
    SistemaDeCuenta,
    TipoEvento,
)
from jml.dominio.valores import SolicitudId, ascii_minuscula, hoy_en_bogota

if TYPE_CHECKING:
    from tests.dobles.memoria import Almacen

SOLICITUDES_EN_CURSO = {
    EstadoSolicitud.APROBADA,
    EstadoSolicitud.EN_EJECUCION,
    EstadoSolicitud.ERROR,
}


def _sin_resolver(t: TicketSeguido) -> bool:
    """Para el tablero, 'pendiente' es todo ticket cuyo estado en GLPI aun no es Resuelto."""
    return t.observacion is None or t.observacion.estado < EstadoDeTicket.RESUELTO


def indicadores(a: "Almacen", ahora: datetime) -> Indicadores:
    creados = [t for t in a.tickets.values() if t.id_externo is not None]

    # (a) pendientes por cola y prioridad, sin contar los programados que aun no llegan
    pend = Counter(
        (t.ticket.cola, t.ticket.prioridad)
        for t in creados
        if _sin_resolver(t) and t.ticket.activo_desde <= ahora
    )
    pendientes = tuple(
        FilaPendientes(cola, prioridad, cantidad)
        for (cola, prioridad), cantidad in sorted(
            pend.items(),
            key=lambda kv: (list(Cola).index(kv[0][0]), list(Prioridad).index(kv[0][1])),
        )
    )

    # (b) vencidos segun SLA: sin resolver y con fecha de vencimiento ya pasada
    venc = Counter(t.ticket.cola for t in creados if _sin_resolver(t) and t.ticket.vence_en < ahora)
    vencidos = tuple(
        FilaVencidos(cola, venc[cola]) for cola in sorted(venc, key=lambda c: list(Cola).index(c))
    )

    # (c) retiros y emergencias con tickets de baja abiertos y sus horas de exposicion
    exposicion: list[FilaExposicion] = []
    for s in a.solicitudes.values():
        if s.tipo not in (TipoEvento.RET, TipoEvento.EMG) or s.estado not in SOLICITUDES_EN_CURSO:
            continue
        abiertos = [
            t
            for t in a.tickets.values()
            if t.ticket.solicitud_id == s.id.valor
            and t.ticket.accion is AccionDeTicket.BAJA
            and not ticket_resuelto(t)
        ]
        if not abiertos:
            continue
        # EMG: la exposicion corre desde la emision; RET, desde el final del ultimo dia laborado.
        desde = min(
            t.ticket.emitido_en if s.tipo is TipoEvento.EMG else t.ticket.vence_en for t in abiertos
        )
        horas = max(0, int((ahora - desde).total_seconds() // 3600))
        exposicion.append(
            FilaExposicion(s.id, s.tipo, s.colaborador_id, len(abiertos), horas, desde)
        )
    exposicion.sort(key=lambda f: (-f.horas_de_exposicion, f.solicitud_id.valor))

    # (d) solicitudes por estado y tipo en el mes actual (mes calendario de Bogota)
    hoy = hoy_en_bogota(ahora)
    mes = Counter(
        (s.estado, s.tipo)
        for s in a.solicitudes.values()
        if (hoy_en_bogota(s.creada_en).year, hoy_en_bogota(s.creada_en).month)
        == (hoy.year, hoy.month)
    )
    del_mes = tuple(
        FilaSolicitudesDelMes(estado, tipo, cantidad)
        for (estado, tipo), cantidad in sorted(
            mes.items(),
            key=lambda kv: (
                list(EstadoSolicitud).index(kv[0][0]),
                list(TipoEvento).index(kv[0][1]),
            ),
        )
    )

    # (e) cuentas por estado y sistema
    cu = Counter((c.sistema, c.estado) for c in a.cuentas.values())
    cuentas = tuple(
        FilaCuentas(sistema, estado, cantidad)
        for (sistema, estado), cantidad in sorted(
            cu.items(),
            key=lambda kv: (
                list(SistemaDeCuenta).index(kv[0][0]),
                list(EstadoDeCuenta).index(kv[0][1]),
            ),
        )
    )

    # (f) equipos asignados y equipos pendientes de devolucion (S-27)
    en_baja = {
        s.colaborador_id
        for s in a.solicitudes.values()
        if s.tipo in (TipoEvento.RET, TipoEvento.EMG) and s.estado in SOLICITUDES_EN_CURSO
    }
    asignados = sum(len(v) for v in a.activos.values())
    pendientes_devolucion = sum(
        len(v)
        for colaborador_id, v in a.activos.items()
        if colaborador_id in en_baja
        or (
            colaborador_id in a.colaboradores
            and a.colaboradores[colaborador_id].estado is EstadoColaborador.RETIRADO
        )
    )

    # (g) tickets programados para los proximos 7 dias
    limite = ahora + timedelta(days=7)
    programados = tuple(
        FilaProgramado(
            t.ticket.clave_de_idempotencia,
            t.ticket.cola,
            _id(a, t),
            t.ticket.activo_desde,
        )
        for t in sorted(
            creados, key=lambda t: (t.ticket.activo_desde, t.ticket.clave_de_idempotencia)
        )
        if t.ticket.clase is not ClaseTicket.CIERRE_INMEDIATO
        and _sin_resolver(t)
        and ahora < t.ticket.activo_desde <= limite
    )

    # (h) tickets con cierre incompleto o reabiertos
    incompletos = tuple(
        FilaIncompleto(
            t.ticket.clave_de_idempotencia,
            t.ticket.cola,
            _id(a, t),
            "cierre_incompleto" if cierre_incompleto(t) else "reabierto",
        )
        for t in sorted(creados, key=lambda t: t.ticket.clave_de_idempotencia)
        if cierre_incompleto(t) or t.reabierto
    )

    return Indicadores(
        generados_en=ahora,
        ultima_sincronizacion=a.sincronizaciones[-1] if a.sincronizaciones else None,
        cola_resaltada=None,
        pendientes=pendientes,
        vencidos=vencidos,
        exposicion=tuple(exposicion),
        solicitudes_del_mes=del_mes,
        cuentas=cuentas,
        equipos=IndicadorDeEquipos(asignados, pendientes_devolucion),
        programados=programados,
        incompletos=incompletos,
    )


def _id(a: "Almacen", t: TicketSeguido) -> SolicitudId:
    return a.solicitudes[t.ticket.solicitud_id].id


def _resumen_cuenta(c: Cuenta) -> ResumenDeCuenta:
    return ResumenDeCuenta(c.sistema, c.estado, c.marca, c.desde, c.ticket_origen)


def _cuentas_de(a: "Almacen", colaborador_id: ColaboradorId) -> tuple[ResumenDeCuenta, ...]:
    propias = [c for (cid, _), c in a.cuentas.items() if cid == colaborador_id]
    propias.sort(key=lambda c: list(SistemaDeCuenta).index(c.sistema))
    return tuple(_resumen_cuenta(c) for c in propias)


def buscar_cuentas(a: "Almacen", f: FiltroDeCuentas) -> PaginaDeCuentas:
    def coincide(colaborador_id: ColaboradorId) -> bool:
        c = a.colaboradores[colaborador_id]
        if f.nombre is not None:
            texto = ascii_minuscula(c.nombre_completo)
            if not all(p in texto for p in ascii_minuscula(f.nombre).split()):
                return False
        if f.documento is not None and c.documento.valor != f.documento.strip().upper():
            return False
        if f.usuario is not None and (
            c.usuario is None or ascii_minuscula(f.usuario) not in c.usuario.valor
        ):
            return False
        if f.departamento is not None and ascii_minuscula(c.departamento) != ascii_minuscula(
            f.departamento
        ):
            return False
        if f.sede is not None and ascii_minuscula(c.sede) != ascii_minuscula(f.sede):
            return False
        if f.sistema is not None or f.estado_de_cuenta is not None:
            return any(
                (f.sistema is None or cu.sistema is f.sistema)
                and (f.estado_de_cuenta is None or cu.estado is f.estado_de_cuenta)
                for (cid, _), cu in a.cuentas.items()
                if cid == colaborador_id
            )
        return True

    ordenados = sorted(
        (c for c in a.colaboradores.values() if coincide(c.id)),
        key=lambda c: (ascii_minuscula(c.apellidos), ascii_minuscula(c.nombres), c.id),
    )
    inicio = (f.pagina - 1) * f.tamano
    pagina = ordenados[inicio : inicio + f.tamano]
    filas = tuple(
        FilaDeColaborador(
            c.id,
            c.nombre_completo,
            c.documento.valor,
            c.usuario.valor if c.usuario else None,
            c.departamento,
            c.sede,
            c.estado,
            _cuentas_de(a, c.id),
        )
        for c in pagina
    )
    return PaginaDeCuentas(filas, len(ordenados), f.pagina, f.tamano)


def ficha(a: "Almacen", colaborador_id: ColaboradorId) -> FichaDeColaborador | None:
    c = a.colaboradores.get(colaborador_id)
    if c is None:
        return None
    solicitudes = sorted(
        (s for s in a.solicitudes.values() if s.colaborador_id == colaborador_id),
        key=lambda s: s.id.valor,
    )
    ids = {s.id.valor for s in solicitudes}
    tickets = sorted(
        (t for t in a.tickets.values() if t.ticket.solicitud_id in ids),
        key=lambda t: t.ticket.clave_de_idempotencia,
    )
    return FichaDeColaborador(
        colaborador_id=c.id,
        nombre_completo=c.nombre_completo,
        documento=c.documento.valor,
        vinculacion=c.vinculacion,
        departamento=c.departamento,
        cargo=c.cargo,
        sede=c.sede,
        jefe_id=c.jefe_id,
        estado=c.estado,
        usuario=c.usuario.valor if c.usuario else None,
        fecha_ingreso=c.fecha_ingreso,
        fecha_fin=c.fecha_fin,
        cuentas=_cuentas_de(a, c.id),
        equipos=tuple(a.activos.get(c.id, ())),
        licencias=tuple(a.licencias.get(c.id, ())),
        solicitudes=tuple(
            ResumenDeSolicitud(s.id, s.tipo, s.estado, s.fecha_efectiva, s.creada_en)
            for s in solicitudes
        ),
        tickets=tuple(
            ResumenDeTicket(
                t.ticket.clave_de_idempotencia,
                a.solicitudes[t.ticket.solicitud_id].id,
                t.ticket.cola,
                t.ticket.clase,
                t.ticket.accion,
                t.id_externo,
                t.observacion.estado if t.observacion else None,
                bool(t.observacion and t.observacion.tiene_solucion),
                t.reabierto,
                cierre_incompleto(t),
            )
            for t in tickets
        ),
    )
