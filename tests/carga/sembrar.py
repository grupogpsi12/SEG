"""Semilla para RNF-06: 300 colaboradores con su historia, emitidos con los casos de uso reales.

Corre dentro de la imagen de la aplicación contra la base DESECHABLE de `infra/scripts/carga.sh`.
Usa el `Mundo` de las pruebas con los repositorios de Django: los tickets van al GLPI en memoria
(el GLPI real no se toca) y vuelven por la misma sincronización que en producción, de modo que
tickets, cuentas, colaboradores y auditoría quedan como los dejaría el sistema.

    python -m tests.carga.sembrar 300
"""

import json
import sys
import time
from datetime import timedelta

import django

django.setup()

from jml.adaptadores.salida.persistencia.repositorios import RepositoriosDjango  # noqa: E402
from jml.dominio.tipos import Subtipo, TipoDeVinculacion  # noqa: E402
from tests.fabricas import MATRIZ, SEDES  # noqa: E402
from tests.mundo import Mundo, emergencia, ingreso, retiro, vacaciones  # noqa: E402

NOMBRES = ("Ana", "Bruno", "Carla", "Diego", "Elena", "Fabio", "Gloria", "Hugo", "Inés", "Julián")
APELLIDOS = ("Rojas", "Pérez", "Gómez", "Ruiz", "Díaz", "Mora", "Vargas", "Castro", "Ortiz", "León")


def sembrar(cantidad: int) -> dict[str, object]:
    inicio = time.monotonic()
    m = Mundo.nuevo(repositorios=RepositoriosDjango)
    departamentos = sorted(MATRIZ)
    nuevos: list[str] = []
    for i in range(cantidad):
        r = m.emitir(
            ingreso(
                nombres=NOMBRES[i % len(NOMBRES)],
                apellidos=f"{APELLIDOS[(i // len(NOMBRES)) % len(APELLIDOS)]} {i:03d}",
                documento=str(81_000_000 + i),
                departamento=departamentos[i % len(departamentos)],
                sede=SEDES[i % len(SEDES)],
                requiere_equipo=i % 2 == 0,
                vinculacion=TipoDeVinculacion.EMPLEADO if i % 5 else TipoDeVinculacion.CONTRATISTA,
                dias=1 + i % 20,
            )
        )
        nuevos.append(r.colaborador_id)
    m.correr_bandeja_hasta_vaciar(maximo=200)
    # Dos de cada tres ingresos ya los resolvió TI: sus cuentas pasan a `activa` al sincronizar.
    with m.puerto.unidad_de_trabajo() as u:
        abiertas = [s.id for c in nuevos for s in u.solicitudes.de_colaborador(c)]
    for n, sid in enumerate(abiertas):
        if n % 3:
            m.tecnico_resuelve_todo(sid)
    m.sincronizar()
    m.sincronizar_activos()
    # Movimiento posterior sobre los activos: vacaciones, retiros y algunas emergencias.
    activos = [c for n, c in enumerate(nuevos) if n % 3]
    otros = []
    for n, c in enumerate(activos[:60]):
        v = vacaciones("u-rrhh", c, 2 + n % 10, 15 + n % 10, justificacion="Vacaciones aprobadas")
        otros.append(m.emitir(v))
    for n, c in enumerate(activos[60:90]):
        sub = Subtipo.RENUNCIA if n % 2 else Subtipo.FIN_DE_CONTRATO
        otros.append(m.emitir(retiro("u-rrhh", c, subtipo=sub, dias=3 + n % 15)))
    for c in activos[90:96]:
        otros.append(m.emitir(emergencia("u-rrhh", c)))
    m.correr_bandeja_hasta_vaciar(maximo=200)
    for n, r in enumerate(otros):
        if n % 2:
            m.tecnico_resuelve_todo(r.solicitud_id)
    m.avanzar(timedelta(hours=3))  # las emergencias abiertas acumulan exposición
    m.sincronizar()
    with m.puerto.unidad_de_trabajo() as u:
        auditoria = len(u.auditoria.registros())
        valida = u.auditoria.verificar().valida
    return {
        "colaboradores_nuevos": len(nuevos),
        "eventos_posteriores": len(otros),
        "registros_de_auditoria": auditoria,
        "cadena_valida": valida,
        "colaborador_de_ejemplo": activos[0],
        "solicitud_de_ejemplo": otros[0].solicitud_id.valor,
        "segundos": round(time.monotonic() - inicio, 1),
    }


if __name__ == "__main__":
    print(json.dumps(sembrar(int(sys.argv[1]) if len(sys.argv) > 1 else 300)))
