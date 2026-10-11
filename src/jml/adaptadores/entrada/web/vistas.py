"""Vistas. Solo validan el formulario, verifican el rol y llaman a un caso de uso (CLAUDE.md).

La identidad llega en la sesion de Django (`usuario_id`), que `ingreso.py` crea solo despues de
verificar el TOTP (AAL2). Sin sesion, o con una sesion vencida, se redirige al ingreso.
"""

import logging
from collections.abc import Callable
from functools import wraps
from typing import Any

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, connections
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from jml.adaptadores.entrada.web import composicion
from jml.adaptadores.entrada.web.formularios import (
    ETIQUETAS_DE_TIPO,
    FORMULARIOS,
    FormularioDeJustificacion,
)
from jml.adaptadores.entrada.web.mensajes import texto_del_error
from jml.aplicacion.dtos import (
    NuevaSolicitud,
    PerfilDeUsuario,
    ResultadoDeDecision,
    SolicitudRegistrada,
)
from jml.dominio.errores import (
    DatoInvalido,
    ErrorDeDominio,
    NoAutorizado,
    NoEncontrado,
    RolesIncompatibles,
)
from jml.dominio.permisos import puede_ver_dashboard
from jml.dominio.tipos import EstadoSolicitud, Rol, TipoEvento
from jml.dominio.valores import SolicitudId, hoy_en_bogota

registro = logging.getLogger(__name__)

SESION_USUARIO = "usuario_id"
SESION_INICIO = "inicio"  # epoch del ingreso: RF-04, 8 horas como maximo
EMISORES = frozenset({Rol.RRHH, Rol.ADMINISTRADOR})  # RRHH emite; el Administrador, por excepcion

type VistaConPerfil = Callable[..., HttpResponse]


@require_GET
def salud(request: HttpRequest) -> JsonResponse:
    """RNF-01: el chequeo de salud de `web` verifica la conexion con la base de datos.

    Responde sin detalles internos (RNF-02); el error real va al log con su correlation_id.
    """
    try:
        connections["default"].ensure_connection()
    except DatabaseError:
        registro.exception("la base de datos no responde")
        return JsonResponse({"estado": "no_disponible"}, status=503)
    return JsonResponse({"estado": "ok"})


def con_sesion(vista: VistaConPerfil) -> VistaConPerfil:
    """Exige sesion y pasa el perfil vigente (roles de la base, no los de la sesion: RF-05)."""

    @wraps(vista)
    def envoltura(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        usuario_id = request.session.get(SESION_USUARIO)
        inicio = request.session.get(SESION_INICIO)
        if not usuario_id or not isinstance(inicio, int | float):
            return redirect(settings.LOGIN_URL)
        if composicion.reloj().ahora().timestamp() - inicio > settings.JML_SESION_MAXIMA_S:
            request.session.flush()  # RF-04: 8 horas de duracion total
            return redirect(settings.LOGIN_URL)
        try:
            perfil = composicion.casos().mi_perfil.ejecutar(usuario_id)
        except (NoAutorizado, RolesIncompatibles):  # desactivado o roles cambiados: RF-05
            request.session.flush()
            return redirect(settings.LOGIN_URL)
        return vista(request, perfil, *args, **kwargs)

    return envoltura


def _contexto(perfil: PerfilDeUsuario, **extra: Any) -> dict[str, Any]:
    return {
        "perfil": perfil,
        "es_rrhh": Rol.RRHH in perfil.roles,
        "es_tecnico": puede_ver_dashboard(perfil.roles),
        **extra,
    }


def _tipos_disponibles(perfil: PerfilDeUsuario, hay_subordinados: bool) -> list[TipoEvento]:
    if perfil.roles & EMISORES:
        return list(TipoEvento)
    if Rol.SOLICITANTE not in perfil.roles:
        return []
    disponibles: list[TipoEvento] = []
    if perfil.colaborador is not None:
        disponibles += [TipoEvento.VAC, TipoEvento.RET]
    if hay_subordinados:
        disponibles += [TipoEvento.CDP, TipoEvento.CSU]
    return disponibles


@require_GET
def inicio(request: HttpRequest) -> HttpResponse:
    return redirect("solicitudes")


@require_GET
@con_sesion
def solicitudes(request: HttpRequest, perfil: PerfilDeUsuario) -> HttpResponse:
    filas = composicion.casos().mis_solicitudes.ejecutar(perfil.usuario_id)
    return render(request, "web/solicitudes.html", _contexto(perfil, filas=filas))


@require_GET
@con_sesion
def nueva_indice(request: HttpRequest, perfil: PerfilDeUsuario) -> HttpResponse:
    hay = bool(composicion.casos().subordinados.ejecutar(perfil.usuario_id))
    tipos = [(t.value, ETIQUETAS_DE_TIPO[t]) for t in _tipos_disponibles(perfil, hay)]
    return render(request, "web/nueva_indice.html", _contexto(perfil, tipos=tipos))


@require_http_methods(["GET", "POST"])
@con_sesion
def nueva(request: HttpRequest, perfil: PerfilDeUsuario, tipo: str) -> HttpResponse:
    try:
        evento = TipoEvento(tipo)
    except ValueError:
        raise Http404 from None
    casos = composicion.casos()
    subordinados = casos.subordinados.ejecutar(perfil.usuario_id)
    if evento not in _tipos_disponibles(perfil, bool(subordinados)):
        raise PermissionDenied
    emision = bool(perfil.roles & EMISORES)
    formulario = FORMULARIOS[evento](
        request.POST or None, request.FILES or None, emision=emision, subordinados=subordinados
    )
    estado = 200
    if request.method == "POST" and formulario.is_valid():
        try:
            registrada = _enviar(casos, perfil, evento, formulario, emision)
        except NoAutorizado as e:
            formulario.add_error(None, texto_del_error(e))
            estado = 403
        except ErrorDeDominio as e:
            formulario.add_error(None, texto_del_error(e))
        else:
            if registrada is not None:
                messages.success(request, registrada)
                return redirect("solicitudes")
    return render(
        request,
        "web/nueva.html",
        _contexto(perfil, formulario=formulario, titulo=ETIQUETAS_DE_TIPO[evento]),
        status=estado,
    )


def _enviar(
    casos: composicion.Casos,
    perfil: PerfilDeUsuario,
    evento: TipoEvento,
    formulario: Any,
    emision: bool,
) -> str | None:
    """Resuelve a quien afecta la solicitud y llama al caso. `None`: el error quedo en el form."""
    if emision and evento is not TipoEvento.ING:
        encontrado = casos.colaborador_por_documento.ejecutar(
            perfil.usuario_id, formulario.documento_buscado()
        )
        if encontrado is None:
            formulario.add_error(
                "documento_del_colaborador", "No hay un colaborador con ese documento."
            )
            return None
        sujeto: str | None = encontrado.colaborador_id
    elif emision:
        sujeto = None  # el ingreso crea a la persona
    elif evento in (TipoEvento.CDP, TipoEvento.CSU):
        sujeto = formulario.colaborador_elegido()
    else:
        sujeto = perfil.colaborador.colaborador_id if perfil.colaborador else None
    # S-03: la emergencia es efectiva el dia de la emision; el formulario no la pregunta.
    hoy = hoy_en_bogota(composicion.reloj().ahora()) if evento is TipoEvento.EMG else None
    peticion = formulario.a_nueva_solicitud(perfil.usuario_id, sujeto, hoy)
    caso: Callable[[NuevaSolicitud], SolicitudRegistrada]
    if not emision:
        caso = casos.registrar.ejecutar
    elif Rol.RRHH in perfil.roles:
        caso = casos.emitir.ejecutar
    else:
        caso = casos.emitir_por_excepcion.ejecutar
    r = caso(peticion)
    if r.estado is EstadoSolicitud.PENDIENTE_APROBACION:
        return f"Solicitud {r.solicitud_id} registrada: queda pendiente de aprobación de RRHH."
    return (
        f"Solicitud {r.solicitud_id} emitida: se enviaron {r.tickets_encolados} tickets a la cola."
    )


@require_GET
@con_sesion
def detalle(request: HttpRequest, perfil: PerfilDeUsuario, solicitud: str) -> HttpResponse:
    """2.8: el campo restringido solo llega lleno para RRHH; la pagina no se guarda en cache."""
    try:
        d = composicion.casos().consultar_solicitud.ejecutar(
            perfil.usuario_id, SolicitudId(solicitud)
        )
    except (DatoInvalido, NoEncontrado):
        raise Http404 from None
    respuesta = render(request, "web/detalle.html", _contexto(perfil, d=d))
    if d.restringido is not None:
        respuesta["Cache-Control"] = "no-store"
    return respuesta


@require_GET
@con_sesion
def bandeja(request: HttpRequest, perfil: PerfilDeUsuario) -> HttpResponse:
    casos = composicion.casos()
    try:
        filas = casos.pendientes.ejecutar(perfil.usuario_id)
        contratos = casos.contratos_por_vencer.ejecutar(perfil.usuario_id)
    except NoAutorizado:
        raise PermissionDenied from None
    return render(request, "web/bandeja.html", _contexto(perfil, filas=filas, contratos=contratos))


@require_POST
@con_sesion
def decidir(
    request: HttpRequest, perfil: PerfilDeUsuario, solicitud: str, accion: str
) -> HttpResponse:
    try:
        solicitud_id = SolicitudId(solicitud)
    except DatoInvalido:
        raise Http404 from None
    casos = composicion.casos()
    caso: Callable[[str, SolicitudId, str | None], ResultadoDeDecision] = {
        "aprobar": casos.aprobar.ejecutar,
        "rechazar": casos.rechazar.ejecutar,
        "cancelar": casos.cancelar.ejecutar,
    }[accion]
    destino = "bandeja" if accion != "cancelar" and Rol.RRHH in perfil.roles else "solicitudes"
    justificacion = FormularioDeJustificacion(request.POST)
    if not justificacion.is_valid():
        messages.error(request, "La justificación no puede superar los 500 caracteres.")
        return redirect(destino)
    try:
        caso(perfil.usuario_id, solicitud_id, justificacion.cleaned_data["justificacion"] or None)
    except ErrorDeDominio as e:
        messages.error(request, texto_del_error(e))
    else:
        hecho = {"aprobar": "aprobada", "rechazar": "rechazada", "cancelar": "cancelada"}[accion]
        messages.success(request, f"Solicitud {solicitud_id} {hecho}.")
    return redirect(destino)
