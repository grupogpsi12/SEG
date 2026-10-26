"""Registra la evidencia de un ítem de la auditoría (plan §9.2, puntos 1 y 4).

    python auditoria/herramientas/registrar.py ITEM TIPO --version "pytest 9.1.1" -- <comando bash>

Crea auditoria/evidencia/<TIPO>/<ITEM>/ con:
  cmd.txt         el comando EXACTO (una evidencia sin comando reproducible no cuenta)
  salida.txt      stdout + stderr, enmascarados con enmascarar.py
  version.txt     versión de la herramienta, tal como la declara quien registra
  commit.txt      `git rev-parse HEAD` y si el árbol tenía cambios sin confirmar
  fecha-utc.txt   cuándo se ejecutó
  codigo.txt      código de salida del comando
y reescribe auditoria/manifiesto.sha256 con el sha256 de TODA la evidencia.

Imprime solo el final de la salida (el resto va al archivo), y el código de salida del comando
sale como el del registrador: así un comando que falla no se confunde con uno verificado.
"""

import argparse
import hashlib
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
EVIDENCIA = RAIZ / "auditoria" / "evidencia"
MANIFIESTO = RAIZ / "auditoria" / "manifiesto.sha256"
# En Windows, `bash` a secas puede ser el de WSL (System32): se usa el de Git, el del proyecto.
_GIT_BASH = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Git" / "bin" / "bash.exe"
BASH = str(_GIT_BASH) if _GIT_BASH.exists() else "bash"
TIPOS = {
    "funcionales",
    "estaticos",
    "vulnerabilidades",
    "trafico",
    "autorizacion",
    "disponibilidad",
    "controles-positivos",
}

sys.path.insert(0, str(Path(__file__).parent))
from enmascarar import enmascarar  # noqa: E402


def _entorno() -> dict[str, str]:
    env = dict(os.environ)
    extra = [
        "/c/Program Files/Docker/Docker/resources/bin",
        str(RAIZ / ".venv" / "Scripts"),
        str(RAIZ / ".venv" / "bin"),
    ]
    paquetes = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    for patron in ("FiloSottile.age*/age", "SecretsOPerationS.SOPS*"):
        extra += [str(p) for p in paquetes.glob(patron)]
    env["PATH"] = os.pathsep.join([*extra, env.get("PATH", "")])
    env["PYTHONUTF8"] = "1"
    return env


def sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def actualizar_manifiesto() -> int:
    lineas = [
        f"{sha256(p)}  {p.relative_to(RAIZ).as_posix()}"
        for p in sorted(EVIDENCIA.rglob("*"))
        if p.is_file()
    ]
    MANIFIESTO.write_text("\n".join(lineas) + "\n", encoding="utf-8", newline="\n")
    return len(lineas)


def _git(*args: str, cwd: Path = RAIZ) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    return r.stdout.strip()


def registrar(
    item: str, tipo: str, comando: str, version: str, timeout: int, cwd: Path = RAIZ
) -> tuple[int, Path]:
    if tipo not in TIPOS:
        raise SystemExit(f"tipo desconocido «{tipo}»; use uno de {sorted(TIPOS)}")
    destino = EVIDENCIA / tipo / item
    destino.mkdir(parents=True, exist_ok=True)
    inicio = datetime.now(UTC)
    try:
        r = subprocess.run(
            [BASH, "-c", comando],
            cwd=cwd, env=_entorno(), capture_output=True, timeout=timeout, check=False,
        )  # fmt: skip
        salida = r.stdout.decode("utf-8", errors="replace") + r.stderr.decode(
            "utf-8", errors="replace"
        )
        codigo = r.returncode
    except subprocess.TimeoutExpired as e:
        salida = (e.stdout or b"").decode(
            "utf-8", errors="replace"
        ) + f"\n[TIMEOUT tras {timeout} s]\n"
        codigo = 124
    (destino / "cmd.txt").write_text(comando + "\n", encoding="utf-8", newline="\n")
    (destino / "salida.txt").write_text(enmascarar(salida), encoding="utf-8", newline="\n")
    (destino / "version.txt").write_text(version + "\n", encoding="utf-8", newline="\n")
    sucio = (
        "con cambios sin confirmar" if _git("status", "--porcelain", cwd=cwd) else "árbol limpio"
    )
    rama = _git("branch", "--show-current", cwd=cwd) or "sin rama"
    (destino / "commit.txt").write_text(
        f"{_git('rev-parse', 'HEAD', cwd=cwd)} ({rama}; {sucio})\n",
        encoding="utf-8", newline="\n",
    )  # fmt: skip
    (destino / "fecha-utc.txt").write_text(
        inicio.strftime("%Y-%m-%dT%H:%M:%SZ") + "\n", encoding="utf-8", newline="\n"
    )
    (destino / "codigo.txt").write_text(f"{codigo}\n", encoding="utf-8", newline="\n")
    return codigo, destino


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]  # consola de Windows
    argv = sys.argv[1:]
    if "--" not in argv:
        raise SystemExit("uso: registrar.py ITEM TIPO --version V -- <comando bash>")
    corte = argv.index("--")
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("item")
    ap.add_argument("tipo")
    ap.add_argument("--version", required=True)
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--cwd", default=None, help="directorio de ejecución y de git (un worktree)")
    ap.add_argument("--lineas", type=int, default=12, help="líneas finales que se muestran")
    a = ap.parse_args(argv[:corte])
    comando = " ".join(argv[corte + 1 :]).strip()
    if not comando:
        raise SystemExit("falta el comando después de --")
    cwd = Path(a.cwd).resolve() if a.cwd else RAIZ
    codigo, destino = registrar(a.item, a.tipo, comando, a.version, a.timeout, cwd)
    cuantos = actualizar_manifiesto()
    cola = (destino / "salida.txt").read_text(encoding="utf-8").splitlines()[-a.lineas :]
    print(os.linesep.join(cola))
    print(
        f"-- {a.item}: código {codigo} · {destino.relative_to(RAIZ).as_posix()}"
        f" · manifiesto: {cuantos} archivos"
    )
    return codigo


if __name__ == "__main__":
    sys.exit(main())
