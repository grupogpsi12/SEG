#!/usr/bin/env bash
# F1-06: N corridas seguidas de la suite unitaria (sin reintentos automaticos: el proyecto no usa
# pytest-rerunfailures). Una prueba inestable es la que falla en alguna corrida y pasa en otra.
#   auditoria/scripts/estabilidad.sh [N]
set -u
N="${1:-20}"
PY=".venv/Scripts/python.exe"
[ -x "$PY" ] || PY=python
fallos=0
for i in $(seq 1 "$N"); do
  salida="$($PY -m pytest -q -p no:cacheprovider -rf tests/dominio tests/aplicacion tests/contratos tests/escenarios tests/adaptadores tests/seguridad 2>&1)"
  resumen="$(echo "$salida" | tail -1)"
  echo "corrida $i/$N: $resumen"
  echo "$salida" | grep '^FAILED' | sed "s/^/  corrida $i: /"
  echo "$resumen" | grep -q failed && fallos=$((fallos + 1))
done
echo "corridas con fallos: $fallos de $N"
[ "$fallos" -eq 0 ]
