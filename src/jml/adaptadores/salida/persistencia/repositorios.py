"""Repositorios sobre el ORM de Django: implementan los puertos de `jml.aplicacion.puertos`.

La base de datos garantiza las reglas (RD-01, RD-09); el codigo solo traduce el
`IntegrityError` al error del puerto, dentro de un savepoint para que la transaccion siga viva.
"""

from collections.abc import Sequence
from datetime import datetime
from types import TracebackType
from typing import Self

from django.contrib.auth.models import Group, User
from django.db import IntegrityError, transaction

from jml.adaptadores.salida.persistencia import consultas
from jml.adaptadores.salida.persistencia import mapeo as mp
from jml.adaptadores.salida.persistencia import models as m
from jml.aplicacion.bandeja import EntradaDeBandeja, EstadoDeEntrada
from jml.aplicacion.dtos import (
    FichaDeColaborador,
    FiltroDeCuentas,
    Indicadores,
    PaginaDeCuentas,
    ResultadoDeSincronizacion,
)
from jml.aplicacion.puertos import (
    ContenidoDeSolicitudModificado,
    DocumentoYaRegistrado,
    DuplicadoAbierto,
    Reloj,
)
from jml.dominio.activos import ActivoAsignado, LicenciaAsignada
from jml.dominio.auditoria import (
    EventoDeAuditoria,
    RegistroDeAuditoria,
    ResultadoDeVerificacion,
    ValorAuditable,
    encadenar,
    verificar_cadena,
)
from jml.dominio.catalogo import ColaboradorId, UsuarioId
from jml.dominio.colaborador import Colaborador
from jml.dominio.cuentas import CambioDeCuenta, Cuenta
from jml.dominio.perfiles import PerfilDeAcceso
from jml.dominio.permisos import Actor, UsuarioDelSistema
from jml.dominio.solicitud import Decision, Solicitud
from jml.dominio.soporte import Soporte
from jml.dominio.tickets import TicketSeguido
from jml.dominio.tipos import (
    ESTADOS_ABIERTOS,
    EstadoColaborador,
    EstadoSolicitud,
    Rol,
    SistemaDeCuenta,
    TipoEvento,
)
from jml.dominio.valores import Documento, SolicitudId

_ABIERTOS = [e.value for e in ESTADOS_ABIERTOS]
_CANDADO_DE_AUDITORIA = "auditoria"


def _restringido(fila: m.Solicitud) -> str | None:
    r = m.SolicitudRestringida.objects.filter(solicitud_id=fila.id).first()
    return None if r is None else r.contenido


def _solicitud(fila: m.Solicitud) -> Solicitud:
    return mp.solicitud_de_modelo(fila, _restringido(fila))


class RepoSolicitudes:
    def siguiente_id(self, anio: int) -> SolicitudId:
        fila, _ = m.Consecutivo.objects.select_for_update().get_or_create(clave=f"solicitud-{anio}")
        fila.ultimo += 1
        fila.save(update_fields=["ultimo"])
        return SolicitudId.de(anio, fila.ultimo)

    def guardar(self, solicitud: Solicitud) -> None:
        previa = m.Solicitud.objects.filter(pk=solicitud.id.valor).first()
        # RF-14: el disparador de PostgreSQL es la garantia; esto es defensa en profundidad.
        if (
            previa is not None
            and previa.estado != EstadoSolicitud.PENDIENTE_APROBACION.value
            and _solicitud(previa).contenido() != solicitud.contenido()
        ):
            raise ContenidoDeSolicitudModificado(solicitud.id)
        try:
            with transaction.atomic():
                m.Solicitud.objects.update_or_create(
                    pk=solicitud.id.valor, defaults=mp.solicitud_a_campos(solicitud)
                )
                if solicitud.restringido is not None:
                    self._guardar_restringido(solicitud.id, solicitud.restringido.revelar())
        except IntegrityError:
            existente = (
                m.Solicitud.objects.filter(
                    colaborador_id=solicitud.colaborador_id,
                    tipo=solicitud.tipo.value,
                    estado__in=_ABIERTOS,
                )
                .exclude(pk=solicitud.id.valor)
                .first()
            )
            if existente is None:
                raise  # otra restriccion (p. ej. el colaborador no existe): no es un duplicado
            raise DuplicadoAbierto(SolicitudId(existente.id)) from None

    @staticmethod
    def _guardar_restringido(solicitud_id: SolicitudId, contenido: str) -> None:
        """Escribe solo si falta o cambio: PostgreSQL rechaza hasta un UPDATE identico sobre el
        campo restringido de una solicitud aprobada (RF-14), asi que no se reescribe en vano."""
        actual = m.SolicitudRestringida.objects.filter(solicitud_id=solicitud_id.valor).first()
        if actual is None:
            m.SolicitudRestringida.objects.create(
                solicitud_id=solicitud_id.valor, contenido=contenido
            )
        elif actual.contenido != contenido:
            actual.contenido = contenido
            actual.save(update_fields=["contenido"])

    def obtener(self, solicitud_id: SolicitudId) -> Solicitud | None:
        fila = m.Solicitud.objects.filter(pk=solicitud_id.valor).first()
        return None if fila is None else _solicitud(fila)

    def abiertas_de(self, colaborador_id: ColaboradorId) -> Sequence[Solicitud]:
        filas = m.Solicitud.objects.filter(colaborador_id=colaborador_id, estado__in=_ABIERTOS)
        return [_solicitud(f) for f in filas.order_by("id")]

    def de_colaborador(self, colaborador_id: ColaboradorId) -> Sequence[Solicitud]:
        return [
            _solicitud(f)
            for f in m.Solicitud.objects.filter(colaborador_id=colaborador_id).order_by("id")
        ]

    def del_solicitante(self, usuario_id: UsuarioId) -> Sequence[Solicitud]:
        filas = m.Solicitud.objects.filter(solicitante_id=usuario_id).order_by("id")
        return [_solicitud(f) for f in filas]

    def pendientes_de_aprobacion(self) -> Sequence[Solicitud]:
        filas = m.Solicitud.objects.filter(estado=EstadoSolicitud.PENDIENTE_APROBACION.value)
        return [_solicitud(f) for f in filas.order_by("id")]

    def abierta_de_tipo(self, colaborador_id: ColaboradorId, tipo: TipoEvento) -> Solicitud | None:
        fila = m.Solicitud.objects.filter(
            colaborador_id=colaborador_id, tipo=tipo.value, estado__in=_ABIERTOS
        ).first()
        return None if fila is None else _solicitud(fila)


class RepoColaboradores:
    def guardar(self, colaborador: Colaborador) -> None:
        try:
            with transaction.atomic():
                m.Colaborador.objects.update_or_create(
                    pk=colaborador.id, defaults=mp.colaborador_a_campos(colaborador)
                )
        except IntegrityError:
            otro = (
                m.Colaborador.objects.filter(documento=colaborador.documento.valor)
                .exclude(estado=EstadoColaborador.RETIRADO.value)
                .exclude(pk=colaborador.id)
                .first()
            )
            if otro is None:
                raise
            raise DocumentoYaRegistrado(otro.id) from None

    def obtener(self, colaborador_id: ColaboradorId) -> Colaborador | None:
        fila = m.Colaborador.objects.filter(pk=colaborador_id).first()
        return None if fila is None else mp.colaborador_de_modelo(fila)

    def por_documento(self, documento: Documento) -> Colaborador | None:
        fila = (
            m.Colaborador.objects.filter(documento=documento.valor)
            .exclude(estado=EstadoColaborador.RETIRADO.value)
            .first()
        )
        return None if fila is None else mp.colaborador_de_modelo(fila)

    def usuarios_en_uso(self) -> frozenset[str]:
        return frozenset(
            u
            for u in m.Colaborador.objects.exclude(usuario=None).values_list("usuario", flat=True)
            if u
        )

    def con_usuario_glpi(self) -> Sequence[Colaborador]:
        filas = m.Colaborador.objects.exclude(id_usuario_glpi=None).order_by("id")
        return [mp.colaborador_de_modelo(f) for f in filas]

    def subordinados_de(self, jefe_id: ColaboradorId) -> Sequence[Colaborador]:
        filas = m.Colaborador.objects.filter(jefe_id=jefe_id)
        filas = filas.exclude(estado=EstadoColaborador.RETIRADO.value)
        return [mp.colaborador_de_modelo(f) for f in filas.order_by("id")]

    def con_fin_de_contrato(self) -> Sequence[Colaborador]:
        return [
            mp.colaborador_de_modelo(f)
            for f in m.Colaborador.objects.exclude(fecha_fin=None).order_by("id")
        ]


class RepoUsuarios:
    """Usuario de Django con el id de Supabase como `username`; los roles son sus grupos."""

    def guardar(self, usuario: UsuarioDelSistema) -> None:
        cuenta, creado = User.objects.get_or_create(username=usuario.id)
        if creado:
            cuenta.set_unusable_password()  # sin contrasena local: autentica Supabase (RF-06)
        cuenta.is_active = usuario.activo
        cuenta.save()
        cuenta.groups.set([Group.objects.get_or_create(name=r.value)[0] for r in usuario.roles])
        m.PerfilDeUsuario.objects.update_or_create(
            usuario=cuenta, defaults={"colaborador_id": usuario.colaborador_id}
        )

    @staticmethod
    def _roles(cuenta: User) -> frozenset[Rol]:
        return frozenset(Rol(n) for n in cuenta.groups.values_list("name", flat=True))

    def actor_de(self, usuario_id: UsuarioId) -> Actor | None:
        cuenta = User.objects.filter(username=usuario_id, is_active=True).first()
        if cuenta is None:
            return None
        perfil = m.PerfilDeUsuario.objects.filter(usuario=cuenta).first()
        colaborador = None if perfil is None else perfil.colaborador_id
        return Actor(usuario_id, colaborador, self._roles(cuenta))

    def roles_de_colaborador(self, colaborador_id: ColaboradorId) -> frozenset[Rol]:
        roles: set[Rol] = set()
        for perfil in m.PerfilDeUsuario.objects.filter(
            colaborador_id=colaborador_id, usuario__is_active=True
        ).select_related("usuario"):
            roles |= self._roles(perfil.usuario)
        return frozenset(roles)


class RepoPerfiles:
    def guardar(self, perfil: PerfilDeAcceso) -> None:
        fila, _ = m.PerfilDeAcceso.objects.update_or_create(
            departamento=perfil.departamento,
            sede=perfil.sede,
            defaults={
                "grupos_ad": list(perfil.grupos_ad),
                "grupos_red": list(perfil.grupos_red),
                "grupos_m365": list(perfil.grupos_m365),
                "licencias": list(perfil.licencias),
                "tipo_equipo": perfil.tipo_equipo.value,
            },
        )
        fila.recursos.all().delete()
        m.RecursoPerfil.objects.bulk_create(
            m.RecursoPerfil(
                perfil=fila,
                ruta=r.ruta,
                serie=r.serie,
                perfil_de_recurso=r.perfil.value,
                grupo=r.grupo,
            )
            for r in perfil.recursos
        )

    def obtener(self, departamento: str, sede: str) -> PerfilDeAcceso | None:
        fila = m.PerfilDeAcceso.objects.filter(departamento=departamento, sede=sede).first()
        return None if fila is None else mp.perfil_de_modelo(fila)


class RepoTickets:
    def guardar(self, seguido: TicketSeguido) -> None:
        m.Ticket.objects.update_or_create(
            pk=seguido.ticket.clave_de_idempotencia, defaults=mp.ticket_a_campos(seguido)
        )

    def por_clave(self, clave: str) -> TicketSeguido | None:
        fila = m.Ticket.objects.filter(pk=clave).first()
        return None if fila is None else mp.seguido_de_modelo(fila)

    def de_solicitud(self, solicitud_id: SolicitudId) -> Sequence[TicketSeguido]:
        filas = m.Ticket.objects.filter(solicitud_id=solicitud_id.valor).order_by("clave")
        return [mp.seguido_de_modelo(f) for f in filas]

    def creados(self) -> Sequence[TicketSeguido]:
        return [
            mp.seguido_de_modelo(f)
            for f in m.Ticket.objects.exclude(id_externo=None).order_by("clave")
        ]


class RepoCuentas:
    def obtener(self, colaborador_id: ColaboradorId, sistema: SistemaDeCuenta) -> Cuenta | None:
        fila = m.Cuenta.objects.filter(colaborador_id=colaborador_id, sistema=sistema.value).first()
        return None if fila is None else mp.cuenta_de_modelo(fila)

    def guardar(self, cuenta: Cuenta) -> None:
        m.Cuenta.objects.update_or_create(
            colaborador_id=cuenta.colaborador_id,
            sistema=cuenta.sistema.value,
            defaults={
                "estado": cuenta.estado.value,
                "ticket_origen": cuenta.ticket_origen,
                "origen_emitido_en": cuenta.orden_origen[0],
                "origen_vence_en": cuenta.orden_origen[1],
                "desde": cuenta.desde,
                "marca": None if cuenta.marca is None else cuenta.marca.value,
            },
        )

    def agregar_historial(self, cambio: CambioDeCuenta) -> None:
        m.CuentaHistorial.objects.create(
            colaborador_id=cambio.colaborador_id,
            sistema=cambio.sistema.value,
            estado_anterior=None
            if cambio.estado_anterior is None
            else cambio.estado_anterior.value,
            estado_nuevo=cambio.estado_nuevo.value,
            marca_nueva=None if cambio.marca_nueva is None else cambio.marca_nueva.value,
            ticket=cambio.ticket,
            fecha=cambio.fecha,
        )

    def historial(self, colaborador_id: ColaboradorId) -> Sequence[CambioDeCuenta]:
        filas = m.CuentaHistorial.objects.filter(colaborador_id=colaborador_id).order_by("id")
        return [mp.cambio_de_modelo(f) for f in filas]


class RepoDecisiones:
    def agregar(self, decision: Decision) -> None:
        m.Decision.objects.create(
            solicitud_id=decision.solicitud_id.valor,
            tipo=decision.tipo.value,
            justificacion=decision.justificacion,
            usuario_id=decision.usuario_id,
            fecha=decision.fecha,
        )

    def de_solicitud(self, solicitud_id: SolicitudId) -> Sequence[Decision]:
        filas = m.Decision.objects.filter(solicitud_id=solicitud_id.valor).order_by("id")
        return [mp.decision_de_modelo(f) for f in filas]


class RepoSoportes:
    def guardar(self, soporte: Soporte) -> None:
        m.Soporte.objects.update_or_create(
            solicitud_id=soporte.solicitud_id.valor,
            defaults={
                "nombre_original": soporte.nombre_original.valor,
                "tamano": soporte.tamano,
                "sha256": soporte.sha256.valor,
                "nombre_almacenado": soporte.nombre_almacenado,
                "estado": soporte.estado.value,
                "id_documento_glpi": soporte.id_documento_glpi,
            },
        )

    def obtener(self, solicitud_id: SolicitudId) -> Soporte | None:
        fila = m.Soporte.objects.filter(solicitud_id=solicitud_id.valor).first()
        return None if fila is None else mp.soporte_de_modelo(fila)


class RepoBandeja:
    def encolar(self, entradas: Sequence[EntradaDeBandeja]) -> None:
        for e in entradas:
            m.EntradaDeBandeja.objects.get_or_create(  # idempotente por clave
                ticket_id=e.clave,
                defaults={
                    "estado": e.estado.value,
                    "intentos": e.intentos,
                    "proximo_intento": e.proximo_intento,
                    "ultimo_error": e.ultimo_error,
                },
            )

    def guardar(self, entrada: EntradaDeBandeja) -> None:
        m.EntradaDeBandeja.objects.update_or_create(
            ticket_id=entrada.clave,
            defaults={
                "estado": entrada.estado.value,
                "intentos": entrada.intentos,
                "proximo_intento": entrada.proximo_intento,
                "ultimo_error": entrada.ultimo_error,
            },
        )

    def vencidas(self, ahora: datetime, limite: int) -> Sequence[EntradaDeBandeja]:
        filas = (
            m.EntradaDeBandeja.objects.filter(
                estado=EstadoDeEntrada.PENDIENTE.value, proximo_intento__lte=ahora
            )
            .select_related("ticket")
            .order_by("proximo_intento", "ticket_id")[:limite]
        )
        return [mp.entrada_de_modelo(f) for f in filas]

    def obtener(self, clave: str) -> EntradaDeBandeja | None:
        fila = m.EntradaDeBandeja.objects.filter(ticket_id=clave).select_related("ticket").first()
        return None if fila is None else mp.entrada_de_modelo(fila)

    def de_solicitud(self, solicitud_id: SolicitudId) -> Sequence[EntradaDeBandeja]:
        filas = (
            m.EntradaDeBandeja.objects.filter(ticket__solicitud_id=solicitud_id.valor)
            .select_related("ticket")
            .order_by("ticket_id")
        )
        return [mp.entrada_de_modelo(f) for f in filas]


class RepoActivos:
    def reemplazar(
        self,
        colaborador_id: ColaboradorId,
        activos: Sequence[ActivoAsignado],
        licencias: Sequence[LicenciaAsignada],
    ) -> None:
        m.ActivoAsignado.objects.filter(colaborador_id=colaborador_id).delete()
        m.LicenciaAsignada.objects.filter(colaborador_id=colaborador_id).delete()
        m.ActivoAsignado.objects.bulk_create(
            m.ActivoAsignado(
                colaborador_id=colaborador_id,
                id_glpi=a.id_glpi,
                tipo=a.tipo,
                serie=a.serie,
                modelo=a.modelo,
                asignado_desde=a.asignado_desde,
                tiene_acta=a.tiene_acta,
            )
            for a in activos
        )
        m.LicenciaAsignada.objects.bulk_create(
            m.LicenciaAsignada(
                colaborador_id=colaborador_id,
                id_glpi=lic.id_glpi,
                software=lic.software,
                licencia=lic.licencia,
            )
            for lic in licencias
        )

    def activos_de(self, colaborador_id: ColaboradorId) -> Sequence[ActivoAsignado]:
        return [
            ActivoAsignado(f.id_glpi, f.tipo, f.serie, f.modelo, f.asignado_desde, f.tiene_acta)
            for f in m.ActivoAsignado.objects.filter(colaborador_id=colaborador_id).order_by("id")
        ]

    def licencias_de(self, colaborador_id: ColaboradorId) -> Sequence[LicenciaAsignada]:
        return [
            LicenciaAsignada(f.id_glpi, f.software, f.licencia)
            for f in m.LicenciaAsignada.objects.filter(colaborador_id=colaborador_id).order_by("id")
        ]


class RepoSincronizaciones:
    def registrar(self, resultado: ResultadoDeSincronizacion) -> None:
        m.Sincronizacion.objects.create(
            inicio=resultado.inicio,
            fin=resultado.fin,
            resultado=resultado.resultado,
            tickets_leidos=resultado.tickets_leidos,
            errores=resultado.errores,
        )

    def ultima(self) -> ResultadoDeSincronizacion | None:
        f = m.Sincronizacion.objects.order_by("-id").first()
        return None if f is None else consultas.sincronizacion_de_modelo(f)


def _datos_auditables(datos: object) -> dict[str, ValorAuditable]:
    """JSON -> datos de auditoria: las listas vuelven a tuplas (el formato canonico es el mismo)."""
    salida: dict[str, ValorAuditable] = {}
    if not isinstance(datos, dict):
        return salida
    for clave, valor in datos.items():
        if isinstance(valor, list):
            salida[str(clave)] = tuple(
                v if v is None or isinstance(v, str | int | bool) else str(v) for v in valor
            )
        elif valor is None or isinstance(valor, str | int | bool):
            salida[str(clave)] = valor
        else:
            salida[str(clave)] = str(valor)
    return salida


def registro_de_modelo(f: m.RegistroDeAuditoria) -> RegistroDeAuditoria:
    return RegistroDeAuditoria(
        secuencia=f.secuencia,
        fecha=f.fecha,
        actor=f.actor,
        accion=f.accion,
        objeto=f.objeto,
        datos=_datos_auditables(f.datos),
        hash_anterior=f.hash_anterior,
        hash=f.hash,
    )


class AuditoriaDjango:
    """Unica via de escritura de la cadena (invariante 4).

    Bloquea una fila candado antes de leer el ultimo registro: dos transacciones concurrentes
    no pueden encadenar sobre el mismo `hash_anterior` y bifurcar la cadena.
    """

    def __init__(self, reloj: Reloj) -> None:
        self._reloj = reloj

    def registrar(self, actor: str, evento: EventoDeAuditoria) -> RegistroDeAuditoria:
        m.Consecutivo.objects.select_for_update().get_or_create(clave=_CANDADO_DE_AUDITORIA)
        ultimo = m.RegistroDeAuditoria.objects.order_by("-secuencia").first()
        anterior = None if ultimo is None else registro_de_modelo(ultimo)
        r = encadenar(anterior, self._reloj.ahora(), actor, evento)
        m.RegistroDeAuditoria.objects.create(
            secuencia=r.secuencia,
            fecha=r.fecha,
            actor=r.actor,
            accion=r.accion,
            objeto=r.objeto,
            datos={k: list(v) if isinstance(v, tuple) else v for k, v in r.datos.items()},
            hash_anterior=r.hash_anterior,
            hash=r.hash,
        )
        return r

    def registros(self) -> Sequence[RegistroDeAuditoria]:
        return tuple(
            registro_de_modelo(f) for f in m.RegistroDeAuditoria.objects.order_by("secuencia")
        )

    def verificar(self) -> ResultadoDeVerificacion:
        return verificar_cadena(self.registros())


class UnidadDeTrabajoDjango:
    """Transaccion atomica de Django: si el bloque lanza, se deshace todo (CA-02)."""

    def __init__(self, reloj: Reloj) -> None:
        self.solicitudes = RepoSolicitudes()
        self.colaboradores = RepoColaboradores()
        self.usuarios = RepoUsuarios()
        self.perfiles = RepoPerfiles()
        self.tickets = RepoTickets()
        self.cuentas = RepoCuentas()
        self.decisiones = RepoDecisiones()
        self.soportes = RepoSoportes()
        self.bandeja = RepoBandeja()
        self.activos = RepoActivos()
        self.sincronizaciones = RepoSincronizaciones()
        self.auditoria = AuditoriaDjango(reloj)
        self._atomico = transaction.atomic()

    def __enter__(self) -> Self:
        self._atomico.__enter__()
        return self

    def __exit__(
        self,
        tipo: type[BaseException] | None,
        error: BaseException | None,
        traza: TracebackType | None,
    ) -> None:
        self._atomico.__exit__(tipo, error, traza)


class RepositoriosDjango:
    def __init__(self, reloj: Reloj) -> None:
        self._reloj = reloj

    def unidad_de_trabajo(self) -> UnidadDeTrabajoDjango:
        return UnidadDeTrabajoDjango(self._reloj)

    def indicadores(self, ahora: datetime) -> Indicadores:
        return consultas.indicadores(ahora)

    def buscar_cuentas(self, filtro: FiltroDeCuentas) -> PaginaDeCuentas:
        return consultas.buscar_cuentas(filtro)

    def ficha(self, colaborador_id: ColaboradorId) -> FichaDeColaborador | None:
        return consultas.ficha(colaborador_id)
