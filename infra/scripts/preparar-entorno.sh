#!/usr/bin/env bash
# Prepara lo que necesita `docker compose -f infra/compose.yaml` (item 2.2, ADR-009).
#
#   infra/scripts/preparar-entorno.sh            # local: secretos en ./secrets
#   JML_SECRETOS=/run/secrets infra/scripts/preparar-entorno.sh   # Azure: tmpfs desde Key Vault
#
# 1. Genera los secretos aleatorios que falten (nunca sobrescribe uno existente).
# 2. Escribe infra/.env (ignorado por git, permisos 600) con las variables que las imagenes de
#    terceros solo aceptan por entorno (API_TOKEN de BunkerWeb, clave de MariaDB para GLPI) y la
#    configuracion no secreta. En Azure, apuntar ENV_SALIDA a un tmpfs.
#
# No genera los secretos que vienen de Supabase (db_password, supabase_ca_crt,
# supabase_service_role): esos los crea el administrador (docs/spikes/supabase.md).
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
SECRETOS="${JML_SECRETOS:-$RAIZ/secrets}"
ENV_SALIDA="${ENV_SALIDA:-$RAIZ/infra/.env}"
umask 077
mkdir -p "$SECRETOS"

aleatorio() { python3 -c "import secrets; print(secrets.token_urlsafe($1))"; }

asegurar() {  # nombre longitud
  if [ ! -s "$SECRETOS/$1" ]; then
    aleatorio "$2" > "$SECRETOS/$1"
    echo "creado: $SECRETOS/$1"
  fi
}

asegurar django_secret_key 50
asegurar bw_api_token 32
asegurar glpi_db_password 32

for requerido in db_password supabase_ca_crt; do
  if [ ! -s "$SECRETOS/$requerido" ]; then
    echo "falta $SECRETOS/$requerido (ver docs/spikes/supabase.md)" >&2
    exit 1
  fi
done
# admin-usuarios lo monta solo si existe; compose exige el archivo, aunque sea vacio.
[ -e "$SECRETOS/supabase_service_role" ] || : > "$SECRETOS/supabase_service_role"
[ -e "$SECRETOS/db_owner_password" ] || : > "$SECRETOS/db_owner_password"  # solo `migrar` (ADR-028)

{
  echo "# Generado por infra/scripts/preparar-entorno.sh: NO versionar (ADR-009)"
  echo "BW_API_TOKEN=$(cat "$SECRETOS/bw_api_token")"
  echo "GLPI_DB_PASSWORD=$(cat "$SECRETOS/glpi_db_password")"
  echo "APP_DOMINIO=${APP_DOMINIO:-app.localhost}"
  echo "GLPI_DOMINIO=${GLPI_DOMINIO:-glpi.localhost}"
  echo "SECURITY_MODE=${SECURITY_MODE:-block}"
  echo "JML_DB_HOST=${JML_DB_HOST:-aws-0-us-east-1.pooler.supabase.com}"
  echo "JML_DB_USUARIO=${JML_DB_USUARIO:?defina JML_DB_USUARIO=app_backend.<ref>}"
  echo "JML_DB_USUARIO_DUENIO=${JML_DB_USUARIO_DUENIO:-app_owner.${JML_DB_USUARIO#*.}}"
  echo "JML_SUPABASE_URL=${JML_SUPABASE_URL:?defina JML_SUPABASE_URL}"
  echo "JML_SUPABASE_CLAVE_PUBLICA=${JML_SUPABASE_CLAVE_PUBLICA:?defina JML_SUPABASE_CLAVE_PUBLICA}"
} > "$ENV_SALIDA"
chmod 600 "$ENV_SALIDA"
echo "escrito: $ENV_SALIDA"
