#!/usr/bin/env bash
# F6 (plan §9: «ZAP en las dos posiciones») y Entrega 3 (Documento 2): ZAP ACTIVO autenticado contra la aplicacion DIRECTA
# (web:8000, sin WAF) del stack LOCAL. Mide el codigo sin el borde; sin WAF no hay baneo ni limite de ritmo.
#
#   MINUTOS=8 auditoria/scripts/escaner-directo.sh
#
# Neutraliza antes y despues (copia de la base, worker detenido, restauracion). La sesion de cada rol se crea con
# sesiones-laboratorio.py (equivale a haber pasado el TOTP). Se excluyen /salir, /ingreso y los CSV.
set -u
export MSYS_NO_PATHCONV=1
RAIZ="$(pwd -W 2>/dev/null || pwd)"
C="-f infra/compose.yaml -f infra/compose.local.yaml"
ZAP=ghcr.io/zaproxy/zaproxy@sha256:5ccfff9a411743ab2615136a2edd7416bec9ce41572fa94e935df38c14adb2b6
CSRF="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
MINUTOS="${MINUTOS:-8}"
LAB="lab-f6-directo"
S="$RAIZ/.contrato-tmp/zap-directo"
rm -rf "$S" && mkdir -p "$S" && chmod 777 "$S"

bash auditoria/scripts/neutralizar.sh pre
docker compose $C run --rm --no-deps -T -v "$RAIZ:/repo:ro" -w /repo -e PYTHONPATH=/repo web \
  python auditoria/scripts/sesiones-laboratorio.py 2>/dev/null | tail -1 > "$S/sesiones.json"
clave() { sed -E "s/.*\"$1\": \"([^\"]+)\".*/\1/" "$S/sesiones.json"; }
RRHH="$(clave rrhh)"; TEC="$(clave tecnico)"
IPWEB=$(docker inspect jml-web-1 --format '{{(index .NetworkSettings.Networks "jml_app").IPAddress}}')
echo "== aplicacion directa en $IPWEB:8000 (Host app.localhost, sin WAF)"
echo "   control: GET /ingreso -> $(docker run --rm --network jml_app --add-host app.localhost:$IPWEB nicolaka/netshoot@sha256:b09d9b21381f47a79b3cbcb30da25266dc17186ea00ae65e99fdc51396f48e70 curl -s -o /dev/null -w '%{http_code}' http://app.localhost:8000/ingreso)"

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
  echo "== ZAP activo DIRECTO, autenticado como $1 (hasta $MINUTOS minutos)"
  docker run --rm --network jml_app --add-host app.localhost:$IPWEB -e COOKIE="sessionid=$2; csrftoken=$CSRF" -e LAB="$LAB" -e MINUTOS="$MINUTOS" \
    -v "$S:/zap/wrk:rw" "$ZAP" zap-full-scan.py -t "http://app.localhost:8000$3" -m "$MINUTOS" -I \
    --hook=/zap/wrk/hook.py -r "directo-$1.html" -J "directo-$1.json" > "$S/directo-$1.log" 2>&1
  grep -E "^(FAIL|WARN)-NEW|FAIL-INPROG|PASS: [0-9]+|WARN-NEW: [0-9]+|FAIL-NEW: [0-9]+" "$S/directo-$1.log" | tail -4
done

echo "== resumen de alertas de ZAP (riesgo: cantidad)"
for f in "$S"/directo-*.json; do
  [ -f "$f" ] && echo "   $(basename "$f"): $(grep -o '"riskdesc": *"[A-Za-z]*' "$f" | sed 's/.*"//' | sort | uniq -c | tr '\n' ' ')"
done
echo "== cadena de auditoria despues de la corrida (antes de restaurar)"
docker exec -i jml-web-1 python manage.py shell -c "
from jml.adaptadores.salida.persistencia.repositorios import RepositoriosDjango
from jml.adaptadores.salida.reloj import RelojDelSistema
from jml.dominio.auditoria import verificar_cadena
with RepositoriosDjango(RelojDelSistema()).unidad_de_trabajo() as u:
    r = u.auditoria.registros()
v = verificar_cadena(r)
print('registros:', len(r), '· valida:', v.valida, '· primer afectado:', v.primer_afectado)
" 2>&1 | tail -1

echo "== neutralizar al terminar"
bash auditoria/scripts/neutralizar.sh post
mkdir -p "$RAIZ/auditoria/.captura-local"
cp "$S"/*.json "$S"/*.log "$RAIZ/auditoria/.captura-local/" 2>/dev/null
