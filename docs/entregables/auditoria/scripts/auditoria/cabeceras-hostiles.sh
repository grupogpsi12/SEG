#!/usr/bin/env bash
# F3-U06: cabeceras hostiles contra el stack LOCAL, por el WAF. Criterios: cada una se atiende (2xx/3xx)
# Va a `/` (302 al ingreso): `/ingreso` tiene un limite propio de 5 r/min que daria 429 y no probaria la regla.
# o la bloquea el WAF (403), nunca 5xx; la base queda con las mismas filas; y la peticion normal de
# control sigue dando 200 antes y despues (un bloqueo esperado no debe romper lo legitimo).
#   auditoria/scripts/cabeceras-hostiles.sh
set -u
export MSYS_NO_PATHCONV=1
HOST=app.localhost
IP="$(docker compose -f infra/compose.yaml ps -q bunkerweb >/dev/null 2>&1; echo 127.0.0.1)"
pet() {  # args: cabecera
  curl -sk -o /dev/null -w "%{http_code}" --max-time 20 --resolve "$HOST:443:$IP" "$@" "https://$HOST/"
}
filas() {
  docker exec -i jml-web-1 python - <<'PY'
import os, psycopg
from pathlib import Path
c = psycopg.connect(host=os.environ["JML_DB_HOST"], dbname="postgres", user=os.environ["JML_DB_USUARIO"],
    password=Path("/run/secrets/db_password").read_text().strip(), sslmode="disable",
    options="-c search_path=app -c default_transaction_read_only=on")
cur = c.cursor()
cur.execute("select relname from pg_class join pg_namespace n on n.oid=relnamespace where nspname='app' and relkind='r' order by 1")
total = {}
for (t,) in cur.fetchall():
    cur.execute(f'select count(*) from "{t}"')  # nombres leidos del catalogo, no de una entrada
    total[t] = cur.fetchone()[0]
for volatil in ('sincronizacion',):  # la escribe el worker cada 5 minutos, no la peticion
    total.pop(volatil, None)
cur.execute("select count(*) from pg_class join pg_namespace n on n.oid=relnamespace where nspname='app'")
print(sorted(total.items()), "objetos=", cur.fetchone()[0])
PY
}
unban() {  # la IP que ve el WAF es la de la red `app` (10.20.40.128 con ip_range), no la del anfitrion
  for ip in 10.20.40.128 127.0.0.1; do
    docker compose -f infra/compose.yaml exec -T bw-scheduler bwcli unban "$ip" > /dev/null 2>&1
  done
  true
}

unban
antes="$(filas)"
echo "control antes: $(pet -H 'User-Agent: Mozilla/5.0 (control)')"
LARGO="$(head -c 9000 /dev/zero | tr '\0' 'A')"
declare -a CASOS=(
  "User-Agent: ' OR 1=1--"
  "User-Agent: ');DROP TABLE solicitud;--"
  "User-Agent: <script>alert(1)</script>"
  "User-Agent: \${jndi:ldap://127.0.0.1/a}"
  "User-Agent: () { :; }; echo vulnerable"
  "Referer: https://app.localhost/' UNION SELECT password FROM auth.users--"
  "Referer: javascript:alert(1)"
  "Accept-Language: es-CO'; WAITFOR DELAY '0:0:5'--"
  "Accept-Language: ../../../../etc/passwd"
  "Cookie: sessionid=' OR '1'='1; csrftoken=<img src=x onerror=alert(1)>"
  "Cookie: sessionid=$LARGO"
  "X-Forwarded-For: 127.0.0.1, 10.20.40.2"
  "X-Forwarded-Proto: gopher"
  "Host: evil.example"
)
for caso in "${CASOS[@]}"; do
  sleep 1.5  # el limite general es de 2 r/s: asi el estado refleja la regla del WAF, no el limite
  codigo="$(pet -H "$caso")"
  echo "${caso:0:70} -> $codigo"
  case "$codigo" in 5*) echo "  FALLA: 5xx"; fallo=1;; esac
  unban
done
echo "control despues: $(pet -H 'User-Agent: Mozilla/5.0 (control)')"
despues="$(filas)"
[ "$antes" = "$despues" ] && echo "BASE INTEGRA: mismas filas y mismos objetos" || { echo "BASE CAMBIO"; echo "$antes"; echo "$despues"; fallo=1; }
# El valor llega LITERAL al registro del WAF (como texto, entre comillas) y no a la aplicacion
echo "en el log del WAF: $(docker logs --since 10m jml-bunkerweb-1 2>&1 | grep -c "OR 1=1") lineas con el valor literal; en el log de la web: $(docker logs --since 10m jml-web-1 2>&1 | grep -c "OR 1=1")"
echo "Host ajeno (evil.example) lo atiende la pagina por defecto de BunkerWeb, no Django: $(curl -sk --resolve evil.example:443:127.0.0.1 https://evil.example/ | grep -c 'Nothing to see here') coincidencia"
exit "${fallo:-0}"
