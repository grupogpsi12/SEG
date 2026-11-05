"""Verifica que el sistema cumple las ocho funciones de la TABLA I del Anexo A («Matriz de funcionalidades»).

    python auditoria/scripts/verificar-anexo-a.py

Por cada función ejecuta las pruebas que la ejercitan (no solo las nombra) y comprueba por lectura del
código los puntos de su descripción que una prueba no cubre. Sale con 0 solo si TODAS pasan. Las
pruebas de PostgreSQL real (inmutabilidad, duplicados concurrentes) están en F3-BD y F4-INTEGRACION.
"""

import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]

# función -> (descripción del anexo, pruebas que la ejercitan, [(archivo, texto que debe existir, por qué)])
FUNCIONES: dict[str, tuple[str, list[str], list[tuple[str, str, str]]]] = {
    "F1": (
        "Inicio de sesión con Supabase Auth y TOTP obligatorio; permisos por rol.",
        [
            "tests/adaptadores/test_ingreso_web.py",
            "tests/adaptadores/test_identidad_supabase.py",
            "tests/seguridad/test_segundo_factor.py",
            "tests/seguridad/test_matriz_authz.py",
        ],
        [
            (
                "src/jml/adaptadores/entrada/web/ingreso.py",
                "casos.completar_ingreso",
                "la sesión solo nace tras verificar el TOTP",
            ),
            (
                "src/jml/aplicacion/casos/ingreso.py",
                "identidad.nivel < 2",
                "solo AAL2 abre una sesión",
            ),
        ],
    ),
    "F2": (
        "Registro con fecha efectiva, consulta, cancelación y deduplicación.",
        [
            "tests/aplicacion/test_registro_y_decision.py",
            "tests/aplicacion/test_listados.py",
            "tests/dominio/test_solicitud.py",
        ],
        [
            ("src/jml/aplicacion/casos/decidir.py", "class CancelarSolicitud", "cancelación"),
            (
                "src/jml/adaptadores/salida/persistencia/models.py",
                "UniqueConstraint",
                "deduplicación en la base (invariante 2)",
            ),
        ],
    ),
    "F3": (
        "Un ticket por cola involucrada, con lista de verificación, prioridad, SLA y, cuando aplica, fecha programada.",
        [
            "tests/dominio/test_tickets.py",
            "tests/dominio/test_tickets_golden.py",
            "tests/aplicacion/test_bandeja.py",
        ],
        [
            (
                "src/jml/dominio/tickets.py",
                "lista_de_verificacion",
                "lista de verificación en cada ticket",
            ),
            ("src/jml/dominio/tickets.py", "vence_en", "SLA (vencimiento)"),
            (
                "src/jml/dominio/tickets.py",
                "activo_desde",
                "fecha programada de los tickets que no son inmediatos",
            ),
        ],
    ),
    "F4": (
        "Estado de los tickets, soluciones, actas y activos desde GLPI, cada 5 minutos.",
        [
            "tests/aplicacion/test_sincronizacion.py",
            "tests/adaptadores/test_worker.py",
            "tests/contratos",
        ],
        [
            (
                "src/jml/adaptadores/entrada/worker/ciclo.py",
                "INTERVALO_SINCRONIZACION_S = 300.0",
                "cada 5 minutos",
            ),
            (
                "src/jml/aplicacion/casos/sincronizar.py",
                "class SincronizarActivos",
                "activos desde GLPI",
            ),
        ],
    ),
    "F5": (
        "Estado de las cuentas por sistema, derivado de los tickets resueltos.",
        [
            "tests/dominio/test_resolucion_cuentas.py",
            "tests/aplicacion/test_sincronizacion.py",
        ],
        [],  # lo comprueba `solo_la_sincronizacion_escribe_cuentas` abajo
    ),
    "F6": (
        "Búsqueda de cuentas y ficha del colaborador (dashboard de los roles técnicos).",
        [
            "tests/adaptadores/test_tecnicos_web.py",
            "tests/aplicacion/test_consultas.py",
        ],
        [
            ("src/jml/aplicacion/casos/consultas.py", "class BuscarCuentas", "búsqueda de cuentas"),
            (
                "src/jml/aplicacion/casos/consultas.py",
                "class ConsultarFicha",
                "ficha del colaborador",
            ),
        ],
    ),
    "F7": (
        "Registro inalterable de cada decisión, emisión, cambio de estado y acceso a datos personales.",
        [
            "tests/dominio/test_auditoria.py",
            "tests/adaptadores/test_auditor_web.py",
            "tests/aplicacion/test_defensas.py",
        ],
        [
            (
                "src/jml/aplicacion/casos/consultas.py",
                '"ficha.consultada"',
                "acceso a datos personales: fichas",
            ),
            (
                "src/jml/aplicacion/casos/listados.py",
                '"restringido.consultado"',
                "acceso a datos personales: campo restringido",
            ),
            (
                "src/jml/aplicacion/casos/sincronizar.py",
                '"ticket.estado_sincronizado"',
                "cambio de estado",
            ),
            ("src/jml/aplicacion/casos/bandeja.py", '"ticket.creado"', "emisión"),
            ("src/jml/aplicacion/casos/_emision.py", "decision", "decisión"),
        ],
    ),
    "F8": (
        "Matriz de perfiles, catálogos (S-32: la propia matriz) y asignación de roles.",
        [
            "tests/adaptadores/test_administracion_web.py",
            "tests/aplicacion/test_administracion.py",
        ],
        [
            (
                "src/config/urls.py",
                "administracion/perfiles",
                "área de administración de la matriz",
            ),
            ("src/config/urls.py", "roles", "asignación de roles"),
        ],
    ),
}


def solo_la_sincronizacion_escribe_cuentas() -> tuple[bool, str]:
    """F5: invariante 6. Ningún caso de uso ni vista, salvo la sincronización, escribe cuentas."""
    escritores = []
    for ruta in (RAIZ / "src" / "jml" / "aplicacion").rglob("*.py"):
        if ruta.name != "sincronizar.py" and re.search(
            r"cuentas\.(guardar|agregar_historial)\(", ruta.read_text(encoding="utf-8")
        ):
            escritores.append(ruta.name)
    for ruta in (RAIZ / "src" / "jml" / "adaptadores" / "entrada").rglob("*.py"):
        if re.search(r"cuentas\.(guardar|agregar_historial)\(", ruta.read_text(encoding="utf-8")):
            escritores.append(ruta.name)
    return not escritores, f"escriben cuentas fuera de la sincronización: {escritores or 'ninguno'}"


def correr(pruebas: list[str]) -> tuple[bool, str]:
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *pruebas],
        cwd=RAIZ, capture_output=True, text=True, check=False,
    )  # fmt: skip
    ultima = (r.stdout.strip().splitlines() or ["(sin salida)"])[-1]
    return r.returncode == 0, ultima


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    todo = True
    for clave, (descripcion, pruebas, lecturas) in FUNCIONES.items():
        ok, resumen = correr(pruebas)
        print(f"\n{clave}. {descripcion}")
        print(f"   pruebas: {'OK   ' if ok else 'FALLA'} {resumen}")
        todo &= ok
        for archivo, texto, motivo in lecturas:
            presente = texto in (RAIZ / archivo).read_text(encoding="utf-8")
            print(f"   código:  {'OK   ' if presente else 'FALLA'} {motivo} ({archivo})")
            todo &= presente
        if clave == "F5":
            ok5, detalle = solo_la_sincronizacion_escribe_cuentas()
            print(f"   código:  {'OK   ' if ok5 else 'FALLA'} {detalle}")
            todo &= ok5
    print(
        f"\nANEXO A, TABLA I: {'las 8 funciones se cumplen' if todo else 'HAY FUNCIONES QUE NO SE CUMPLEN'}"
    )
    return 0 if todo else 1


if __name__ == "__main__":
    sys.exit(main())
