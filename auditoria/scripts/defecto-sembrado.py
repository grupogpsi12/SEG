"""Siembra un defecto, comprueba que la prueba lo ve (ROJO) y restaura el archivo (plan §10).

    python auditoria/scripts/defecto-sembrado.py <ID>      # IDs en DEFECTOS
Sale con 0 solo si: la prueba pasa sin el defecto, FALLA con él y el archivo vuelve idéntico.
El archivo se restaura siempre (finally); no se versiona el defecto.
"""

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
}


def pytest(pruebas: list[str]) -> int:
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-x", *pruebas],
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
