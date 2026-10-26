#!/usr/bin/env bash
# CA-21 (RNF-16): un ataque de prueba aparece clasificado como `waf` en Loki en menos de 2 minutos. Stack LOCAL con el overlay
# de reporteria (compose.reporteria.yaml: BunkerWeb envia sus logs a fluent-bit, que los clasifica con clasificar.lua).
#
#   auditoria/scripts/reporteria-waf.sh
#
# Mide el tiempo hasta que la linea de ModSecurity aparece en Loki con tipo="waf". La parte «sus datos estan en Blob» de CA-21
# no se puede comprobar en local (Azure): aqui Loki guarda en un volumen.
set -u
export MSYS_NO_PATHCONV=1
NET=nicolaka/netshoot@sha256:b09d9b21381f47a79b3cbcb30da25266dc17186ea00ae65e99fdc51396f48e70
ID="lab-ca21-$(date +%s)"
C="-f infra/compose.yaml -f infra/compose.local.yaml -f infra/compose.reporteria.yaml"

docker compose $C up -d bunkerweb bw-scheduler > /dev/null 2>&1
for _ in $(seq 1 60); do [ "$(docker inspect -f '{{.State.Health.Status}}' jml-bunkerweb-1 2> /dev/null)" = healthy ] && break; sleep 3; done
sleep 20
bash auditoria/scripts/neutralizar.sh unban

echo "control positivo: la misma operacion legitima da: $(curl -sk -o /dev/null -w '%{http_code}' --max-time 15 --resolve app.localhost:443:127.0.0.1 https://app.localhost/ingreso)"
t0=$(date +%s)
echo "ataque (inyeccion SQL en la URL, correlation_id $ID) -> $(curl -sk -o /dev/null -w '%{http_code}' --max-time 15 --resolve app.localhost:443:127.0.0.1 -H "X-Request-ID: $ID" "https://app.localhost/ingreso?id=1%27%20OR%20%271%27=%271%27%20UNION%20SELECT%20NULL--")"

for intento in $(seq 1 24); do
  n=$(docker run --rm --network jml_waf-logs "$NET" sh -c "now=\$(date +%s); curl -s -G http://loki:3100/loki/api/v1/query_range --data-urlencode 'query={tipo=\"waf\"} |= \"UNION\"' --data-urlencode \"start=\$((now-600))000000000\" --data-urlencode \"end=\${now}000000000\" --data-urlencode limit=5 | grep -o '\"tipo\":\"waf\"' | wc -l" 2> /dev/null)
  if [ "${n:-0}" -gt 0 ]; then
    t1=$(date +%s)
    echo "la linea de ModSecurity aparece en Loki con tipo=\"waf\" ($n flujos) a los $((t1 - t0)) s del ataque (limite de CA-21: 120 s)"
    [ $((t1 - t0)) -lt 120 ] && echo "CA-21 (parte local) CUMPLIDO" && exit 0
    echo "CA-21 FALLA: tardo demasiado"; exit 1
  fi
  sleep 5
done
echo "CA-21 FALLA: la linea no aparecio en 120 s"; exit 1
