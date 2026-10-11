"""Raiz de composicion de la entrada web: arma los casos de uso con los adaptadores reales.

Es el UNICO lugar de la capa web que conoce las implementaciones concretas. Las vistas piden
`casos()` y no importan repositorios ni modelos. Las pruebas reemplazan `reloj` y el directorio
de soportes sin tocar las vistas.
"""

import uuid
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

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
from jml.aplicacion.casos.listados import (
    ColaboradorPorDocumento,
    MiPerfil,
    MisSolicitudes,
    PendientesDeAprobacion,
    SubordinadosDe,
)
from jml.aplicacion.casos.registrar import RegistrarSolicitud
from jml.aplicacion.puertos import Reloj
from jml.dominio.valores import CalendarioHabil


def reloj() -> Reloj:
    return RelojDelSistema()


def directorio_de_soportes() -> Path:
    return Path(settings.JML_SOPORTES_DIR)


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
    colaborador_por_documento: ColaboradorPorDocumento
    contratos_por_vencer: ContratosPorVencer


def casos() -> Casos:
    r = reloj()
    repos = RepositoriosDjango(r)
    soportes = AlmacenDeSoportesEnDisco(directorio_de_soportes())
    calendario = CalendarioHabil()  # los festivos entran como datos cuando RRHH los cargue (S-01)
    alta = DependenciasDeAlta(repos, soportes, r, calendario, lambda: uuid.uuid4().hex)
    decision = DependenciasDeDecision(repos, r, calendario, soportes)
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
        colaborador_por_documento=ColaboradorPorDocumento(repos),
        contratos_por_vencer=ContratosPorVencer(DependenciasDeConsulta(repos, r)),
    )
