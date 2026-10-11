"""Raiz de composicion de la entrada web: arma los casos de uso con los adaptadores reales.

Es el UNICO lugar de la capa web que conoce las implementaciones concretas. Las vistas piden
`casos()` y no importan repositorios ni modelos. Las pruebas reemplazan `reloj`, el directorio
de soportes y el proveedor de identidad sin tocar las vistas.
"""

import uuid
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from django.conf import settings

from jml.adaptadores.salida.identidad.supabase import ProveedorSupabase
from jml.adaptadores.salida.persistencia.repositorios import RepositoriosDjango
from jml.adaptadores.salida.reloj import RelojDelSistema
from jml.adaptadores.salida.soportes import AlmacenDeSoportesEnDisco
from jml.aplicacion.casos._alta import DependenciasDeAlta
from jml.aplicacion.casos.consultas import ContratosPorVencer, DependenciasDeConsulta
from jml.aplicacion.casos.decidir import (
    AprobarSolicitud,
    CancelarSolicitud,
    DependenciasDeDecision,
    RechazarSolicitud,
)
from jml.aplicacion.casos.emitir import EmitirPorExcepcion, EmitirSolicitud
from jml.aplicacion.casos.ingreso import (
    CompletarIngreso,
    DependenciasDeIngreso,
    IniciarIngreso,
    InscribirTotp,
)
from jml.aplicacion.casos.listados import (
    ColaboradorPorDocumento,
    ConsultarSolicitud,
    MiPerfil,
    MisSolicitudes,
    PendientesDeAprobacion,
    SubordinadosDe,
)
from jml.aplicacion.casos.registrar import RegistrarSolicitud
from jml.aplicacion.puertos import ProveedorDeIdentidad, Reloj
from jml.dominio.valores import CalendarioHabil


def reloj() -> Reloj:
    return RelojDelSistema()


def directorio_de_soportes() -> Path:
    return Path(settings.JML_SOPORTES_DIR)


@cache
def proveedor_de_identidad() -> ProveedorDeIdentidad:
    """UNO por proceso: guarda en memoria los desafios TOTP a medio camino (invariante 9)."""
    return ProveedorSupabase(settings.JML_SUPABASE_URL, settings.JML_SUPABASE_CLAVE_PUBLICA)


@dataclass(frozen=True, slots=True)
class Casos:
    registrar: RegistrarSolicitud
    emitir: EmitirSolicitud
    emitir_por_excepcion: EmitirPorExcepcion
    aprobar: AprobarSolicitud
    rechazar: RechazarSolicitud
    cancelar: CancelarSolicitud
    mis_solicitudes: MisSolicitudes
    pendientes: PendientesDeAprobacion
    subordinados: SubordinadosDe
    mi_perfil: MiPerfil
    consultar_solicitud: ConsultarSolicitud
    colaborador_por_documento: ColaboradorPorDocumento
    contratos_por_vencer: ContratosPorVencer
    iniciar_ingreso: IniciarIngreso
    inscribir_totp: InscribirTotp
    completar_ingreso: CompletarIngreso


def casos() -> Casos:
    r = reloj()
    repos = RepositoriosDjango(r)
    soportes = AlmacenDeSoportesEnDisco(directorio_de_soportes())
    calendario = CalendarioHabil()  # los festivos entran como datos cuando RRHH los cargue (S-01)
    alta = DependenciasDeAlta(repos, soportes, r, calendario, lambda: uuid.uuid4().hex)
    decision = DependenciasDeDecision(repos, r, calendario, soportes)
    identidad = proveedor_de_identidad()
    return Casos(
        registrar=RegistrarSolicitud(alta),
        emitir=EmitirSolicitud(alta),
        emitir_por_excepcion=EmitirPorExcepcion(alta),
        aprobar=AprobarSolicitud(decision),
        rechazar=RechazarSolicitud(decision),
        cancelar=CancelarSolicitud(decision),
        mis_solicitudes=MisSolicitudes(repos),
        pendientes=PendientesDeAprobacion(repos),
        subordinados=SubordinadosDe(repos),
        mi_perfil=MiPerfil(repos),
        consultar_solicitud=ConsultarSolicitud(repos),
        colaborador_por_documento=ColaboradorPorDocumento(repos),
        contratos_por_vencer=ContratosPorVencer(DependenciasDeConsulta(repos, r)),
        iniciar_ingreso=IniciarIngreso(identidad),
        inscribir_totp=InscribirTotp(identidad),
        completar_ingreso=CompletarIngreso(DependenciasDeIngreso(identidad, repos)),
    )
