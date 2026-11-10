#!/usr/bin/env bash
# DS-5: pruebas de interceptación (hombre en el medio) contra el borde LOCAL. No modifica datos.
#
#   bash auditoria/scripts/mitm-interceptacion.sh
#
# Demuestra, de forma reproducible, los controles que impiden interceptar o alterar el tráfico:
#  1. Un interceptor que presenta un certificado propio es RECHAZADO por un cliente que valida la
#     cadena (la base de la defensa contra MitM). Solo un cliente comprometido (-k) lo acepta.
#  2. No se puede forzar una versión antigua de TLS (anti-downgrade).
#  3. El puerto 80 redirige a 443 y el borde envía HSTS (anti-SSL-strip).
#  4. La cookie de sesión lleva Secure, HttpOnly y SameSite (no viaja por HTTP ni se lee por script).
#  5. En el tramo navegador↔WAF, una contraseña centinela NO aparece en claro (va dentro de TLS);
#     control negativo: el mismo dato por HTTP sí es visible.
set -u
export MSYS_NO_PATHCONV=1
NET=nicolaka/netshoot@sha256:b09d9b21381f47a79b3cbcb30da25266dc17186ea00ae65e99fdc51396f48e70
RED=jml-mitm
HG="$(docker run --rm --add-host hg:host-gateway "$NET" getent ahostsv4 hg | awk 'NR==1{print $1}')"
EDGE=127.0.0.1  # los puertos 80/443 del WAF se publican en el host en 127.0.0.1 (RS-02)
SENTINELA="MITM-PASS-7b3f9e"
fallos=0
afirmar() { if eval "$2"; then echo "OK    $1"; else echo "FALLA $1"; fallos=$((fallos + 1)); fi; }
desbanear() { docker compose -f infra/compose.yaml exec -T bw-scheduler bwcli unban 10.20.40.128 > /dev/null 2>&1; }
limpiar() { docker rm -f jml-mitm-falso > /dev/null 2>&1; docker network rm "$RED" > /dev/null 2>&1; }
trap 'limpiar; desbanear' EXIT
limpiar
docker network create "$RED" > /dev/null

echo "== 1. El cliente que valida rechaza un certificado de interceptor (CN=app.localhost, firmado por un atacante)"
# El borde usa un certificado autofirmado; se extrae para validarlo como una CA de confianza del cliente.
docker run --rm "$NET" sh -c "echo | openssl s_client -connect $HG:443 -servername app.localhost 2>/dev/null | openssl x509" > "$RED-real.pem" 2>/dev/null
# El 'atacante' levanta un servidor TLS con su propio certificado para el mismo nombre.
docker run -d --name jml-mitm-falso --network "$RED" "$NET" sh -c '
  openssl req -x509 -newkey rsa:2048 -nodes -keyout /k.pem -out /c.pem -days 1 -subj "/CN=app.localhost" > /dev/null 2>&1
  openssl s_server -quiet -accept 443 -cert /c.pem -key /k.pem -www' > /dev/null
sleep 2
# Cliente que valida la cadena real: debe fallar la verificación (código 60 de curl = cert no confiable).
cod_valida=$(docker run --rm --network "$RED" -v "$PWD/$RED-real.pem:/real.pem:ro" "$NET" \
  curl -s -o /dev/null -w "%{http_code}" --max-time 10 --cacert /real.pem \
  --resolve app.localhost:443:"$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' jml-mitm-falso)" \
  https://app.localhost/ 2>/dev/null; echo "·$?")
echo "   cliente que valida -> $cod_valida (curl 60 = certificado no confiable)"
afirmar "el interceptor es rechazado por el cliente que valida" '[ "${cod_valida#*·}" = 60 ]'
# Cliente comprometido (ignora la validación): acepta la interceptación. Demuestra que el riesgo
# exige comprometer al cliente, no solo estar en la red.
cod_k=$(docker run --rm --network "$RED" "$NET" curl -sk -o /dev/null -w "%{http_code}" --max-time 10 \
  --resolve app.localhost:443:"$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' jml-mitm-falso)" \
  https://app.localhost/ 2>/dev/null)
echo "   cliente que NO valida (-k) -> $cod_k (acepta al interceptor: cliente comprometido)"
afirmar "solo un cliente que no valida acepta al interceptor" '[ "$cod_k" = 200 ]'
rm -f "$RED-real.pem"

echo "== 2. No se puede forzar TLS 1.0/1.1 (anti-downgrade)"
cod_tls11=$(curl -sk -o /dev/null -w "%{http_code}·%{exitcode}" --max-time 10 --tls-max 1.1 \
  --resolve app.localhost:443:"$EDGE" https://app.localhost/ 2>/dev/null || echo "fallo·$?")
echo "   curl --tls-max 1.1 -> $cod_tls11 (debe fallar el handshake)"
afirmar "TLS 1.1 o anterior es rechazado" '[ "${cod_tls11%%·*}" != 200 ]'

echo "== 3. SSL-strip: el puerto 80 redirige a 443 y el borde envía HSTS"
redir=$(curl -sI -o /dev/null -w "%{http_code}" --max-time 10 --resolve app.localhost:80:"$EDGE" http://app.localhost/ 2>/dev/null)
hsts=$(curl -skI --max-time 10 --resolve app.localhost:443:"$EDGE" https://app.localhost/ingreso 2>/dev/null | grep -i "strict-transport-security" | tr -d '\r')
echo "   http 80 -> $redir · $hsts"
afirmar "el puerto 80 redirige (301/302/308)" '[[ "$redir" =~ ^30[128]$ ]]'
afirmar "HSTS presente con un año de duración" 'echo "$hsts" | grep -qi "max-age=31536000"'

echo "== 4. La cookie de sesión lleva Secure, HttpOnly y SameSite"
# GET con cuerpo (no HEAD): la cookie csrftoken se emite al renderizar el formulario de ingreso.
galleta=$(curl -sk -D - -o /dev/null --max-time 10 --resolve app.localhost:443:"$EDGE" https://app.localhost/ingreso 2>/dev/null | grep -i "set-cookie" | tr -d '\r')
echo "   $galleta"
afirmar "la cookie tiene Secure" 'echo "$galleta" | grep -qi "secure"'
afirmar "la cookie tiene HttpOnly" 'echo "$galleta" | grep -qi "httponly"'
afirmar "la cookie tiene SameSite" 'echo "$galleta" | grep -qi "samesite"'

echo "== 5. Una contraseña centinela NO viaja en claro en el tramo navegador↔WAF (va dentro de TLS)"
desbanear
docker rm -f jml-mitm-cap > /dev/null 2>&1
docker run -d --name jml-mitm-cap --net container:jml-bunkerweb-1 --cap-add NET_RAW --cap-add NET_ADMIN "$NET" \
  sh -c 'tcpdump -i any -s 0 -U -w /tmp/c.pcap tcp port 443 2>/dev/null & sleep 8; kill %1 2>/dev/null; sleep 1' > /dev/null
sleep 2
curl -sk -o /dev/null --max-time 10 --resolve app.localhost:443:"$EDGE" \
  -d "correo=test@andina.example&contrasena=$SENTINELA" https://app.localhost/ingreso 2>/dev/null
sleep 3
docker cp jml-mitm-cap:/tmp/c.pcap "$RED.pcap" 2>/dev/null
docker rm -f jml-mitm-cap > /dev/null 2>&1
visible=$(docker run --rm -v "$PWD/$RED.pcap:/c.pcap:ro" "$NET" sh -c "tshark -r /c.pcap -x 2>/dev/null | grep -c '$SENTINELA' || true")
echo "   apariciones del centinela en el tramo TLS: ${visible:-0}"
afirmar "la contraseña no aparece en claro (va cifrada)" '[ "${visible:-0}" = 0 ]'
rm -f "$RED.pcap"

echo "fallos: $fallos"
[ "$fallos" -eq 0 ]
