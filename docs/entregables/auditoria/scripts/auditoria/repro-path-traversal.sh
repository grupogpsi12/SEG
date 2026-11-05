#!/usr/bin/env bash
# Triage de F6: reproduce a mano la alerta «Path Traversal» de ZAP en /cuentas?documento=... contra la aplicacion DIRECTA
# (sin WAF) del stack LOCAL, con la sesion de un tecnico. Una alerta no cuenta hasta que se reproduce o se descarta asi.
#
#   auditoria/scripts/repro-path-traversal.sh
#
# Para cada valor se imprime el codigo, el tamano de la respuesta y si el cuerpo contiene contenido de /etc/passwd o una traza.
# La respuesta de referencia es la de un documento que no existe: si las demas son identicas, el valor no cambia nada.
set -u
export MSYS_NO_PATHCONV=1
RAIZ="$(pwd -W 2>/dev/null || pwd)"
C="-f infra/compose.yaml -f infra/compose.local.yaml"
NET=nicolaka/netshoot@sha256:b09d9b21381f47a79b3cbcb30da25266dc17186ea00ae65e99fdc51396f48e70
S="$RAIZ/.contrato-tmp/repro-pt"
rm -rf "$S" && mkdir -p "$S" && chmod 777 "$S"
bash auditoria/scripts/neutralizar.sh pre
docker compose $C run --rm --no-deps -T -v "$RAIZ:/repo:ro" -w /repo -e PYTHONPATH=/repo web \
  python auditoria/scripts/sesiones-laboratorio.py 2>/dev/null | tail -1 > "$S/sesiones.json"
TEC="$(sed -E 's/.*"tecnico": "([^"]+)".*/\1/' "$S/sesiones.json")"
IPWEB=$(docker inspect jml-web-1 --format '{{(index .NetworkSettings.Networks "jml_app").IPAddress}}')

probar() {  # etiqueta ruta(con query)
  docker run --rm --network jml_app "$NET" sh -c "
    curl -s --resolve app.localhost:8000:$IPWEB -o /tmp/r -w '%{http_code} %{size_download}' -H 'Cookie: sessionid=$TEC' 'http://app.localhost:8000$2'
    printf ' · passwd=%s · traza=%s' \$(grep -c 'root:x:' /tmp/r) \$(grep -ci 'traceback\|exception' /tmp/r)
    printf ' · md5=%s\n' \$(md5sum /tmp/r | cut -c1-8)" | sed "s|^|$1: |"
}
echo "== referencia y valores de ZAP (tecnico, directo, sin WAF)"
probar "documento inexistente (referencia)" "/cuentas?documento=99999999"
probar "documento=cuentas (el valor que uso ZAP)" "/cuentas?documento=cuentas"
probar "documento=../../../../etc/passwd" "/cuentas?documento=../../../../etc/passwd"
probar "documento=%2e%2e%2f%2e%2e%2fetc%2fpasswd" "/cuentas?documento=%2e%2e%2f%2e%2e%2fetc%2fpasswd"
probar "documento=....//....//etc/passwd" "/cuentas?documento=....//....//etc/passwd"
probar "nombre=../../../../etc/passwd" "/cuentas?nombre=../../../../etc/passwd"
probar "ficha con ../ en la ruta" "/colaboradores/..%2f..%2f..%2fetc%2fpasswd"
bash auditoria/scripts/neutralizar.sh post
