#!/usr/bin/env bash
# PostgreSQL local para que el equipo pruebe la aplicacion sin la base de Supabase
# (infra/compose.local.yaml). Reproduce los roles de Supabase y aplica el mismo aprovisionamiento
# del duenio separado (ADR-028). Lo ejecuta la imagen oficial de postgres al crear el volumen.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v clave_backend="'$(cat /run/secrets/db_password)'" <<'SQL'
CREATE ROLE anon NOLOGIN;
CREATE ROLE authenticated NOLOGIN;
CREATE ROLE service_role NOLOGIN;
CREATE ROLE app_backend LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS
  CONNECTION LIMIT 20 PASSWORD :clave_backend;
ALTER ROLE app_backend SET search_path = app;
ALTER ROLE app_backend SET statement_timeout = '30s';
CREATE SCHEMA app;
SQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v clave_duenio="'$(cat /run/secrets/db_owner_password)'" \
  -f /opt/jml/duenio-separado.sql
