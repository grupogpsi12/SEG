#!/usr/bin/env bash
# Reproduce en el equipo el job `integracion` de .github/workflows/verificar.yml: tests/integracion y
# las suites de contrato contra un PostgreSQL 17 DESECHABLE con los roles de Supabase (ADR-028).
#
#   infra/scripts/integracion-local.sh            # argumentos extra van a pytest (p. ej. -x -k H3)
#
# Necesita Docker y el entorno de desarrollo (`uv sync`). Publica PostgreSQL solo en 127.0.0.1, en un
# puerto libre que elige Docker (Windows reserva rangos al azar), mientras dura la corrida. Las
# pruebas de GLPI real se omiten (S-28); para eso esta contrato-glpi.sh.
set -uo pipefail

RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
PG=jml-pg-integracion
PG_IMAGEN=postgres:17@sha256:2d2b8998d31037bf721cfdf764d76ba74171b4fab3431b7f72c27c56ddbdf9e3
PY="$RAIZ/.venv/bin/python"
[ -x "$PY" ] || PY="$RAIZ/.venv/Scripts/python.exe"   # Windows
cd "$RAIZ"

clave() { head -c 18 /dev/urandom | base64 | tr -d '=+/\n'; }
clave_pg="$(clave)"; clave_backend="$(clave)"; clave_duenio="$(clave)"
docker rm -f "$PG" > /dev/null 2>&1
trap 'docker rm -f "$PG" > /dev/null 2>&1' EXIT
docker run -d --name "$PG" -p 127.0.0.1::5432 -e POSTGRES_PASSWORD="$clave_pg" "$PG_IMAGEN" > /dev/null \
  || { echo "no arranco PostgreSQL" >&2; exit 1; }
PUERTO="$(docker port "$PG" 5432/tcp | head -1 | sed 's/.*://')"
for _ in $(seq 1 60); do docker exec "$PG" pg_isready -U postgres -h 127.0.0.1 > /dev/null 2>&1 && break; sleep 1; done
sleep 2
# Los mismos roles que la CI y Supabase, y el duenio separado
docker exec -i "$PG" psql -q -U postgres -v ON_ERROR_STOP=1 > /dev/null <<SQL
create role anon; create role authenticated; create role service_role;
create role app_backend login nosuperuser nocreatedb nocreaterole noinherit nobypassrls
  password '$clave_backend';
create schema app_test authorization app_backend;
SQL
docker exec -i "$PG" psql -q -U postgres -v ON_ERROR_STOP=1 -v clave_duenio="'$clave_duenio'" -f - \
  < infra/supabase/duenio-separado.sql > /dev/null

JML_PG_HOST=127.0.0.1 JML_PG_PUERTO="$PUERTO" JML_PG_USUARIO=app_backend JML_PG_CLAVE="$clave_backend" \
JML_PG_SSLMODE=disable JML_PG_DUENIO_USUARIO=app_owner JML_PG_DUENIO_CLAVE="$clave_duenio" \
  "$PY" -m pytest -q -p no:cacheprovider --ds tests.integracion.ajustes tests/integracion tests/contratos "$@"
