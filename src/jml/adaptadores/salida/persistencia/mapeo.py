"""Mapeo explicito entre los modelos de Django y las entidades del dominio (ADR-016).

Todo lo que entra al dominio se reconstruye con sus constructores validados: un dato corrupto
en la base lanza `DatoInvalido` en vez de colarse como una entidad invalida.
"""

from datetime import date, datetime

from jml.adaptadores.salida.persistencia import models as m
from jml.aplicacion.bandeja import EntradaDeBandeja, EstadoDeEntrada
from jml.dominio.catalogo import (
    DatosCambioDepartamento,
    DatosCambioSucursal,
    DatosDelEvento,
    DatosEmergencia,
    DatosIngreso,
    DatosRetiro,
    DatosVacaciones,
)
from jml.dominio.colaborador import Colaborador
from jml.dominio.cuentas import CambioDeCuenta, Cuenta
from jml.dominio.errores import DatoInvalido
from jml.dominio.perfiles import PerfilDeAcceso, RecursoCompartido
from jml.dominio.solicitud import Decision, Solicitud, TipoDeDecision
from jml.dominio.soporte import Soporte
from jml.dominio.tickets import DatosTecnicos, Observacion, TicketDeCola, TicketSeguido
from jml.dominio.tipos import (
    AccionDeTicket,
    ClaseTicket,
    Cola,
    EstadoColaborador,
    EstadoDeCuenta,
    EstadoDeSoporte,
    EstadoDeTicket,
    EstadoInicialDeTicket,
    EstadoSolicitud,
    MarcaDeCuenta,
    PerfilDeRecurso,
    Prioridad,
    SistemaDeCuenta,
    Subtipo,
    TipoDeEquipo,
    TipoDeVinculacion,
    TipoEvento,
)
from jml.dominio.valores import (
    CampoRestringido,
    Documento,
    NombreDeSoporteSaneado,
    Sha256,
    SolicitudId,
    Usuario,
)

type Json = dict[str, object]


def _corrupto(que: str) -> DatoInvalido:
    return DatoInvalido("persistencia", f"dato corrupto en la base: {que}")


def _dict(valor: object, que: str) -> Json:
    if not isinstance(valor, dict):
        raise _corrupto(que)
    return valor


def _fecha_obligatoria(valor: object, que: str) -> date:
    fecha = _fecha(valor)
    if fecha is None:
        raise _corrupto(que)
    return fecha


def _fecha(valor: object) -> date | None:
    return None if valor is None else date.fromisoformat(str(valor))


def _instante(valor: object) -> datetime:
    return datetime.fromisoformat(str(valor))


def _texto(d: Json, clave: str) -> str:
    return str(d[clave])


# --- datos del evento ------------------------------------------------------------------------


def datos_a_json(datos: DatosDelEvento) -> Json:
    match datos:
        case DatosIngreso():
            return {
                "nombres": datos.nombres,
                "apellidos": datos.apellidos,
                "documento": datos.documento.valor,
                "vinculacion": datos.vinculacion.value,
                "departamento": datos.departamento,
                "cargo": datos.cargo,
                "sede": datos.sede,
                "jefe_id": datos.jefe_id,
                "fecha_fin": datos.fecha_fin.isoformat() if datos.fecha_fin else None,
                "requiere_equipo": datos.requiere_equipo,
                "tipo_equipo": datos.tipo_equipo.value if datos.tipo_equipo else None,
            }
        case DatosVacaciones():
            return {"fecha_regreso": datos.fecha_regreso.isoformat()}
        case DatosCambioDepartamento():
            return {
                "departamento_nuevo": datos.departamento_nuevo,
                "cargo_nuevo": datos.cargo_nuevo,
                "jefe_nuevo_id": datos.jefe_nuevo_id,
            }
        case DatosCambioSucursal():
            return {"sede_nueva": datos.sede_nueva, "traslada_equipo": datos.traslada_equipo}
        case DatosRetiro():
            return {}
        case DatosEmergencia():
            return {
                "reportado_por": datos.reportado_por,
                "hora_del_hecho": datos.hora_del_hecho.isoformat(),
            }


def datos_de_json(tipo: TipoEvento, d: Json) -> DatosDelEvento:
    match tipo:
        case TipoEvento.ING:
            tipo_equipo = d.get("tipo_equipo")
            jefe = d.get("jefe_id")
            return DatosIngreso(
                nombres=_texto(d, "nombres"),
                apellidos=_texto(d, "apellidos"),
                documento=Documento(_texto(d, "documento")),
                vinculacion=TipoDeVinculacion(_texto(d, "vinculacion")),
                departamento=_texto(d, "departamento"),
                cargo=_texto(d, "cargo"),
                sede=_texto(d, "sede"),
                jefe_id=None if jefe is None else str(jefe),
                fecha_fin=_fecha(d.get("fecha_fin")),
                requiere_equipo=bool(d["requiere_equipo"]),
                tipo_equipo=None if tipo_equipo is None else TipoDeEquipo(str(tipo_equipo)),
            )
        case TipoEvento.VAC:
            return DatosVacaciones(_fecha_obligatoria(d["fecha_regreso"], "fecha_regreso"))
        case TipoEvento.CDP:
            jefe = d.get("jefe_nuevo_id")
            return DatosCambioDepartamento(
                _texto(d, "departamento_nuevo"),
                _texto(d, "cargo_nuevo"),
                None if jefe is None else str(jefe),
            )
        case TipoEvento.CSU:
            return DatosCambioSucursal(_texto(d, "sede_nueva"), bool(d["traslada_equipo"]))
        case TipoEvento.RET:
            return DatosRetiro()
        case TipoEvento.EMG:
            return DatosEmergencia(_texto(d, "reportado_por"), _instante(d["hora_del_hecho"]))


# --- solicitud -------------------------------------------------------------------------------


def solicitud_de_modelo(fila: m.Solicitud, restringido: str | None) -> Solicitud:
    tipo = TipoEvento(fila.tipo)
    datos = _dict(fila.datos, "solicitud.datos")
    return Solicitud(
        id=SolicitudId(fila.id),
        colaborador_id=fila.colaborador_id,
        tipo=tipo,
        subtipo=None if fila.subtipo is None else Subtipo(fila.subtipo),
        fecha_efectiva=fila.fecha_efectiva,
        datos=datos_de_json(tipo, datos),
        restringido=None if restringido is None else CampoRestringido(restringido),
        solicitante_id=fila.solicitante_id,
        estado=EstadoSolicitud(fila.estado),
        creada_en=fila.creada_en,
        solicitud_origen_id=(
            None if fila.solicitud_origen_id is None else SolicitudId(fila.solicitud_origen_id)
        ),
        tickets=tuple(str(t) for t in fila.tickets),
        para_revision=fila.para_revision,
    )


def solicitud_a_campos(s: Solicitud) -> Json:
    return {
        "colaborador_id": s.colaborador_id,
        "tipo": s.tipo.value,
        "subtipo": None if s.subtipo is None else s.subtipo.value,
        "fecha_efectiva": s.fecha_efectiva,
        "datos": datos_a_json(s.datos),
        "solicitante_id": s.solicitante_id,
        "estado": s.estado.value,
        "creada_en": s.creada_en,
        "solicitud_origen_id": None
        if s.solicitud_origen_id is None
        else s.solicitud_origen_id.valor,
        "tickets": list(s.tickets),
        "para_revision": s.para_revision,
    }


# --- colaborador, perfil, decision, soporte ----------------------------------------------------


def colaborador_de_modelo(f: m.Colaborador) -> Colaborador:
    return Colaborador(
        id=f.id,
        documento=Documento(f.documento),
        nombres=f.nombres,
        apellidos=f.apellidos,
        vinculacion=TipoDeVinculacion(f.vinculacion),
        departamento=f.departamento,
        cargo=f.cargo,
        sede=f.sede,
        jefe_id=f.jefe_id,
        fecha_ingreso=f.fecha_ingreso,
        fecha_fin=f.fecha_fin,
        estado=EstadoColaborador(f.estado),
        usuario=None if f.usuario is None else Usuario(f.usuario),
        id_usuario_glpi=f.id_usuario_glpi,
    )


def colaborador_a_campos(c: Colaborador) -> Json:
    return {
        "documento": c.documento.valor,
        "nombres": c.nombres,
        "apellidos": c.apellidos,
        "vinculacion": c.vinculacion.value,
        "departamento": c.departamento,
        "cargo": c.cargo,
        "sede": c.sede,
        "jefe_id": c.jefe_id,
        "fecha_ingreso": c.fecha_ingreso,
        "fecha_fin": c.fecha_fin,
        "estado": c.estado.value,
        "usuario": None if c.usuario is None else c.usuario.valor,
        "id_usuario_glpi": c.id_usuario_glpi,
    }


def _tupla(valor: object) -> tuple[str, ...]:
    if not isinstance(valor, list):
        raise _corrupto("lista")
    return tuple(str(v) for v in valor)


def perfil_de_modelo(f: m.PerfilDeAcceso) -> PerfilDeAcceso:
    return PerfilDeAcceso(
        departamento=f.departamento,
        sede=f.sede,
        grupos_ad=_tupla(f.grupos_ad),
        grupos_red=_tupla(f.grupos_red),
        grupos_m365=_tupla(f.grupos_m365),
        licencias=_tupla(f.licencias),
        tipo_equipo=TipoDeEquipo(f.tipo_equipo),
        recursos=tuple(
            RecursoCompartido(r.ruta, r.serie, PerfilDeRecurso(r.perfil_de_recurso), r.grupo)
            for r in f.recursos.order_by("ruta")
        ),
    )


def decision_de_modelo(f: m.Decision) -> Decision:
    return Decision(
        SolicitudId(f.solicitud_id), TipoDeDecision(f.tipo), f.justificacion, f.usuario_id, f.fecha
    )


def soporte_de_modelo(f: m.Soporte) -> Soporte:
    return Soporte(
        solicitud_id=SolicitudId(f.solicitud_id),
        nombre_original=NombreDeSoporteSaneado(f.nombre_original),
        tamano=f.tamano,
        sha256=Sha256(f.sha256),
        nombre_almacenado=f.nombre_almacenado,
        estado=EstadoDeSoporte(f.estado),
        id_documento_glpi=f.id_documento_glpi,
    )


# --- tickets y bandeja -----------------------------------------------------------------------


def ticket_a_json(t: TicketDeCola) -> Json:
    d = t.datos
    return {
        "solicitud_id": t.solicitud_id,
        "cola": t.cola.value,
        "clase": t.clase.value,
        "ordinal": t.ordinal,
        "accion": t.accion.value,
        "categoria": t.categoria,
        "prioridad": t.prioridad.value,
        "titulo": t.titulo,
        "estado_inicial": t.estado_inicial.value,
        "emitido_en": t.emitido_en.isoformat(),
        "vence_en": t.vence_en.isoformat(),
        "activo_desde": t.activo_desde.isoformat(),
        "lista_de_verificacion": list(t.lista_de_verificacion),
        "clave_de_idempotencia": t.clave_de_idempotencia,
        "datos": {
            "colaborador": d.colaborador,
            "usuario": d.usuario,
            "perfil": d.perfil,
            "fecha_efectiva": d.fecha_efectiva.isoformat(),
            "solicitud": d.solicitud,
        },
        "adjunta_soporte": t.adjunta_soporte,
    }


def ticket_de_json(j: Json) -> TicketDeCola:
    d = _dict(j["datos"], "ticket.datos")
    usuario = d.get("usuario")
    fecha = _fecha_obligatoria(d["fecha_efectiva"], "ticket.fecha_efectiva")
    ordinal = j["ordinal"]
    if not isinstance(ordinal, int):
        raise _corrupto("ticket.ordinal")
    return TicketDeCola(
        solicitud_id=_texto(j, "solicitud_id"),
        cola=Cola(_texto(j, "cola")),
        clase=ClaseTicket(_texto(j, "clase")),
        ordinal=ordinal,
        accion=AccionDeTicket(_texto(j, "accion")),
        categoria=_texto(j, "categoria"),
        prioridad=Prioridad(_texto(j, "prioridad")),
        titulo=_texto(j, "titulo"),
        estado_inicial=EstadoInicialDeTicket(_texto(j, "estado_inicial")),
        emitido_en=_instante(j["emitido_en"]),
        vence_en=_instante(j["vence_en"]),
        activo_desde=_instante(j["activo_desde"]),
        lista_de_verificacion=_tupla(j["lista_de_verificacion"]),
        clave_de_idempotencia=_texto(j, "clave_de_idempotencia"),
        datos=DatosTecnicos(
            colaborador=str(d["colaborador"]),
            usuario=None if usuario is None else str(usuario),
            perfil=str(d["perfil"]),
            fecha_efectiva=fecha,
            solicitud=str(d["solicitud"]),
        ),
        adjunta_soporte=bool(j["adjunta_soporte"]),
    )


def ticket_a_campos(s: TicketSeguido) -> Json:
    t, o = s.ticket, s.observacion
    return {
        "solicitud_id": t.solicitud_id,
        "cola": t.cola.value,
        "clase": t.clase.value,
        "accion": t.accion.value,
        "prioridad": t.prioridad.value,
        "emitido_en": t.emitido_en,
        "vence_en": t.vence_en,
        "activo_desde": t.activo_desde,
        "definicion": ticket_a_json(t),
        "id_externo": s.id_externo,
        "estado_glpi": None if o is None else int(o.estado),
        "tiene_solucion": False if o is None else o.tiene_solucion,
        "documentos": 0 if o is None else o.documentos,
        "observado_en": None if o is None else o.observada_en,
        "reabierto": s.reabierto,
    }


def seguido_de_modelo(f: m.Ticket) -> TicketSeguido:
    definicion = _dict(f.definicion, "ticket.definicion")
    observacion = (
        None
        if f.estado_glpi is None or f.observado_en is None
        else Observacion(
            EstadoDeTicket(f.estado_glpi), f.tiene_solucion, f.documentos, f.observado_en
        )
    )
    return TicketSeguido(ticket_de_json(definicion), f.id_externo, observacion, f.reabierto)


def entrada_de_modelo(f: m.EntradaDeBandeja) -> EntradaDeBandeja:
    definicion = _dict(f.ticket.definicion, "ticket.definicion")
    return EntradaDeBandeja(
        ticket=ticket_de_json(definicion),
        estado=EstadoDeEntrada(f.estado),
        intentos=f.intentos,
        proximo_intento=f.proximo_intento,
        ultimo_error=f.ultimo_error,
    )


# --- cuentas ---------------------------------------------------------------------------------


def cuenta_de_modelo(f: m.Cuenta) -> Cuenta:
    return Cuenta(
        colaborador_id=f.colaborador_id,
        sistema=SistemaDeCuenta(f.sistema),
        estado=EstadoDeCuenta(f.estado),
        ticket_origen=f.ticket_origen,
        orden_origen=(f.origen_emitido_en, f.origen_vence_en),
        desde=f.desde,
        marca=None if f.marca is None else MarcaDeCuenta(f.marca),
    )


def cambio_de_modelo(f: m.CuentaHistorial) -> CambioDeCuenta:
    return CambioDeCuenta(
        colaborador_id=f.colaborador_id,
        sistema=SistemaDeCuenta(f.sistema),
        estado_anterior=None if f.estado_anterior is None else EstadoDeCuenta(f.estado_anterior),
        estado_nuevo=EstadoDeCuenta(f.estado_nuevo),
        marca_nueva=None if f.marca_nueva is None else MarcaDeCuenta(f.marca_nueva),
        ticket=f.ticket,
        fecha=f.fecha,
    )
