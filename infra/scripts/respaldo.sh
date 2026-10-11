#!/usr/bin/env bash
# RD-06 / RNF-04 (RPO 24 h): respaldo diario de la base de la aplicacion (Supabase) y de la de
# GLPI (MariaDB), cifrado en reposo por Blob y subido con la identidad administrada de la VM.
# Corre en el HOST (cron diario, 02:00 hora de Bogota). La restauracion: docs/operacion.md.
#
#   JML_STORAGE_CUENTA=<cuenta> infra/scripts/respaldo.sh
#
# - Aplicacion: `pg_dump` en formato custom como `app_owner` (duenio del esquema: lee todo,
#   ADR-028) desde una imagen postgres:17 de un solo uso, por TLS verificando el certificado.
# - GLPI: `mariadb-dump --single-transaction` dentro del contenedor mariadb.
# SIN VERIFICAR contra Azure todavia (item 5.3: la restauracion se prueba con evidencia, CA-11).
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
SECRETOS="${JML_SECRETOS:-/run/secrets}"
CUENTA="${JML_STORAGE_CUENTA:?defina JML_STORAGE_CUENTA}"
DESTINO="$(mktemp -d)"
trap 'rm -rf "$DESTINO"' EXIT
FECHA="$(TZ=America/Bogota date +%Y-%m-%d)"
# shellcheck disable=SC1091
source "$RAIZ/infra/.env"

docker run --rm --network host \
  -v "$SECRETOS/supabase_ca_crt:/ca.crt:ro" -v "$DESTINO:/salida" \
  -e PGPASSWORD="$(cat "$SECRETOS/db_owner_password")" \
  postgres:17@sha256:2d2b8998d31037bf721cfdf764d76ba74171b4fab3431b7f72c27c56ddbdf9e3 \
  pg_dump "host=$JML_DB_HOST port=5432 dbname=postgres user=$JML_DB_USUARIO_DUENIO sslmode=verify-full sslrootcert=/ca.crt" \
    --schema=app --format=custom --no-owner --file="/salida/app-$FECHA.dump"

docker compose -f "$RAIZ/infra/compose.yaml" exec -T mariadb sh -c \
  'mariadb-dump --single-transaction --routines -u glpi -p"$(cat /run/secrets/glpi_db_password)" glpi' \
  | gzip > "$DESTINO/glpi-$FECHA.sql.gz"

az login --identity --output none
for archivo in "$DESTINO"/*; do
  az storage blob upload --auth-mode login --account-name "$CUENTA" --container-name respaldos \
    --file "$archivo" --name "$(basename "$archivo")" --overwrite false --output none
  echo "respaldado: $(basename "$archivo") ($(du -h "$archivo" | cut -f1))"
done
