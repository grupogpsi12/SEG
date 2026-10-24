#!/usr/bin/env bash
# RD-06 / RNF-04 (RPO 24 h): respaldo diario de la base de la aplicacion (Supabase) y de la de
# GLPI (MariaDB), cifrado en reposo por Blob y subido con la identidad administrada de la VM.
# Corre en el HOST (cron diario, 02:00 hora de Bogota). La restauracion: docs/operacion.md.
#
#   JML_STORAGE_CUENTA=<cuenta> infra/scripts/respaldo.sh                     # Azure: sube a Blob
#   JML_MODO=local JML_RESPALDO_DESTINO=<carpeta> infra/scripts/respaldo.sh   # local, sin Azure
#
# - Aplicacion: `pg_dump` en formato custom como `app_owner` (duenio del esquema: lee todo,
#   ADR-028) desde una imagen postgres:17 de un solo uso; contra Supabase, por TLS verificando el
#   certificado. En modo local (compose.local.yaml), contra el PostgreSQL de la red interna pg_net.
# - GLPI: `mariadb-dump --single-transaction` dentro del contenedor mariadb.
# El simulacro de restauracion con evidencia es infra/scripts/restaurar-prueba.sh (CA-11).
# Verificado en local el 24/10/2026; en Azure, pendiente (5.2).
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
FECHA="$(TZ=America/Bogota date +%Y-%m-%d)"
PG_IMAGEN=postgres:17@sha256:2d2b8998d31037bf721cfdf764d76ba74171b4fab3431b7f72c27c56ddbdf9e3

if [ "${JML_MODO:-}" = local ]; then
  SECRETOS="${JML_SECRETOS:-$RAIZ/secrets}"
  DESTINO="${JML_RESPALDO_DESTINO:?defina JML_RESPALDO_DESTINO (carpeta local)}"
  COMPOSE=(-f infra/compose.yaml -f infra/compose.local.yaml)
  RED_PG=(--network jml_pg_net)
  CONEXION="host=postgres port=5432 dbname=postgres user=app_owner sslmode=disable"
  CA=()
else
  SECRETOS="${JML_SECRETOS:-/run/secrets}"
  CUENTA="${JML_STORAGE_CUENTA:?defina JML_STORAGE_CUENTA}"
  DESTINO="$(mktemp -d)"
  trap 'rm -rf "$DESTINO"' EXIT
  COMPOSE=(-f infra/compose.yaml)
  # shellcheck disable=SC1091
  source "$RAIZ/infra/.env"
  RED_PG=(--network host)
  CONEXION="host=$JML_DB_HOST port=5432 dbname=postgres user=$JML_DB_USUARIO_DUENIO sslmode=verify-full sslrootcert=/ca.crt"
  CA=(-v "$SECRETOS/supabase_ca_crt:/ca.crt:ro")
fi
# Rutas relativas para compose y absolutas para `docker run -v` (Git Bash, MSYS_NO_PATHCONV).
cd "$RAIZ"
mkdir -p "$DESTINO"
DESTINO="$(cd "$DESTINO" && pwd)"
clave_duenio="$(cat "$SECRETOS/db_owner_password")"
export MSYS_NO_PATHCONV=1   # Git Bash: las rutas de los contenedores no se traducen

docker run --rm "${RED_PG[@]}" "${CA[@]}" -v "$DESTINO:/salida" -e PGPASSWORD="$clave_duenio" \
  "$PG_IMAGEN" \
  pg_dump "$CONEXION" --schema=app --format=custom --no-owner --file="/salida/app-$FECHA.dump"

docker compose "${COMPOSE[@]}" exec -T mariadb sh -c \
  'mariadb-dump --single-transaction --routines -u glpi -p"$(cat /run/secrets/glpi_db_password)" glpi' \
  | gzip > "$DESTINO/glpi-$FECHA.sql.gz"

if [ "${JML_MODO:-}" = local ]; then
  for archivo in "$DESTINO/app-$FECHA.dump" "$DESTINO/glpi-$FECHA.sql.gz"; do
    echo "respaldado: $archivo ($(du -h "$archivo" | cut -f1))"
  done
  exit 0
fi

az login --identity --output none
for archivo in "$DESTINO"/*; do
  az storage blob upload --auth-mode login --account-name "$CUENTA" --container-name respaldos \
    --file "$archivo" --name "$(basename "$archivo")" --overwrite false --output none
  echo "respaldado: $(basename "$archivo") ($(du -h "$archivo" | cut -f1))"
done
