#!/usr/bin/env bash
# F8-02 / G4: mutacion de `aplicacion` o de los modulos de seguridad con mutmut 3.8.0 en un contenedor LINUX
# (mutmut 3 necesita `fork`; el equipo trabaja en Windows y el proyecto se queda en mutmut<3 para el dominio).
#
#   auditoria/scripts/mutacion-linux.sh aplicacion      # ~2 200 mutantes, unos 25 min
#   auditoria/scripts/mutacion-linux.sh seguridad       # ~500 mutantes, unos 15 min
#
# ESTADO: empaqueta los comandos con los que se midio F8-02 (92,7 % y 96,1 %), que se ejecutaron a mano; este guion NO se corrio de
# extremo a extremo (se interrumpio una corrida de comprobacion por innecesaria). Antes de fiarse de el, correrlo una vez.
# Trabaja sobre un `git worktree` desechable del commit actual (nunca toca el arbol de trabajo) y borra el worktree al terminar.
# Mide con TODOS los directorios de pruebas que ejercitan el codigo: medir `aplicacion` solo con tests/aplicacion dio 77,8 %
# frente a 83,2 % con los demas (leccion de F8-02). Imprime los mutantes, los muertos y el porcentaje.
set -u
export MSYS_NO_PATHCONV=1
OBJ="${1:?uso: $0 aplicacion|seguridad}"
PYBIN="$(command -v python || command -v python3)"
META="${META:-85}"
RAIZ="$(pwd -W 2>/dev/null || pwd)"
W="$RAIZ/.contrato-tmp/mut-$OBJ"
PY=python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
# pytest no puede correr en el contenedor las pruebas que necesitan `git` o el stack de Docker
IGNORAR='"--ignore=tests/adaptadores/test_secretos.py", "--ignore=tests/bdd/test_secretos_y_logs.py", "--ignore=tests/seguridad/test_compuertas.py"'
case "$OBJ" in
  aplicacion)
    CONFIG='paths_to_mutate = ["src/jml/aplicacion/"]
tests_dir = ["tests/aplicacion/", "tests/escenarios/", "tests/contratos/", "tests/adaptadores/", "tests/bdd/"]
do_not_mutate = ["src/jml/aplicacion/puertos.py"]' ;;
  seguridad)
    CONFIG='paths_to_mutate = ["src/jml/adaptadores/registro.py", "src/jml/adaptadores/entrada/web/middleware.py", "src/jml/adaptadores/salida/identidad/supabase.py"]
tests_dir = ["tests/adaptadores/", "tests/seguridad/"]
do_not_mutate = []' ;;
  *) echo "objetivo desconocido: $OBJ" >&2; exit 2 ;;
esac

git worktree remove --force "$W" > /dev/null 2>&1; rm -rf "$W"
git worktree add --detach "$W" HEAD > /dev/null || exit 1
"$PYBIN" - "$W/pyproject.toml" "$CONFIG" "$IGNORAR" << 'PY'
import re, sys
ruta, config, ignorar = sys.argv[1:4]
t = open(ruta, encoding="utf-8").read()
t = re.sub(r"\n\[tool\.mutmut\]\n(?:[^\[\n][^\n]*\n|\n)*", "\n", t)  # quita la configuracion de mutmut 2 (dominio)
t += f'\n[tool.mutmut]\n{config}\nalso_copy = ["tests/", "src/", "pyproject.toml"]\npytest_add_cli_args = [{ignorar}]\n'
open(ruta, "w", encoding="utf-8", newline="\n").write(t)
PY
docker run --rm -v "$W:/w" -w /w "$PY" sh -c '
  pip install -q --disable-pip-version-check uv > /dev/null 2>&1 &&
  uv sync --frozen -q &&
  uv pip install -q mutmut==3.8.0 &&
  HYPOTHESIS_PROFILE=mutacion .venv/bin/mutmut run --max-children 4 > /w/mut.log 2>&1
  .venv/bin/mutmut results > /w/resultados.txt 2>&1'
ultimo=$(tr '\r' '\n' < "$W/mut.log" | grep -E "[0-9]+/[0-9]+" | tail -1)
total=$(echo "$ultimo" | sed -E 's#.* ([0-9]+)/([0-9]+) .*#\2#')
muertos=$(echo "$ultimo" | sed -E 's#.*🎉 ([0-9]+).*#\1#')
echo "objetivo: $OBJ · mutantes: $total · muertos: $muertos · supervivientes: $(grep -c ': survived' "$W/resultados.txt")"
pct=$("$PYBIN" -c "print(round(100*$muertos/$total, 1))")
echo "MUTACION $OBJ = $pct % (meta $META %)"
mkdir -p "$RAIZ/.contrato-tmp/resultados-mutacion"
cp "$W/resultados.txt" "$RAIZ/.contrato-tmp/resultados-mutacion/$OBJ.txt"
git worktree remove --force "$W" > /dev/null 2>&1; rm -rf "$W"
"$PYBIN" -c "import sys; sys.exit(0 if $pct >= $META else 1)"
