#!/usr/bin/env bash
# Spike 0.3: corre la suite de contrato de SistemaDeTickets contra el GLPI REAL del compose.
# Va dentro de la red de Docker (como el worker): GLPI no publica puertos (RS-02).
#
#   infra/scripts/contrato-glpi.sh                    # toda la suite del puerto
#   infra/scripts/contrato-glpi.sh -k "timeout" -x    # argumentos extra para pytest
#
# Requisitos: el stack arriba, `configurar-glpi` corrido y secrets/glpi_{app,user,admin_user}_token.
set -euo pipefail

if [ "${JML_GLPI_DE_PRUEBAS:-}" != "si" ]; then
  echo "Esta suite BORRA los tickets cuya clave empieza con SOL- en GLPI." >&2
  echo "Usela solo con un GLPI de pruebas: JML_GLPI_DE_PRUEBAS=si $0" >&2
  exit 2
fi

RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
RED="${JML_RED_APP:-jml_app}"
SECRETOS="$RAIZ/secrets"
# Dentro del repo y no en /tmp: Docker Desktop no ve el /tmp de Git Bash.
CACHE="$RAIZ/.contrato-tmp"
mkdir -p "$CACHE"
trap 'rm -rf "$CACHE"' EXIT
uv export --frozen --format requirements-txt --no-emit-project -o "$CACHE/req.txt" > /dev/null

# MSYS_NO_PATHCONV: Git Bash de Windows no debe reescribir las rutas del contenedor.
MSYS_NO_PATHCONV=1 docker run --rm --network "$RED" \
  -v "$RAIZ:/repo:ro" -v "$CACHE:/req:ro" -w /repo \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/repo/src:/repo \
  -e DJANGO_SETTINGS_MODULE=tests.adaptadores.ajustes \
  -e JML_GLPI_API_URL=http://glpi/apirest.php -e JML_GLPI_DE_PRUEBAS="${JML_GLPI_DE_PRUEBAS:-}" \
  -e JML_GLPI_APP_TOKEN="$(cat "$SECRETOS/glpi_app_token")" \
  -e JML_GLPI_USER_TOKEN="$(cat "$SECRETOS/glpi_user_token")" \
  -e JML_GLPI_ADMIN_TOKEN="$(cat "$SECRETOS/glpi_admin_user_token")" \
  python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 \
  sh -c 'pip install -q --disable-pip-version-check --no-cache-dir -r /req/req.txt \
         && python -m pytest -p no:cacheprovider -q tests/contratos/test_sistema_de_tickets.py tests/integracion/test_glpi_real.py -k "glpi_real or CA_ or 3_1" "$@"' sh "$@"
