#!/usr/bin/env bash
# F6-02 / F6-03: ZAP activo y sqlmap A TRAVES DEL WAF contra el stack LOCAL de pruebas.
#
#   auditoria/scripts/escaner-con-waf.sh exento        # baneo y limites de ritmo relajados (lab); CRS en bloqueo
#   auditoria/scripts/escaner-con-waf.sh sin_exencion  # configuracion real: el baneo debe actuar
#
# Neutraliza antes y despues (neutralizar.sh), registra la exencion y comprueba, con un ataque de
# control antes y despues, que ModSecurity siga en bloqueo. Las dos mediciones se reportan por separado.
set -u
export MSYS_NO_PATHCONV=1
MODO="${1:?uso: $0 exento|sin_exencion}"
RAIZ="$(pwd -W 2>/dev/null || pwd)"
C="-f infra/compose.yaml -f infra/compose.local.yaml"
ZAP=ghcr.io/zaproxy/zaproxy@sha256:5ccfff9a411743ab2615136a2edd7416bec9ce41572fa94e935df38c14adb2b6
PY=python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
SQLMAP="sqlmap==1.10.10 --hash=sha256:32c4b516735c1c1a3183effd0d50a9217c9f22fc9e8b17ca4c4f6a5f2028bd93"
CSRF="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"  # secreto fijo de la cookie csrftoken (Django lo enmascara)
MINUTOS="${MINUTOS:-8}"
S="$RAIZ/.contrato-tmp/escaner-$MODO"
LAB="lab-f6-$(echo "$MODO" | tr '_' '-')"  # correlation_id de laboratorio (X-Request-ID valido)
rm -rf "$S" && mkdir -p "$S" && chmod 777 "$S"

curl_waf() { curl -sk -o /dev/null -w "%{http_code}" --max-time 15 --resolve app.localhost:443:127.0.0.1 "$@"; }
unban() { bash auditoria/scripts/neutralizar.sh unban >/dev/null 2>&1; }

echo "== modo: $MODO · correlation_id de laboratorio: $LAB"
bash auditoria/scripts/neutralizar.sh pre

if [ "$MODO" = exento ]; then
  echo "== EXENCION REGISTRADA: baneo y limites de ritmo relajados para TODO el sitio en este stack de laboratorio"
  echo "   (BunkerWeb no tiene exencion por IP sin saltar ModSecurity); overlay: auditoria/laboratorio/compose.escaner.yaml"
  docker compose $C -f auditoria/laboratorio/compose.escaner.yaml up -d bw-scheduler > /dev/null 2>&1
else
  echo "== sin exencion: configuracion real del proyecto (2 r/s, ban de 1 hora por mal comportamiento)"
  docker compose $C up -d bw-scheduler > /dev/null 2>&1
fi
echo "   esperando a que BunkerWeb recargue la configuracion..."
sleep 45
unban

echo "== controles antes de escanear"
antes_legit=$(curl_waf -H 'User-Agent: Mozilla/5.0 (control)' https://app.localhost/)
sleep 1.5
antes_ataque=$(curl_waf -H "User-Agent: ' OR 1=1--" https://app.localhost/)
echo "   peticion legitima: $antes_legit (esperado 302) · ataque SQL por User-Agent: $antes_ataque (esperado 403: CRS en bloqueo)"
unban
if [ "$MODO" = exento ]; then
  rafaga=$(for _ in $(seq 1 30); do curl_waf https://app.localhost/salud; echo; done | sort | uniq -c | tr '\n' ' ')
  echo "   30 peticiones seguidas a /salud: $rafaga (sin 429 = limites relajados)"
fi

echo "== sesiones de laboratorio"
docker compose $C run --rm --no-deps -T -v "$RAIZ:/repo:ro" -w /repo -e PYTHONPATH=/repo web \
  python auditoria/scripts/sesiones-laboratorio.py 2>/dev/null | tail -1 > "$S/sesiones.json"
clave() { sed -E "s/.*\"$1\": \"([^\"]+)\".*/\1/" "$S/sesiones.json"; }
RRHH="$(clave rrhh)"; TEC="$(clave tecnico)"; AUD="$(clave auditor)"
COL="$(sed -E 's/.*"colaborador": "([^"]+)".*/\1/' "$S/sesiones.json")"; SOL="$(sed -E 's/.*"solicitud": "([^"]+)".*/\1/' "$S/sesiones.json")"

cat > "$S/hook.py" << 'PY'
"""Hook de ZAP: cookie de sesion, correlation_id de laboratorio y exclusiones (no salir, no ingreso, no CSV)."""
import os


def zap_started(zap, target):
    zap.replacer.add_rule(description="sesion", enabled=True, matchtype="REQ_HEADER", matchregex=False,
                          matchstring="Cookie", replacement=os.environ["COOKIE"])
    zap.replacer.add_rule(description="lab", enabled=True, matchtype="REQ_HEADER", matchregex=False,
                          matchstring="X-Request-ID", replacement=os.environ["LAB"])
    for patron in (r".*/salir.*", r".*/ingreso.*", r".*\.csv.*"):
        zap.spider.exclude_from_scan(patron)
        zap.ascan.exclude_from_scan(patron)
    zap.ascan.set_option_max_scan_duration_in_mins(int(os.environ["MINUTOS"]))
    zap.ascan.set_option_thread_per_host(4)
PY

for par in "rrhh $RRHH /solicitudes" "tecnico $TEC /dashboard"; do
  set -- $par
  echo "== ZAP activo por el WAF, autenticado como $1 (hasta $MINUTOS minutos)"
  docker run --rm --add-host app.localhost:host-gateway -e COOKIE="sessionid=$2; csrftoken=$CSRF" -e LAB="$LAB" -e MINUTOS="$MINUTOS" \
    -v "$S:/zap/wrk:rw" "$ZAP" zap-full-scan.py -t "https://app.localhost$3" -m "$MINUTOS" -I \
    --hook=/zap/wrk/hook.py -r "activo-$1.html" -J "activo-$1.json" > "$S/activo-$1.log" 2>&1
  grep -E "^(FAIL|WARN)-NEW|FAIL-INPROG|PASS: [0-9]+|WARN-NEW: [0-9]+" "$S/activo-$1.log" | tail -3
done

echo "== sqlmap nivel 3 por el WAF"
printf '%s\n' "$SQLMAP" > "$S/req-sqlmap.txt"
cat > "$S/sqlmap.sh" << SH
set -u
pip install -q --disable-pip-version-check --root-user-action=ignore --require-hashes -r /salida/req-sqlmap.txt
B="--batch --level=3 --risk=1 --flush-session --output-dir=/salida/sqlmap --disable-coloring --headers=X-Request-ID:$LAB --timeout=15 --retries=1"
probar() { echo "### \$1"; shift; timeout 600 sqlmap "\$@" \$B 2>&1 | grep -E "is vulnerable|injectable|all tested|not injectable|CRITICAL|WAF/IPS|ERROR" | sort | uniq -c | sort -rn | head -6; }
probar "GET /cuentas (tecnico)" -u "https://app.localhost/cuentas?nombre=Ana&usuario=ana&pagina=1" --cookie="sessionid=$TEC"
probar "ruta /colaboradores/<id> (tecnico)" -u "https://app.localhost/colaboradores/$COL*" --cookie="sessionid=$TEC"
probar "ruta /solicitudes/<id> (rrhh)" -u "https://app.localhost/solicitudes/$SOL*" --cookie="sessionid=$RRHH"
probar "GET /auditoria?pagina (auditor)" -u "https://app.localhost/auditoria?pagina=1" --cookie="sessionid=$AUD"
SH
docker run --rm --add-host app.localhost:host-gateway -v "$S:/salida" "$PY" sh /salida/sqlmap.sh > "$S/sqlmap.log" 2>&1
cat "$S/sqlmap.log"

echo "== controles despues de escanear"
bans=$(docker compose $C exec -T bw-scheduler bwcli bans 2>/dev/null | sed 's/\x1b\[[0-9;]*m//g' | grep -c "🔒")
echo "   IPs baneadas al terminar: $bans"
if [ "$MODO" = exento ]; then
  unban
  sleep 1.5
  despues_ataque=$(curl_waf -H "User-Agent: ' OR 1=1--" https://app.localhost/)
  echo "   ataque SQL por User-Agent despues del escaneo: $despues_ataque (esperado 403: ModSecurity siguio en bloqueo)"
fi
echo "== resumen de alertas de ZAP (riesgo: cantidad)"
for f in "$S"/activo-*.json; do
  [ -f "$f" ] && echo "   $(basename "$f"): $(grep -o '"riskdesc": *"[A-Za-z]*' "$f" | sed 's/.*"//' | sort | uniq -c | tr '\n' ' ')"
done
echo "== trafico visto por el WAF durante la corrida (codigos HTTP de app.localhost)"
docker logs --since 60m jml-bunkerweb-1 2>&1 | grep '^app.localhost' | awk '{print $9}' | sort | uniq -c | sort -rn | head -8

echo "== neutralizar al terminar"
if [ "$MODO" = exento ]; then docker compose $C up -d bw-scheduler > /dev/null 2>&1; fi
bash auditoria/scripts/neutralizar.sh post
cp -r "$S"/*.json "$S"/*.log "$RAIZ/.contrato-tmp/" 2>/dev/null
