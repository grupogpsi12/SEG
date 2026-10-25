"""Siembra un defecto, comprueba que la prueba lo ve (ROJO) y restaura el archivo (plan §10).

    python auditoria/scripts/defecto-sembrado.py <ID>      # IDs en DEFECTOS
Sale con 0 solo si: la prueba pasa sin el defecto, FALLA con él y el archivo vuelve idéntico.
El archivo se restaura siempre (finally); no se versiona el defecto.
"""

import shlex
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]

# id: (archivo, texto original, texto sembrado, pruebas que deben ponerse en rojo)
DEFECTOS: dict[str, tuple[str, str, str, list[str]]] = {
    "U01-segundo-uso": (
        "src/jml/adaptadores/salida/identidad/supabase.py",
        "        self._descartar(desafio_id)  # un desafio se usa una sola vez",
        "        pass  # DEFECTO SEMBRADO: el desafio sigue valiendo",
        ["tests/seguridad/test_segundo_factor.py"],
    ),
    "U02-sin-firma": (
        "src/jml/dominio/soporte.py",
        "    if not contenido.startswith(FIRMA_PDF):",
        "    if False:  # DEFECTO SEMBRADO: se acepta cualquier contenido con extension .pdf",
        ["tests/seguridad/test_soporte.py"],
    ),
    "U04-filtro-roto": (
        "src/jml/adaptadores/registro.py",
        "    return any(p in sin_acentos for p in PALABRAS_PROHIBIDAS)",
        "    return False  # DEFECTO SEMBRADO: el filtro deja pasar todo",
        ["tests/seguridad/test_filtro_de_logs.py"],
    ),
    "U05-sin-bloqueo": (
        "src/jml/adaptadores/salida/persistencia/repositorios.py",
        '_con_restringido().select_for_update(of=("self",)).filter(pk=solicitud_id.valor).first()',
        "_con_restringido().filter(pk=solicitud_id.valor).first()  # DEFECTO SEMBRADO: sin bloqueo",
        ["bash", "infra/scripts/integracion-local.sh", "-k", "U05", "-x"],
    ),
    "BD-sin-revoke": (
        "src/jml/adaptadores/salida/persistencia/migrations/0004_permisos_minimos_de_app_backend.py",
        "    REVOKE UPDATE, DELETE, TRUNCATE ON auditoria, decision, cuenta_historial FROM app_backend;",
        "    NULL;  -- DEFECTO SEMBRADO: sin REVOKE de solo insercion",
        ["bash", "infra/scripts/integracion-local.sh", "-k", "test_BD or RD_02", "-x"],
    ),
    "BD-sin-disparador": (
        "src/jml/adaptadores/salida/persistencia/migrations/0002_reglas_de_postgresql.py",
        "CREATE TRIGGER solicitud_inmutable BEFORE UPDATE ON solicitud",
        "CREATE TRIGGER solicitud_inmutable BEFORE INSERT ON solicitud",
        ["bash", "infra/scripts/integracion-local.sh", "-k", "RF_14 or test_BD", "-x"],
    ),
    "BD-sin-rls": (
        "src/jml/adaptadores/salida/persistencia/migrations/0006_rls_en_las_tablas_del_framework.py",
        "AND c.relkind = 'r' AND NOT c.relrowsecurity",
        "AND c.relkind = 'r' AND false",  # DEFECTO SEMBRADO
        ["bash", "infra/scripts/integracion-local.sh", "-k", "RD_10 or test_BD", "-x"],
    ),
}


def pytest(pruebas: list[str]) -> int:
    # Si la lista empieza por "bash", es un comando completo (p. ej. integracion-local.sh)
    orden = (
        pruebas
        if pruebas[0] == "bash"
        else [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-x", *pruebas]
    )
    if orden[0] == "bash":
        sys.path.insert(0, str(RAIZ / "auditoria" / "herramientas"))
        import registrar  # el mismo bash de Git y el mismo PATH (docker, venv) que la evidencia

        orden = [registrar.BASH, "-c", shlex.join(orden[1:])]
        entorno = registrar._entorno()
    else:
        entorno = None
    r = subprocess.run(
        orden,
        env=entorno,
        cwd=RAIZ, capture_output=True, text=True, check=False,
    )  # fmt: skip
    print("   ", (r.stdout.strip().splitlines() or ["(sin salida)"])[-1])
    return r.returncode


def main(clave: str) -> int:
    archivo, original, sembrado, pruebas = DEFECTOS[clave]
    ruta = RAIZ / archivo
    antes = ruta.read_bytes()
    texto = antes.decode("utf-8")
    if original not in texto:
        print(f"ERROR: el texto original no está en {archivo}; el defecto no se puede sembrar")
        return 2
    try:
        print(f"[{clave}] sin defecto:")
        limpio = pytest(pruebas)
        ruta.write_bytes(texto.replace(original, sembrado, 1).encode("utf-8"))
        print(f"[{clave}] con el defecto sembrado en {archivo}:")
        roto = pytest(pruebas)
    finally:
        ruta.write_bytes(antes)
    restaurado = ruta.read_bytes() == antes
    print(f"[{clave}] archivo restaurado: {restaurado}")
    ok = limpio == 0 and roto != 0 and restaurado
    print(f"[{clave}] {'DETECTADO: verde sin defecto, rojo con él' if ok else 'NO DETECTADO'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
