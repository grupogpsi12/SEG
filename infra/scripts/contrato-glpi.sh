#!/usr/bin/env bash
# Pruebas contra el GLPI REAL del compose (spike 0.3 e item 5.1), dentro de la red de Docker como
# el worker: GLPI no publica puertos (RS-02) y su API esta cerrada en el WAF.
#
#   JML_GLPI_DE_PRUEBAS=si infra/scripts/contrato-glpi.sh                  # todo
#   JML_GLPI_DE_PRUEBAS=si infra/scripts/contrato-glpi.sh -k "VAC" -x      # argumentos para pytest
#
# Corre: la suite de contrato de SistemaDeTickets, la integracion de GLPI (CA-03, CA-06, CA-10, 3.1)
# y los flujos VAC, RET, EMG y la caida de GLPI (CA-04, CA-06, CA-07) con repositorios reales. Para
# estos levanta un PostgreSQL 17 DESECHABLE en la misma red, con los roles de Supabase (ADR-028),
# y lo borra al terminar: nunca toca la base del stack.
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
PG=jml-pg-pruebas
PG_IMAGEN=postgres:17@sha256:2d2b8998d31037bf721cfdf764d76ba74171b4fab3431b7f72c27c56ddbdf9e3
# Dentro del repo y no en /tmp: Docker Desktop no ve el /tmp de Git Bash.
CACHE="$RAIZ/.contrato-tmp"
mkdir -p "$CACHE"
trap 'rm -rf "$CACHE"; docker rm -f "$PG" > /dev/null 2>&1 || true' EXIT
uv export --frozen --format requirements-txt --no-emit-project -o "$CACHE/req.txt" > /dev/null
# Despues de `uv` (que si necesita la ruta traducida): Git Bash no debe reescribir las rutas que
# van a los contenedores.
export MSYS_NO_PATHCONV=1

# Claves de un solo uso: la base vive lo que dura la corrida y no sale de la red interna.
clave_pg="$(head -c 18 /dev/urandom | base64 | tr -d '=+/\n')"
clave_backend="$(head -c 18 /dev/urandom | base64 | tr -d '=+/\n')"
clave_duenio="$(head -c 18 /dev/urandom | base64 | tr -d '=+/\n')"
docker rm -f "$PG" > /dev/null 2>&1 || true
docker run -d --name "$PG" --network "$RED" -e POSTGRES_PASSWORD="$clave_pg" "$PG_IMAGEN" > /dev/null
for _ in $(seq 1 60); do
  docker exec "$PG" pg_isready -U postgres -h 127.0.0.1 > /dev/null 2>&1 && break
  sleep 1
done
# Los mismos roles que Supabase y la CI (.github/workflows/verificar.yml), y el duenio separado.
docker exec -i "$PG" psql -q -U postgres -v ON_ERROR_STOP=1 > /dev/null <<SQL
create role anon; create role authenticated; create role service_role;
create role app_backend login nosuperuser nocreatedb nocreaterole noinherit nobypassrls
  password '$clave_backend';
create schema app_test authorization app_backend;
SQL
docker exec -i "$PG" psql -q -U postgres -v ON_ERROR_STOP=1 -v clave_duenio="'$clave_duenio'" \
  -f - < "$RAIZ/infra/supabase/duenio-separado.sql" > /dev/null

docker run --rm --network "$RED" \
  -v "$RAIZ:/repo:ro" -v "$CACHE:/req:ro" -w /repo \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/repo/src:/repo \
  -e JML_PG_HOST="$PG" -e JML_PG_USUARIO=app_backend -e JML_PG_CLAVE="$clave_backend" \
  -e JML_PG_SSLMODE=disable -e JML_PG_DUENIO_USUARIO=app_owner -e JML_PG_DUENIO_CLAVE="$clave_duenio" \
  -e JML_GLPI_API_URL=http://glpi/apirest.php -e JML_GLPI_DE_PRUEBAS="${JML_GLPI_DE_PRUEBAS:-}" \
  -e JML_GLPI_APP_TOKEN="$(cat "$SECRETOS/glpi_app_token")" \
  -e JML_GLPI_USER_TOKEN="$(cat "$SECRETOS/glpi_user_token")" \
  -e JML_GLPI_ADMIN_TOKEN="$(cat "$SECRETOS/glpi_admin_user_token")" \
  python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 \
  sh -c 'pip install -q --disable-pip-version-check --root-user-action=ignore --no-cache-dir -r /req/req.txt \
         && python -m pytest -p no:cacheprovider -q --ds tests.integracion.ajustes \
              tests/contratos/test_sistema_de_tickets.py tests/integracion/test_glpi_real.py \
              tests/integracion/test_flujos_glpi_real.py -k "glpi_real or CA_ or 3_1" "$@"' sh "$@"
