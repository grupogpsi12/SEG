"""RF-36: el Auditor consulta la auditoria y verifica la cadena (CA-09). Solo el rol Auditor."""

from jml.aplicacion.dtos import PaginaDeAuditoria
from jml.aplicacion.puertos import Repositorios
from jml.dominio.auditoria import EventoDeAuditoria, ResultadoDeVerificacion
from jml.dominio.errores import DatoInvalido, NoAutorizado
from jml.dominio.permisos import puede_consultar_auditoria

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
        with self._repos.unidad_de_trabajo() as uow:
            todos = uow.auditoria.registros()
        inicio = len(todos) - pagina * TAMANO_DE_PAGINA
        tramo = todos[max(inicio, 0) : max(inicio + TAMANO_DE_PAGINA, 0)]
        return PaginaDeAuditoria(tuple(reversed(tramo)), len(todos), pagina, TAMANO_DE_PAGINA)


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
