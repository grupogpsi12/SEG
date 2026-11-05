#!/usr/bin/env bash
# B-01: la IP fija de BunkerWeb (10.20.40.2, la UNICA en la que Django confía para X-Forwarded-*,
# RS-05) no está reservada: si otro contenedor de la red `app` arranca antes, la toma y BunkerWeb
# no arranca. Pasa de verdad cuando Docker reinicia y reanuda los contenedores en cualquier orden.
#
# Reproducción determinista, solo en el stack LOCAL de pruebas (lo detiene y lo deja arriba):
#   auditoria/scripts/reproducir-ip-confianza.sh
# Resultado esperado ANTES de la corrección: web = 10.20.40.2 y bunkerweb falla con «Address already
# in use». DESPUÉS: web recibe una IP del rango dinámico y bunkerweb arranca con 10.20.40.2.
set -uo pipefail
cd "$(dirname "$0")/../.."
C="-f infra/compose.yaml -f infra/compose.local.yaml -f infra/compose.reporteria.yaml"
export MSYS_NO_PATHCONV=1

docker compose $C --profile glpi down > /dev/null 2>&1
docker compose $C up -d --no-deps postgres > /dev/null 2>&1
sleep 8
docker compose $C up -d --no-deps web > /dev/null 2>&1      # arranca ANTES que bunkerweb
sleep 3
echo "IP de web en la red app:  $(docker inspect jml-web-1 --format '{{(index .NetworkSettings.Networks "jml_app").IPAddress}}')"
if docker compose $C up -d --no-deps bunkerweb > /dev/null 2>&1; then
  sleep 3
  echo "IP de bunkerweb:          $(docker inspect jml-bunkerweb-1 --format '{{(index .NetworkSettings.Networks "jml_app").IPAddress}}')"
  echo "RESULTADO: bunkerweb ARRANCO con su IP fija"
else
  echo "RESULTADO: bunkerweb NO ARRANCO: $(docker inspect jml-bunkerweb-1 --format '{{.State.Error}}' 2> /dev/null)"
fi
echo "IP de confianza declarada: $(grep -o 'JML_PROXIES_CONFIABLES: "[^"]*"' infra/compose.yaml)"
