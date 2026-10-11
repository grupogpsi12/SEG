"""Consultas de lectura del dashboard, la busqueda y la ficha (RF-29 a RF-33) sobre el ORM.

Los indicadores agregan en la base (COUNT/MIN con GROUP BY) y se comparan con el oraculo en
memoria (CA-15). La busqueda filtra sin tildes en Python: con 300 colaboradores (SUP-06) cabe en
memoria y evita depender de la extension `unaccent` de PostgreSQL.
"""

from collections.abc import Iterable
from datetime import datetime, time, timedelta

from django.db.models import Count, Min, Q

from jml.adaptadores.salida.persistencia import mapeo as mp
from jml.adaptadores.salida.persistencia import models as m
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
    ResultadoDeSincronizacion,
    ResumenDeCuenta,
    ResumenDeSolicitud,
    ResumenDeTicket,
)
from jml.dominio.activos import ActivoAsignado, LicenciaAsignada
from jml.dominio.catalogo import ColaboradorId
from jml.dominio.colaborador import Colaborador
from jml.dominio.resolucion import cierre_incompleto
from jml.dominio.tipos import (
    AccionDeTicket,
    ClaseTicket,
    Cola,
    EstadoColaborador,
    EstadoDeCuenta,
    EstadoDeTicket,
    EstadoSolicitud,
    MarcaDeCuenta,
    Prioridad,
    SistemaDeCuenta,
    TipoEvento,
)
from jml.dominio.valores import BOGOTA, SolicitudId, ascii_minuscula, hoy_en_bogota

_RESUELTO = int(EstadoDeTicket.RESUELTO)
_EN_CURSO = [
    EstadoSolicitud.APROBADA.value,
    EstadoSolicitud.EN_EJECUCION.value,
    EstadoSolicitud.ERROR.value,
]
_SIN_RESOLVER = Q(estado_glpi__isnull=True) | Q(estado_glpi__lt=_RESUELTO)
# RF-24: resuelto = estado >= Resuelto + solucion (+ acta en Inventario)
_RESUELTO_DE_VERDAD = Q(estado_glpi__gte=_RESUELTO, tiene_solucion=True) & (
    ~Q(cola=Cola.INVENTARIO.value) | Q(documentos__gte=1)
)


def _orden(enum: Iterable[object], valor: object) -> int:
    return list(enum).index(valor)


def sincronizacion_de_modelo(f: m.Sincronizacion) -> ResultadoDeSincronizacion:
    return ResultadoDeSincronizacion(f.inicio, f.fin, f.resultado, f.tickets_leidos, f.errores)


def _limites_del_mes(ahora: datetime) -> tuple[datetime, datetime]:
    """Mes calendario de Bogota, como intervalo semiabierto en UTC (S-02)."""
    hoy = hoy_en_bogota(ahora)
    inicio = hoy.replace(day=1)
    siguiente = (inicio + timedelta(days=32)).replace(day=1)
    return datetime.combine(inicio, time(), BOGOTA), datetime.combine(siguiente, time(), BOGOTA)


def indicadores(ahora: datetime) -> Indicadores:
    creados = m.Ticket.objects.exclude(id_externo=None)

    # (a) pendientes por cola y prioridad, sin los programados que aun no llegan
    a = creados.filter(_SIN_RESOLVER, activo_desde__lte=ahora).values("cola", "prioridad")
    pendientes = sorted(
        (
            FilaPendientes(Cola(f["cola"]), Prioridad(f["prioridad"]), f["n"])
            for f in a.annotate(n=Count("clave"))
        ),
        key=lambda f: (_orden(Cola, f.cola), _orden(Prioridad, f.prioridad)),
    )

    # (b) vencidos segun SLA
    b = creados.filter(_SIN_RESOLVER, vence_en__lt=ahora).values("cola").annotate(n=Count("clave"))
    vencidos = sorted(
        (FilaVencidos(Cola(f["cola"]), f["n"]) for f in b), key=lambda f: _orden(Cola, f.cola)
    )

    # (c) exposicion: EMG desde la emision; RET desde el final del ultimo dia laborado
    exposicion: list[FilaExposicion] = []
    for tipo, campo in ((TipoEvento.EMG, "emitido_en"), (TipoEvento.RET, "vence_en")):
        filas = (
            m.Ticket.objects.filter(
                accion=AccionDeTicket.BAJA.value,
                solicitud__tipo=tipo.value,
                solicitud__estado__in=_EN_CURSO,
            )
            .exclude(_RESUELTO_DE_VERDAD)
            .values("solicitud_id", "solicitud__colaborador_id")
            .annotate(n=Count("clave"), desde=Min(campo))
        )
        for f in filas:
            horas = max(0, int((ahora - f["desde"]).total_seconds() // 3600))
            exposicion.append(
                FilaExposicion(
                    SolicitudId(f["solicitud_id"]),
                    tipo,
                    f["solicitud__colaborador_id"],
                    f["n"],
                    horas,
                    f["desde"],
                )
            )
    exposicion.sort(key=lambda f: (-f.horas_de_exposicion, f.solicitud_id.valor))

    # (d) solicitudes por estado y tipo en el mes actual (Bogota)
    inicio, fin = _limites_del_mes(ahora)
    d = (
        m.Solicitud.objects.filter(creada_en__gte=inicio, creada_en__lt=fin)
        .values("estado", "tipo")
        .annotate(n=Count("id"))
    )
    del_mes = sorted(
        (
            FilaSolicitudesDelMes(EstadoSolicitud(f["estado"]), TipoEvento(f["tipo"]), f["n"])
            for f in d
        ),
        key=lambda f: (_orden(EstadoSolicitud, f.estado), _orden(TipoEvento, f.tipo)),
    )

    # (e) cuentas por estado y sistema
    e = m.Cuenta.objects.values("sistema", "estado").annotate(n=Count("id"))
    cuentas = sorted(
        (
            FilaCuentas(SistemaDeCuenta(f["sistema"]), EstadoDeCuenta(f["estado"]), f["n"])
            for f in e
        ),
        key=lambda f: (_orden(SistemaDeCuenta, f.sistema), _orden(EstadoDeCuenta, f.estado)),
    )

    # (f) equipos asignados y pendientes de devolucion (S-27)
    en_baja = m.Solicitud.objects.filter(
        tipo__in=[TipoEvento.RET.value, TipoEvento.EMG.value], estado__in=_EN_CURSO
    ).values("colaborador_id")
    retirados = m.Colaborador.objects.filter(estado=EstadoColaborador.RETIRADO.value).values("id")
    equipos = IndicadorDeEquipos(
        m.ActivoAsignado.objects.count(),
        m.ActivoAsignado.objects.filter(
            Q(colaborador_id__in=en_baja) | Q(colaborador_id__in=retirados)
        ).count(),
    )

    # (g) programados para los proximos 7 dias
    g = (
        creados.filter(
            _SIN_RESOLVER, activo_desde__gt=ahora, activo_desde__lte=ahora + timedelta(days=7)
        )
        .exclude(clase=ClaseTicket.CIERRE_INMEDIATO.value)
        .order_by("activo_desde", "clave")
    )
    programados = tuple(
        FilaProgramado(f.clave, Cola(f.cola), SolicitudId(f.solicitud_id), f.activo_desde)
        for f in g
    )

    # (h) cierre incompleto o reabiertos
    h = creados.filter(Q(estado_glpi__gte=_RESUELTO) | Q(reabierto=True)).order_by("clave")
    incompletos: list[FilaIncompleto] = []
    for t in h:
        seguido = mp.seguido_de_modelo(t)
        if cierre_incompleto(seguido):
            incompletos.append(
                FilaIncompleto(
                    t.clave, Cola(t.cola), SolicitudId(t.solicitud_id), "cierre_incompleto"
                )
            )
        elif t.reabierto:
            incompletos.append(
                FilaIncompleto(t.clave, Cola(t.cola), SolicitudId(t.solicitud_id), "reabierto")
            )

    ultima = m.Sincronizacion.objects.order_by("-id").first()
    return Indicadores(
        generados_en=ahora,
        ultima_sincronizacion=None if ultima is None else sincronizacion_de_modelo(ultima),
        cola_resaltada=None,
        pendientes=tuple(pendientes),
        vencidos=tuple(vencidos),
        exposicion=tuple(exposicion),
        solicitudes_del_mes=tuple(del_mes),
        cuentas=tuple(cuentas),
        equipos=equipos,
        programados=programados,
        incompletos=tuple(incompletos),
    )


# --- busqueda y ficha ------------------------------------------------------------------------


def _resumenes(colaborador_id: ColaboradorId) -> tuple[ResumenDeCuenta, ...]:
    filas = sorted(
        m.Cuenta.objects.filter(colaborador_id=colaborador_id),
        key=lambda f: _orden(SistemaDeCuenta, SistemaDeCuenta(f.sistema)),
    )
    return tuple(
        ResumenDeCuenta(
            SistemaDeCuenta(f.sistema),
            EstadoDeCuenta(f.estado),
            None if f.marca is None else MarcaDeCuenta(f.marca),
            f.desde,
            f.ticket_origen,
        )
        for f in filas
    )


def _coincide(c: Colaborador, f: FiltroDeCuentas) -> bool:
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
        cuentas = m.Cuenta.objects.filter(colaborador_id=c.id)
        if f.sistema is not None:
            cuentas = cuentas.filter(sistema=f.sistema.value)
        if f.estado_de_cuenta is not None:
            cuentas = cuentas.filter(estado=f.estado_de_cuenta.value)
        return cuentas.exists()
    return True


def buscar_cuentas(f: FiltroDeCuentas) -> PaginaDeCuentas:
    colaboradores = [mp.colaborador_de_modelo(fila) for fila in m.Colaborador.objects.all()]
    ordenados = sorted(
        (c for c in colaboradores if _coincide(c, f)),
        key=lambda c: (ascii_minuscula(c.apellidos), ascii_minuscula(c.nombres), c.id),
    )
    inicio = (f.pagina - 1) * f.tamano
    filas = tuple(
        FilaDeColaborador(
            c.id,
            c.nombre_completo,
            c.documento.valor,
            None if c.usuario is None else c.usuario.valor,
            c.departamento,
            c.sede,
            c.estado,
            _resumenes(c.id),
        )
        for c in ordenados[inicio : inicio + f.tamano]
    )
    return PaginaDeCuentas(filas, len(ordenados), f.pagina, f.tamano)


def ficha(colaborador_id: ColaboradorId) -> FichaDeColaborador | None:
    fila = m.Colaborador.objects.filter(pk=colaborador_id).first()
    if fila is None:
        return None
    c = mp.colaborador_de_modelo(fila)
    solicitudes = m.Solicitud.objects.filter(colaborador_id=colaborador_id).order_by("id")
    tickets = m.Ticket.objects.filter(solicitud__colaborador_id=colaborador_id).order_by("clave")
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
        usuario=None if c.usuario is None else c.usuario.valor,
        fecha_ingreso=c.fecha_ingreso,
        fecha_fin=c.fecha_fin,
        cuentas=_resumenes(c.id),
        equipos=tuple(
            ActivoAsignado(a.id_glpi, a.tipo, a.serie, a.modelo, a.asignado_desde, a.tiene_acta)
            for a in m.ActivoAsignado.objects.filter(colaborador_id=c.id).order_by("id")
        ),
        licencias=tuple(
            LicenciaAsignada(lic.id_glpi, lic.software, lic.licencia)
            for lic in m.LicenciaAsignada.objects.filter(colaborador_id=c.id).order_by("id")
        ),
        solicitudes=tuple(
            ResumenDeSolicitud(
                SolicitudId(s.id),
                TipoEvento(s.tipo),
                EstadoSolicitud(s.estado),
                s.fecha_efectiva,
                s.creada_en,
            )
            for s in solicitudes
        ),
        tickets=tuple(
            ResumenDeTicket(
                t.clave,
                SolicitudId(t.solicitud_id),
                Cola(t.cola),
                ClaseTicket(t.clase),
                AccionDeTicket(t.accion),
                t.id_externo,
                None if t.estado_glpi is None else EstadoDeTicket(t.estado_glpi),
                t.tiene_solucion,
                t.reabierto,
                cierre_incompleto(mp.seguido_de_modelo(t)),
            )
            for t in tickets
        ),
    )
