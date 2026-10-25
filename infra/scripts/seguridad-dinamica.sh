#!/usr/bin/env bash
# CA-12 / RS-13 (item 5.4): pruebas dinamicas con OWASP ZAP y sqlmap, con informes.
#
#   infra/scripts/seguridad-dinamica.sh            # todo; informes en .contrato-tmp/seguridad/
#   PARTES="sqlmap" infra/scripts/seguridad-dinamica.sh    # solo una parte: baseline zap sqlmap
#
# - Contra la aplicacion DIRECTA (sin WAF), para ver si resiste por si misma, en el entorno
#   desechable de infra/scripts/carga.sh (30 colaboradores; se levanta si no esta).
# - `baseline` repite el baseline pasivo A TRAVES DEL WAF contra https://app.localhost (el stack local
#   debe estar arriba). El escaneo activo y sqlmap no van por el WAF: los bloquea (es su trabajo,
#   CA-20) y banean la IP una hora.
# - ZAP activo autenticado como RRHH y como tecnico (hook: cookie de sesion, CSRF fija, sin /salir).
# - sqlmap nivel 3 sobre los parametros GET, los identificadores de la ruta y los formularios POST.
# Herramientas fijadas: ZAP por digest y sqlmap 1.10.10 por hash.
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
SALIDA="$RAIZ/.contrato-tmp/seguridad"
PARTES="${PARTES:-baseline zap sqlmap}"
ZAP=ghcr.io/zaproxy/zaproxy@sha256:5ccfff9a411743ab2615136a2edd7416bec9ce41572fa94e935df38c14adb2b6
PY=python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
SQLMAP="sqlmap==1.10.10 --hash=sha256:32c4b516735c1c1a3183effd0d50a9217c9f22fc9e8b17ca4c4f6a5f2028bd93"
CSRF="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"  # secreto fijo de la cookie csrftoken (Django lo enmascara)
mkdir -p "$SALIDA"
chmod 777 "$SALIDA"
cd "$RAIZ"

if [ -z "$(docker ps -q --filter name=jml-carga-web)" ]; then
  echo "== entorno desechable (infra/scripts/carga.sh, 30 colaboradores)"
  MANTENER=si COLABORADORES=30 USUARIOS=3 VUELTAS=1 infra/scripts/carga.sh > /dev/null
fi
export MSYS_NO_PATHCONV=1
# Sesiones nuevas (vencen a los 30 minutos sin uso) y datos de la semilla
docker run --rm --network jml-carga -e DJANGO_ALLOWED_HOSTS=web -e JML_DB_HOST=jml-carga-pg \
  -e JML_DB_SSLMODE=disable -e PYTHONPATH=/repo -e JML_DB_USUARIO=app_backend \
  -v "$RAIZ/.contrato-tmp/carga/backend:/run/secrets:ro" -v "$RAIZ:/repo:ro" -w /repo \
  jml-app:local python -m tests.carga.sesiones | tail -1 > "$SALIDA/sesiones.json"
cp "$RAIZ/.contrato-tmp/carga/semilla.json" "$SALIDA/semilla.json"
clave() { sed -E "s/.*\"$1\": \"([^\"]+)\".*/\1/" "$SALIDA/$2"; }
TEC="$(clave tecnico sesiones.json)"; RRHH="$(clave rrhh sesiones.json)"; AUD="$(clave auditor sesiones.json)"
COL="$(clave colaborador_de_ejemplo semilla.json)"; SOL="$(clave solicitud_de_ejemplo semilla.json)"

if [[ " $PARTES " == *" baseline "* ]]; then
  echo "== ZAP baseline: directo y a traves del WAF"
  docker run --rm --network jml-carga -v "$SALIDA:/zap/wrk:rw" "$ZAP" \
    zap-baseline.py -t http://web:8000/ingreso -I -r baseline-directo.html -J baseline-directo.json \
    > "$SALIDA/baseline-directo.log" 2>&1 || true
  if [ -n "$(docker ps -q --filter name=jml-bunkerweb-1)" ]; then
    docker exec jml-bw-scheduler-1 bwcli unban 10.20.40.1 > /dev/null 2>&1 || true
    docker run --rm --add-host app.localhost:host-gateway -v "$SALIDA:/zap/wrk:rw" "$ZAP" \
      zap-baseline.py -t https://app.localhost/ingreso -I -r baseline-waf.html -J baseline-waf.json \
      > "$SALIDA/baseline-waf.log" 2>&1 || true
  fi
fi

if [[ " $PARTES " == *" zap "* ]]; then
  cat > "$SALIDA/hook.py" << 'PY'
"""Hook de ZAP para el escaneo autenticado (item 5.4)."""
import os


def zap_started(zap, target):
    zap.replacer.add_rule(
        description="sesion", enabled=True, matchtype="REQ_HEADER", matchregex=False,
        matchstring="Cookie", replacement=os.environ["COOKIE"],
    )
    for patron in (r".*/salir.*", r".*/ingreso.*", r".*\.csv.*"):
        zap.spider.exclude_from_scan(patron)
        zap.ascan.exclude_from_scan(patron)
    zap.ascan.set_option_max_scan_duration_in_mins(12)
    zap.ascan.set_option_thread_per_host(4)
PY
  for par in "rrhh $RRHH /solicitudes" "tecnico $TEC /dashboard"; do
    set -- $par
    echo "== ZAP activo autenticado como $1"
    docker run --rm --network jml-carga -e COOKIE="sessionid=$2; csrftoken=$CSRF" \
      -v "$SALIDA:/zap/wrk:rw" "$ZAP" zap-full-scan.py -t "http://web:8000$3" -m 3 -I \
      --hook=/zap/wrk/hook.py -r "activo-$1.html" -J "activo-$1.json" > "$SALIDA/activo-$1.log" 2>&1 || true
  done
fi

if [[ " $PARTES " == *" sqlmap "* ]]; then
  echo "== sqlmap nivel 3"
  printf '%s\n' "$SQLMAP" > "$SALIDA/req-sqlmap.txt"
  cat > "$SALIDA/sqlmap.sh" << SH
set -u
pip install -q --disable-pip-version-check --root-user-action=ignore --require-hashes -r /salida/req-sqlmap.txt
B="--batch --level=3 --risk=1 --flush-session --output-dir=/salida/sqlmap --disable-coloring"
probar() { echo "### \$1"; shift; sqlmap "\$@" \$B 2>&1 | grep -E "is vulnerable|injectable|appears to be|might be|all tested|not injectable|CRITICAL|ERROR" ; }
probar "GET /cuentas (tecnico)" -u "http://web:8000/cuentas?nombre=Ana&documento=81000001&usuario=ana&departamento=Finanzas&sede=Cali&sistema=AD&estado_de_cuenta=activa&pagina=1" --cookie="sessionid=$TEC"
probar "ruta /colaboradores/<id> (tecnico)" -u "http://web:8000/colaboradores/$COL*" --cookie="sessionid=$TEC"
probar "GET /solicitudes?pagina (rrhh)" -u "http://web:8000/solicitudes?pagina=1" --cookie="sessionid=$RRHH"
probar "ruta /solicitudes/<id> (rrhh)" -u "http://web:8000/solicitudes/$SOL*" --cookie="sessionid=$RRHH"
probar "GET /auditoria?pagina (auditor)" -u "http://web:8000/auditoria?pagina=1" --cookie="sessionid=$AUD"
probar "POST /ingreso (sin sesion)" -u "http://web:8000/ingreso" --data="correo=ana@andina.example&contrasena=clave&csrfmiddlewaretoken=x" --csrf-token=csrfmiddlewaretoken --cookie="csrftoken=$CSRF"
probar "POST /solicitudes/nueva/RET (rrhh)" -u "http://web:8000/solicitudes/nueva/RET" --data="fecha_efectiva=2026-12-01&documento_del_colaborador=81000001&subtipo_elegido=fin_de_contrato&motivo=prueba&justificacion=prueba&csrfmiddlewaretoken=x" --csrf-token=csrfmiddlewaretoken --cookie="sessionid=$RRHH; csrftoken=$CSRF"
SH
  docker run --rm --network jml-carga -v "$SALIDA:/salida" "$PY" sh /salida/sqlmap.sh > "$SALIDA/sqlmap.log" 2>&1 || true
  cat "$SALIDA/sqlmap.log"
fi
echo "Informes en $SALIDA"
