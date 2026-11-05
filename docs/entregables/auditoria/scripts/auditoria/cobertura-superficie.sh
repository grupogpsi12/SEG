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
ROLES="${ROLES:-rrhh tecnico auditor administrador solicitante}"
# CONSERVAR=si agrega a una corrida anterior (para repetir solo un rol sin perder los demas)
[ -n "${CONSERVAR:-}" ] || rm -rf "$S"
mkdir -p "$S" && chmod 777 "$S"
bash auditoria/scripts/neutralizar.sh pre
echo "== EXENCION REGISTRADA (igual que F6-02): baneo y limites relajados en este stack de laboratorio"
docker compose $C -f auditoria/laboratorio/compose.escaner.yaml up -d bw-scheduler > /dev/null 2>&1
sleep 30
# Reiniciar BunkerWeb libera las conexiones colgadas de escaneos anteriores (limit_conn por IP, zona v1ips)
docker restart jml-bunkerweb-1 > /dev/null
# y se le hace reenviar la configuracion: al arrancar, BunkerWeb carga la ULTIMA guardada, no la del overlay
for _ in $(seq 1 30); do [ "$(docker inspect -f '{{.State.Health.Status}}' jml-bunkerweb-1)" = healthy ] && break; sleep 4; done
sleep 20
# Un 200 no basta: tras reiniciar, BunkerWeb puede servir su pagina por defecto («Nothing to see here») hasta que el
# planificador le reenvia la configuracion. Se espera a ver el formulario de ingreso de LA APLICACION.
for _ in $(seq 1 40); do
  curl -sk --resolve app.localhost:443:127.0.0.1 https://app.localhost/ingreso | grep -q csrfmiddlewaretoken && break
  bash auditoria/scripts/neutralizar.sh unban > /dev/null 2>&1; sleep 8
done
curl -sk --resolve app.localhost:443:127.0.0.1 https://app.localhost/ingreso | grep -q csrfmiddlewaretoken || { echo "ABORTA: BunkerWeb no sirve la aplicacion"; docker compose $C up -d bw-scheduler > /dev/null 2>&1; bash auditoria/scripts/neutralizar.sh post; exit 3; }
echo "   BunkerWeb sirve la aplicacion (formulario de ingreso visto)"
# La exencion se COMPRUEBA: 20 peticiones seguidas sin ningun 429. Si no, se espera a la recarga (hasta 4 minutos).
for intento in 1 2 3 4 5 6 7 8; do
  bash auditoria/scripts/neutralizar.sh unban
  rafaga=$(for _ in $(seq 1 20); do curl -sk -o /dev/null -w "%{http_code}
" --resolve app.localhost:443:127.0.0.1 https://app.localhost/salud; done | sort | uniq -c | tr '
' ' ')
  echo "   comprobacion $intento: $rafaga"
  case "$rafaga" in *429*) sleep 30 ;; *) break ;; esac
done
case "$rafaga" in *429*) echo "ABORTA: la exencion no se aplico"; docker compose $C up -d bw-scheduler > /dev/null 2>&1; bash auditoria/scripts/neutralizar.sh post; exit 3 ;; esac
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
for rol in $ROLES; do
  echo "== ZAP como $rol"
  # marcas en el log del WAF: lo que hay entre ellas es lo de ESTA corrida (docker logs --since fallaba con la zona horaria)
  curl -sk -o /dev/null --resolve app.localhost:443:127.0.0.1 "https://app.localhost/salud?marca=INICIO-$rol"; sleep 2
  docker run --rm --add-host app.localhost:host-gateway -e COOKIE="sessionid=$(clave $rol); csrftoken=$CSRF" -e MINUTOS=3     -v "$S:/zap/wrk:rw" "$ZAP" zap-full-scan.py -t "https://app.localhost/solicitudes" -m 3 -I     --hook=/zap/wrk/hook.py > "$S/zap-$rol.log" 2>&1
  curl -sk -o /dev/null --resolve app.localhost:443:127.0.0.1 "https://app.localhost/salud?marca=FIN-$rol"; sleep 2
  docker logs jml-bunkerweb-1 2>&1 | grep '^app.localhost' | sed -n "/marca=INICIO-$rol/,/marca=FIN-$rol/p" > "$S/waf-$rol.log"
  echo "   lineas del WAF: $(wc -l < "$S/waf-$rol.log")"
  bash auditoria/scripts/neutralizar.sh unban
done
cp "$S"/waf-*.log "$RAIZ/.contrato-tmp/" 2>/dev/null
echo "== neutralizar al terminar"
docker compose $C up -d bw-scheduler > /dev/null 2>&1
bash auditoria/scripts/neutralizar.sh post
