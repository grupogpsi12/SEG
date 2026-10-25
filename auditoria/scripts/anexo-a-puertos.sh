#!/usr/bin/env bash
# Anexo A, Tabla III: contrasta la matriz de puertos y flujos con el stack LOCAL (docker compose con compose.local.yaml).
#
#   auditoria/scripts/anexo-a-puertos.sh
#
# Para cada flujo que la tabla permite se intenta una conexion TCP desde la red que corresponde; para cada flujo que
# NO aparece en la tabla se intenta y se espera que falle. Los flujos hacia Azure, Let's Encrypt, Cloudflare y Supabase
# no existen en el stack local: se listan al final como «no verificable aqui».
set -u
export MSYS_NO_PATHCONV=1
NET=nicolaka/netshoot@sha256:b09d9b21381f47a79b3cbcb30da25266dc17186ea00ae65e99fdc51396f48e70
FALLAS=0

# desde_red destino puerto esperado(abre|cierra) fila_de_la_tabla
conexion() {
  local red="$1" destino="$2" puerto="$3" esperado="$4" fila="$5"
  if docker run --rm --network "$red" "$NET" nc -z -w 3 "$destino" "$puerto" > /dev/null 2>&1; then real=abre; else real=cierra; fi
  if [ "$real" = "$esperado" ]; then r="OK  "; else r="FALLA"; FALLAS=$((FALLAS + 1)); fi
  printf '%s %-34s %-12s -> %-22s esperado=%-6s real=%-6s\n' "$r" "$fila" "$red" "$destino:$puerto" "$esperado" "$real"
}

desde_el_host() {
  local puerto="$1" esperado="$2" fila="$3"
  if (exec 3<>"/dev/tcp/127.0.0.1/$puerto") 2> /dev/null; then real=abre; else real=cierra; fi
  if [ "$real" = "$esperado" ]; then r="OK  "; else r="FALLA"; FALLAS=$((FALLAS + 1)); fi
  printf '%s %-34s %-12s -> %-22s esperado=%-6s real=%-6s\n' "$r" "$fila" "host" "127.0.0.1:$puerto" "$esperado" "$real"
}

echo "== flujos que la Tabla III permite"
desde_el_host 443 abre    "F1 Usuarios -> bunkerweb 443"
desde_el_host 80 abre     "F2 Usuarios -> bunkerweb 80"
conexion jml_app web 8000 abre                 "F4 bunkerweb -> web 8000"
conexion jml_app glpi 80 abre                  "F5 bunkerweb -> glpi 80"
conexion jml_bw-universe bunkerweb 5000 abre   "F6 bw-scheduler -> bunkerweb 5000"
conexion jml_app glpi 80 abre                  "F7 worker -> glpi 80"
conexion jml_db_net mariadb 3306 abre          "F8 glpi -> mariadb 3306"
conexion jml_waf-logs loki 3100 abre           "F15/F16 fluent-bit y grafana -> loki 3100"
desde_el_host 3000 abre                        "F17 tunel SSH -> grafana (127.0.0.1)"
conexion jml_pg_net postgres 5432 abre         "F20 web, worker -> postgres:17 (local)"

echo "== flujos que la tabla NO contempla: deben fallar"
conexion jml_app mariadb 3306 cierra           "MariaDB solo por db_net"
conexion jml_app postgres 5432 cierra          "PostgreSQL solo por pg_net"
conexion jml_pg_net glpi 80 cierra             "pg_net no llega a GLPI"
conexion jml_pg_net bunkerweb 8443 cierra      "pg_net no llega al WAF"
conexion jml_waf-logs web 8000 cierra          "la reporteria no llega a la aplicacion"
conexion jml_waf-logs glpi 80 cierra           "la reporteria no llega a GLPI"
conexion jml_bw-universe web 8000 cierra       "bw-universe no llega a la aplicacion"
conexion jml_bw-universe mariadb 3306 cierra   "bw-universe no llega a MariaDB"

echo "== puertos que publica el stack (el host puede tener sus propios servicios en 3306, 22, etc.: se mira lo que publica Docker)"
publicados=$(docker ps --format '{{.Names}} {{.Ports}}' | grep -E '(0\.0\.0\.0|127\.0\.0\.1|\[::\]):[0-9]+->' | tr ',' '
' | sed -E 's/^ +//' | grep -oE '^(jml-[a-z0-9-]+ )?(0\.0\.0\.0|127\.0\.0\.1|\[::\]):[0-9]+->[0-9]+' | tr '
' ';')
echo "publicados: $publicados"
for contenedor in jml-web-1 jml-worker-1 jml-glpi-1 jml-mariadb-1 jml-postgres-1 jml-loki-1 jml-bw-scheduler-1; do
  n=$(docker inspect "$contenedor" --format '{{len .HostConfig.PortBindings}}')
  [ "$n" = 0 ] && echo "OK   $contenedor no publica ningun puerto" || { echo "FALLA $contenedor publica $n puertos"; FALLAS=$((FALLAS + 1)); }
done
for contenedor in jml-bunkerweb-1; do
  escuchando=$(docker inspect "$contenedor" --format '{{range $p, $b := .HostConfig.PortBindings}}{{$p}} {{end}}')
  echo "OK   $contenedor publica: $escuchando (el unico expuesto a usuarios)"
done
echo "== redes internas (sin salida a internet)"
for n in jml_db_net jml_pg_net; do
  i=$(docker network inspect "$n" --format '{{.Internal}}')
  [ "$i" = true ] && echo "OK   $n internal=true" || { echo "FALLA $n internal=$i"; FALLAS=$((FALLAS + 1)); }
done

echo "== redirect del puerto 80 y TLS del 443"
curl -s -o /dev/null -w "HTTP 80 -> %{http_code} %{redirect_url}\n" --max-time 10 --resolve app.localhost:80:127.0.0.1 http://app.localhost/ingreso
curl -sk -o /dev/null -w "HTTPS 443 -> %{http_code}\n" --max-time 10 --resolve app.localhost:443:127.0.0.1 https://app.localhost/ingreso

echo "== no verificable en el stack local (Azure, Let's Encrypt, Cloudflare, Supabase)"
cat <<'LISTA'
F3  Administrador -> VM (sshd) 22        Azure: NSG limitado a IPs del equipo
F9  web, worker, migrar -> Supabase 5432  solo lectura de catalogo en F3 (no se ejercita desde los contenedores)
F10 web -> Supabase Auth 443              cubierto por GoTrue simulado; no se llama al servicio real
F11 admin-usuarios -> Supabase admin 443  idem
F12 VM -> Key Vault 443                   Azure; localmente los secretos salen de /run/secrets (SOPS + age)
F13 VM -> Blob 443                        Azure; localmente la exportacion de auditoria escribe a un directorio
F14 bw-scheduler -> Let's Encrypt 443     localmente BunkerWeb usa un certificado autofirmado
F18 loki -> Blob 443                      Azure con identidad administrada
F19 cloudflared -> Cloudflare 7844        propuesta (ADR-024), no desplegada
LISTA

echo
[ "$FALLAS" -eq 0 ] && echo "TABLA III: todos los flujos comprobables coinciden" || { echo "TABLA III: $FALLAS diferencias"; exit 1; }
