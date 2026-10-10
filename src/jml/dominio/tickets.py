"""Generacion de tickets por cola (SRS 4.3 a 4.5, RF-16, RF-17, RF-20) y su seguimiento.

`generar_tickets` es una funcion pura: la misma entrada produce los mismos tickets, con las
mismas claves de idempotencia. Los tickets llevan SOLO datos tecnicos (RF-20): nunca el motivo
de un retiro, la descripcion de una emergencia, el subtipo ni contrasenas (RD-05, T7, T9).
Las acciones las ejecutan personas: la lista de verificacion es texto para ellas, no una orden
para ningun directorio (ADR-019).
"""

from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import TypeVar

from jml.dominio.catalogo import DatosCambioSucursal, DatosIngreso, DatosVacaciones
from jml.dominio.colaborador import Colaborador
from jml.dominio.errores import DatoInvalido, TransicionInvalida
from jml.dominio.perfiles import DiferenciaDePerfiles, PerfilDeAcceso, diferencia
from jml.dominio.sla import (
    activo_desde_la_eliminacion,
    fecha_base_de_eliminacion,
    prioridad_del_evento,
    vence_el_cambio,
    vence_el_ingreso,
    vence_la_baja,
    vence_la_eliminacion,
    vence_la_emergencia,
    vence_la_reactivacion,
    vence_la_suspension,
)
from jml.dominio.solicitud import Solicitud
from jml.dominio.tipos import (
    AccionDeTicket,
    ClaseTicket,
    Cola,
    EstadoDeTicket,
    EstadoInicialDeTicket,
    EstadoSolicitud,
    Prioridad,
    SistemaDeCuenta,
    TipoEvento,
)
from jml.dominio.valores import CalendarioHabil, Usuario, a_utc, inicio_del_dia

T = TypeVar("T")

COLA_A_SISTEMA: dict[Cola, SistemaDeCuenta | None] = {
    Cola.AD: SistemaDeCuenta.AD,
    Cola.COMUNICACIONES: SistemaDeCuenta.RED,
    Cola.LICENCIAS: SistemaDeCuenta.M365,
    Cola.INVENTARIO: None,
    Cola.REVISION_MANUAL: None,
}

ORDEN_DE_COLAS = (Cola.AD, Cola.COMUNICACIONES, Cola.LICENCIAS, Cola.INVENTARIO)
ORDEN_DE_CLASES = (
    ClaseTicket.CIERRE_INMEDIATO,
    ClaseTicket.CIERRE_PROGRAMADO,
    ClaseTicket.POSTERIOR,
)

# La unica mencion permitida de una contrasena: se cambia a un valor que nadie conoce (SRS 4.5).
FRASE_DE_CONTRASENA = "Cambiar la contraseña a un valor aleatorio que no se comunica a nadie."


@dataclass(frozen=True, slots=True)
class DatosTecnicos:
    """RF-20: el unico contenido descriptivo permitido de un ticket."""

    colaborador: str
    usuario: str | None
    perfil: str
    fecha_efectiva: date
    solicitud: str


@dataclass(frozen=True, slots=True)
class TicketDeCola:
    solicitud_id: str
    cola: Cola
    clase: ClaseTicket
    ordinal: int
    accion: AccionDeTicket
    categoria: str
    prioridad: Prioridad
    titulo: str
    estado_inicial: EstadoInicialDeTicket
    emitido_en: datetime
    vence_en: datetime
    activo_desde: datetime  # desde cuando cuenta como pendiente (programados: su fecha)
    lista_de_verificacion: tuple[str, ...]
    clave_de_idempotencia: str
    datos: DatosTecnicos
    adjunta_soporte: bool

    @property
    def sistema(self) -> SistemaDeCuenta | None:
        return COLA_A_SISTEMA[self.cola]

    @property
    def bloquea_el_cierre(self) -> bool:
        return self.clase is not ClaseTicket.POSTERIOR

    def como_texto(self) -> str:
        """Todo lo que veria GLPI; la prueba de confidencialidad serializa esto."""
        d = self.datos
        partes = [
            self.titulo,
            self.categoria,
            f"Prioridad: {self.prioridad.value}",
            f"Colaborador: {d.colaborador}",
            f"Usuario: {d.usuario or '-'}",
            f"Perfil: {d.perfil}",
            f"Fecha efectiva: {d.fecha_efectiva.isoformat()}",
            f"Solicitud: {d.solicitud}",
            *self.lista_de_verificacion,
        ]
        return "\n".join(partes)


def clave_de_idempotencia(solicitud_id: str, cola: Cola, clase: ClaseTicket, ordinal: int) -> str:
    return f"{solicitud_id}:{cola.value}:{clase.value}:{ordinal}"


def categoria_del_ticket(tipo: TipoEvento, cola: Cola, accion: AccionDeTicket) -> str:
    """RF-19: la aplicacion fija la categoria; una regla de GLPI asigna el grupo."""
    return f"JML/{tipo.value}/{cola.value}/{accion.value}"


# --- listas de verificacion -------------------------------------------------------------------


def _lista(titulo: str, valores: tuple[str, ...]) -> str:
    return f"{titulo}: {', '.join(valores)}."


def _accesos(titulo: str, dif_o_perfil: tuple[str, ...]) -> list[str]:
    return [titulo, *(f"  - {linea}" for linea in dif_o_perfil)] if dif_o_perfil else []


def _grupos_ad_ingreso(perfil: PerfilDeAcceso) -> list[str]:
    return [
        _lista("Agregar los grupos de AD del perfil", perfil.grupos_ad),
        *_accesos(
            "Aplicar en cada recurso compartido su perfil mediante el grupo FS-*:",
            tuple(a.como_texto() for a in perfil.accesos_a_aplicar()),
        ),
    ]


_VERIFICAR_SOPORTE = (
    "Verificar el soporte de vinculación adjunto (acta de inicio firmada si es contratista; "
    "acto administrativo de nombramiento o contrato en los demás casos)."
)


def _ing_ad(datos: DatosIngreso, c: Colaborador, perfil: PerfilDeAcceso) -> list[str]:
    usuario = _usuario(c)
    items = [
        _VERIFICAR_SOPORTE,
        f"Crear la cuenta con el usuario sugerido: {usuario.valor} ({usuario.upn_ad().valor}).",
        *_grupos_ad_ingreso(perfil),
    ]
    if datos.fecha_fin is not None:  # S-21
        items.append(f"Fijar la fecha de expiración de la cuenta: {datos.fecha_fin.isoformat()}.")
    return items


def _ing_com(perfil: PerfilDeAcceso) -> list[str]:
    return [_lista("Agregar los grupos de red del perfil", perfil.grupos_red)]


def _ing_lic(c: Colaborador, perfil: PerfilDeAcceso) -> list[str]:
    usuario = _usuario(c)
    return [
        _VERIFICAR_SOPORTE,
        f"Crear la identidad en M365 o Entra ID: {usuario.upn_m365().valor}.",
        _lista("Agregar los grupos de M365 del perfil", perfil.grupos_m365),
        _lista("Registrar en GLPI las licencias del perfil", perfil.licencias),
    ]


def _ing_inv(datos: DatosIngreso) -> list[str]:
    equipo = datos.tipo_equipo.value if datos.tipo_equipo else "sin especificar"
    return [
        f"Asignar el equipo ({equipo}) al usuario en GLPI y adjuntar el acta de entrega firmada."
    ]


def _cambios_ad(dif: DiferenciaDePerfiles) -> list[str]:
    items: list[str] = []
    if dif.grupos_ad_quitar:
        items.append(_lista("Quitar los grupos de AD del perfil anterior", dif.grupos_ad_quitar))
    if dif.grupos_ad_agregar:
        items.append(_lista("Agregar los grupos de AD del perfil nuevo", dif.grupos_ad_agregar))
    items += _accesos(
        "Aplicar el perfil en los recursos compartidos nuevos o modificados:",
        tuple(a.como_texto() for a in dif.recursos_a_aplicar),
    )
    items += _accesos(
        "Aplicar 'Retiro de accesos' en los recursos que ya no corresponden:",
        tuple(a.como_texto() for a in dif.recursos_a_retirar),
    )
    return items


def _cambios_red(dif: DiferenciaDePerfiles) -> list[str]:
    items: list[str] = []
    if dif.grupos_red_quitar:
        items.append(_lista("Quitar los grupos de red", dif.grupos_red_quitar))
    if dif.grupos_red_agregar:
        items.append(_lista("Agregar los grupos de red", dif.grupos_red_agregar))
    return items


def _cambios_m365(dif: DiferenciaDePerfiles) -> list[str]:
    items: list[str] = []
    if dif.grupos_m365_quitar:
        items.append(_lista("Quitar los grupos de M365", dif.grupos_m365_quitar))
    if dif.grupos_m365_agregar:
        items.append(_lista("Agregar los grupos de M365", dif.grupos_m365_agregar))
    if dif.licencias_quitar:
        items.append(_lista("Liberar las licencias en GLPI", dif.licencias_quitar))
    if dif.licencias_agregar:
        items.append(_lista("Registrar en GLPI las licencias", dif.licencias_agregar))
    return items


def _baja_ad(c: Colaborador, perfil: PerfilDeAcceso) -> list[str]:
    usuario = _usuario(c)
    items = [
        f"Deshabilitar la cuenta {usuario.valor} ({usuario.upn_ad().valor}).",
        FRASE_DE_CONTRASENA,
        "Revocar las sesiones activas.",
        _lista("Quitar los grupos de AD", perfil.grupos_ad)
        + " Listar en la solución los grupos retirados.",
        *_accesos(
            "Aplicar 'Retiro de accesos' en todos los recursos compartidos:",
            tuple(a.como_texto() for a in perfil.accesos_de_retiro()),
        ),
        "Mover la cuenta a la OU Deshabilitados.",
    ]
    if c.jefe_id is not None:
        items.append("Dar al jefe directo perfil Consulta sobre la carpeta personal por 30 días.")
    return items


def _baja_com(perfil: PerfilDeAcceso) -> list[str]:
    return [_lista("Quitar todos los grupos de red", perfil.grupos_red)]


def _baja_lic(c: Colaborador, perfil: PerfilDeAcceso) -> list[str]:
    upn = _usuario(c).upn_m365().valor
    return [
        f"Bloquear el inicio de sesión de {upn}.",
        "Revocar las sesiones activas.",
        _lista("Quitar los grupos de M365", perfil.grupos_m365),
        _lista("Liberar las licencias en GLPI", perfil.licencias),
    ]


def _usuario(c: Colaborador) -> Usuario:
    if c.usuario is None:
        raise DatoInvalido("usuario", "el colaborador no tiene usuario sugerido asignado")
    return c.usuario


# --- generacion -------------------------------------------------------------------------------


def _como(datos: object, clase: type[T]) -> T:
    """Estrecha el tipo de los datos del evento; el catalogo ya garantiza que coinciden."""
    if not isinstance(datos, clase):
        raise DatoInvalido("datos", f"se esperaba {clase.__name__}")
    return datos


def _requerir(perfil: PerfilDeAcceso | None, nombre: str, tipo: TipoEvento) -> PerfilDeAcceso:
    if perfil is None:
        raise DatoInvalido(nombre, f"obligatorio para generar los tickets de {tipo.value}")
    return perfil


INMEDIATO, PROGRAMADO, POSTERIOR = ORDEN_DE_CLASES


class _Emision:
    """Acumula los tickets de una solicitud con sus datos comunes."""

    def __init__(self, s: Solicitud, c: Colaborador, perfil: PerfilDeAcceso, ahora: datetime):
        self.s = s
        self.c = c
        self.ahora = a_utc(ahora, "ahora")
        self.prioridad = prioridad_del_evento(s.tipo)
        self.tickets: list[TicketDeCola] = []
        self.datos = DatosTecnicos(
            colaborador=c.nombre_completo,
            usuario=c.usuario.valor if c.usuario else None,
            perfil=f"{perfil.departamento} / {perfil.sede}",
            fecha_efectiva=s.fecha_efectiva,
            solicitud=s.id.valor,
        )

    def agregar(
        self,
        cola: Cola,
        clase: ClaseTicket,
        accion: AccionDeTicket,
        titulo: str,
        lista: list[str],
        vence_en: datetime,
        *,
        prioridad: Prioridad | None = None,
        activo_desde: datetime | None = None,
        adjunta_soporte: bool = False,
    ) -> None:
        inmediato = clase is INMEDIATO
        self.tickets.append(
            TicketDeCola(
                solicitud_id=self.s.id.valor,
                cola=cola,
                clase=clase,
                ordinal=1,
                accion=accion,
                categoria=categoria_del_ticket(self.s.tipo, cola, accion),
                prioridad=prioridad or self.prioridad,
                titulo=f"{self.s.id.valor} · {titulo} · {self.c.nombre_completo}",
                estado_inicial=(
                    EstadoInicialDeTicket.NUEVO if inmediato else EstadoInicialDeTicket.EN_ESPERA
                ),
                emitido_en=self.ahora,
                vence_en=vence_en,
                activo_desde=self.ahora if inmediato else (activo_desde or self.ahora),
                lista_de_verificacion=tuple(lista),
                clave_de_idempotencia=clave_de_idempotencia(self.s.id.valor, cola, clase, 1),
                datos=self.datos,
                adjunta_soporte=adjunta_soporte,
            )
        )

    def resultado(self) -> tuple[TicketDeCola, ...]:
        def orden(t: TicketDeCola) -> tuple[int, int]:
            return ORDEN_DE_COLAS.index(t.cola), ORDEN_DE_CLASES.index(t.clase)

        return tuple(sorted(self.tickets, key=orden))


def _tickets_de_ingreso(
    s: Solicitud, c: Colaborador, nuevo: PerfilDeAcceso, ahora: datetime
) -> tuple[TicketDeCola, ...]:
    datos = _como(s.datos, DatosIngreso)
    e = _Emision(s, c, nuevo, ahora)
    vence = vence_el_ingreso(s.fecha_efectiva)
    alta = AccionDeTicket.ALTA
    e.agregar(
        Cola.AD,
        INMEDIATO,
        alta,
        "Ingreso: cuenta y accesos",
        _ing_ad(datos, c, nuevo),
        vence,
        adjunta_soporte=True,
    )
    e.agregar(
        Cola.COMUNICACIONES, INMEDIATO, alta, "Ingreso: grupos de red", _ing_com(nuevo), vence
    )
    e.agregar(
        Cola.LICENCIAS,
        INMEDIATO,
        alta,
        "Ingreso: identidad y licencias",
        _ing_lic(c, nuevo),
        vence,
        adjunta_soporte=True,
    )
    if datos.requiere_equipo:  # S-04
        e.agregar(
            Cola.INVENTARIO,
            INMEDIATO,
            AccionDeTicket.EQUIPO,
            "Ingreso: entrega de equipo",
            _ing_inv(datos),
            vence,
        )
    return e.resultado()


def _tickets_de_vacaciones(
    s: Solicitud, c: Colaborador, actual: PerfilDeAcceso, ahora: datetime
) -> tuple[TicketDeCola, ...]:
    datos = _como(s.datos, DatosVacaciones)
    e = _Emision(s, c, actual, ahora)
    inicio, regreso = s.fecha_efectiva, datos.fecha_regreso
    u = _usuario(c)
    upn = u.upn_m365().valor
    desde_regreso = inicio_del_dia(regreso)
    suspension, reactivacion = AccionDeTicket.SUSPENSION, AccionDeTicket.REACTIVACION
    e.agregar(
        Cola.AD,
        INMEDIATO,
        suspension,
        "Vacaciones: suspender cuenta",
        [
            f"Deshabilitar la cuenta {u.valor} al inicio de las vacaciones ({inicio.isoformat()}).",
            "No cambiar la contraseña ni quitar los grupos; revocar las sesiones.",
        ],
        vence_la_suspension(inicio),
    )
    e.agregar(
        Cola.AD,
        PROGRAMADO,
        reactivacion,
        "Vacaciones: reactivar cuenta",
        [f"Habilitar la cuenta {u.valor} en la fecha de regreso ({regreso.isoformat()})."],
        vence_la_reactivacion(regreso),
        activo_desde=desde_regreso,
    )
    e.agregar(
        Cola.LICENCIAS,
        INMEDIATO,
        suspension,
        "Vacaciones: bloquear identidad",
        [f"Bloquear el inicio de sesión de {upn} y revocar sus sesiones."],
        vence_la_suspension(inicio),
    )
    e.agregar(
        Cola.LICENCIAS,
        PROGRAMADO,
        reactivacion,
        "Vacaciones: desbloquear identidad",
        [f"Desbloquear el inicio de sesión de {upn} el {regreso.isoformat()}, fecha de regreso."],
        vence_la_reactivacion(regreso),
        activo_desde=desde_regreso,
    )
    return e.resultado()


def _tickets_de_cambio(
    s: Solicitud,
    c: Colaborador,
    actual: PerfilDeAcceso,
    nuevo: PerfilDeAcceso,
    calendario: CalendarioHabil,
    ahora: datetime,
) -> tuple[TicketDeCola, ...]:
    """CDP y CSU. Sin diferencia en una cola no se genera ticket vacio (S-05)."""
    es_cdp = s.tipo is TipoEvento.CDP
    traslada_equipo = False
    if es_cdp:
        if nuevo.sede != actual.sede:
            raise DatoInvalido("perfil_nuevo", "un cambio de departamento conserva la sede")
    else:
        sucursal = _como(s.datos, DatosCambioSucursal)
        if nuevo.departamento != actual.departamento or nuevo.sede != sucursal.sede_nueva:
            raise DatoInvalido("perfil_nuevo", "un cambio de sucursal solo cambia la sede")
        traslada_equipo = sucursal.traslada_equipo
    dif = diferencia(actual, nuevo)
    e = _Emision(s, c, nuevo, ahora)
    vence = vence_el_cambio(s.fecha_efectiva, calendario)
    etiqueta = "Cambio de departamento" if es_cdp else "Cambio de sucursal"
    cambio = AccionDeTicket.CAMBIO
    if dif.cambia_ad:
        e.agregar(Cola.AD, INMEDIATO, cambio, f"{etiqueta}: accesos de AD", _cambios_ad(dif), vence)
    if dif.cambia_red:
        e.agregar(
            Cola.COMUNICACIONES,
            INMEDIATO,
            cambio,
            f"{etiqueta}: grupos de red",
            _cambios_red(dif),
            vence,
        )
    if es_cdp and dif.cambia_m365:
        e.agregar(
            Cola.LICENCIAS,
            INMEDIATO,
            cambio,
            f"{etiqueta}: grupos y licencias",
            _cambios_m365(dif),
            vence,
        )
    if es_cdp and dif.equipo_nuevo is not None:
        cambio_de_equipo = (
            f"Cambiar el equipo {actual.tipo_equipo.value} por {dif.equipo_nuevo.value}; "
            "adjuntar el acta."
        )
        e.agregar(
            Cola.INVENTARIO,
            INMEDIATO,
            AccionDeTicket.EQUIPO,
            f"{etiqueta}: cambio de equipo",
            [cambio_de_equipo],
            vence,
        )
    if traslada_equipo:
        e.agregar(
            Cola.INVENTARIO,
            INMEDIATO,
            AccionDeTicket.EQUIPO,
            f"{etiqueta}: traslado de equipo",
            [f"Trasladar el equipo a la sede {nuevo.sede}; adjuntar el acta."],
            vence,
        )
    return e.resultado()


def _tickets_de_baja(
    s: Solicitud, c: Colaborador, actual: PerfilDeAcceso, ahora: datetime
) -> tuple[TicketDeCola, ...]:
    """RET y EMG: baja inmediata por cola y eliminacion posterior a 90 dias en AD y Licencias."""
    emergencia = s.tipo is TipoEvento.EMG
    e = _Emision(s, c, actual, ahora)
    vence = vence_la_emergencia(ahora) if emergencia else vence_la_baja(s.fecha_efectiva)
    base = fecha_base_de_eliminacion(s.tipo, s.fecha_efectiva, ahora)
    vence_eliminar = vence_la_eliminacion(base)
    desde_eliminar = activo_desde_la_eliminacion(base)
    prefijo = ["Emergencia: ejecutar de inmediato."] if emergencia else []
    etiqueta = "Emergencia" if emergencia else "Retiro"
    u = _usuario(c)
    baja, eliminacion = AccionDeTicket.BAJA, AccionDeTicket.ELIMINACION
    e.agregar(
        Cola.AD,
        INMEDIATO,
        baja,
        f"{etiqueta}: baja de cuenta y accesos",
        [*prefijo, *_baja_ad(c, actual)],
        vence,
    )
    e.agregar(
        Cola.AD,
        POSTERIOR,
        eliminacion,
        f"{etiqueta}: eliminar cuenta (90 días)",
        [f"Eliminar la cuenta {u.valor} (90 días después de la baja)."],
        vence_eliminar,
        prioridad=Prioridad.MEDIA,  # S-17
        activo_desde=desde_eliminar,
    )
    e.agregar(
        Cola.COMUNICACIONES,
        INMEDIATO,
        baja,
        f"{etiqueta}: grupos de red",
        [*prefijo, *_baja_com(actual)],
        vence,
    )
    e.agregar(
        Cola.LICENCIAS,
        INMEDIATO,
        baja,
        f"{etiqueta}: identidad y licencias",
        [*prefijo, *_baja_lic(c, actual)],
        vence,
    )
    e.agregar(
        Cola.LICENCIAS,
        POSTERIOR,
        eliminacion,
        f"{etiqueta}: eliminar identidad (90 días)",
        [f"Eliminar la identidad {u.upn_m365().valor} (90 días después de la baja)."],
        vence_eliminar,
        prioridad=Prioridad.MEDIA,  # S-17
        activo_desde=desde_eliminar,
    )
    equipo = (
        "Recuperar el equipo con acta de recepción."
        if emergencia
        else "Recibir el equipo con acta de recepción y paz y salvo."
    )
    e.agregar(
        Cola.INVENTARIO,
        INMEDIATO,
        AccionDeTicket.EQUIPO,
        f"{etiqueta}: recuperar equipo",
        [*prefijo, equipo],
        vence,
    )
    return e.resultado()


def generar_tickets(
    solicitud: Solicitud,
    perfil_actual: PerfilDeAcceso | None,
    perfil_nuevo: PerfilDeAcceso | None,
    colaborador: Colaborador,
    calendario: CalendarioHabil,
    ahora: datetime,
) -> tuple[TicketDeCola, ...]:
    """Matriz evento x cola del SRS 4.4. Sin diferencia no se genera un ticket vacio (S-05)."""
    if solicitud.estado is not EstadoSolicitud.APROBADA:
        raise TransicionInvalida(solicitud.estado.value, "generar_tickets")
    if colaborador.id != solicitud.colaborador_id:
        raise DatoInvalido("colaborador", "no corresponde a la solicitud")
    tipo = solicitud.tipo
    if tipo is TipoEvento.ING:
        nuevo = _requerir(perfil_nuevo, "perfil_nuevo", tipo)
        return _tickets_de_ingreso(solicitud, colaborador, nuevo, ahora)
    if tipo is TipoEvento.VAC:
        actual = perfil_actual or perfil_nuevo
        if actual is None:
            raise DatoInvalido("perfil_actual", "obligatorio para generar los tickets de VAC")
        return _tickets_de_vacaciones(solicitud, colaborador, actual, ahora)
    actual = _requerir(perfil_actual, "perfil_actual", tipo)
    if tipo in (TipoEvento.CDP, TipoEvento.CSU):
        nuevo = _requerir(perfil_nuevo, "perfil_nuevo", tipo)
        return _tickets_de_cambio(solicitud, colaborador, actual, nuevo, calendario, ahora)
    return _tickets_de_baja(solicitud, colaborador, actual, ahora)


# --- seguimiento de lo que GLPI informa -------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Observacion:
    """Lo que GLPI dice de un ticket en un instante (RF-22)."""

    estado: EstadoDeTicket
    tiene_solucion: bool
    documentos: int
    observada_en: datetime

    def __post_init__(self) -> None:
        if self.documentos < 0:
            raise DatoInvalido("documentos", "no puede ser negativo")
        object.__setattr__(self, "observada_en", a_utc(self.observada_en, "observada_en"))

    @property
    def resuelta(self) -> bool:
        return self.estado >= EstadoDeTicket.RESUELTO


@dataclass(frozen=True, slots=True)
class TicketSeguido:
    ticket: TicketDeCola
    id_externo: str | None = None
    observacion: Observacion | None = None
    reabierto: bool = False

    def creado(self, id_externo: str) -> "TicketSeguido":
        if not id_externo.strip():
            raise DatoInvalido("id_externo", "no puede estar vacio")
        return replace(self, id_externo=id_externo)

    def observar(self, nueva: Observacion) -> "TicketSeguido":
        """Idempotente y tolerante al orden: una observacion mas vieja se ignora (RF-25)."""
        previa = self.observacion
        if previa is not None and nueva.observada_en < previa.observada_en:
            return self
        reabierto = self.reabierto
        if previa is not None and previa.resuelta and not nueva.resuelta:
            reabierto = True
        elif nueva.resuelta and nueva.tiene_solucion:
            reabierto = False
        return replace(self, observacion=nueva, reabierto=reabierto)
