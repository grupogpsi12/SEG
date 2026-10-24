#!/usr/bin/env bash
# Item 5.8: pruebas de la interfaz con Playwright (ING, VAC, RET y EMG), a traves del WAF y hasta GLPI.
#
#   JML_GLPI_DE_PRUEBAS=si infra/scripts/e2e-interfaz.sh
#
# Requisitos: el stack LOCAL de pruebas arriba con GLPI y el worker (docs/probar-localmente.md, §2 y
# §3). Crea en su base colaboradores y usuarios de prueba nuevos en cada corrida (tests/e2e/
# preparar.py) y tickets reales en su GLPI: solo para un stack de pruebas.
#
# El navegador (imagen oficial de Playwright, fijada por digest) corre en la red `app`: llega a
# bunkerweb (10.20.40.2:8443) como cualquier navegador, y a la API de GLPI, que desde fuera esta
# cerrada.
set -euo pipefail

if [ "${JML_GLPI_DE_PRUEBAS:-}" != "si" ]; then
  echo "Crea datos y tickets de prueba en el stack: JML_GLPI_DE_PRUEBAS=si $0" >&2
  exit 2
fi
RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
COMPOSE="${COMPOSE:--f infra/compose.yaml -f infra/compose.local.yaml}"
PLAYWRIGHT=mcr.microsoft.com/playwright/python:v1.63.0-noble@sha256:72bd171a9ffc2b4b59532aaa6210e21014d07093120dc25528870c0b840da1f0
CACHE="$RAIZ/.contrato-tmp/e2e"
cd "$RAIZ"
mkdir -p "$CACHE"
trap 'rm -rf "$CACHE"' EXIT
uv export --frozen --format requirements-txt --no-emit-project -o "$CACHE/req.txt" > /dev/null

# Desde aqui las rutas van tal cual a Docker; en Git Bash, el repositorio en formato de Windows.
export MSYS_NO_PATHCONV=1
REPO="$(cygpath -w "$RAIZ" 2> /dev/null || printf '%s' "$RAIZ")"

echo "== datos y sesiones de prueba"
docker compose $COMPOSE run --rm -T -v "$REPO:/repo:ro" -e PYTHONPATH=/repo -w /repo web \
  python -m tests.e2e.preparar > "$CACHE/datos.salida" 2>&1 \
  || { tail -5 "$CACHE/datos.salida" >&2; exit 1; }
grep '"sesion_rrhh"' "$CACHE/datos.salida" | tail -1 > "$CACHE/datos.json"
[ -s "$CACHE/datos.json" ] || { echo "no se prepararon los datos" >&2; exit 1; }

echo "== Playwright por el WAF"
docker run --rm --network jml_app --ipc=host \
  -v "$REPO:/repo:ro" -v "$REPO/.contrato-tmp/e2e:/e2e" -w /repo \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/repo/src:/repo \
  -e DJANGO_SETTINGS_MODULE=tests.adaptadores.ajustes \
  -e JML_E2E_DATOS=/e2e/datos.json -e JML_E2E_WAF=10.20.40.2:8443 \
  -e JML_GLPI_API_URL=http://glpi/apirest.php \
  -e JML_GLPI_APP_TOKEN="$(cat "$RAIZ/secrets/glpi_app_token")" \
  -e JML_GLPI_ADMIN_TOKEN="$(cat "$RAIZ/secrets/glpi_admin_user_token")" \
  "$PLAYWRIGHT" sh -c 'pip install -q --disable-pip-version-check --break-system-packages \
      --root-user-action=ignore -r /e2e/req.txt && python -m pytest -p no:cacheprovider -q tests/e2e "$@"' sh "$@"
