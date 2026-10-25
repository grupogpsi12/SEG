#!/usr/bin/env bash
# B-36: cuantas navegaciones de pagina seguidas aguanta el limite de 2 r/s del WAF antes de responder 429. Stack LOCAL.
#
#   auditoria/scripts/limite-de-ritmo.sh
#
# Para cada espera entre peticiones se levantan los baneos, se piden 6 paginas (302 sin sesion) y se imprimen los codigos.
# Las peticiones a /static/ tienen su propio limite (10 r/s) y no cuentan aqui. Al final se levantan los baneos.
set -u
export MSYS_NO_PATHCONV=1
for espera in 0 0.2 0.4 0.55 1.0; do
  bash auditoria/scripts/neutralizar.sh unban
  sleep 4
  salida=""
  for _ in 1 2 3 4 5 6; do
    c=$(curl -sk -o /dev/null -w "%{http_code}" --max-time 10 --resolve app.localhost:443:127.0.0.1 https://app.localhost/solicitudes)
    salida="$salida $c"
    [ "$espera" != 0 ] && sleep "$espera"
  done
  echo "espera entre peticiones=${espera}s ->$salida"
done
bash auditoria/scripts/neutralizar.sh unban
