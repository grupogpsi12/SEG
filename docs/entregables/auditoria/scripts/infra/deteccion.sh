#!/usr/bin/env bash
# RNF-01 y CA-11: cuanto tarda el chequeo de salud en marcar un fallo de GLPI o de la base.
#
#   infra/scripts/deteccion.sh glpi        # detiene GLPI y mide hasta que el worker queda unhealthy
#   infra/scripts/deteccion.sh base        # detiene la base (modo local) y mide hasta que web cae
#   COMPOSE="-f infra/compose.yaml -f infra/compose.local.yaml" infra/scripts/deteccion.sh glpi
#
# Al terminar vuelve a levantar el servicio detenido. Solo para el stack de pruebas: corta el
# servicio de verdad durante la medicion. Limite: 5 minutos.
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
COMPOSE="${COMPOSE:--f infra/compose.yaml -f infra/compose.local.yaml}"
cd "$RAIZ"
case "${1:-}" in
  glpi) detener=glpi; vigilar=worker ;;
  base) detener=postgres; vigilar=web ;;
  *) echo "uso: $0 glpi|base" >&2; exit 2 ;;
esac
contenedor="$(docker compose $COMPOSE --profile glpi ps -q "$vigilar")"
[ -n "$contenedor" ] || { echo "no esta arriba: $vigilar" >&2; exit 1; }
estado() { docker inspect "$contenedor" --format '{{.State.Health.Status}}'; }
[ "$(estado)" = healthy ] || { echo "$vigilar debe empezar healthy (esta $(estado))" >&2; exit 1; }

trap 'docker compose $COMPOSE --profile glpi start "$detener" > /dev/null' EXIT
docker compose $COMPOSE --profile glpi stop "$detener" > /dev/null
inicio=$(date +%s)
while [ "$(estado)" != unhealthy ]; do
  [ $(( $(date +%s) - inicio )) -lt 300 ] || { echo "$detener detenido: $vigilar sigue $(estado) a los 300 s (NO detectado)"; exit 1; }
  sleep 2
done
echo "$detener detenido: $vigilar unhealthy a los $(( $(date +%s) - inicio )) s (RNF-01 exige menos de 120)"
