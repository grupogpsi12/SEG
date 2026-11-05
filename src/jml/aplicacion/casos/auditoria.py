"""RF-36: el Auditor consulta y verifica la cadena (CA-09); RD-04: exportacion diaria."""

import json
from dataclasses import dataclass
from datetime import date

from jml.aplicacion.dtos import PaginaDeAuditoria
from jml.aplicacion.puertos import Repositorios
from jml.dominio.auditoria import HASH_GENESIS, EventoDeAuditoria, ResultadoDeVerificacion
from jml.dominio.errores import DatoInvalido, NoAutorizado
from jml.dominio.permisos import puede_consultar_auditoria
from jml.dominio.valores import hoy_en_bogota

TAMANO_DE_PAGINA = 50


def _exigir_auditor(repos: Repositorios, usuario_id: str) -> None:
    with repos.unidad_de_trabajo() as uow:
        actor = uow.usuarios.actor_de(usuario_id)
    if actor is None or not puede_consultar_auditoria(actor.roles):
        raise NoAutorizado("auditoria", "solo el Auditor consulta la auditoria")


class ConsultarAuditoria:
    def __init__(self, repos: Repositorios) -> None:
        self._repos = repos

    def ejecutar(self, usuario_id: str, pagina: int = 1) -> PaginaDeAuditoria:
        if pagina < 1:
            raise DatoInvalido("pagina", "empieza en 1")
        _exigir_auditor(self._repos, usuario_id)
        # ADR-030: solo el tramo de la pagina; la cadena crece sin limite.
        with self._repos.unidad_de_trabajo() as uow:
            total = uow.auditoria.total()
            inicio = total - pagina * TAMANO_DE_PAGINA
            tramo = uow.auditoria.tramo(max(inicio, 0), max(inicio + TAMANO_DE_PAGINA, 0))
        return PaginaDeAuditoria(tuple(reversed(tramo)), total, pagina, TAMANO_DE_PAGINA)


class VerificarAuditoria:
    """Recorre la cadena completa. La verificacion misma queda auditada, con su resultado."""

    def __init__(self, repos: Repositorios) -> None:
        self._repos = repos

    def ejecutar(self, usuario_id: str) -> ResultadoDeVerificacion:
        _exigir_auditor(self._repos, usuario_id)
        with self._repos.unidad_de_trabajo() as uow:
            resultado = uow.auditoria.verificar()
            uow.auditoria.registrar(
                usuario_id,
                EventoDeAuditoria(
                    "auditoria.verificada",
                    "cadena",
                    {"valida": resultado.valida, "primer_afectado": resultado.primer_afectado or 0},
                ),
            )
        return resultado


@dataclass(frozen=True, slots=True)
class ExportacionDeAuditoria:
    """RD-04: lo que el worker escribe cada dia para la copia fuera del equipo.

    `lineas` son los registros del dia en su forma canonica con sus hashes (verificables sin la
    base); `ancla_*` es la cabeza de TODA la cadena en el momento de exportar. Guardada fuera de la
    base, el ancla delata una reescritura completa de la cadena (revision externa H1, punto 3).
    """

    dia: date
    lineas: tuple[str, ...]
    ancla_secuencia: int
    ancla_hash: str
    cadena_valida: bool


class ExportarAuditoria:
    def __init__(self, repos: Repositorios) -> None:
        self._repos = repos

    def ejecutar(self, dia: date) -> ExportacionDeAuditoria:
        with self._repos.unidad_de_trabajo() as uow:
            registros = uow.auditoria.registros()
            verificacion = uow.auditoria.verificar()
        del_dia = [r for r in registros if hoy_en_bogota(r.fecha) == dia]
        lineas = tuple(
            json.dumps(
                {
                    "registro": json.loads(r.contenido()),
                    "hash_anterior": r.hash_anterior,
                    "hash": r.hash,
                },
                sort_keys=True,
                ensure_ascii=False,
            )
            for r in del_dia
        )
        ultimo = registros[-1] if registros else None
        return ExportacionDeAuditoria(
            dia,
            lineas,
            ultimo.secuencia if ultimo else 0,
            ultimo.hash if ultimo else HASH_GENESIS,
            verificacion.valida,
        )
