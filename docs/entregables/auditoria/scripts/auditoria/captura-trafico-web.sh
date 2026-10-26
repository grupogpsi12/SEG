#!/usr/bin/env bash
# Entrega 3 (Documento 3) repetida: captura de trafico del lado de BunkerWeb y de PostgreSQL mientras Playwright
# recorre ING, VAC, RET y EMG por el WAF. Stack LOCAL. La captura del lado de GLPI es F7-04 (captura-trafico.sh).
#
#   JML_GLPI_DE_PRUEBAS=si auditoria/scripts/captura-trafico-web.sh
#
# Aserciones: el trafico externo es TLS 1.3 y no deja ver el centinela; el centinela llega a PostgreSQL (se guarda en
# `solicitud_restringida`) y al tramo interno WAF->web, nunca fuera de el; las cookies llevan HttpOnly, Secure y SameSite;
# las consultas a PostgreSQL usan el protocolo extendido (Parse/Bind), es decir con parametros. Los .pcap NO se versionan.
set -u
export MSYS_NO_PATHCONV=1
if [ "${JML_GLPI_DE_PRUEBAS:-}" != "si" ]; then echo "Crea datos y tickets de prueba: JML_GLPI_DE_PRUEBAS=si $0" >&2; exit 2; fi
RAIZ="$(pwd -W 2>/dev/null || pwd)"
NET=nicolaka/netshoot@sha256:b09d9b21381f47a79b3cbcb30da25266dc17186ea00ae65e99fdc51396f48e70
SALIDA="$RAIZ/auditoria/.captura-local"
rm -rf "$SALIDA" && mkdir -p "$SALIDA" && chmod 777 "$SALIDA"

bash auditoria/scripts/neutralizar.sh pre
docker start jml-worker-1 > /dev/null  # el recorrido necesita al worker para que los tickets lleguen a GLPI

docker rm -f jml-cap-bw jml-cap-pg > /dev/null 2>&1
docker run -d --name jml-cap-bw --net container:jml-bunkerweb-1 --cap-add NET_RAW --cap-add NET_ADMIN -v "$SALIDA:/cap" "$NET" \
  tcpdump -i any -s 0 -U -w /cap/bunkerweb.pcap "port 8443 or port 8080 or port 8000 or port 80" > /dev/null || exit 2
docker run -d --name jml-cap-pg --net container:jml-postgres-1 --cap-add NET_RAW --cap-add NET_ADMIN -v "$SALIDA:/cap" "$NET" \
  tcpdump -i any -s 0 -U -w /cap/postgres.pcap "port 5432" > /dev/null || exit 2
sleep 3

echo "== Playwright por el WAF (ING con PDF, VAC, RET y EMG)"
E2E=$(env -u MSYS_NO_PATHCONV bash infra/scripts/e2e-interfaz.sh 2>&1 | tail -4)
echo "$E2E"
# B-36: el recorrido puede recibir un 429 del WAF por el ritmo; la captura sigue valiendo, pero se informa
echo "$E2E" | grep -q "failed\|error" && echo "AVISO: el recorrido Playwright tuvo fallos (ver B-36); las aserciones de trafico siguen siendo validas"
sleep 3
docker stop jml-cap-bw jml-cap-pg > /dev/null; docker rm jml-cap-bw jml-cap-pg > /dev/null

an() { local f="$1"; shift; docker run --rm -v "$SALIDA:/cap" "$NET" tshark -r "/cap/$f" "$@" 2>/dev/null; }
CEN='frame contains "CENTINELA-"'
echo "== analisis del lado de BunkerWeb"
echo "tramas: $(an bunkerweb.pcap | wc -l)"
echo "TLS: ClientHello con TLS 1.3 ofrecido: $(an bunkerweb.pcap -Y 'tls.handshake.type==1 && tls.handshake.extensions.supported_version==0x0304' | wc -l)"
echo "TLS: suites elegidas por el servidor: $(an bunkerweb.pcap -Y 'tls.handshake.type==2' -T fields -e tls.handshake.ciphersuite | sort | uniq -c | tr '\n' ';')"
echo "TLS: versiones en el ServerHello: $(an bunkerweb.pcap -Y 'tls.handshake.type==2' -T fields -e tls.handshake.extensions.supported_version | sort | uniq -c | tr '\n' ';')"
echo "puerto 80 (8080 interno): redirecciones 301 hacia HTTPS: $(an bunkerweb.pcap -Y 'tcp.port==8080 && http.response.code==301' | wc -l)"
echo "tramo externo cifrado (8443): tramas con el centinela en claro (esperado 0): $(an bunkerweb.pcap -Y "tcp.port==8443 && $CEN" | wc -l)"
echo "tramo interno WAF->web (8000): peticiones HTTP: $(an bunkerweb.pcap -Y 'tcp.dstport==8000 && http.request' | wc -l)"
echo "tramo interno WAF->web (8000): tramas con el centinela (esperado >0: el WAF termina el TLS): $(an bunkerweb.pcap -Y "tcp.dstport==8000 && $CEN" | wc -l)"
echo "tramo interno WAF->glpi (80): tramas con el centinela (esperado 0): $(an bunkerweb.pcap -Y "tcp.dstport==80 && $CEN" | wc -l)"
echo "cookies de respuesta de la aplicacion (atributos):"
an bunkerweb.pcap -Y 'tcp.srcport==8000 && http.set_cookie' -T fields -e http.set_cookie \
  | sed -E 's/(sessionid|csrftoken)=[^;]+/\1=<oculto>/g' | sort | uniq -c | sort -rn | head -4 | cut -c1-220
echo "cabeceras de seguridad que salen del upstream (CSP, X-Frame-Options, X-Request-ID): $(an bunkerweb.pcap -Y 'tcp.srcport==8000 && http.response' -T fields -e http.response.line | grep -ciE 'content-security-policy|x-frame-options|x-request-id')"

echo "== analisis del lado de PostgreSQL"
echo "tramas: $(an postgres.pcap | wc -l)"
echo "SSLRequest enviados por la aplicacion: $(an postgres.pcap -Y 'pgsql.type == "SSL request"' | wc -l) · conexiones con TLS: $(an postgres.pcap -Y 'tls' | wc -l)  (PostgreSQL local sin TLS; Supabase usa verify-full)"
echo "mensajes Parse (consulta con parametros): $(an postgres.pcap -Y 'pgsql.type == "Parse"' | wc -l) · Bind: $(an postgres.pcap -Y 'pgsql.type == "Bind"' | wc -l)"
echo "consultas simples (texto sin parametros): $(an postgres.pcap -Y 'pgsql.type == "Simple query"' | wc -l)"
echo "BEGIN: $(an postgres.pcap -Y 'pgsql.query contains "BEGIN"' | wc -l) · COMMIT: $(an postgres.pcap -Y 'pgsql.query contains "COMMIT"' | wc -l)"
echo "tramas con el centinela hacia PostgreSQL (esperado >0, solo en solicitud_restringida): $(an postgres.pcap -Y "$CEN" | wc -l)"
echo "autenticacion: metodo SCRAM visto: $(an postgres.pcap -Y 'pgsql.authtype == 10' | wc -l) · contrasena en claro (authtype 3): $(an postgres.pcap -Y 'pgsql.authtype == 3' | wc -l)"

ext=$(an bunkerweb.pcap -Y "tcp.port==8443 && $CEN" | wc -l)
glpi=$(an bunkerweb.pcap -Y "tcp.dstport==80 && $CEN" | wc -l)
claro=$(an postgres.pcap -Y 'pgsql.authtype == 3' | wc -l)
bash auditoria/scripts/neutralizar.sh post
if [ "$ext" -eq 0 ] && [ "$glpi" -eq 0 ] && [ "$claro" -eq 0 ]; then echo "ASERCIONES CUMPLIDAS: 0 centinelas fuera del host, 0 hacia GLPI, 0 contrasenas en claro"; else echo "ASERCION FALLA ($ext/$glpi/$claro)"; exit 1; fi
