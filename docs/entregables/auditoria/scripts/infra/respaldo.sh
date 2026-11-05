#!/usr/bin/env bash
# RD-06 / RNF-04 (RPO 24 h): respaldo diario de la base de la aplicacion (PostgreSQL 17 local) y
# de la de GLPI (MariaDB), guardado fuera del equipo (disco externo) con 30 dias de retencion
# (ADR-031). Se programa una vez al dia en el host. La restauracion: docs/operacion.md.
#
#   JML_RESPALDO_DESTINO=/e/jml/respaldos infra/scripts/respaldo.sh
#
# - Aplicacion: `pg_dump` en formato custom como `app_owner` (duenio del esquema: lee todo,
#   ADR-028) desde una imagen postgres:17 de un solo uso, por la red interna pg_net.
# - GLPI: `mariadb-dump --single-transaction` dentro del contenedor mariadb.
# - Retencion: borra del destino los respaldos de mas de 30 dias, solo los de este script.
# El simulacro de restauracion con evidencia es infra/scripts/restaurar-prueba.sh (CA-11).
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
# Hora de Bogota con desfase fijo: Git Bash en Windows no trae zoneinfo y TZ=America/Bogota daba UTC.
FECHA="$(TZ='<-05>5' date +%Y-%m-%d)"
PG_IMAGEN=postgres:17@sha256:2d2b8998d31037bf721cfdf764d76ba74171b4fab3431b7f72c27c56ddbdf9e3
SECRETOS="${JML_SECRETOS:-$RAIZ/secrets}"
DESTINO="${JML_RESPALDO_DESTINO:?defina JML_RESPALDO_DESTINO (carpeta del disco externo)}"
RETENCION_DIAS=30
COMPOSE=(-f infra/compose.yaml -f infra/compose.local.yaml)
CONEXION="host=postgres port=5432 dbname=postgres user=app_owner sslmode=disable"

# Rutas relativas para compose y absolutas para `docker run -v` (Git Bash, MSYS_NO_PATHCONV).
cd "$RAIZ"
mkdir -p "$DESTINO"
DESTINO="$(cd "$DESTINO" && pwd)"
clave_duenio="$(cat "$SECRETOS/db_owner_password")"
export MSYS_NO_PATHCONV=1   # Git Bash: las rutas de los contenedores no se traducen

docker run --rm --network jml_pg_net -v "$DESTINO:/salida" -e PGPASSWORD="$clave_duenio" \
  "$PG_IMAGEN" \
  pg_dump "$CONEXION" --schema=app --format=custom --no-owner --file="/salida/app-$FECHA.dump"

docker compose "${COMPOSE[@]}" exec -T mariadb sh -c \
  'mariadb-dump --single-transaction --routines -u glpi -p"$(cat /run/secrets/glpi_db_password)" glpi' \
  | gzip > "$DESTINO/glpi-$FECHA.sql.gz"

for archivo in "$DESTINO/app-$FECHA.dump" "$DESTINO/glpi-$FECHA.sql.gz"; do
  echo "respaldado: $archivo ($(du -h "$archivo" | cut -f1))"
done
find "$DESTINO" -maxdepth 1 -type f \( -name 'app-*.dump' -o -name 'glpi-*.sql.gz' \) \
  -mtime +"$RETENCION_DIAS" -print -delete | sed 's/^/retirado por retencion: /'
