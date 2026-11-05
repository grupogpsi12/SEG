#!/usr/bin/env bash
# F6-00: antes de creer en un escaneo dinamico, sqlmap y ZAP deben ENCONTRAR lo que se sembro (plan §10).
#   auditoria/scripts/control-positivo-dinamico.sh
# Levanta una aplicacion de laboratorio con SQLi, XSS reflejado y sin cabeceras de seguridad en una red
# Docker propia (`jml-lab`, sin puertos publicados). Nada de esto toca el stack del proyecto.
set -u
export MSYS_NO_PATHCONV=1
RAIZ="$(pwd -W 2>/dev/null || pwd)"  # ruta de Windows: Python nativo y Docker Desktop la entienden
PY=python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
ZAP=ghcr.io/zaproxy/zaproxy@sha256:5ccfff9a411743ab2615136a2edd7416bec9ce41572fa94e935df38c14adb2b6
SQLMAP="sqlmap==1.10.10 --hash=sha256:32c4b516735c1c1a3183effd0d50a9217c9f22fc9e8b17ca4c4f6a5f2028bd93"
PYBIN=".venv/Scripts/python.exe"
[ -x "$PYBIN" ] || PYBIN=python
T="$RAIZ/.contrato-tmp/cp-dinamico"
rm -rf "$T" && mkdir -p "$T/app" "$T/salida" && chmod 777 "$T/salida"
$PYBIN auditoria/controles-positivos/generar.py "$T/app" > /dev/null || exit 2
limpiar() { docker rm -f jml-lab-vulnerable > /dev/null 2>&1; docker network rm jml-lab > /dev/null 2>&1; rm -rf "$T"; }
trap limpiar EXIT
docker rm -f jml-lab-vulnerable > /dev/null 2>&1; docker network rm jml-lab > /dev/null 2>&1
docker network create jml-lab > /dev/null || exit 2
docker run -d --name jml-lab-vulnerable --network jml-lab -v "$T/app:/app:ro" "$PY" python /app/app_vulnerable.py > /dev/null || exit 2
sleep 3
falta=0

echo "== sqlmap nivel 3 contra la aplicacion sembrada (debe decir que es vulnerable)"
printf '%s\n' "$SQLMAP" > "$T/salida/req-sqlmap.txt"
docker run --rm --network jml-lab -v "$T/salida:/salida" "$PY" sh -c '
  pip install -q --disable-pip-version-check --root-user-action=ignore --require-hashes -r /salida/req-sqlmap.txt
  sqlmap -u "http://jml-lab-vulnerable:8000/buscar?id=1" --batch --level=3 --risk=1 --flush-session \
    --output-dir=/salida/sqlmap --disable-coloring 2>&1 | grep -E "is vulnerable|injectable|appears to be|back-end DBMS"' > "$T/salida/sqlmap.txt" 2>&1
cat "$T/salida/sqlmap.txt"
grep -q "is vulnerable" "$T/salida/sqlmap.txt" && echo "OK    sqlmap ve la inyeccion SQL sembrada" || { echo "FALLA sqlmap NO ve la inyeccion SQL sembrada"; falta=1; }

echo "== ZAP baseline (pasivo) contra la aplicacion sembrada"
docker run --rm --network jml-lab -v "$T/salida:/zap/wrk:rw" "$ZAP" \
  zap-baseline.py -t "http://jml-lab-vulnerable:8000/eco?x=hola" -I -J baseline.json > "$T/salida/baseline.log" 2>&1
n=$(grep -cE "WARN-NEW|FAIL-NEW" "$T/salida/baseline.log")
grep -E "WARN-NEW|FAIL-NEW" "$T/salida/baseline.log" | head -6
[ "$n" -ge 1 ] && echo "OK    ZAP baseline reporta $n alertas (cabeceras ausentes)" || { echo "FALLA ZAP baseline no reporta nada"; falta=1; }

echo "== ZAP activo, 3 minutos como maximo (debe ver el XSS reflejado o la inyeccion SQL)"
docker run --rm --network jml-lab -v "$T/salida:/zap/wrk:rw" "$ZAP" \
  zap-full-scan.py -t "http://jml-lab-vulnerable:8000/" -m 3 -I -J activo.json > "$T/salida/activo.log" 2>&1
grep -E "WARN-NEW|FAIL-NEW" "$T/salida/activo.log" | grep -iE "cross site scripting|sql injection" | head -4
grep -qiE "(FAIL|WARN)-NEW: (Cross Site Scripting|SQL Injection)" "$T/salida/activo.log" \
  && echo "OK    ZAP activo ve el XSS o la inyeccion sembrados" || { echo "FALLA ZAP activo NO ve XSS ni SQLi sembrados"; falta=1; }

[ "$falta" -eq 0 ] && echo "CONTROL POSITIVO DINAMICO: sqlmap y ZAP ven lo sembrado" || echo "CONTROL POSITIVO DINAMICO FALLIDO: los escaneos de F6 no cuentan"
exit "$falta"
