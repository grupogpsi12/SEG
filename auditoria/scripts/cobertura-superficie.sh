#!/usr/bin/env bash
# F6-05: que parte de las rutas de urls.py VIO el escaner, por rol (meta >= 95 %). Stack LOCAL, por el WAF.
#   auditoria/scripts/cobertura-superficie.sh
# Corre ZAP (spider + escaneo activo, 3 minutos) como cada rol con el baneo y los limites relajados
# (misma exencion registrada que F6-02), guarda el log del WAF de cada corrida y lo cruza con las rutas.
set -u
export MSYS_NO_PATHCONV=1
RAIZ="$(pwd -W 2>/dev/null || pwd)"
C="-f infra/compose.yaml -f infra/compose.local.yaml"
ZAP=ghcr.io/zaproxy/zaproxy@sha256:5ccfff9a411743ab2615136a2edd7416bec9ce41572fa94e935df38c14adb2b6
CSRF="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
S="$RAIZ/.contrato-tmp/cobertura"
rm -rf "$S" && mkdir -p "$S" && chmod 777 "$S"
bash auditoria/scripts/neutralizar.sh pre
echo "== EXENCION REGISTRADA (igual que F6-02): baneo y limites relajados en este stack de laboratorio"
docker compose $C -f auditoria/laboratorio/compose.escaner.yaml up -d bw-scheduler > /dev/null 2>&1
sleep 45
bash auditoria/scripts/neutralizar.sh unban
docker compose $C run --rm --no-deps -T -v "$RAIZ:/repo:ro" -w /repo -e PYTHONPATH=/repo web \
  python auditoria/scripts/sesiones-laboratorio.py 2>/dev/null | tail -1 > "$S/sesiones.json"
clave() { sed -E "s/.*\"$1\": \"([^\"]+)\".*/\1/" "$S/sesiones.json"; }
cat > "$S/hook.py" << 'PY'
import os


def zap_started(zap, target):
    zap.replacer.add_rule(description="sesion", enabled=True, matchtype="REQ_HEADER", matchregex=False,
                          matchstring="Cookie", replacement=os.environ["COOKIE"])
    for patron in (r".*/salir.*", r".*/ingreso.*"):
        zap.spider.exclude_from_scan(patron)
        zap.ascan.exclude_from_scan(patron)
    zap.ascan.set_option_max_scan_duration_in_mins(int(os.environ["MINUTOS"]))
    zap.ascan.set_option_thread_per_host(4)
PY
for rol in rrhh tecnico auditor administrador solicitante; do
  echo "== ZAP como $rol"
  inicio="$(date -u +%Y-%m-%dT%H:%M:%S)"
  docker run --rm --add-host app.localhost:host-gateway -e COOKIE="sessionid=$(clave $rol); csrftoken=$CSRF" -e MINUTOS=3 \
    -v "$S:/zap/wrk:rw" "$ZAP" zap-full-scan.py -t "https://app.localhost/solicitudes" -m 3 -I \
    --hook=/zap/wrk/hook.py > "$S/zap-$rol.log" 2>&1
  docker logs --since "${inicio}Z" jml-bunkerweb-1 2>&1 | grep '^app.localhost' > "$S/waf-$rol.log"
  echo "   lineas del WAF: $(wc -l < "$S/waf-$rol.log")"
  bash auditoria/scripts/neutralizar.sh unban
done
cp "$S"/waf-*.log "$RAIZ/.contrato-tmp/" 2>/dev/null
echo "== neutralizar al terminar"
docker compose $C up -d bw-scheduler > /dev/null 2>&1
bash auditoria/scripts/neutralizar.sh post
