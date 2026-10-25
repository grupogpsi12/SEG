#!/usr/bin/env bash
# Deja GLPI listo para JML (items 3.1 y 0.3) y escribe sus secretos. IDEMPOTENTE.
#
#   infra/glpi/preparar-glpi.sh                          # compose normal
#   COMPOSE="-f infra/compose.yaml -f infra/compose.local.yaml" infra/glpi/preparar-glpi.sh
#   docker compose ... run --rm configurar-glpi          # despues: categorias, reglas, SLA, plantillas
#
# Escribe en secrets/: glpi_app_token, glpi_user_token, glpi_admin_user_token y glpi_admin_password.
# Cierra los riesgos de una instalacion nueva de GLPI: deshabilita las cuentas de demostracion
# (post-only, tech, normal) y cambia la clave por defecto del administrador `glpi`.
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
SECRETOS="${JML_SECRETOS:-$RAIZ/secrets}"
COMPOSE="${COMPOSE:--f infra/compose.yaml}"
cd "$RAIZ"
umask 077
mkdir -p "$SECRETOS"

# `php < archivo`: sin copiar nada al contenedor. MSYS_NO_PATHCONV: Git Bash no debe tocar las rutas.
export MSYS_NO_PATHCONV=1
salida="$(docker compose $COMPOSE exec -T glpi php < infra/glpi/bootstrap.php | tr -d '\r')"
[ "$(printf '%s\n' "$salida" | wc -l)" -eq 3 ] || { echo "bootstrap.php no devolvio tres tokens:" >&2; echo "$salida" >&2; exit 1; }
printf '%s' "$(printf '%s\n' "$salida" | sed -n 1p)" > "$SECRETOS/glpi_app_token"
printf '%s' "$(printf '%s\n' "$salida" | sed -n 2p)" > "$SECRETOS/glpi_user_token"
printf '%s' "$(printf '%s\n' "$salida" | sed -n 3p)" > "$SECRETOS/glpi_admin_user_token"

# Cuentas de demostracion fuera, y clave propia para el administrador (solo si aun no se hizo).
for cuenta in post-only tech normal; do
  docker compose $COMPOSE exec -T glpi php /var/www/glpi/bin/console user:disable "$cuenta" > /dev/null 2>&1 || true
done
if [ ! -s "$SECRETOS/glpi_admin_password" ]; then
  clave="$(head -c 24 /dev/urandom | base64 | tr -d '=+/\n' | head -c 28)"
  docker compose $COMPOSE exec -T glpi php /var/www/glpi/bin/console user:reset_password glpi --password="$clave" > /dev/null
  printf '%s' "$clave" > "$SECRETOS/glpi_admin_password"
  echo "clave del administrador de GLPI: $SECRETOS/glpi_admin_password"
fi
echo "GLPI listo: API habilitada, cliente de API, perfil y usuario de servicio, y tokens en $SECRETOS"
