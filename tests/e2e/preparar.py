"""Datos y sesiones para las pruebas de la interfaz (item 5.8), en la base del stack de PRUEBAS.

Corre dentro del servicio `web` (`docker compose run`), con su red y sus secretos. En cada corrida
crea colaboradores nuevos, con documentos aleatorios: un retiro o una emergencia los deja
retirados, y la deduplicación (invariante 2) no dejaría repetir sobre los mismos.

Las sesiones equivalen a alguien que ya pasó el TOTP (`ingreso.py` guarda `usuario_id` e
`inicio`). El ingreso real con TOTP se probó de punta a punta aparte (docs/estado.md). Imprime un
JSON con las sesiones y los documentos.
"""

import json
import secrets
import uuid
from datetime import date

import django

django.setup()

from django.contrib.sessions.backends.db import SessionStore  # noqa: E402

from jml.adaptadores.entrada.web.vistas import SESION_INICIO, SESION_USUARIO  # noqa: E402
from jml.adaptadores.salida.persistencia.repositorios import RepositoriosDjango  # noqa: E402
from jml.adaptadores.salida.reloj import RelojDelSistema  # noqa: E402
from jml.dominio.colaborador import Colaborador  # noqa: E402
from jml.dominio.permisos import UsuarioDelSistema  # noqa: E402
from jml.dominio.tipos import EstadoColaborador, Rol, TipoDeVinculacion  # noqa: E402
from jml.dominio.valores import Documento, Usuario  # noqa: E402


def _sesion(usuario_id: str) -> str:
    sesion = SessionStore()
    sesion[SESION_USUARIO] = usuario_id
    sesion[SESION_INICIO] = RelojDelSistema().ahora().timestamp()
    sesion.create()
    assert sesion.session_key is not None
    return sesion.session_key


def preparar() -> dict[str, object]:
    marca = secrets.token_hex(3)
    personas = []
    with RepositoriosDjango(RelojDelSistema()).unidad_de_trabajo() as u:
        for n, depto in enumerate(("Finanzas", "Comercial", "Operaciones")):
            documento = str(90_000_000 + secrets.randbelow(9_000_000))
            c = Colaborador(
                id=f"e2e-{marca}-{n}",
                documento=Documento(documento),
                nombres="Prueba",
                apellidos=f"Interfaz {marca} {n}",
                vinculacion=TipoDeVinculacion.EMPLEADO,
                departamento=depto,
                cargo="Analista",
                sede="Bogotá",
                jefe_id=None,
                fecha_ingreso=date(2025, 1, 15),
                fecha_fin=None,
                estado=EstadoColaborador.ACTIVO,
                usuario=Usuario(f"prueba.{marca}{n}"),  # como lo deja un ingreso
            )
            u.colaboradores.guardar(c)
            personas.append(c)
        rrhh = str(uuid.uuid4())
        solicitante = str(uuid.uuid4())
        u.usuarios.guardar(UsuarioDelSistema(rrhh, None, frozenset({Rol.RRHH})))
        u.usuarios.guardar(
            UsuarioDelSistema(solicitante, personas[0].id, frozenset({Rol.SOLICITANTE}))
        )
    return {
        "marca": marca,
        "sesion_rrhh": _sesion(rrhh),
        "sesion_solicitante": _sesion(solicitante),
        "documento_vac": personas[0].documento.valor,
        "documento_ret": personas[1].documento.valor,
        "documento_emg": personas[2].documento.valor,
        "documento_ing": str(80_000_000 + secrets.randbelow(9_000_000)),
    }


if __name__ == "__main__":
    print(json.dumps(preparar()))
